from __future__ import annotations

import asyncio
import fcntl
import logging
import os
from pathlib import Path
import sys

from telegram import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    MenuButtonCommands,
    MenuButtonWebApp,
    Update,
    WebAppInfo,
)
from telegram.ext import Application, ApplicationBuilder
from telegram.request import HTTPXRequest

from notes_bot.config import Config, load_config
from notes_bot.database import Database
from notes_bot.handlers import register_handlers


async def _tunnel_sync_worker(application: Application) -> None:
    """Continuously monitors .tunnel_ready and auto-updates Telegram Menu Button on new URL."""
    tunnel_file = Path(__file__).resolve().parent.parent / ".tunnel_ready"
    admin_ids: frozenset[int] = application.bot_data.get("admin_ids", frozenset())
    last_synced_url = application.bot_data.get("mini_app_url") or ""

    while True:
        try:
            await asyncio.sleep(4)
            if tunnel_file.is_file():
                current_url = tunnel_file.read_text(encoding="utf-8").strip()
                if current_url.startswith("https://") and current_url != last_synced_url:
                    logging.getLogger(__name__).info(
                        "Fresh tunnel URL detected (%s -> %s). Syncing Telegram menu buttons...",
                        last_synced_url,
                        current_url,
                    )
                    application.bot_data["mini_app_url"] = current_url
                    last_synced_url = current_url

                    for admin_id in admin_ids:
                        try:
                            await application.bot.set_chat_menu_button(
                                chat_id=admin_id,
                                menu_button=MenuButtonWebApp(
                                    text="CyberLearn Studio",
                                    web_app=WebAppInfo(url=current_url),
                                ),
                            )
                            logging.getLogger(__name__).info(
                                "Auto-updated menu button for admin %s to %s",
                                admin_id,
                                current_url,
                            )
                        except Exception as e:
                            logging.getLogger(__name__).warning(
                                "Could not update menu button for admin %s: %s", admin_id, e
                            )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logging.getLogger(__name__).warning("Error in tunnel sync worker: %s", exc)


async def post_init(application: Application) -> None:
    database: Database = application.bot_data["database"]
    await asyncio.to_thread(database.open)
    logging.getLogger(__name__).info("Database schema is ready.")

    # Check .tunnel_ready file first for freshest live URL on boot
    tunnel_file = Path(__file__).resolve().parent.parent / ".tunnel_ready"
    if tunnel_file.is_file():
        try:
            live_url = tunnel_file.read_text(encoding="utf-8").strip()
            if live_url.startswith("https://"):
                application.bot_data["mini_app_url"] = live_url
        except Exception:
            pass

    # Default commands for students
    default_commands = [
        BotCommand("subjects", "Browse subjects & notes"),
        BotCommand("search", "Search notes by keyword"),
        BotCommand("help", "Help & commands"),
        BotCommand("delete_me", "Delete your registration"),
    ]
    await application.bot.set_my_commands(
        default_commands, scope=BotCommandScopeDefault()
    )
    await application.bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    # Custom menu commands for admins
    admin_commands = [
        BotCommand("studio", "🚀 CyberLearn Studio"),
        BotCommand("newnote", "➕ Add a new note (guided)"),
        BotCommand("subjects", "Browse subjects & notes"),
        BotCommand("search", "Search notes by keyword"),
        BotCommand("addsubject", "Create a new subject"),
        BotCommand("channel", "View the linked channel"),
        BotCommand("setchannel", "Link a Telegram channel"),
        BotCommand("announce", "📢 Message all students"),
        BotCommand("deletenote", "Delete a note by ID"),
        BotCommand("deletesubject", "Delete a subject"),
        BotCommand("help", "Help & all commands"),
    ]
    admin_ids: frozenset[int] = application.bot_data["admin_ids"]
    for admin_id in admin_ids:
        try:
            await application.bot.set_my_commands(
                admin_commands, scope=BotCommandScopeChat(chat_id=admin_id)
            )
            if application.bot_data["mini_app_url"]:
                await application.bot.set_chat_menu_button(
                    chat_id=admin_id,
                    menu_button=MenuButtonWebApp(
                        text="CyberLearn Studio",
                        web_app=WebAppInfo(url=application.bot_data["mini_app_url"]),
                    ),
                )
            else:
                await application.bot.set_chat_menu_button(
                    chat_id=admin_id, menu_button=MenuButtonCommands()
                )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "Could not set commands for admin %s: %s", admin_id, exc
            )




    saved_channel = await asyncio.to_thread(database.get_setting, "channel_id")
    if saved_channel:
        application.bot_data["channel_id"] = int(saved_channel) if saved_channel.lstrip("-").isdigit() else saved_channel
        logging.getLogger(__name__).info("Loaded linked channel: %s", saved_channel)

    # Spawn auto-sync worker to keep menu button and links synchronized with Cloudflare tunnel
    asyncio.create_task(_tunnel_sync_worker(application))


async def post_shutdown(application: Application) -> None:
    database: Database = application.bot_data["database"]
    await asyncio.to_thread(database.close)


def build_application(config: Config) -> Application:
    database = Database(config.database_url)
    request = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=30.0,
        write_timeout=20.0,
        pool_timeout=20.0,
    )
    application = (
        ApplicationBuilder()
        .token(config.bot_token)
        .request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data["database"] = database
    application.bot_data["admin_ids"] = config.admin_ids
    application.bot_data["mini_app_url"] = config.mini_app_url
    register_handlers(application, config.admin_ids)
    return application


_lock_file = None


def acquire_process_lock() -> None:
    global _lock_file
    lock_path = "/tmp/cyberlearn_bot.lock"
    try:
        _lock_file = open(lock_path, "w")
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.write(f"{os.getpid()}\n")
        _lock_file.flush()
    except (BlockingIOError, IOError):
        logging.getLogger(__name__).error(
            "Another instance of CyberLearn bot is already running! "
            "Exiting this process to prevent Telegram polling conflicts."
        )
        sys.exit(0)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    acquire_process_lock()
    config = load_config()
    application = build_application(config)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
