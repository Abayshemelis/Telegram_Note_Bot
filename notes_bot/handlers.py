from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape, unescape
import logging
import math
from pathlib import Path
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, WebAppInfo
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PollAnswerHandler,
    filters,
)

from notes_bot.database import Database
from notes_bot.formatter import standardize_academic_markdown, standardize_title

logger = logging.getLogger(__name__)

PAGE_SIZE = 5
MAX_BROADCAST_LENGTH = 4_000
MAX_CHANNEL_MESSAGE_LENGTH = 3_800
SEND_DELAY_SECONDS = 0.05

WIZ_CHOOSE_SUBJECT, WIZ_NEW_SUBJECT_NAME, WIZ_ENTER_TITLE, WIZ_ENTER_CONTENT = range(4)

SUPPORTED_DOCUMENT_MIME_TYPES = {
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    ".ppt": {"application/vnd.ms-powerpoint"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    },
}

KIND_ICONS = {
    "text": "📝",
    "document": "📄",
    "photo": "🖼",
}


def is_supported_document(mime_type: str | None, file_name: str | None) -> bool:
    suffix = ""
    if file_name:
        parts = file_name.rsplit(".", 1)
        if len(parts) == 2 and parts[1]:
            suffix = f".{parts[1].lower()}"

    if suffix:
        allowed = SUPPORTED_DOCUMENT_MIME_TYPES.get(suffix, set())
        if not allowed:
            return False
        return mime_type in (
            None,
            "",
            "application/octet-stream",
            *allowed,
        )

    supported_mime_types = {
        mime
        for mime_types in SUPPORTED_DOCUMENT_MIME_TYPES.values()
        for mime in mime_types
    }
    return mime_type in (None, "", "application/octet-stream", *supported_mime_types)


def format_note_content(content: str) -> list[tuple[str, str]]:
    """Classify note text for presentation without rewriting its meaning."""
    blocks: list[tuple[str, str]] = []
    code_lines: list[str] = []
    in_code = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append(("code", "\n".join(code_lines)))
                code_lines.clear()
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not stripped:
            if blocks and blocks[-1][0] != "spacer":
                blocks.append(("spacer", ""))
            continue

        heading = re.match(r"^#{1,3}\s+(.+)$", stripped)
        if heading:
            blocks.append(("heading", heading.group(1)))
            continue

        if stripped.startswith(">"):
            blocks.append(("quote", stripped[1:].strip()))
            continue

        label = re.match(
            r"^(definition|example|explanation|exercise|practice|"
            r"key takeaway|takeaway|important|note|command)\s*:\s*(.*)$",
            stripped,
            flags=re.IGNORECASE,
        )
        if label:
            blocks.append(
                ("callout", f"{label.group(1).title()}: {label.group(2)}")
            )
            continue

        if stripped.endswith(":") and len(stripped) <= 80:
            blocks.append(("heading", stripped[:-1]))
            continue

        bullet = re.match(r"^(?:[-*+]|\d+[.)])\s+(.+)$", stripped)
        if bullet:
            blocks.append(("bullet", bullet.group(1)))
            continue

        blocks.append(("paragraph", line))

    if code_lines:
        blocks.append(("code", "\n".join(code_lines)))
    return blocks


INLINE_MARKUP_PATTERN = re.compile(r"\*\*(.+?)\*\*|`([^`]+)`")
MAX_FORMATTED_BLOCK_LENGTH = 1_800
SECTION_ICONS = {
    "definition": "📌",
    "example": "💡",
    "explanation": "📖",
    "exercise": "🧪",
    "practice": "🧪",
    "key takeaway": "🔥",
    "takeaway": "🔥",
    "important": "⚠️",
    "note": "📝",
    "command": "⌨️",
}


def _split_text_by_escaped_length(text: str, max_length: int) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start
        escaped_length = 0
        last_space = -1
        while end < len(text):
            char = text[end]
            char_length = max(
                len(escape(char, quote=False)),
                len(char.encode("utf-16-le")) // 2,
            )
            if escaped_length + char_length > max_length:
                break
            escaped_length += char_length
            if text[end].isspace():
                last_space = end + 1
            end += 1
        if end == start:
            end += 1
        elif end < len(text) and last_space > start:
            end = last_space
        chunks.append(text[start:end])
        start = end
    return chunks


def _telegram_text_length(text: str) -> int:
    visible_text = unescape(re.sub(r"<[^>]*>", "", text))
    return len(visible_text.encode("utf-16-le")) // 2


def _inline_html_fragments(text: str) -> list[str]:
    fragments: list[str] = []

    def append_text(value: str, tag: str = "") -> None:
        for piece in _split_text_by_escaped_length(
            value, MAX_FORMATTED_BLOCK_LENGTH - 20
        ):
            escaped = escape(piece, quote=False)
            if tag == "bold":
                fragments.append(f"<b>{escaped}</b>")
            elif tag == "code":
                fragments.append(f"<code>{escaped}</code>")
            else:
                fragments.append(escaped)

    cursor = 0
    for match in INLINE_MARKUP_PATTERN.finditer(text):
        append_text(text[cursor:match.start()])
        append_text(match.group(1), "bold") if match.group(1) is not None else append_text(match.group(2), "code")
        cursor = match.end()
    append_text(text[cursor:])
    return fragments


def _format_content_blocks(content: str) -> list[str]:
    rendered: list[str] = []
    section_number = 0
    for kind, text in format_note_content(content):
        if kind == "spacer":
            continue
        if kind == "code":
            code_chunks = _split_text_by_escaped_length(
                text, MAX_FORMATTED_BLOCK_LENGTH - 20
            )
            rendered.extend(
                f"<pre>{escape(chunk, quote=False)}</pre>" for chunk in code_chunks
            )
            continue

        if kind == "heading":
            section_number += 1
            heading = f"📖 {section_number:02d} | {text}"
            rendered.extend(
                f"<b>{fragment}</b>" for fragment in _inline_html_fragments(heading)
            )
            continue

        if kind == "callout":
            label, separator, body = text.partition(":")
            icon = SECTION_ICONS.get(label.casefold(), "📌")
            rendered.append(
                f"<b>{icon} {escape(label, quote=False)}:</b>"
            )
            if separator:
                rendered.extend(_inline_html_fragments(f" {body.strip()}"))
            continue

        if kind == "quote":
            rendered.extend(
                f"<blockquote>{fragment}</blockquote>"
                for fragment in _inline_html_fragments(text)
            )
            continue

        if kind == "bullet":
            rendered.append("•")
            rendered.extend(_inline_html_fragments(f" {text}"))
            continue

        rendered.extend(_inline_html_fragments(text))
    return rendered


def extract_summary(content: str, max_length: int = 240) -> str:
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    paragraphs = []
    for line in lines:
        if (
            line.startswith("#")
            or line.startswith("```")
            or line.startswith("|")
            or line.startswith("==")
            or line.startswith("--")
            or line.startswith("§§")
            or line.startswith("![")
        ):
            continue
        cleaned = re.sub(r"[*_`#>\[\]]", "", line).strip()
        if re.match(r"^(hey|hello|hi|good morning|welcome|day \d+|cybersecurity journey)\b", cleaned, re.I):
            continue
        if len(cleaned) >= 40 and not cleaned.endswith(":"):
            paragraphs.append(cleaned)
            if len(" ".join(paragraphs)) >= max_length:
                break
    text = " ".join(paragraphs) if paragraphs else (lines[0] if lines else "Tap below to read the complete lesson.")
    if len(text) > max_length:
        text = text[:max_length].rstrip() + "..."
    return text


def _course_icon(subject: str, title: str, content: str) -> str:
    source = f"{subject} {title} {content}".casefold()
    if any(term in source for term in ("cybersecurity", "security", "phishing", "malware")):
        return "🛡️"
    if any(term in source for term in ("network", "tcp", "ip address", "router")):
        return "🌐"
    if any(term in source for term in ("programming", "python", "javascript", "code", "function")):
        return "💻"
    if any(term in source for term in ("linux", "terminal", "shell", "command line")):
        return "🐧"
    return "📚"


def format_channel_lesson(
    subject: str, title: str, content: str
) -> list[str]:
    icon = _course_icon(subject, title, content)
    header = (
        f"{icon} <b>{escape(subject, quote=False)}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>{escape(title, quote=False)}</b>"
    )
    footer = (
        "\n\n🧠 <b>QUICK CHECK</b>\n"
        f"1. Explain <b>{escape(title, quote=False)}</b> in your own words.\n"
        "2. What real-world example can you connect to this lesson?\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "💬 <b>Your turn:</b> What question would you like to discuss?"
    )
    pieces = _format_content_blocks(content)
    if not pieces:
        pieces = ["📝 No lesson text was provided."]

    messages: list[str] = []
    current: list[str] = []
    continuation_header = (
        f"{icon} <b>{escape(subject, quote=False)} · {escape(title, quote=False)}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "↪️ <b>CONTINUED</b>"
    )
    reserved_header = max(
        len(header),
        len(continuation_header),
        _telegram_text_length(header),
        _telegram_text_length(continuation_header),
    )
    reserved_footer = max(len(footer), _telegram_text_length(footer))
    body_limit = (
        MAX_CHANNEL_MESSAGE_LENGTH
        - reserved_header
        - reserved_footer
        - 20
    )
    for piece in pieces:
        # Formatting tokens are emitted as complete Telegram HTML elements.
        if len(piece) > body_limit:
            raise ValueError("A formatted lesson block exceeded the safe message size.")
        proposed = "\n".join((*current, piece))
        proposed_size = max(len(proposed), _telegram_text_length(proposed))
        if current and proposed_size > body_limit:
            messages.append("\n".join(current))
            current = [piece]
        else:
            current.append(piece)
    if current:
        messages.append("\n".join(current))

    output = []
    for index, body in enumerate(messages):
        part_header = header if index == 0 else continuation_header
        part_footer = footer if index == len(messages) - 1 else ""
        output.append(f"{part_header}\n\n{body}{part_footer}")
    if any(
        max(len(message), _telegram_text_length(message))
        > MAX_CHANNEL_MESSAGE_LENGTH
        for message in output
    ):
        raise ValueError("Formatted lesson exceeds Telegram's safe message size.")
    return output


def parse_file_caption(caption: str | None) -> tuple[str, str] | None:
    if not caption:
        return None
    parts = caption.split("|", 1)
    if len(parts) != 2:
        return None
    subject, title = (part.strip() for part in parts)
    if not subject or not title or len(subject) > 60 or len(title) > 100:
        return None
    return subject, title


def parse_text_note(text: str) -> tuple[str, str, str] | None:
    parts = text.split("|", 2)
    if len(parts) != 3:
        return None
    subject, title, content = (part.strip() for part in parts)
    if not subject or not title or not content:
        return None
    if len(subject) > 60 or len(title) > 100:
        return None
    return subject, title, content


async def _db_call(context: ContextTypes.DEFAULT_TYPE, method: str, *args):
    database: Database = context.application.bot_data["database"]
    return await asyncio.to_thread(getattr(database, method), *args)


async def _reply_with_text_note(
    message: Message, subject: str, title: str, content: str
) -> None:
    for part in format_channel_lesson(subject, title, content):
        await message.reply_text(part, parse_mode="HTML")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    await _db_call(
        context,
        "add_user",
        user.id,
        user.full_name[:255],
        user.id in context.application.bot_data["admin_ids"],
    )

    if context.args and context.args[0].startswith("quiz_"):
        raw_id = context.args[0].removeprefix("quiz_")
        if raw_id.isdigit():
            quiz_id = int(raw_id)
            quiz = await _db_call(context, "miniapp_get_quiz", quiz_id)
            if quiz and quiz.get("questions"):
                # Enforce 1-attempt rule: check existing completed submission
                existing_sub = await _db_call(context, "get_quiz_submission", quiz_id, user.id)
                if existing_sub:
                    score = existing_sub["score"]
                    total = existing_sub["total_questions"]
                    pct = int((score / total) * 100) if total else 0
                    c_date = (
                        existing_sub["completed_at"].strftime("%b %d, %Y at %H:%M")
                        if hasattr(existing_sub["completed_at"], "strftime")
                        else str(existing_sub["completed_at"])[:16]
                    )
                    await message.reply_text(
                        f"⚠️ <b>You have already completed this quiz!</b>\n\n"
                        f"📝 <b>Quiz:</b> {escape(quiz['title'])}\n"
                        f"🏆 <b>Your Score:</b> {score} / {total} ({pct}%)\n"
                        f"📅 <b>Submitted on:</b> {c_date}\n\n"
                        f"<i>Note: Only one attempt is permitted per student.</i>",
                        parse_mode="HTML",
                    )
                    return

                # Check if user already has an active poll waiting for response
                active_poll = await _db_call(context, "get_user_active_poll", quiz_id, user.id)
                if active_poll:
                    duration_min = quiz.get("duration_minutes") or 1
                    created_at = active_poll.get("created_at")
                    is_expired = False
                    if created_at:
                        now_utc = datetime.now(timezone.utc)
                        delta = (now_utc - created_at).total_seconds()
                        if delta > (duration_min * 60 + 30):
                            is_expired = True

                    if is_expired:
                        # Auto-finalize expired attempt with 0 score
                        await _db_call(
                            context,
                            "record_quiz_submission",
                            quiz_id,
                            user.id,
                            user.full_name or "Student",
                            0,
                            len(quiz["questions"]),
                            [],
                        )
                        await _db_call(context, "clear_user_active_polls", quiz_id, user.id)
                        await _update_channel_quiz_card(context, quiz_id)
                        await message.reply_text(
                            f"⚠️ <b>Time expired!</b>\n\n"
                            f"Your personal timer for <b>{escape(quiz['title'])}</b> has elapsed.\n"
                            f"Your attempt has concluded. Only one attempt is permitted per student.",
                            parse_mode="HTML",
                        )
                        return
                    else:
                        await message.reply_text(
                            f"⚠️ <b>Quiz in Progress!</b>\n\n"
                            f"You already started <b>{escape(quiz['title'])}</b>.\n"
                            f"Please answer the poll question sent above before your timer runs out!",
                            parse_mode="HTML",
                        )
                        return

                title = quiz.get("title") or "Quiz"
                duration = quiz.get("duration_minutes")
                q_count = len(quiz["questions"])
                instructions = (quiz.get("instructions") or "").strip()
                first_q = (quiz["questions"][0].get("question_text") or "").strip()
                clean_instructions = instructions if instructions.casefold() != first_q.casefold() else ""

                lines = [
                    f"🎯 <b>Ready for the quiz: {escape(title)}?</b>",
                ]
                if clean_instructions:
                    lines.append(escape(clean_instructions))
                meta = [f"• <b>Questions:</b> {q_count}"]
                if duration:
                    meta.append(f"• <b>Time limit:</b> {duration} minute{'s' if duration != 1 else ''} per question")
                    meta.append("\n⏱ <i>Your individual countdown timer will start the second you tap the button below!</i>")
                else:
                    meta.append("\n<i>Tap below when you are ready to begin!</i>")
                lines.append("\n".join(meta))

                start_btn = InlineKeyboardButton(
                    "🚀 I'm Ready — Send Question 1",
                    callback_data=f"quiz_start:{quiz['id']}:0",
                )
                await message.reply_text(
                    "\n\n".join(lines),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([[start_btn]]),
                )
                return

    if context.args and context.args[0].startswith("note_"):
        raw_id = context.args[0].removeprefix("note_")
        if raw_id.isdigit():
            note = await _db_call(context, "get_note", int(raw_id))
            if note:
                icon = KIND_ICONS.get(note["kind"], "📝")
                if note["kind"] == "text":
                    await _reply_with_text_note(
                        message, "Study note", note["title"], note["content"]
                    )
                elif note["kind"] == "document":
                    await message.reply_document(note["content"], caption=f"{icon} {note['title']}")
                elif note["kind"] == "photo":
                    await message.reply_photo(note["content"], caption=f"{icon} {note['title']}")
                return

    if context.args and (context.args[0].startswith("lesson_") or context.args[0].startswith("lesson-")):
        raw_id = context.args[0].replace("lesson_", "").replace("lesson-", "")
        if raw_id.isdigit():
            lesson = await _db_call(context, "miniapp_get_lesson", int(raw_id))
            if lesson:
                title = lesson.get("title") or "Lesson"
                course = lesson.get("course_title") or "Study Notes"
                content = lesson.get("content") or ""
                words = len(content.split())
                minutes = max(1, math.ceil(words / 190))
                summary = extract_summary(content)
                icon = _course_icon(course, title, content)
                mini_app_url = context.application.bot_data.get("mini_app_url")

                buttons = []
                if mini_app_url:
                    buttons.append([
                        InlineKeyboardButton(
                            "📖 Read Full Lesson",
                            web_app=WebAppInfo(url=f"{mini_app_url.rstrip('/')}/#lesson-{raw_id}")
                        )
                    ])

                card_lines = [
                    f"{icon} <b>{escape(course)}</b>",
                    "━━━━━━━━━━━━━━━━━━",
                    f"🎯 <b>{escape(title)}</b>\n",
                    f"⏱ <b>~{minutes} min read</b> • {words} words • Academic Reference\n",
                    f"📝 <i>{escape(summary)}</i>\n",
                    "<i>Tap below to open the complete lesson in the Academic PDF Reader:</i>"
                ]

                await message.reply_text(
                    "\n".join(card_lines),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(buttons) if buttons else None
                )
                return

    await message.reply_text(
        "Welcome to the study notes bot!\n"
        "Use /subjects to browse notes, /quizzes to take knowledge checks, "
        "/search <word> to find a note, or /help to see commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    admin_ids: frozenset[int] = context.application.bot_data["admin_ids"]
    is_admin = update.effective_user is not None and update.effective_user.id in admin_ids
    text = (
        "Student commands:\n"
        "/subjects - browse subjects and notes\n"
        "/quizzes - take timed knowledge check quizzes\n"
        "/search <word> - search note titles\n"
        "/delete_me - delete your registration data"
    )
    if is_admin:
        text += (
            "\n\nAdmin commands:\n"
            "/newnote - ➕ add a note step-by-step (guided & easy)\n"
            "/addsubject <name> - create a subject\n"
            "/deletesubject <name> - delete a subject and all its notes\n"
            "/addnote Subject | Title | Text - quick text note\n"
            "/deletenote <id> - delete a note by ID\n"
            "/announce <message> - message all students & channel\n"
            "/channel - view or link your Telegram channel\n"
            "To upload a PDF, Word/PowerPoint file, or image, send it with caption: Subject | Title\n"
            "Tip: Forward any post from your channel here to link it!"
        )
    await message.reply_text(text)


async def subjects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    rows = await _db_call(context, "get_subjects")
    if not rows:
        await message.reply_text("No subjects yet.")
        return
    buttons = [
        [InlineKeyboardButton(row["name"], callback_data=f"sub:{row['id']}:0")]
        for row in rows
    ]
    await message.reply_text(
        "Choose a subject:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    query = " ".join(context.args).strip()
    if not query:
        await message.reply_text("Use: /search <word>")
        return
    if len(query) > 100:
        await message.reply_text("Search text must be 100 characters or fewer.")
        return
    rows = await _db_call(context, "search_notes", query, 10)
    if not rows:
        await message.reply_text("No matching notes found.")
        return
    buttons = [
        [
            InlineKeyboardButton(
                f"{KIND_ICONS.get(row['kind'], '📝')} {row['title']}",
                callback_data=f"note:{row['id']}",
            )
        ]
        for row in rows
    ]
    await message.reply_text(
        "Search results:", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def delete_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    await _db_call(context, "delete_user", user.id)
    await message.reply_text(
        "Your registration data has been deleted. Use /start to register again."
    )


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return
    await query.answer()
    data = query.data or ""

    if data == "back_to_subjects":
        rows = await _db_call(context, "get_subjects")
        if not rows:
            await query.edit_message_text("No subjects yet.")
            return
        buttons = [
            [InlineKeyboardButton(row["name"], callback_data=f"sub:{row['id']}:0")]
            for row in rows
        ]
        await query.edit_message_text(
            "Choose a subject:", reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("sub:"):
        parts = data.split(":")
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            return
        subject_id, page = int(parts[1]), int(parts[2])
        if subject_id <= 0 or page > 100_000:
            return
        notes = await _db_call(
            context, "get_notes", subject_id, PAGE_SIZE, page * PAGE_SIZE
        )
        admin_ids: frozenset[int] = context.application.bot_data.get("admin_ids", frozenset())
        is_admin = query.from_user is not None and query.from_user.id in admin_ids

        if not notes:
            back_btn = []
            if is_admin:
                back_btn.append([InlineKeyboardButton("➕ Add Note to this Subject", callback_data=f"wiz_direct:{subject_id}")])
            back_btn.append([InlineKeyboardButton("« Back to Subjects", callback_data="back_to_subjects")])
            await query.edit_message_text("No notes in this subject yet.", reply_markup=InlineKeyboardMarkup(back_btn))
            return
        buttons = [
            [
                InlineKeyboardButton(
                    f"{KIND_ICONS.get(note['kind'], '📝')} {note['title']}",
                    callback_data=f"note:{note['id']}",
                )
            ]
            for note in notes
        ]
        navigation = []
        if page > 0:
            navigation.append(
                InlineKeyboardButton(
                    "« Previous", callback_data=f"sub:{subject_id}:{page - 1}"
                )
            )
        if len(notes) == PAGE_SIZE:
            navigation.append(
                InlineKeyboardButton(
                    "Next »", callback_data=f"sub:{subject_id}:{page + 1}"
                )
            )
        if navigation:
            buttons.append(navigation)
        if is_admin:
            buttons.append([InlineKeyboardButton("➕ Add Note to this Subject", callback_data=f"wiz_direct:{subject_id}")])
        buttons.append([InlineKeyboardButton("« Back to Subjects", callback_data="back_to_subjects")])
        await query.edit_message_text(
            "Notes:", reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    if data.startswith("note:"):
        note_id_text = data.removeprefix("note:")
        if not note_id_text.isdigit():
            return
        note = await _db_call(context, "get_note", int(note_id_text))
        if note is None or query.message is None:
            if query.message is not None:
                await query.message.reply_text("That note is no longer available.")
            return
        admin_ids: frozenset[int] = context.application.bot_data.get("admin_ids", frozenset())
        is_admin = query.from_user is not None and query.from_user.id in admin_ids
        admin_hint = f"\n\n(ID: {note['id']} | Delete with /deletenote {note['id']})" if is_admin else ""
        icon = KIND_ICONS.get(note["kind"], "📝")
        if note["kind"] == "text":
            await _reply_with_text_note(
                query.message, "Study note", note["title"], note["content"]
            )
            if admin_hint:
                await query.message.reply_text(admin_hint.strip())
        elif note["kind"] == "document":
            await query.message.reply_document(note["content"], caption=f"{icon} {note['title']}{admin_hint}")
        elif note["kind"] == "photo":
            await query.message.reply_photo(note["content"], caption=f"{icon} {note['title']}{admin_hint}")
        return

    if data.startswith("quiz_info:"):
        quiz_id_text = data.removeprefix("quiz_info:")
        if not quiz_id_text.isdigit():
            return
        quiz_id = int(quiz_id_text)
        quiz = await _db_call(context, "miniapp_get_quiz", quiz_id)
        if not quiz or not quiz.get("questions"):
            await query.edit_message_text("Quiz not found or has no questions.")
            return

        # Enforce 1-attempt rule
        existing_sub = await _db_call(context, "get_quiz_submission", quiz_id, query.from_user.id)
        if existing_sub:
            score = existing_sub["score"]
            total = existing_sub["total_questions"]
            pct = int((score / total) * 100) if total else 0
            c_date = (
                existing_sub["completed_at"].strftime("%b %d, %Y at %H:%M")
                if hasattr(existing_sub["completed_at"], "strftime")
                else str(existing_sub["completed_at"])[:16]
            )
            await query.edit_message_text(
                f"⚠️ <b>You have already completed this quiz!</b>\n\n"
                f"📝 <b>Quiz:</b> {escape(quiz['title'])}\n"
                f"🏆 <b>Your Score:</b> {score} / {total} ({pct}%)\n"
                f"📅 <b>Submitted on:</b> {c_date}\n\n"
                f"<i>Note: Only one attempt is permitted per student.</i>",
                parse_mode="HTML",
            )
            return

        title = quiz.get("title") or "Quiz"
        duration = quiz.get("duration_minutes")
        q_count = len(quiz["questions"])
        instructions = (quiz.get("instructions") or "").strip()
        first_q = (quiz["questions"][0].get("question_text") or "").strip()
        clean_instructions = instructions if instructions.casefold() != first_q.casefold() else ""

        lines = [
            f"🎯 <b>Ready for the quiz: {escape(title)}?</b>",
        ]
        if clean_instructions:
            lines.append(escape(clean_instructions))
        meta = [f"• <b>Questions:</b> {q_count}"]
        if duration:
            meta.append(f"• <b>Time limit:</b> {duration} minute{'s' if duration != 1 else ''} per question")
            meta.append("\n⏱ <i>Your individual countdown timer will start the second you tap the button below!</i>")
        else:
            meta.append("\n<i>Tap below when you are ready to begin!</i>")
        lines.append("\n".join(meta))

        start_btn = InlineKeyboardButton(
            "🚀 I'm Ready — Send Question 1",
            callback_data=f"quiz_start:{quiz['id']}:0",
        )
        await query.edit_message_text(
            "\n\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[start_btn]]),
        )
        return

    if data.startswith("quiz_start:"):
        parts = data.split(":")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            quiz_id, q_index = int(parts[1]), int(parts[2])

            # Enforce 1-attempt rule
            existing_sub = await _db_call(context, "get_quiz_submission", quiz_id, query.from_user.id)
            if existing_sub:
                await query.edit_message_text(
                    f"⚠️ You have already completed this quiz! Your final score was {existing_sub['score']}/{existing_sub['total_questions']}."
                )
                return

            if q_index == 0:
                active_poll = await _db_call(context, "get_user_active_poll", quiz_id, query.from_user.id)
                if active_poll:
                    await query.edit_message_text(
                        "⚠️ You have already started this quiz! Please answer the question sent above."
                    )
                    return

            quiz = await _db_call(context, "miniapp_get_quiz", quiz_id)
            if not quiz or not quiz.get("questions"):
                await query.edit_message_text("Quiz not found or has no questions.")
                return
            questions = quiz["questions"]
            if q_index >= len(questions):
                await query.edit_message_text(
                    f"🎉 You have completed all questions in <b>{escape(quiz['title'])}</b>!",
                    parse_mode="HTML",
                )
                return

            question = questions[q_index]
            correct_option_id = next(
                (
                    index for index, option in enumerate(question["options"])
                    if option.get("is_correct")
                ),
                None,
            )
            if correct_option_id is None:
                await query.edit_message_text("Error: Question has no correct answer configured.")
                return

            duration_minutes = quiz.get("duration_minutes")
            open_period = max(5, min(int(duration_minutes * 60), 600)) if duration_minutes else None

            try:
                await query.edit_message_text(
                    f"⏱ <b>Question {q_index + 1} of {len(questions)} released!</b> Countdown is active below:",
                    parse_mode="HTML",
                )
            except Exception:
                pass

            poll_kwargs = {
                "chat_id": query.from_user.id,
                "question": question["question_text"],
                "options": [option["option_text"] for option in question["options"]],
                "type": "quiz",
                "is_anonymous": False,
                "correct_option_id": correct_option_id,
                "explanation": (question.get("explanation") or "")[:200] or None,
            }
            if open_period:
                poll_kwargs["open_period"] = open_period

            sent = await context.bot.send_poll(**poll_kwargs)

            # Register poll in active polls for on_poll_answer tracking
            poll_id = getattr(getattr(sent, "poll", None), "id", None)
            if poll_id:
                user_name = query.from_user.full_name or query.from_user.username or "Student"
                await _db_call(
                    context,
                    "register_active_poll",
                    str(poll_id),
                    quiz_id,
                    query.from_user.id,
                    user_name,
                    q_index,
                    correct_option_id,
                    len(questions),
                )
                context.application.bot_data.setdefault("active_quiz_polls", {})[str(poll_id)] = {
                    "quiz_id": quiz_id,
                    "user_id": query.from_user.id,
                    "user_name": user_name,
                    "question_index": q_index,
                    "correct_option_id": correct_option_id,
                    "total_questions": len(questions),
                }

            if q_index + 1 < len(questions):
                next_btn = InlineKeyboardButton(
                    f"➡️ Ready for Question {q_index + 2}",
                    callback_data=f"quiz_start:{quiz_id}:{q_index + 1}",
                )
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=f"When you are ready for Question {q_index + 2}, tap below to start its timer:",
                    reply_markup=InlineKeyboardMarkup([[next_btn]]),
                )
            else:
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=f"🏁 That's the final question of <b>{escape(quiz['title'])}</b>! Answer above before time runs out.",
                    parse_mode="HTML",
                )
            return


async def quizzes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    quizzes = await _db_call(context, "list_available_quizzes")
    if not quizzes:
        await message.reply_text("No quizzes available yet. Check back soon!")
        return

    buttons = []
    for q in quizzes:
        dur_text = f" · {q['duration_minutes']} min" if q.get("duration_minutes") else ""
        btn_label = f"📝 {q['title']} ({q['question_count']} Qs{dur_text})"
        buttons.append([InlineKeyboardButton(btn_label, callback_data=f"quiz_info:{q['id']}")])

    await message.reply_text(
        "📚 <b>Available Knowledge Checks:</b>\n"
        "Tap a quiz to review rules and start when you're ready:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def on_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    answer = update.poll_answer
    if answer is None:
        return
    poll_id = str(answer.poll_id)
    active_polls = context.application.bot_data.get("active_quiz_polls", {})
    poll_info = active_polls.pop(poll_id, None)

    # Fallback to database lookup
    db_poll = await _db_call(context, "pop_active_poll", poll_id)
    if not poll_info:
        poll_info = db_poll

    if not poll_info:
        logger.debug("on_poll_answer: poll_id %s not recognized", poll_id)
        return

    user_id = poll_info["user_id"]
    quiz_id = poll_info["quiz_id"]
    user_name = (
        (answer.user.full_name if answer.user else None)
        or poll_info.get("user_name")
        or "Student"
    )
    q_index = poll_info["question_index"]
    correct_id = poll_info["correct_option_id"]
    total_q = poll_info["total_questions"]

    selected_option = answer.option_ids[0] if answer.option_ids else -1
    is_correct = (selected_option == correct_id)

    sessions = context.application.bot_data.setdefault("quiz_sessions", {})
    session_key = (user_id, quiz_id)
    if session_key not in sessions:
        sessions[session_key] = []
    sessions[session_key].append({"q_index": q_index, "is_correct": is_correct})

    if len(sessions[session_key]) >= total_q:
        user_answers = sessions.pop(session_key, [])
        score = sum(1 for a in user_answers if a.get("is_correct"))

        await _db_call(
            context,
            "record_quiz_submission",
            quiz_id,
            user_id,
            user_name,
            score,
            total_q,
            user_answers,
        )
        await _db_call(context, "clear_user_active_polls", quiz_id, user_id)

        pct = int((score / total_q) * 100) if total_q else 0
        congrats = (
            f"🎉 <b>Quiz Complete!</b>\n\n"
            f"🏆 <b>Your Final Score:</b> {score} / {total_q} ({pct}%)\n"
            f"✅ Your response has been recorded. Thank you for participating!\n\n"
            f"<i>Only one attempt is permitted per student.</i>"
        )
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=congrats,
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.debug("Could not send quiz completion message: %s", exc)

        await _update_channel_quiz_card(context, quiz_id)


async def _update_channel_quiz_card(context: ContextTypes.DEFAULT_TYPE, quiz_id: int) -> None:
    card_info = await _db_call(context, "get_quiz_channel_card", quiz_id)
    if not card_info or not card_info.get("channel_id") or not card_info.get("telegram_message_ids"):
        return
    channel_id = card_info["channel_id"]
    message_id = card_info["telegram_message_ids"][0]

    stats = await _db_call(context, "get_quiz_stats", quiz_id)
    title = escape(card_info["title"])
    duration = card_info.get("duration_minutes")

    bot_username = getattr(context.bot, "username", "Amazia_note_taking_bot") or "Amazia_note_taking_bot"
    start_url = f"https://t.me/{bot_username}?start=quiz_{quiz_id}"
    btn_label = f"🚀 Start Timed Quiz ({duration} min)" if duration else "🚀 Start Quiz"
    reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn_label, url=start_url)]])

    lines = [f"📝 <b>Quiz: {title}</b>"]
    if duration:
        lines.append(f"⏱ <b>Time limit:</b> {duration} minute{'s' if duration != 1 else ''} per question")

    lines.append(
        f"📊 <b>Live Participation:</b>\n"
        f"👥 <b>{stats['total_participants']} student{'s' if stats['total_participants'] != 1 else ''} completed</b>\n"
        f"📈 <b>Average Score:</b> {stats['avg_percentage']}%"
    )

    if stats.get("top_scorers"):
        top_lines = ["🏆 <b>Top Scorers:</b>"]
        for s in stats["top_scorers"]:
            top_lines.append(f"• {escape(s['user_name'])}: {s['pct']}% ({s['score']}/{s['total_questions']})")
        lines.append("\n".join(top_lines))

    lines.append("<i>Tap below to take your timed quiz. Countdown begins when you confirm!</i>")

    try:
        await context.bot.edit_message_text(
            chat_id=channel_id,
            message_id=message_id,
            text="\n\n".join(lines),
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except Exception as exc:
        logger.debug("Could not edit channel quiz card: %s", exc)


async def add_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    name = " ".join(context.args).strip()
    if not name:
        await message.reply_text("Use: /addsubject <name>")
        return
    if len(name) > 60:
        await message.reply_text("Subject names must be 60 characters or fewer.")
        return
    created = await _db_call(context, "add_subject", name)
    await message.reply_text(
        f"Subject created: {name}" if created else f"Subject already exists: {name}"
    )


async def delete_subject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    name = " ".join(context.args).strip()
    if not name:
        await message.reply_text("Use: /deletesubject <name>")
        return
    deleted = await _db_call(context, "delete_subject", name)
    await message.reply_text(
        f"Subject '{name}' and its notes were deleted."
        if deleted
        else f"Subject '{name}' not found."
    )


async def delete_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    arg = " ".join(context.args).strip()
    if not arg or not arg.isdigit():
        await message.reply_text("Use: /deletenote <id>")
        return
    note_id = int(arg)
    deleted = await _db_call(context, "delete_note", note_id)
    await message.reply_text(
        f"Note {note_id} deleted." if deleted else f"Note {note_id} not found."
    )


async def _send_new_note_alerts(
    context: ContextTypes.DEFAULT_TYPE, title: str
) -> tuple[int, int]:
    student_ids = await _db_call(context, "get_student_ids")
    sent = failed = 0
    for student_id in student_ids:
        try:
            await context.bot.send_message(student_id, f"New note: {title}")
            sent += 1
        except TelegramError:
            failed += 1
            logger.warning("Could not send new-note alert to user %s", student_id)
        await asyncio.sleep(SEND_DELAY_SECONDS)
    return sent, failed


async def _publish_note_to_channel(
    context: ContextTypes.DEFAULT_TYPE,
    subject_name: str,
    title: str,
    kind: str,
    content: str,
    note_id: int,
) -> bool:
    channel_id = context.application.bot_data.get("channel_id")
    if not channel_id:
        saved_id = await _db_call(context, "get_setting", "channel_id")
        if saved_id:
            channel_id = int(saved_id) if saved_id.lstrip("-").isdigit() else saved_id
            context.application.bot_data["channel_id"] = channel_id
    if not channel_id:
        return False

    icon = KIND_ICONS.get(kind, "📝")
    try:
        bot_info = await context.bot.get_me()
        bot_username = bot_info.username or "Amazia_note_taking_bot"
        bot_url = f"https://t.me/{bot_username}?start=note_{note_id}"
        read_btn = InlineKeyboardMarkup(
            [[InlineKeyboardButton("📖 Open in Bot", url=bot_url)]]
        )
        if kind == "text":
            words = len(content.split())
            minutes = max(1, math.ceil(words / 190))
            summary = extract_summary(content)
            course_icon = _course_icon(subject_name, title, content)
            tunnel_file = Path(__file__).resolve().parent.parent / ".tunnel_ready"
            if tunnel_file.is_file():
                try:
                    live_url = tunnel_file.read_text(encoding="utf-8").strip()
                    if live_url.startswith("https://"):
                        context.application.bot_data["mini_app_url"] = live_url
                except Exception:
                    pass
            mini_app_url = context.application.bot_data.get("mini_app_url")

            buttons = [
                [InlineKeyboardButton("📖 Read in Study Bot", url=bot_url)],
            ]
            if mini_app_url:
                buttons.append([InlineKeyboardButton("🌐 Web Reader (Direct)", url=mini_app_url)])
            card_keyboard = InlineKeyboardMarkup(buttons)

            card_lines = [
                f"{course_icon} <b>{escape(subject_name)}</b>",
                "━━━━━━━━━━━━━━━━━━",
                f"🎯 <b>{escape(title)}</b>\n",
                f"⏱ <b>~{minutes} min read</b> • {words} words • Academic Reference\n",
                f"📝 <i>{escape(summary)}</i>\n",
                "<i>Tap below to open the complete study note:</i>",
            ]
            await context.bot.send_message(
                channel_id,
                "\n".join(card_lines),
                parse_mode="HTML",
                reply_markup=card_keyboard,
            )
        elif kind == "document":
            caption = f"📚 {subject_name}\n📄 {title}"
            await context.bot.send_document(channel_id, content, caption=caption, reply_markup=read_btn)
        elif kind == "photo":
            caption = f"📚 {subject_name}\n🖼 {title}"
            await context.bot.send_photo(channel_id, content, caption=caption, reply_markup=read_btn)
        return True
    except TelegramError as exc:
        logger.warning("Could not publish note %s to channel %s: %s", note_id, channel_id, exc)
        return False


async def add_text_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    raw_text = message.text or ""
    parts = raw_text.split(None, 1)
    args_text = parts[1] if len(parts) > 1 else ""
    parsed = parse_text_note(args_text)
    if parsed is None:
        await message.reply_text(
            "Use: /addnote Subject | Title | Text\n"
            "Subject (60), title (100), and note text are required."
        )
        return
    subject_name, title, content = parsed
    title = standardize_title(title, content)
    content = standardize_academic_markdown(content, title)
    subject = next(
        (
            row
            for row in await _db_call(context, "get_subjects")
            if row["name"].casefold() == subject_name.casefold()
        ),
        None,
    )
    if subject is None:
        await message.reply_text("Unknown subject. Create it first with /addsubject.")
        return
    note_id = await _db_call(context, "add_note", subject["id"], title, "text", content)
    sent, failed = await _send_new_note_alerts(context, title)
    published = await _publish_note_to_channel(context, subject["name"], title, "text", content, note_id)
    chan_msg = " & published to channel" if published else ""
    await message.reply_text(
        f"Text note saved (ID: {note_id}){chan_msg}. Alerts sent: {sent}; failed: {failed}."
    )


async def upload_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    parsed = parse_file_caption(message.caption)
    if parsed is None:
        await message.reply_text("Caption format: Subject | Title")
        return
    subject_name, title = parsed
    subject = next(
        (
            row
            for row in await _db_call(context, "get_subjects")
            if row["name"].casefold() == subject_name.casefold()
        ),
        None,
    )
    if subject is None:
        await message.reply_text("Unknown subject. Create it first with /addsubject.")
        return

    if message.document is not None:
        if not is_supported_document(
            message.document.mime_type, message.document.file_name
        ):
            await message.reply_text(
                "Supported documents are PDF, Word (.doc/.docx), and "
                "PowerPoint (.ppt/.pptx)."
            )
            return
        kind, file_id = "document", message.document.file_id
    elif message.photo:
        kind, file_id = "photo", message.photo[-1].file_id
    else:
        await message.reply_text("Send a document or photo with the required caption.")
        return

    note_id = await _db_call(context, "add_note", subject["id"], title, kind, file_id)
    sent, failed = await _send_new_note_alerts(context, title)
    published = await _publish_note_to_channel(context, subject["name"], title, kind, file_id, note_id)
    chan_msg = " & published to channel" if published else ""
    await message.reply_text(f"Note saved (ID: {note_id}){chan_msg}. Alerts sent: {sent}; failed: {failed}.")


async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    raw_text = message.text or ""
    parts = raw_text.split(None, 1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await message.reply_text("Use: /announce <message>")
        return
    if len(text) > MAX_BROADCAST_LENGTH:
        await message.reply_text(
            f"Announcement must be {MAX_BROADCAST_LENGTH} characters or fewer."
        )
        return

    sent = failed = 0
    for student_id in await _db_call(context, "get_student_ids"):
        try:
            await context.bot.send_message(student_id, text)
            sent += 1
        except TelegramError:
            failed += 1
            logger.warning("Could not send announcement to user %s", student_id)
        await asyncio.sleep(SEND_DELAY_SECONDS)

    channel_id = context.application.bot_data.get("channel_id")
    if not channel_id:
        saved_id = await _db_call(context, "get_setting", "channel_id")
        if saved_id:
            channel_id = int(saved_id) if saved_id.lstrip("-").isdigit() else saved_id
            context.application.bot_data["channel_id"] = channel_id
    if channel_id:
        try:
            await context.bot.send_message(channel_id, f"📢 **Announcement**\n\n{text}")
        except TelegramError as exc:
            logger.warning("Could not send announcement to channel %s: %s", channel_id, exc)

    await message.reply_text(f"Announcement complete. Sent: {sent}; failed: {failed}.")


async def on_error(
    update: object, context: ContextTypes.DEFAULT_TYPE
) -> None:
    error = context.error
    if error is not None:
        logger.error(
            "Unhandled exception while handling update",
            exc_info=(type(error), error, error.__traceback__),
        )
    if isinstance(update, Update) and update.effective_message is not None:
        try:
            await update.effective_message.reply_text(
                "Something went wrong. Please try again later."
            )
        except TelegramError:
            logger.info("Could not deliver the error message to the user.")


async def start_new_note_wizard(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return ConversationHandler.END
    admin_ids: frozenset[int] = context.application.bot_data.get("admin_ids", frozenset())
    if user.id not in admin_ids:
        await message.reply_text(
            f"⚠️ Unauthorized: You are not configured as an admin.\nYour Telegram ID is: {user.id}"
        )
        return ConversationHandler.END

    context.user_data.clear()
    rows = await _db_call(context, "get_subjects")
    buttons = [
        [InlineKeyboardButton(row["name"], callback_data=f"wiz_sub:{row['id']}")]
        for row in rows
    ]
    buttons.append([InlineKeyboardButton("➕ Create New Subject", callback_data="wiz_new_subject")])
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="wiz_cancel")])

    await message.reply_text(
        "📚 **Add Note (Step 1/3)**\n\nChoose an existing subject or create a new one:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return WIZ_CHOOSE_SUBJECT


async def wiz_direct_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.from_user is None or query.message is None:
        return ConversationHandler.END
    await query.answer()
    admin_ids: frozenset[int] = context.application.bot_data.get("admin_ids", frozenset())
    if query.from_user.id not in admin_ids:
        return ConversationHandler.END

    parts = (query.data or "").split(":")
    if len(parts) != 2 or not parts[1].isdigit():
        return ConversationHandler.END
    subject_id = int(parts[1])
    subjects = await _db_call(context, "get_subjects")
    sub_name = next((s["name"] for s in subjects if s["id"] == subject_id), "Subject")

    context.user_data.clear()
    context.user_data["wiz_subject_id"] = subject_id
    context.user_data["wiz_subject_name"] = sub_name

    cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wiz_cancel")]])
    await query.message.reply_text(
        f"✏️ **Add Note (Step 2/3)**\nSubject: **{sub_name}**\n\nSend the **title** for this note (up to 100 characters, or /cancel):",
        reply_markup=cancel_btn,
    )
    return WIZ_ENTER_TITLE


async def wiz_subject_chosen(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.message is None:
        return ConversationHandler.END
    await query.answer()
    data = query.data or ""

    if data == "wiz_cancel":
        await query.edit_message_text("❌ Note creation cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == "wiz_new_subject":
        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wiz_cancel")]])
        await query.edit_message_text(
            "📁 **Create New Subject**\n\nType the name for the new subject (up to 60 characters, or /cancel):",
            reply_markup=cancel_btn,
        )
        return WIZ_NEW_SUBJECT_NAME

    if data.startswith("wiz_sub:"):
        parts = data.split(":")
        if len(parts) != 2 or not parts[1].isdigit():
            return ConversationHandler.END
        subject_id = int(parts[1])
        subjects = await _db_call(context, "get_subjects")
        sub_name = next((s["name"] for s in subjects if s["id"] == subject_id), "Subject")

        context.user_data["wiz_subject_id"] = subject_id
        context.user_data["wiz_subject_name"] = sub_name

        cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wiz_cancel")]])
        await query.edit_message_text(
            f"✏️ **Add Note (Step 2/3)**\nSubject: **{sub_name}**\n\nSend the **title** for this note (up to 100 characters, or /cancel):",
            reply_markup=cancel_btn,
        )
        return WIZ_ENTER_TITLE

    return ConversationHandler.END


async def wiz_new_subject_name_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.effective_message
    if message is None or not message.text:
        return WIZ_NEW_SUBJECT_NAME
    name = message.text.strip()
    if not name or len(name) > 60:
        await message.reply_text("Subject name must be between 1 and 60 characters. Please try again (or /cancel):")
        return WIZ_NEW_SUBJECT_NAME

    await _db_call(context, "add_subject", name)
    subjects = await _db_call(context, "get_subjects")
    subject = next((s for s in subjects if s["name"].casefold() == name.casefold()), None)
    if subject is None:
        await message.reply_text("Could not create subject. Please try again or /cancel:")
        return WIZ_NEW_SUBJECT_NAME

    context.user_data["wiz_subject_id"] = subject["id"]
    context.user_data["wiz_subject_name"] = subject["name"]

    cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wiz_cancel")]])
    await message.reply_text(
        f"✅ Subject created: **{subject['name']}**\n\n✏️ **Add Note (Step 2/3)**\nSend the **title** for this note (up to 100 characters, or /cancel):",
        reply_markup=cancel_btn,
    )
    return WIZ_ENTER_TITLE


async def wiz_title_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.effective_message
    if message is None or not message.text:
        return WIZ_ENTER_TITLE
    title = message.text.strip()
    if not title or len(title) > 100:
        await message.reply_text("Title must be between 1 and 100 characters. Please try again (or /cancel):")
        return WIZ_ENTER_TITLE

    context.user_data["wiz_title"] = title
    sub_name = context.user_data.get("wiz_subject_name", "Subject")

    cancel_btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="wiz_cancel")]])
    await message.reply_text(
        f"📝 **Add Note (Step 3/3)**\n"
        f"Subject: **{sub_name}**\n"
        f"Title: **{title}**\n\n"
        "Send the content now! You can send:\n"
        "• Plain text (paste your notes)\n"
        "• A PDF, Word, or PowerPoint document\n"
        "• An image/photo\n\n"
        "(or send /cancel to abort)",
        reply_markup=cancel_btn,
    )
    return WIZ_ENTER_CONTENT


async def wiz_content_received(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    message = update.effective_message
    if message is None:
        return WIZ_ENTER_CONTENT

    subject_id = context.user_data.get("wiz_subject_id")
    sub_name = context.user_data.get("wiz_subject_name", "Subject")
    title = context.user_data.get("wiz_title")

    if not subject_id or not title:
        await message.reply_text("Session expired. Please start over with /newnote.")
        context.user_data.clear()
        return ConversationHandler.END

    if message.text:
        kind, content = "text", message.text
        title = standardize_title(title, content)
        content = standardize_academic_markdown(content, title)
    elif message.document:
        if not is_supported_document(
            message.document.mime_type, message.document.file_name
        ):
            await message.reply_text(
                "Please send a PDF, Word (.doc/.docx), or "
                "PowerPoint (.ppt/.pptx) document, or text:"
            )
            return WIZ_ENTER_CONTENT
        kind, content = "document", message.document.file_id
    elif message.photo:
        kind, content = "photo", message.photo[-1].file_id
    else:
        await message.reply_text(
            "Please send text, a supported document, or a photo (or /cancel):"
        )
        return WIZ_ENTER_CONTENT

    note_id = await _db_call(context, "add_note", subject_id, title, kind, content)
    sent, failed = await _send_new_note_alerts(context, title)
    published = await _publish_note_to_channel(context, sub_name, title, kind, content, note_id)
    chan_msg = "\n📢 Published to your Telegram channel!" if published else ""
    icon = KIND_ICONS.get(kind, "📝")
    await message.reply_text(
        f"✅ **Note saved successfully!** (ID: {note_id})\n\n"
        f"{icon} **{title}**\n"
        f"📚 Subject: {sub_name}\n"
        f"📢 Alerts sent to students: {sent}{chan_msg}"
    )
    context.user_data.clear()
    return ConversationHandler.END


async def wiz_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    context.user_data.clear()
    query = update.callback_query
    if query is not None:
        await query.answer()
        await query.edit_message_text("❌ Note creation cancelled.")
    elif update.effective_message is not None:
        await update.effective_message.reply_text("❌ Note creation cancelled.")
    return ConversationHandler.END


async def on_forwarded_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    admin_ids: frozenset[int] = context.application.bot_data.get("admin_ids", frozenset())
    if user.id not in admin_ids:
        return

    channel_chat = getattr(message, "forward_from_chat", None)
    if not channel_chat and getattr(message, "forward_origin", None):
        channel_chat = getattr(message.forward_origin, "chat", None)

    if channel_chat and getattr(channel_chat, "type", "") == "channel":
        channel_id = channel_chat.id
        channel_title = channel_chat.title or "Channel"
        await _db_call(context, "set_setting", "channel_id", str(channel_id))
        await _db_call(context, "set_setting", "channel_title", channel_title)
        context.application.bot_data["channel_id"] = channel_id
        await message.reply_text(
            f"🎉 **Channel linked successfully!**\n\n"
            f"📢 **Channel:** {channel_title}\n"
            f"🆔 **ID:** `{channel_id}`\n\n"
            "Make sure @Amazia_note_taking_bot is an **Admin** in the channel with 'Post Messages' permission.\n"
            "All new study notes and announcements will now automatically be published to this channel!"
        )


async def on_channel_post(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    post = update.channel_post
    if post and post.chat and post.chat.type == "channel":
        channel_id = post.chat.id
        channel_title = post.chat.title or "Channel"
        await _db_call(context, "set_setting", "channel_id", str(channel_id))
        await _db_call(context, "set_setting", "channel_title", channel_title)
        context.application.bot_data["channel_id"] = channel_id
        logger.info("Auto-detected and saved channel %s (%s)", channel_title, channel_id)


async def on_my_chat_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    member_update = update.my_chat_member
    if member_update and member_update.chat and member_update.chat.type == "channel":
        new_status = member_update.new_chat_member.status
        if new_status in ("administrator", "creator"):
            channel_id = member_update.chat.id
            channel_title = member_update.chat.title or "Channel"
            await _db_call(context, "set_setting", "channel_id", str(channel_id))
            await _db_call(context, "set_setting", "channel_title", channel_title)
            context.application.bot_data["channel_id"] = channel_id
            logger.info("Bot added as admin to channel %s (%s)", channel_title, channel_id)
            admin_ids: frozenset[int] = context.application.bot_data.get("admin_ids", frozenset())
            for admin_id in admin_ids:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"🎉 **Channel Connected!**\n\n"
                        f"The bot is now an Admin in **{channel_title}** (ID: `{channel_id}`).\n"
                        "All new study notes will automatically be published there!",
                    )
                except TelegramError:
                    pass


async def channel_info_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    admin_ids: frozenset[int] = context.application.bot_data.get("admin_ids", frozenset())
    if user.id not in admin_ids:
        await unauthorized_admin_command(update, context)
        return

    saved_id = await _db_call(context, "get_setting", "channel_id")
    saved_title = await _db_call(context, "get_setting", "channel_title") or "Channel"
    if saved_id:
        await message.reply_text(
            f"📢 **Linked Channel:** {saved_title}\n"
            f"🆔 **ID:** `{saved_id}`\n\n"
            "To link a different channel, simply forward any post from your channel here, or use /setchannel <id_or_username>."
        )
    else:
        await message.reply_text(
            "ℹ️ No channel linked yet.\n\n"
            "To link your channel:\n"
            "1. Add @Amazia_note_taking_bot as an **Admin** in your channel.\n"
            "2. **Forward any post** from your channel into this chat!"
        )


async def set_channel_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    admin_ids: frozenset[int] = context.application.bot_data.get("admin_ids", frozenset())
    if user.id not in admin_ids:
        await unauthorized_admin_command(update, context)
        return

    target = " ".join(context.args).strip()
    if not target:
        await message.reply_text("Use: /setchannel <@username_or_numeric_id>\nOr simply forward any post from your channel here.")
        return

    channel_id = int(target) if target.lstrip("-").isdigit() else target
    try:
        chat = await context.bot.get_chat(channel_id)
        channel_title = chat.title or str(channel_id)
        await _db_call(context, "set_setting", "channel_id", str(chat.id))
        await _db_call(context, "set_setting", "channel_title", channel_title)
        context.application.bot_data["channel_id"] = chat.id
        await message.reply_text(
            f"🎉 Channel linked: **{channel_title}** (ID: `{chat.id}`)!\n"
            "Make sure the bot is an admin in the channel with 'Post Messages' permission."
        )
    except TelegramError as exc:
        await message.reply_text(f"Could not connect to that channel: {exc}")


async def unauthorized_admin_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is not None and message is not None:
        await message.reply_text(
            f"⚠️ Unauthorized: You are not configured as an admin.\n"
            f"Your Telegram ID is: {user.id}\n"
            "To grant access, add this ID to ADMIN_IDS in your .env file."
        )


async def studio_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    if message is None:
        return

    user = update.effective_user
    admin_ids: frozenset[int] = context.bot_data.get("admin_ids", frozenset())

    if user and user.id not in admin_ids:
        await message.reply_text(
            f"🔒 <b>Admin Access Required</b>\n\n"
            f"CyberLearn Studio is reserved for administrators.\n"
            f"Your numeric Telegram User ID is: <code>{user.id}</code>\n\n"
            f"To grant access, add <code>{user.id}</code> to <code>ADMIN_IDS</code> in your <code>.env</code> file, then restart the bot.",
            parse_mode="HTML",
        )
        return

    # Always reload freshest tunnel URL from .tunnel_ready or .env so stale URLs are never served
    tunnel_file = Path(__file__).resolve().parent.parent / ".tunnel_ready"
    if tunnel_file.is_file():
        try:
            live_url = tunnel_file.read_text(encoding="utf-8").strip()
            if live_url.startswith("https://"):
                context.bot_data["mini_app_url"] = live_url
        except Exception:
            pass

    mini_app_url = context.bot_data.get("mini_app_url")
    if mini_app_url:
        from notes_bot.web import create_browser_admin_token

        browser_token = create_browser_admin_token(
            context.bot.token,
            user.id,
            user.first_name or "Admin",
            user.username or "",
        )
        browser_admin_url = f"{mini_app_url.rstrip('/')}/?admin_token={browser_token}"
        try:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="🚀 Open Studio (Telegram WebApp)",
                        web_app=WebAppInfo(url=mini_app_url),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🌐 Open Admin Studio in Browser",
                        url=browser_admin_url,
                    )
                ]
            ])
            await message.reply_text(
                "<b>CyberLearn Studio</b>\n\n"
                "Tap below to launch your studio workspace inside Telegram or in your web browser (valid 7 days):\n\n"
                f"🔗 Browser Admin Link: <a href=\"{browser_admin_url}\">Open Admin Studio</a>\n"
                f"<i>(Do not share the Browser Admin Link with students — it signs in as you.)</i>",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return
        except Exception as exc:
            logger.warning("Could not send WebApp button: %s. Sending link fallback.", exc)
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        text="🌐 Open Admin Studio in Browser",
                        url=browser_admin_url,
                    )
                ]
            ])
            await message.reply_text(
                f"<b>CyberLearn Studio</b>\n\n"
                f"Access your admin workspace in your browser (valid 7 days):\n"
                f"🔗 <a href=\"{browser_admin_url}\">Open Admin Studio</a>",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return
    else:
        await message.reply_text(
            "<b>CyberLearn Studio</b>\n\n"
            "The studio is running locally on your computer at: <code>http://127.0.0.1:8000</code>\n\n"
            "To enable opening it inside Telegram:\n"
            "1. Run <code>./start_tunnel.sh</code> in a terminal to get an HTTPS link.\n"
            "2. In your <code>.env</code> file, set <code>MINI_APP_URL=https://...</code>\n"
            "3. Restart the bot.",
            parse_mode="HTML",
        )


async def unknown_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.effective_message
    if message is not None:
        await message.reply_text("Unknown command. Type /help to see all available commands.")


def register_handlers(application: Application, admin_ids: frozenset[int]) -> None:
    admin_filter = filters.User(user_id=set(admin_ids))
    non_admin_filter = ~admin_filter

    # Interactive Step-by-Step Note Creation Wizard (Admin only)
    note_wizard = ConversationHandler(
        entry_points=[
            CommandHandler(["newnote", "newnotes"], start_new_note_wizard, filters=admin_filter),
            CallbackQueryHandler(wiz_direct_start, pattern=r"^wiz_direct:\d+$"),
        ],
        states={
            WIZ_CHOOSE_SUBJECT: [
                CallbackQueryHandler(wiz_subject_chosen, pattern=r"^(wiz_sub:\d+|wiz_new_subject|wiz_cancel)$"),
            ],
            WIZ_NEW_SUBJECT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wiz_new_subject_name_received),
                CallbackQueryHandler(wiz_cancel, pattern=r"^wiz_cancel$"),
            ],
            WIZ_ENTER_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wiz_title_received),
                CallbackQueryHandler(wiz_cancel, pattern=r"^wiz_cancel$"),
            ],
            WIZ_ENTER_CONTENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wiz_content_received),
                MessageHandler(filters.Document.ALL, wiz_content_received),
                MessageHandler(filters.PHOTO, wiz_content_received),
                CallbackQueryHandler(wiz_cancel, pattern=r"^wiz_cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", wiz_cancel),
            CallbackQueryHandler(wiz_cancel, pattern=r"^wiz_cancel$"),
        ],
    )
    application.add_handler(note_wizard)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("subjects", subjects))
    application.add_handler(CommandHandler(["quizzes", "quiz"], quizzes_command))
    application.add_handler(CommandHandler("search", search))
    application.add_handler(CommandHandler("delete_me", delete_me))

    # Studio command
    application.add_handler(CommandHandler("studio", studio_command))

    # Channel management commands
    application.add_handler(CommandHandler("channel", channel_info_command, filters=admin_filter))
    application.add_handler(CommandHandler("setchannel", set_channel_command, filters=admin_filter))
    application.add_handler(ChatMemberHandler(on_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.ChatType.CHANNEL, on_channel_post))
    application.add_handler(
        MessageHandler(
            admin_filter & filters.FORWARDED,
            on_forwarded_message,
        )
    )

    # Admin commands (authorized, with common typo aliases)
    application.add_handler(CommandHandler(["addsubject", "addsubjects"], add_subject, filters=admin_filter))
    application.add_handler(CommandHandler(["deletesubject", "deletesubjects"], delete_subject, filters=admin_filter))
    application.add_handler(CommandHandler(["addnote", "addnot"], add_text_note, filters=admin_filter))
    application.add_handler(CommandHandler(["deletenote", "deletenotes"], delete_note, filters=admin_filter))
    application.add_handler(CommandHandler("announce", announce, filters=admin_filter))
    application.add_handler(
        MessageHandler(
            admin_filter & (filters.Document.ALL | filters.PHOTO),
            upload_file,
        )
    )

    # Admin commands feedback (unauthorized)
    for cmd in ("newnote", "newnotes", "channel", "setchannel", "addsubject", "addsubjects", "deletesubject", "deletesubjects", "addnote", "addnot", "deletenote", "deletenotes", "announce"):
        application.add_handler(CommandHandler(cmd, unauthorized_admin_command, filters=non_admin_filter))

    application.add_handler(PollAnswerHandler(on_poll_answer))
    application.add_handler(CallbackQueryHandler(on_button))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_error_handler(on_error)
