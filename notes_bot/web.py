from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import math
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl

import httpx
import uvicorn
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.request import HTTPXRequest

from notes_bot.config import Config, load_config
from notes_bot.database import Database
from notes_bot.formatter import standardize_academic_markdown, standardize_title
from notes_bot.handlers import _course_icon, extract_summary, format_channel_lesson

logger = logging.getLogger(__name__)
INIT_DATA_MAX_AGE_SECONDS = 86_400
INIT_DATA_FUTURE_SKEW_SECONDS = 60


class CourseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Course title cannot be blank.")
        return value


class CourseArchiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_archived: bool


class LessonInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    source_content: str = Field(default="", max_length=500_000)
    content: str | None = Field(default=None, max_length=500_000)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Lesson title cannot be blank.")
        return value


class LessonUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    source_content: str = Field(max_length=500_000)
    content: str = Field(max_length=500_000)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Lesson title cannot be blank.")
        return value


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    content: str = Field(max_length=500_000)


class QuizOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_text: str = Field(min_length=1, max_length=500)
    match_text: str | None = Field(default=None, max_length=500)
    is_correct: bool = False

    @field_validator("option_text")
    @classmethod
    def option_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Answer options cannot be blank.")
        return value

    @field_validator("match_text")
    @classmethod
    def match_text_must_not_be_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Matching answers cannot be blank.")
        return value


class QuizQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: Literal["multiple_choice", "true_false"]
    question_text: str = Field(min_length=1, max_length=1_000)
    explanation: str = Field(default="", max_length=2_000)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    options: list[QuizOptionInput] = Field(default_factory=list, max_length=10)

    @field_validator("question_text")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question text cannot be blank.")
        return value

    @model_validator(mode="after")
    def validate_answer_options(self) -> QuizQuestionInput:
        correct_options = [option for option in self.options if option.is_correct]
        if self.question_type == "true_false":
            if len(self.options) != 2:
                raise ValueError("True/false questions must have exactly two options: True and False.")
            labels = [option.option_text.strip().casefold() for option in self.options]
            if labels != ["true", "false"] and set(labels) != {"true", "false"}:
                raise ValueError("True/false questions must have True and False options.")
            if len(correct_options) != 1:
                raise ValueError("Select exactly one correct answer (True or False).")
        elif self.question_type == "multiple_choice":
            if not 2 <= len(self.options) <= 10:
                raise ValueError("Multiple choice questions must have between 2 and 10 options.")
            for i, option in enumerate(self.options, start=1):
                if not option.option_text.strip():
                    raise ValueError(f"Option {i} cannot be blank.")
            if len(correct_options) != 1:
                raise ValueError("Multiple choice questions must have exactly one correct answer selected.")
        else:
            raise ValueError("Only 'multiple_choice' and 'true_false' questions are supported.")
        return self


class QuizUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    instructions: str = Field(default="", max_length=2_000)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    duration_minutes: int | None = Field(default=None, ge=1, le=600)
    questions: list[QuizQuestionInput] = Field(default_factory=list, max_length=100)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Quiz title cannot be blank.")
        return value


class CategoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=2_000)
    color: str = Field(default="#4f46e5", max_length=20)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Category name cannot be blank.")
        return value


class ModuleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2_000)
    position: int = Field(default=0, ge=0)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Module title cannot be blank.")
        return value


class AttachmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=100)
    file_size: int = Field(default=0, ge=0)
    telegram_file_id: str = Field(min_length=1)


class AIGenerationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: int | None = None
    quiz_id: int | None = None
    source_text: str = Field(min_length=1)
    generation_type: str = Field(min_length=1, max_length=100)
    provider: str | None = Field(default=None, max_length=100)


class ScheduledPublicationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_id: int = Field(ge=1)
    scheduled_at: str
    channel_id: str = Field(min_length=1)


class ScheduledPublicationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheduled_at: str | None = None
    status: str | None = None


class LessonDuplicateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LessonReorderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lesson_orders: list[list[int]]  # [[lesson_id, position], ...]


class QuestionBankItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: Literal["multiple_choice", "true_false"]
    question_text: str = Field(min_length=1, max_length=1000)
    explanation: str = Field(default="", max_length=2000)
    difficulty: str = Field(default="medium")
    options: list[dict[str, Any]] = Field(default_factory=list)


class QuestionBankImportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: int = Field(ge=1)
    quiz_id: int = Field(ge=1)
    position: int = Field(ge=0, default=0)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channel_id: str | None = None
    channel_title: str | None = None
    delivery_mode: str | None = None
    post_header_style: str | None = None
    branding_signature: str | None = None
    require_approval: bool | None = None
    quiz_anonymous: bool | None = None
    quiz_default_duration: int | None = None
    quiz_pass_percentage: int | None = None
    autosave_enabled: bool | None = None
    autosave_interval: int | None = None
    ai_provider: str | None = None
    ai_provider_api_key: str | None = None
    ai_provider_url: str | None = None
    ai_provider_model: str | None = None
    groq_api_key: str | None = None
    gemini_api_key: str | None = None
    grok_api_key: str | None = None
    groq_model: str | None = None
    gemini_model: str | None = None
    grok_model: str | None = None


class ChannelVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channel: str = Field(min_length=1, max_length=100)


def verify_telegram_init_data(
    init_data: str,
    bot_token: str,
    admin_ids: frozenset[int],
    *,
    now: int | None = None,
) -> dict[str, Any]:
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
        values = dict(pairs)
        if len(values) != len(pairs) or "hash" not in values:
            raise ValueError("Malformed init data.")
        supplied_hash = values.pop("hash")
        if len(supplied_hash) != 64:
            raise ValueError("Invalid init data signature.")

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(values.items())
        )
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
        ).digest()
        expected_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(supplied_hash, expected_hash):
            raise ValueError("Invalid init data signature.")

        auth_timestamp = int(values["auth_date"])
        current_time = int(time.time()) if now is None else now
        if auth_timestamp > current_time + INIT_DATA_FUTURE_SKEW_SECONDS:
            raise ValueError("Init data is from the future.")
        if current_time - auth_timestamp > INIT_DATA_MAX_AGE_SECONDS:
            raise ValueError("Init data has expired.")

        user = json.loads(values["user"])
        if not isinstance(user, dict) or isinstance(user.get("id"), bool):
            raise ValueError("Invalid Telegram user.")
        user_id = int(user["id"])
        if user_id <= 0:
            raise ValueError("Invalid Telegram user.")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=401, detail="Telegram authentication is invalid or expired."
        ) from exc

    if user_id not in admin_ids:
        raise HTTPException(status_code=403, detail="Administrator access required.")
    return user


def create_app(
    config: Config,
    *,
    database: Database | None = None,
    bot: Bot | None = None,
) -> FastAPI:
    db = database or Database(config.database_url)
    telegram_bot = bot or Bot(
        config.bot_token,
        request=HTTPXRequest(connect_timeout=15.0, read_timeout=25.0),
    )
    owns_db = database is None
    owns_bot = bot is None

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if owns_db:
            await asyncio.to_thread(db.open)
        if owns_bot:
            for attempt in range(3):
                try:
                    await telegram_bot.initialize()
                    break
                except Exception as exc:
                    if attempt == 2:
                        logger.warning(
                            "Bot initialize failed during web startup: %s. Continuing anyway.",
                            exc,
                        )
                    else:
                        await asyncio.sleep(1)
        app.state.database = db
        app.state.bot = telegram_bot
        try:
            yield
        finally:
            if owns_bot:
                try:
                    await telegram_bot.shutdown()
                except Exception:
                    pass
            if owns_db:
                await asyncio.to_thread(db.close)

    app = FastAPI(
        title="CyberLearn Studio",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )

    def admin_user(
        x_telegram_init_data: Annotated[
            str | None, Header(alias="X-Telegram-Init-Data")
        ] = None,
    ) -> dict[str, Any]:
        if not x_telegram_init_data:
            raise HTTPException(
                status_code=401, detail="Open this app from Telegram to sign in."
            )
        return verify_telegram_init_data(
            x_telegram_init_data, config.bot_token, config.admin_ids
        )

    async def db_call(method: str, *args: Any) -> Any:
        return await asyncio.to_thread(
            getattr(app.state.database, method), *args
        )

    def sanitize_quiz_for_client(quiz: dict[str, Any] | None) -> dict[str, Any] | None:
        if not quiz or "questions" not in quiz:
            return quiz
        for question in quiz["questions"]:
            if question.get("question_type") not in {"multiple_choice", "true_false"}:
                question["question_type"] = "multiple_choice"
                for opt in question.get("options", []):
                    opt["match_text"] = None
        if quiz.get("latest_version") and isinstance(quiz["latest_version"], dict):
            snapshot = quiz["latest_version"].get("snapshot")
            if snapshot and "questions" in snapshot:
                for question in snapshot["questions"]:
                    if question.get("question_type") not in {"multiple_choice", "true_false"}:
                        question["question_type"] = "multiple_choice"
                        for opt in question.get("options", []):
                            opt["match_text"] = None
        return quiz

    def quiz_publish_validation_error(quiz: dict[str, Any]) -> str | None:
        questions = quiz.get("questions") or []
        if not questions:
            return "Add at least one question before approving this quiz."
        unsupported = sorted({
            question["question_type"]
            for question in questions
            if question.get("question_type") not in {"multiple_choice", "true_false"}
        })
        if unsupported:
            return (
                "Telegram interactive quiz polls currently support only "
                "multiple-choice and true/false questions. Remove or change "
                f"these unsupported formats before approval: {', '.join(unsupported)}."
            )
        for index, question in enumerate(questions, start=1):
            q_text = (question.get("question_text") or "").strip()
            if not 1 <= len(q_text) <= 300:
                return f"Question {index} must be 1–300 characters for a Telegram poll."
            options = question.get("options") or []
            q_type = question.get("question_type")
            if q_type == "true_false":
                if len(options) != 2:
                    return f"Question {index} (True/False) must have exactly 2 options."
                labels = {opt.get("option_text", "").strip().casefold() for opt in options}
                if labels != {"true", "false"}:
                    return f"Question {index} (True/False) options must be True and False."
            else:
                if not 2 <= len(options) <= 10:
                    return f"Question {index} must have 2–10 answer options."
            if sum(1 for option in options if option.get("is_correct")) != 1:
                return f"Question {index} must have exactly one correct answer."
            if any(not 1 <= len((option.get("option_text") or "").strip()) <= 100 for option in options):
                return f"Each answer option in question {index} must be 1–100 characters."
        return None

    def sanitize_ai_config(provider: str | None, url: str | None, model: str | None) -> tuple[str, str]:
        prov = (provider or "groq").lower().strip()
        m = (model or "").strip()
        u = (url or "").strip()

        if prov == "groq":
            if not u or "api.x.ai" in u or "googleapis.com" in u:
                u = "https://api.groq.com/openai/v1/chat/completions"
            if not m or m == "gpt-4o" or m.startswith("gemini") or "llama" in m:
                m = "openai/gpt-oss-120b"
        elif prov == "gemini":
            if not u or "api.x.ai" in u or "api.groq.com" in u:
                u = "https://generativelanguage.googleapis.com/v1beta/models"
            if not m or m.startswith("llama") or m == "gpt-4o" or m.startswith("grok") or "gemini-2.5" in m or "gemini-1.5" in m:
                m = "gemini-3-flash-preview"
        elif prov == "grok":
            if not u or "api.groq.com" in u or "googleapis.com" in u:
                u = "https://api.x.ai/v1/chat/completions"
            if not m or m.startswith("llama") or m.startswith("gemini") or m == "gpt-4o":
                m = "grok-2-latest"
        else:
            u = u or "https://api.openai.com/v1/chat/completions"
            m = m or "gpt-4o"

        return u, m

    async def call_ai_provider(
        prompt: str,
        system_prompt: str | None = None,
    ) -> str:
        """Call the configured AI provider (Google Gemini, Grok, or OpenAI-compatible). Returns the generated text."""
        provider = await db_call("get_setting", "ai_provider") or config.ai_provider or "groq"
        
        # Check provider-specific keys first, with fallback to active general key
        api_key = None
        raw_model = None
        if provider == "groq":
            api_key = await db_call("get_setting", "groq_api_key")
            raw_model = await db_call("get_setting", "groq_model")
        elif provider == "gemini":
            api_key = await db_call("get_setting", "gemini_api_key")
            raw_model = await db_call("get_setting", "gemini_model")
        elif provider == "grok":
            api_key = await db_call("get_setting", "grok_api_key")
            raw_model = await db_call("get_setting", "grok_model")

        if not api_key:
            api_key = await db_call("get_setting", "ai_provider_api_key") or config.ai_provider_api_key
        if not raw_model:
            raw_model = await db_call("get_setting", "ai_provider_model") or config.ai_provider_model
        raw_url = await db_call("get_setting", "ai_provider_url") or config.ai_provider_url

        if not api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "AI provider API key is not configured. Add your Gemini, Groq, or Grok API key "
                    "in Studio Settings or set AI_PROVIDER_API_KEY in .env."
                ),
            )

        url, model = sanitize_ai_config(provider, raw_url, raw_model)

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    if provider == "gemini" or "generateContent" in url or "googleapis.com" in url:
                        candidate_models = [model]
                        for fb in ["gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-3.8-flash"]:
                            if fb not in candidate_models:
                                candidate_models.append(fb)
                        last_exc = None
                        for cand in candidate_models:
                            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{cand}:generateContent?key={api_key}"
                            contents_text = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
                            payload = {"contents": [{"parts": [{"text": contents_text}]}]}
                            try:
                                response = await client.post(endpoint, json=payload)
                                response.raise_for_status()
                                data = response.json()
                                return data["candidates"][0]["content"]["parts"][0]["text"]
                            except httpx.HTTPStatusError as g_err:
                                last_exc = g_err
                                if g_err.response.status_code in (404, 503) and cand != candidate_models[-1]:
                                    continue
                                raise
                        if last_exc:
                            raise last_exc
                    else:
                        messages = []
                        if system_prompt:
                            messages.append({"role": "system", "content": system_prompt})
                        messages.append({"role": "user", "content": prompt})
                        payload = {
                            "model": model,
                            "messages": messages,
                            "temperature": 0.7,
                            "max_tokens": 4000,
                        }
                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        }
                        response = await client.post(
                            url,
                            json=payload,
                            headers=headers,
                        )
                        response.raise_for_status()
                        data = response.json()
                        return data["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (503, 429) and attempt < 2:
                    logger.info("AI provider busy (%s), retrying attempt %s...", exc.response.status_code, attempt + 1)
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                logger.warning(
                    "AI provider returned error status %s: %s",
                    exc.response.status_code,
                    exc.response.text[:500],
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"AI provider error {exc.response.status_code}: {exc.response.text[:300]}",
                ) from exc
            except Exception as exc:
                logger.warning("AI provider request failed: %s", exc)
                raise HTTPException(
                    status_code=502,
                    detail=f"AI provider request failed: {exc}",
                ) from exc

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/me")
    async def me(
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        return {
            "id": user["id"],
            "first_name": user.get("first_name", ""),
            "username": user.get("username"),
        }

    @app.get("/api/courses")
    async def list_courses(
        include_archived: bool = False,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_courses", include_archived)

    @app.get("/api/dashboard")
    async def dashboard(
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        return await db_call("miniapp_dashboard_summary")

    @app.post("/api/courses", status_code=201)
    async def create_course(
        payload: CourseInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        return await db_call(
            "miniapp_create_course",
            payload.title,
            payload.description.strip(),
            int(user["id"]),
        )

    @app.put("/api/courses/{course_id}")
    async def update_course(
        course_id: int,
        payload: CourseInput,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        course = await db_call(
            "miniapp_update_course",
            course_id,
            payload.title,
            payload.description.strip(),
        )
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found.")
        return course

    @app.patch("/api/courses/{course_id}/archive")
    async def set_course_archived(
        course_id: int,
        payload: CourseArchiveInput,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        course = await db_call(
            "miniapp_set_course_archived", course_id, payload.is_archived
        )
        if course is None:
            raise HTTPException(status_code=404, detail="Course not found.")
        return course

    @app.get("/api/courses/{course_id}/lessons")
    async def list_lessons(
        course_id: int,
        query: str = "",
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_lessons", course_id, query.strip())

    @app.get("/api/courses/{course_id}/quizzes")
    async def list_quizzes(
        course_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_quizzes", course_id)

    @app.post("/api/courses/{course_id}/quizzes", status_code=201)
    async def create_quiz(
        course_id: int,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        quiz = await db_call(
            "miniapp_create_quiz", course_id, "Untitled quiz", int(user["id"])
        )
        if quiz is None:
            raise HTTPException(
                status_code=404,
                detail="Course not found or is archived.",
            )
        return quiz

    @app.get("/api/quizzes/{quiz_id}")
    async def get_quiz(
        quiz_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        quiz = await db_call("miniapp_get_quiz", quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Quiz not found.")
        return sanitize_quiz_for_client(quiz)

    @app.get("/api/quizzes/{quiz_id}/versions")
    async def list_quiz_versions(
        quiz_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        quiz = await db_call("miniapp_get_quiz", quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Quiz not found.")
        return await db_call("miniapp_list_quiz_versions", quiz_id)

    @app.put("/api/quizzes/{quiz_id}")
    async def update_quiz(
        quiz_id: int,
        payload: QuizUpdate,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        quiz = await db_call(
            "miniapp_save_quiz", quiz_id, payload.model_dump()
        )
        if quiz is None:
            raise HTTPException(status_code=404, detail="Quiz not found.")
        return sanitize_quiz_for_client(quiz)

    @app.delete("/api/quizzes/{quiz_id}")
    async def delete_quiz(
        quiz_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        deleted = await db_call("miniapp_delete_quiz", quiz_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Quiz not found.")
        return {"status": "deleted", "id": quiz_id}

    @app.post("/api/quizzes/{quiz_id}/approve")
    async def approve_quiz(
        quiz_id: int,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        quiz = await db_call("miniapp_get_quiz", quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Quiz not found.")
        validation_error = quiz_publish_validation_error(quiz)
        if validation_error:
            raise HTTPException(status_code=422, detail=validation_error)
        version = await db_call(
            "miniapp_approve_quiz", quiz_id, int(user["id"])
        )
        if version is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This quiz is already approved without changes, is currently "
                    "publishing, or has a partial delivery. Save changes or check "
                    "the existing delivery before trying again."
                ),
            )
        return version

    @app.post("/api/quizzes/{quiz_id}/publish")
    async def publish_quiz(
        quiz_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        channel_id = await db_call("get_setting", "channel_id")
        if not channel_id:
            raise HTTPException(
                status_code=409,
                detail="No channel is linked. Link one with /setchannel in the bot.",
            )
        quiz = await db_call("miniapp_get_quiz", quiz_id)
        if quiz is None:
            raise HTTPException(status_code=404, detail="Quiz not found.")
        approved = await db_call(
            "miniapp_claim_quiz_publish", quiz_id, str(channel_id)
        )
        if approved is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "No current approved quiz is ready to publish. Approve the "
                    "latest saved quiz version first; partial deliveries cannot "
                    "be retried automatically."
                ),
            )

        snapshot = approved["snapshot"]
        message_ids: list[int] = []
        try:
            questions = snapshot.get("questions") or []
            title = html.escape(snapshot.get("title") or "")
            instructions = (snapshot.get("instructions") or "").strip()
            duration_minutes = snapshot.get("duration_minutes")

            # Telegram Polls support native countdown timers via open_period (5-600 seconds)
            open_period: int | None = None
            if duration_minutes:
                open_period = max(5, min(int(duration_minutes * 60), 600))

            # Avoid repeating question text if user placed the question in instructions
            first_q_text = (questions[0].get("question_text") or "").strip() if questions else ""
            clean_instructions = (
                instructions
                if instructions and instructions.casefold() != first_q_text.casefold()
                else ""
            )

            bot_user = await telegram_bot.get_me() if hasattr(telegram_bot, "get_me") else None
            bot_username = getattr(bot_user, "username", "Amazia_note_taking_bot") or "Amazia_note_taking_bot"
            start_url = f"https://t.me/{bot_username}?start=quiz_{quiz_id}"

            # Always send an announcement card with live stats & deep link button
            intro_lines = [f"📝 <b>Quiz: {title}</b>"]
            if clean_instructions:
                intro_lines.append(html.escape(clean_instructions))
            if duration_minutes:
                intro_lines.append(
                    f"⏱ Time limit: {duration_minutes} minute{'s' if duration_minutes != 1 else ''}"
                )
            intro_lines.append(
                "📊 <b>Live Participation:</b>\n"
                "👥 <b>0 students completed</b>\n"
                "📈 <b>Average Score:</b> 0%"
            )
            intro_lines.append(
                "<i>Tap below to take your timed quiz. Countdown begins when you confirm!</i>"
            )
            intro = "\n\n".join(intro_lines)

            btn_label = f"🚀 Start Timed Quiz ({duration_minutes} min)" if duration_minutes else "🚀 Start Quiz"
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(btn_label, url=start_url)]
            ])

            intro_message = await telegram_bot.send_message(
                chat_id=channel_id,
                text=intro,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            message_ids.append(intro_message.message_id)

            for question_index, question in enumerate(questions, start=1):
                correct_option_id = next(
                    (
                        index for index, option in enumerate(question["options"])
                        if option["is_correct"]
                    ),
                    None,
                )
                if correct_option_id is None:
                    raise ValueError(
                        f"Question {question_index} has no correct answer."
                    )
                is_anon_setting = await db_call("get_setting", "quiz_anonymous")
                poll_kwargs: dict[str, Any] = {
                    "chat_id": channel_id,
                    "question": question["question_text"],
                    "options": [option["option_text"] for option in question["options"]],
                    "type": "quiz",
                    "correct_option_id": correct_option_id,
                    "explanation": question["explanation"][:200] or None,
                    "is_anonymous": is_anon_setting != "false",
                }
                if open_period:
                    poll_kwargs["open_period"] = open_period

                sent = await telegram_bot.send_poll(**poll_kwargs)
                message_ids.append(sent.message_id)
        except (TelegramError, ValueError) as exc:
            error = str(exc)[:1_000]
            await db_call(
                "miniapp_finish_quiz_publish",
                approved["id"],
                message_ids,
                error,
            )
            logger.warning(
                "Mini App quiz publish failed for quiz %s, version %s, after %s messages.",
                quiz_id,
                approved["version_number"],
                len(message_ids),
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "Telegram could not complete quiz publishing. Check quiz "
                    "delivery history before creating another approval."
                ),
            ) from exc

        await db_call(
            "miniapp_finish_quiz_publish",
            approved["id"],
            message_ids,
        )
        return {
            "status": "published",
            "version_number": approved["version_number"],
            "message_ids": message_ids,
        }

    @app.post("/api/courses/{course_id}/lessons", status_code=201)
    async def create_lesson(
        course_id: int,
        payload: LessonInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        initial_content = (
            payload.source_content if payload.content is None else payload.content
        )
        clean_title = standardize_title(payload.title, payload.source_content or payload.content or "")
        clean_content = standardize_academic_markdown(initial_content, clean_title) if initial_content else ""
        clean_source = (
            standardize_academic_markdown(payload.source_content, clean_title)
            if payload.source_content
            else clean_content
        )
        lesson = await db_call(
            "miniapp_create_lesson",
            course_id,
            clean_title,
            clean_source,
            clean_content,
            int(user["id"]),
        )
        if lesson is None:
            raise HTTPException(status_code=404, detail="Course not found.")
        return lesson

    @app.get("/api/notes")
    async def search_importable_notes(
        query: str = "",
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_search_notes", query.strip(), 30)

    @app.post("/api/courses/{course_id}/notes/{note_id}/import", status_code=201)
    async def import_note(
        course_id: int,
        note_id: int,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        result, lesson = await db_call(
            "miniapp_import_note", course_id, note_id, int(user["id"])
        )
        if result == "course_not_found":
            raise HTTPException(status_code=404, detail="Course not found.")
        if result == "note_not_found":
            raise HTTPException(status_code=404, detail="Bot note not found.")
        if result == "unsupported_note_type":
            raise HTTPException(
                status_code=422,
                detail="Only text notes can be imported as lesson content.",
            )
        if result == "empty_note":
            raise HTTPException(
                status_code=422,
                detail="This bot note has no text to import.",
            )
        if result == "already_imported":
            raise HTTPException(
                status_code=409,
                detail="This bot note has already been imported.",
            )
        if lesson is None:
            raise HTTPException(status_code=500, detail="Note import failed.")
        return lesson

    @app.get("/api/lessons/{lesson_id}")
    async def get_lesson(
        lesson_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        lesson = await db_call("miniapp_get_lesson", lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        return lesson

    @app.put("/api/lessons/{lesson_id}")
    async def update_lesson(
        lesson_id: int,
        payload: LessonUpdate,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        clean_title = standardize_title(payload.title, payload.content or payload.source_content or "")
        clean_content = standardize_academic_markdown(payload.content, clean_title) if payload.content else ""
        clean_source = (
            standardize_academic_markdown(payload.source_content, clean_title)
            if payload.source_content
            else clean_content
        )
        lesson = await db_call(
            "miniapp_update_lesson",
            lesson_id,
            clean_title,
            clean_source,
            clean_content,
        )
        if lesson is None:
            raise HTTPException(
                status_code=409,
                detail="Lesson cannot be edited in its current state.",
            )
        return lesson

    @app.delete("/api/lessons/{lesson_id}")
    async def delete_lesson(
        lesson_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        deleted = await db_call("miniapp_delete_lesson", lesson_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        return {"status": "deleted", "id": lesson_id}

    @app.post("/api/format-markdown")
    async def format_markdown(
        payload: PreviewInput,
    ) -> dict[str, Any]:
        clean_title = standardize_title(payload.title, payload.content)
        clean_content = standardize_academic_markdown(payload.content, clean_title)
        return {
            "title": clean_title,
            "content": clean_content,
        }

    @app.post("/api/lessons/{lesson_id}/preview")
    async def preview_lesson(
        lesson_id: int,
        payload: PreviewInput,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        lesson = await db_call("miniapp_get_lesson", lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        if not payload.content.strip():
            raise HTTPException(
                status_code=422,
                detail="Add lesson text before creating a preview.",
            )
        return {
            "parse_mode": "HTML",
            "parts": format_channel_lesson(
                lesson["course_title"], payload.title, payload.content
            ),
        }

    @app.post("/api/lessons/{lesson_id}/approve")
    async def approve_lesson(
        lesson_id: int,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        lesson = await db_call("miniapp_get_lesson", lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        if not lesson["content"].strip():
            if not lesson["source_content"].strip():
                raise HTTPException(
                    status_code=422,
                    detail="Add lesson text or source material before approval.",
                )
            lesson = await db_call(
                "miniapp_update_lesson",
                lesson_id,
                lesson["title"],
                lesson["source_content"],
                lesson["source_content"],
            )
            if lesson is None:
                raise HTTPException(
                    status_code=409,
                    detail="Lesson cannot be edited in its current state.",
                )
        version = await db_call(
            "miniapp_approve_lesson", lesson_id, int(user["id"])
        )
        if version is None:
            raise HTTPException(
                status_code=409,
                detail="Only a draft or failed lesson can be approved.",
            )
        return version

    @app.get("/api/lessons/{lesson_id}/versions")
    async def list_versions(
        lesson_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        lesson = await db_call("miniapp_get_lesson", lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        return await db_call("miniapp_list_versions", lesson_id)

    @app.get("/api/public/lessons")
    async def list_public_lessons() -> list[dict[str, Any]]:
        rows = await db_call("miniapp_list_public_lessons")
        return [
            {
                "id": r["id"],
                "course_id": r.get("course_id"),
                "course_title": r.get("course_title", "Course"),
                "title": r.get("title", "Untitled Lesson"),
                "status": r.get("status"),
                "updated_at": (
                    r["updated_at"].isoformat()
                    if r.get("updated_at") and hasattr(r["updated_at"], "isoformat")
                    else str(r.get("updated_at") or "")
                ),
            }
            for r in rows
        ]

    @app.get("/api/public/lessons/{lesson_id}")
    async def get_public_lesson(lesson_id: int) -> dict[str, Any]:
        lesson = await db_call("miniapp_get_lesson", lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        content = lesson.get("content") or ""
        words = len(content.split())
        minutes = max(1, math.ceil(words / 190))
        return {
            "id": lesson["id"],
            "course_id": lesson.get("course_id"),
            "course_title": lesson.get("course_title", "Course"),
            "title": lesson.get("title", "Untitled Lesson"),
            "content": content,
            "status": lesson.get("status"),
            "words": words,
            "reading_minutes": minutes,
            "created_at": (
                lesson["created_at"].isoformat()
                if lesson.get("created_at") and hasattr(lesson["created_at"], "isoformat")
                else str(lesson.get("created_at") or "")
            ),
            "updated_at": (
                lesson["updated_at"].isoformat()
                if lesson.get("updated_at") and hasattr(lesson["updated_at"], "isoformat")
                else str(lesson.get("updated_at") or "")
            ),
        }

    @app.post("/api/lessons/{lesson_id}/publish")
    async def publish_lesson(
        lesson_id: int,
        mode: str = "card",
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        channel_id = await db_call("get_setting", "channel_id")
        if not channel_id:
            raise HTTPException(
                status_code=409,
                detail="No channel is linked. Link one with /setchannel in the bot.",
            )
        lesson = await db_call("miniapp_get_lesson", lesson_id)
        if lesson is None:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        if lesson["status"] == "approved" and not lesson["content"].strip():
            raise HTTPException(
                status_code=409,
                detail="This approved lesson has no content. Edit it and add lesson text before publishing.",
            )
        approved = await db_call(
            "miniapp_claim_publish", lesson_id, str(channel_id)
        )
        if approved is None:
            raise HTTPException(
                status_code=409,
                detail="No approved version is ready, or it is already publishing/published.",
            )

        message_ids: list[int] = []
        try:
            if mode == "full":
                parts = format_channel_lesson(
                    approved["course_title"], approved["title"], approved["content"]
                )
                for part in parts:
                    sent = await telegram_bot.send_message(
                        chat_id=channel_id, text=part, parse_mode="HTML"
                    )
                    message_ids.append(sent.message_id)
            else:
                # Default "card" mode: 1 clean channel announcement card + interactive reader link
                summary = extract_summary(approved["content"])
                words = len(approved["content"].split())
                minutes = max(1, math.ceil(words / 190))
                icon = _course_icon(approved["course_title"], approved["title"], approved["content"])

                card_lines = [
                    f"{icon} <b>{html.escape(approved['course_title'])}</b>",
                    "━━━━━━━━━━━━━━━━━━━━",
                    f"🎯 <b>{html.escape(approved['title'])}</b>\n",
                    f"⏱ <b>~{minutes} min read</b> • {words} words • Academic Reference\n",
                    f"📝 <i>{html.escape(summary)}</i>\n",
                    "<i>Tap below to open the complete lesson in the Academic PDF Reader:</i>",
                ]
                card_text = "\n".join(card_lines)

                bot_user = (
                    await telegram_bot.get_me()
                    if hasattr(telegram_bot, "get_me")
                    else None
                )
                bot_username = (
                    getattr(bot_user, "username", "Amazia_note_taking_bot")
                    or "Amazia_note_taking_bot"
                )

                bot_deep_url = f"https://t.me/{bot_username}?start=lesson_{lesson_id}"
                buttons = [
                    [InlineKeyboardButton("📖 Read Full Lesson", url=bot_deep_url)],
                ]
                live_url = None
                tunnel_file = Path(__file__).resolve().parent.parent / ".tunnel_ready"
                if tunnel_file.is_file():
                    try:
                        cand = tunnel_file.read_text(encoding="utf-8").strip()
                        if cand.startswith("https://"):
                            live_url = cand
                    except Exception:
                        pass
                effective_url = live_url or config.mini_app_url
                if effective_url:
                    reader_url = f"{effective_url.rstrip('/')}/#lesson-{lesson_id}"
                    buttons.append([InlineKeyboardButton("🌐 Web Reader (Direct)", url=reader_url)])

                reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
                sent = await telegram_bot.send_message(
                    chat_id=channel_id,
                    text=card_text,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
                message_ids.append(sent.message_id)
        except (TelegramError, ValueError) as exc:
            error = str(exc)[:1_000]
            await db_call(
                "miniapp_finish_publish",
                lesson_id,
                approved["job_id"],
                message_ids,
                error,
            )
            logger.warning(
                "Mini App publish failed for lesson %s, job %s, after %s messages.",
                lesson_id,
                approved["job_id"],
                len(message_ids),
            )
            raise HTTPException(
                status_code=502,
                detail=(
                    "Telegram could not complete publishing. "
                    "Check publishing history before retrying."
                ),
            ) from exc

        await db_call(
            "miniapp_finish_publish",
            lesson_id,
            approved["job_id"],
            message_ids,
        )
        return {
            "status": "published",
            "job_id": approved["job_id"],
            "message_ids": message_ids,
        }

    # ------------------------------------------------------------------
    # Course categories
    # ------------------------------------------------------------------

    @app.get("/api/course-categories")
    async def list_categories(
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_categories")

    @app.post("/api/course-categories", status_code=201)
    async def create_category(
        payload: CategoryInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        return await db_call(
            "miniapp_create_category",
            payload.name.strip(),
            payload.description.strip(),
            payload.color.strip(),
        )

    @app.patch("/api/course-categories/{category_id}")
    async def update_category(
        category_id: int,
        payload: CategoryInput,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        category = await db_call(
            "miniapp_update_category",
            category_id,
            payload.name.strip(),
            payload.description.strip(),
            payload.color.strip(),
        )
        if category is None:
            raise HTTPException(status_code=404, detail="Category not found.")
        return category

    @app.delete("/api/course-categories/{category_id}")
    async def delete_category(
        category_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, str]:
        deleted = await db_call("miniapp_delete_category", category_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Category not found.")
        return {"status": "deleted"}

    # ------------------------------------------------------------------
    # Course modules
    # ------------------------------------------------------------------

    @app.get("/api/courses/{course_id}/modules")
    async def list_modules(
        course_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_modules", course_id)

    @app.post("/api/courses/{course_id}/modules", status_code=201)
    async def create_module(
        course_id: int,
        payload: ModuleInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        module = await db_call(
            "miniapp_create_module",
            course_id,
            payload.title.strip(),
            payload.description.strip(),
            payload.position,
        )
        if module is None:
            raise HTTPException(status_code=404, detail="Course not found.")
        return module

    @app.patch("/api/modules/{module_id}")
    async def update_module(
        module_id: int,
        payload: ModuleInput,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        module = await db_call(
            "miniapp_update_module",
            module_id,
            payload.title.strip(),
            payload.description.strip(),
            payload.position,
        )
        if module is None:
            raise HTTPException(status_code=404, detail="Module not found.")
        return module

    @app.delete("/api/modules/{module_id}")
    async def delete_module(
        module_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, str]:
        deleted = await db_call("miniapp_delete_module", module_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Module not found.")
        return {"status": "deleted"}

    # ------------------------------------------------------------------
    # Lesson attachments
    # ------------------------------------------------------------------

    @app.get("/api/lessons/{lesson_id}/attachments")
    async def list_attachments(
        lesson_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_attachments", lesson_id)

    @app.post("/api/lessons/{lesson_id}/attachments", status_code=201)
    async def create_attachment(
        lesson_id: int,
        payload: AttachmentInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        attachment = await db_call(
            "miniapp_create_attachment",
            lesson_id,
            payload.file_name.strip(),
            payload.mime_type.strip(),
            payload.file_size,
            payload.telegram_file_id.strip(),
        )
        if attachment is None:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        return attachment

    @app.delete("/api/attachments/{attachment_id}")
    async def delete_attachment(
        attachment_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, str]:
        deleted = await db_call("miniapp_delete_attachment", attachment_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Attachment not found.")
        return {"status": "deleted"}

    # ------------------------------------------------------------------
    # AI generations
    # ------------------------------------------------------------------

    @app.post("/api/ai/generate", status_code=201)
    async def create_ai_generation(
        payload: AIGenerationInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        if payload.lesson_id is None and payload.quiz_id is None:
            raise HTTPException(
                status_code=422,
                detail="Either lesson_id or quiz_id is required.",
            )

        system_prompts = {
            "structure_lesson": (
                "You are an educational content assistant. Organize the following "
                "raw notes into a structured lesson with clear sections, headings, "
                "learning objectives, key terms, and a summary. Do not invent facts. "
                "Preserve all original information."
            ),
            "improve_content": (
                "You are an educational editor. Improve the grammar, readability, "
                "and clarity of the following lesson content while preserving all "
                "original facts and technical accuracy."
            ),
            "generate_examples": (
                "You are an educational content assistant. Create clear, practical "
                "examples for the following lesson content. Each example should "
                "illustrate a key concept."
            ),
            "create_summary": (
                "You are an educational content assistant. Create a concise summary "
                "of the following lesson content, highlighting the most important "
                "points."
            ),
            "extract_terms": (
                "You are an educational content assistant. Extract the key terms and "
                "their definitions from the following lesson content. Format as a "
                "glossary."
            ),
            "generate_learning_objectives": (
                "You are an educational content assistant. Create measurable learning "
                "objectives for the following lesson content. Use action verbs "
                "(e.g., explain, demonstrate, compare, solve)."
            ),
            "generate_quiz_suggestions": (
                "You are an educational content assistant. Suggest quiz questions "
                "based on the following lesson content. Support ONLY two formats: "
                "multiple-choice (with 4 choices A, B, C, D and exactly one correct answer) "
                "and true/false (with True and False options and exactly one correct answer). "
                "Do not output any other question formats. Clearly indicate the single "
                "correct answer and an explanation for each question."
            ),
        }
        system_prompt = system_prompts.get(
            payload.generation_type,
            "You are an educational content assistant. Help organize and improve educational content.",
        )

        generated = await call_ai_provider(payload.source_text, system_prompt)

        return await db_call(
            "miniapp_create_ai_generation",
            payload.lesson_id,
            payload.quiz_id,
            payload.source_text,
            generated,
            payload.generation_type,
            payload.provider or "ai-provider",
        )

    @app.get("/api/ai/generations")
    async def list_ai_generations(
        lesson_id: int | None = None,
        quiz_id: int | None = None,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_ai_generations", lesson_id, quiz_id)

    @app.patch("/api/ai/generations/{generation_id}/accept")
    async def accept_ai_generation(
        generation_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        generation = await db_call("miniapp_accept_ai_generation", generation_id)
        if generation is None:
            raise HTTPException(status_code=404, detail="AI generation not found.")
        return generation

    # ------------------------------------------------------------------
    # Scheduled publications
    # ------------------------------------------------------------------

    @app.get("/api/scheduled")
    async def list_scheduled_publications(
        status: str | None = None,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_scheduled_publications", status)

    @app.post("/api/scheduled", status_code=201)
    async def create_scheduled_publication(
        payload: ScheduledPublicationInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        publication = await db_call(
            "miniapp_create_scheduled_publication",
            payload.lesson_id,
            payload.scheduled_at,
            payload.channel_id,
            int(user["id"]),
        )
        if publication is None:
            raise HTTPException(
                status_code=404,
                detail="Lesson not found or course is archived.",
            )
        return publication

    @app.patch("/api/scheduled/{publication_id}")
    async def update_scheduled_publication(
        publication_id: int,
        payload: ScheduledPublicationUpdate,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        publication = await db_call(
            "miniapp_update_scheduled_publication",
            publication_id,
            payload.scheduled_at,
            payload.status,
        )
        if publication is None:
            raise HTTPException(status_code=404, detail="Scheduled publication not found.")
        return publication

    @app.delete("/api/scheduled/{publication_id}")
    async def cancel_scheduled_publication(
        publication_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, str]:
        cancelled = await db_call("miniapp_cancel_scheduled_publication", publication_id)
        if not cancelled:
            raise HTTPException(
                status_code=404,
                detail="Scheduled publication not found or cannot be cancelled.",
            )
        return {"status": "cancelled"}

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    @app.get("/api/audit")
    async def list_audit_events(
        limit: int = 100,
        offset: int = 0,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        return await db_call("miniapp_list_audit_events", limit, offset)

    # ------------------------------------------------------------------
    # Settings & Configuration
    # ------------------------------------------------------------------

    @app.get("/api/settings")
    async def get_settings_endpoint(
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        all_settings = await db_call("get_all_settings") if hasattr(db, "get_all_settings") else {}
        if not isinstance(all_settings, dict):
            all_settings = {}
        channel_id = all_settings.get("channel_id") or await db_call("get_setting", "channel_id") or ""
        channel_title = all_settings.get("channel_title") or await db_call("get_setting", "channel_title") or ""
        ai_provider = all_settings.get("ai_provider") or config.ai_provider or "groq"
        
        # Provider-specific keys
        groq_key = all_settings.get("groq_api_key") or ""
        gemini_key = all_settings.get("gemini_api_key") or ""
        grok_key = all_settings.get("grok_api_key") or ""
        generic_key = all_settings.get("ai_provider_api_key") or config.ai_provider_api_key or ""

        # Auto-associate generic_key if it matches known prefixes
        if generic_key.startswith("gsk_") and not groq_key:
            groq_key = generic_key
        elif (generic_key.startswith("AQ.") or generic_key.startswith("AIzaSy")) and not gemini_key:
            gemini_key = generic_key
        elif generic_key.startswith("xai-") and not grok_key:
            grok_key = generic_key

        if not groq_key and config.ai_provider == "groq" and config.ai_provider_api_key:
            groq_key = config.ai_provider_api_key
        if not gemini_key and config.ai_provider == "gemini" and config.ai_provider_api_key:
            gemini_key = config.ai_provider_api_key
        if not grok_key and config.ai_provider == "grok" and config.ai_provider_api_key:
            grok_key = config.ai_provider_api_key

        groq_model = all_settings.get("groq_model") or "openai/gpt-oss-120b"
        gemini_model = all_settings.get("gemini_model") or "gemini-3-flash-preview"
        grok_model = all_settings.get("grok_model") or "grok-2-latest"

        # Active key & model
        if ai_provider == "groq":
            active_key = groq_key or generic_key
            active_model = groq_model
        elif ai_provider == "gemini":
            active_key = gemini_key or generic_key
            active_model = gemini_model
        elif ai_provider == "grok":
            active_key = grok_key or generic_key
            active_model = grok_model
        else:
            active_key = generic_key
            active_model = all_settings.get("ai_provider_model") or "gpt-4o"

        clean_url, clean_model = sanitize_ai_config(
            ai_provider,
            all_settings.get("ai_provider_url") or config.ai_provider_url,
            active_model,
        )
        return {
            "channel_id": str(channel_id),
            "channel_title": str(channel_title),
            "delivery_mode": all_settings.get("delivery_mode", "card"),
            "post_header_style": all_settings.get("post_header_style", "academic"),
            "branding_signature": all_settings.get("branding_signature", "CyberLearn Academic Team"),
            "require_approval": all_settings.get("require_approval", "true") == "true",
            "quiz_anonymous": all_settings.get("quiz_anonymous", "true") == "true",
            "quiz_default_duration": int(all_settings.get("quiz_default_duration", 10)),
            "quiz_pass_percentage": int(all_settings.get("quiz_pass_percentage", 70)),
            "autosave_enabled": all_settings.get("autosave_enabled", "true") == "true",
            "autosave_interval": int(all_settings.get("autosave_interval", 2)),
            "ai_provider": ai_provider,
            "ai_provider_api_key": active_key,
            "ai_provider_has_key": bool(active_key),
            "ai_provider_url": clean_url,
            "ai_provider_model": clean_model,
            "groq_api_key": groq_key,
            "groq_has_key": bool(groq_key),
            "groq_model": groq_model,
            "gemini_api_key": gemini_key,
            "gemini_has_key": bool(gemini_key),
            "gemini_model": gemini_model,
            "grok_api_key": grok_key,
            "grok_has_key": bool(grok_key),
            "grok_model": grok_model,
            "admin": admin,
        }

    @app.put("/api/settings")
    async def update_settings_endpoint(
        payload: SettingsUpdate,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        before_settings = await db_call("get_all_settings") if hasattr(db, "get_all_settings") else {}
        if not isinstance(before_settings, dict):
            before_settings = {}
        data = payload.model_dump(exclude_unset=True)
        updated: dict[str, str] = {}
        for key, value in data.items():
            if value is not None:
                str_val = "true" if value is True else "false" if value is False else str(value).strip()
                await db_call("set_setting", key, str_val)
                updated[key] = str_val

        target_prov = updated.get("ai_provider") or before_settings.get("ai_provider") or "groq"

        # If generic ai_provider_api_key was supplied, also update matching provider
        if "ai_provider_api_key" in updated:
            k = updated["ai_provider_api_key"]
            if k.startswith("gsk_") or target_prov == "groq":
                await db_call("set_setting", "groq_api_key", k)
                updated["groq_api_key"] = k
            if k.startswith("AQ.") or k.startswith("AIzaSy") or target_prov == "gemini":
                await db_call("set_setting", "gemini_api_key", k)
                updated["gemini_api_key"] = k
            if k.startswith("xai-") or target_prov == "grok":
                await db_call("set_setting", "grok_api_key", k)
                updated["grok_api_key"] = k

        # Sync active credentials
        if target_prov == "groq":
            active_k = updated.get("groq_api_key") or updated.get("ai_provider_api_key") or before_settings.get("groq_api_key")
            active_m = updated.get("groq_model") or updated.get("ai_provider_model") or before_settings.get("groq_model") or "openai/gpt-oss-120b"
            if active_k:
                await db_call("set_setting", "ai_provider_api_key", active_k)
                updated["ai_provider_api_key"] = active_k
            if active_m:
                await db_call("set_setting", "ai_provider_model", active_m)
                updated["ai_provider_model"] = active_m
        elif target_prov == "gemini":
            active_k = updated.get("gemini_api_key") or updated.get("ai_provider_api_key") or before_settings.get("gemini_api_key")
            active_m = updated.get("gemini_model") or updated.get("ai_provider_model") or before_settings.get("gemini_model") or "gemini-3-flash-preview"
            if active_k:
                await db_call("set_setting", "ai_provider_api_key", active_k)
                updated["ai_provider_api_key"] = active_k
            if active_m:
                await db_call("set_setting", "ai_provider_model", active_m)
                updated["ai_provider_model"] = active_m
        elif target_prov == "grok":
            active_k = updated.get("grok_api_key") or updated.get("ai_provider_api_key") or before_settings.get("grok_api_key")
            active_m = updated.get("grok_model") or updated.get("ai_provider_model") or before_settings.get("grok_model") or "grok-2-latest"
            if active_k:
                await db_call("set_setting", "ai_provider_api_key", active_k)
                updated["ai_provider_api_key"] = active_k
            if active_m:
                await db_call("set_setting", "ai_provider_model", active_m)
                updated["ai_provider_model"] = active_m

        # Auto-fill default URL and model if switching provider or if model needs sanitizing
        if "ai_provider" in updated:
            prov = updated["ai_provider"]
            clean_url, clean_model = sanitize_ai_config(
                prov,
                updated.get("ai_provider_url") or before_settings.get("ai_provider_url"),
                updated.get("ai_provider_model") or before_settings.get("ai_provider_model"),
            )
            if "ai_provider_url" not in updated:
                await db_call("set_setting", "ai_provider_url", clean_url)
                updated["ai_provider_url"] = clean_url
            if updated.get("ai_provider_model") in ("gpt-4o", "", None) and prov in ("groq", "gemini", "grok"):
                await db_call("set_setting", "ai_provider_model", clean_model)
                updated["ai_provider_model"] = clean_model

        await db_call(
            "miniapp_create_audit_event",
            int(admin["id"]),
            "update_settings",
            "settings",
            None,
            before_settings,
            updated,
        )
        return {"status": "saved", "updated": updated}

    @app.post("/api/settings/test-ai")
    async def test_ai_endpoint(
        payload: dict[str, Any] = Body(default_factory=dict),
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        provider = (
            payload.get("ai_provider")
            or await db_call("get_setting", "ai_provider")
            or config.ai_provider
            or "groq"
        )
        if "ai_provider_api_key" in payload:
            api_key = payload["ai_provider_api_key"]
        elif "groq_api_key" in payload and provider == "groq":
            api_key = payload["groq_api_key"]
        elif "gemini_api_key" in payload and provider == "gemini":
            api_key = payload["gemini_api_key"]
        elif "grok_api_key" in payload and provider == "grok":
            api_key = payload["grok_api_key"]
        else:
            api_key = None
            if provider == "groq":
                api_key = await db_call("get_setting", "groq_api_key")
            elif provider == "gemini":
                api_key = await db_call("get_setting", "gemini_api_key")
            elif provider == "grok":
                api_key = await db_call("get_setting", "grok_api_key")
            if not api_key:
                api_key = await db_call("get_setting", "ai_provider_api_key") or config.ai_provider_api_key

        model = (
            payload.get("ai_provider_model")
            or (payload.get("groq_model") if provider == "groq" else None)
            or (payload.get("gemini_model") if provider == "gemini" else None)
            or (payload.get("grok_model") if provider == "grok" else None)
            or (await db_call("get_setting", "groq_model") if provider == "groq" else None)
            or (await db_call("get_setting", "gemini_model") if provider == "gemini" else None)
            or (await db_call("get_setting", "grok_model") if provider == "grok" else None)
            or await db_call("get_setting", "ai_provider_model")
            or config.ai_provider_model
        )
        url = (
            payload.get("ai_provider_url")
            or await db_call("get_setting", "ai_provider_url")
            or config.ai_provider_url
        )

        api_key = (api_key or "").strip()
        if not api_key:
            raise HTTPException(
                status_code=422,
                detail=f"API key is required to test {provider.upper()} connection.",
            )

        url, model = sanitize_ai_config(provider, url, model)

        prompt = "Respond with exactly: 'AI connection verified successfully!'"
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    if provider == "gemini" or "generateContent" in url or "googleapis.com" in url:
                        candidate_models = [model]
                        for fb in ["gemini-3-flash-preview", "gemini-flash-lite-latest", "gemini-3.8-flash"]:
                            if fb not in candidate_models:
                                candidate_models.append(fb)
                        reply = None
                        last_exc = None
                        for cand in candidate_models:
                            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{cand}:generateContent?key={api_key}"
                            try:
                                response = await client.post(endpoint, json={"contents": [{"parts": [{"text": prompt}]}]})
                                response.raise_for_status()
                                reply = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                                model = cand
                                break
                            except httpx.HTTPStatusError as g_err:
                                last_exc = g_err
                                if g_err.response.status_code in (404, 503) and cand != candidate_models[-1]:
                                    continue
                                raise
                        if not reply and last_exc:
                            raise last_exc
                    else:
                        headers = {
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        }
                        data_body = {
                            "model": model,
                            "messages": [{"role": "user", "content": prompt}],
                            "max_tokens": 100,
                        }
                        response = await client.post(url, json=data_body, headers=headers)
                        response.raise_for_status()
                        reply = response.json()["choices"][0]["message"]["content"]
                return {
                    "ok": True,
                    "provider": provider,
                    "model": model,
                    "reply": reply.strip() if reply else "AI connection verified successfully!",
                }
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (503, 429) and attempt < 2:
                    await asyncio.sleep(2.0 * (attempt + 1))
                    continue
                detail = f"AI API returned error {exc.response.status_code}: {exc.response.text[:300]}"
                raise HTTPException(status_code=400, detail=detail) from exc
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Connection test failed: {exc}") from exc

    @app.post("/api/settings/fetch-models")
    async def fetch_provider_models(
        payload: dict[str, Any] = Body(default_factory=dict),
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        provider = (
            payload.get("ai_provider")
            or await db_call("get_setting", "ai_provider")
            or config.ai_provider
            or "groq"
        )
        api_key = (
            payload.get("ai_provider_api_key")
            or (payload.get("groq_api_key") if provider == "groq" else None)
            or (payload.get("gemini_api_key") if provider == "gemini" else None)
            or (payload.get("grok_api_key") if provider == "grok" else None)
            or (await db_call("get_setting", "groq_api_key") if provider == "groq" else None)
            or (await db_call("get_setting", "gemini_api_key") if provider == "gemini" else None)
            or (await db_call("get_setting", "grok_api_key") if provider == "grok" else None)
            or await db_call("get_setting", "ai_provider_api_key")
            or config.ai_provider_api_key
            or ""
        ).strip()
        url = (
            payload.get("ai_provider_url")
            or await db_call("get_setting", "ai_provider_url")
            or config.ai_provider_url
            or ""
        ).strip()

        if not api_key:
            raise HTTPException(status_code=422, detail="API key is required to fetch available models.")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                if provider == "groq":
                    models_url = "https://api.groq.com/openai/v1/models"
                    resp = await client.get(
                        models_url,
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    models = [
                        m["id"]
                        for m in data.get("data", [])
                        if m.get("active", True) is not False
                        and not m.get("id", "").startswith("whisper")
                    ]
                elif provider == "gemini":
                    models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                    resp = await client.get(models_url)
                    resp.raise_for_status()
                    data = resp.json()
                    models = [
                        m["name"].replace("models/", "")
                        for m in data.get("models", [])
                        if "generateContent" in m.get("supportedGenerationMethods", [])
                    ]
                elif provider == "grok":
                    models_url = "https://api.x.ai/v1/models"
                    resp = await client.get(
                        models_url,
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    models = [m["id"] for m in data.get("data", [])]
                else:
                    base = url.split("/chat/completions")[0] if "/chat/completions" in url else "https://api.openai.com/v1"
                    models_url = f"{base}/models"
                    resp = await client.get(
                        models_url,
                        headers={"Authorization": f"Bearer {api_key}"},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    models = [m["id"] for m in data.get("data", [])]

            return {"ok": True, "provider": provider, "models": sorted(models)}
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Provider returned error {exc.response.status_code}: {exc.response.text[:200]}",
            ) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not load models: {exc}") from exc

    @app.post("/api/settings/verify-channel")
    async def verify_channel_endpoint(
        payload: ChannelVerifyRequest,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        target = payload.channel.strip()
        if not target:
            raise HTTPException(status_code=422, detail="Channel username or numeric ID is required.")
        channel_id = int(target) if target.lstrip("-").isdigit() else target
        try:
            chat = await telegram_bot.get_chat(channel_id)
            title = getattr(chat, "title", str(channel_id)) or str(channel_id)
            is_admin = True
            try:
                me = await telegram_bot.get_me() if hasattr(telegram_bot, "get_me") else None
                if me and hasattr(telegram_bot, "get_chat_member"):
                    member = await telegram_bot.get_chat_member(chat.id, me.id)
                    status = getattr(member, "status", "")
                    is_admin = status in {"administrator", "creator"}
            except Exception:
                pass
            return {
                "ok": True,
                "id": str(chat.id),
                "title": title,
                "username": getattr(chat, "username", None),
                "is_admin": is_admin,
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not connect to channel: {exc}")

    # ------------------------------------------------------------------
    # Course delete with relationship checks
    # ------------------------------------------------------------------

    @app.delete("/api/courses/{course_id}")
    async def delete_course(
        course_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, str]:
        result = await db_call("miniapp_delete_course", course_id)
        if result == "course_not_found":
            raise HTTPException(status_code=404, detail="Course not found.")
        if result == "course_has_lessons":
            raise HTTPException(
                status_code=409,
                detail="Cannot delete course with existing lessons. "
                       "Archive the course instead, or delete its lessons first.",
            )
        if result == "course_has_modules":
            raise HTTPException(
                status_code=409,
                detail="Cannot delete course with existing modules. "
                       "Remove modules first.",
            )
        return {"status": "deleted"}

    # ------------------------------------------------------------------
    # Lesson duplication and reordering
    # ------------------------------------------------------------------

    @app.post("/api/lessons/{lesson_id}/duplicate", status_code=201)
    async def duplicate_lesson(
        lesson_id: int,
        payload: LessonDuplicateInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        duplicated = await db_call(
            "miniapp_duplicate_lesson", lesson_id, int(user["id"])
        )
        if duplicated is None:
            raise HTTPException(status_code=404, detail="Lesson not found.")
        return duplicated

    @app.patch("/api/courses/{course_id}/lessons/reorder")
    async def reorder_lessons(
        course_id: int,
        payload: LessonReorderInput,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, str]:
        lesson_orders = [
            (int(item[0]), int(item[1])) for item in payload.lesson_orders
        ]
        await db_call("miniapp_reorder_lessons", course_id, lesson_orders)
        return {"status": "reordered"}

    # ------------------------------------------------------------------
    # Question bank (reusable quiz questions)
    # ------------------------------------------------------------------

    @app.get("/api/question-bank")
    async def list_question_bank(
        course_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> list[dict[str, Any]]:
        items = await db_call("miniapp_list_question_bank", course_id)
        return [
            item for item in items
            if item.get("question_type") in {"multiple_choice", "true_false"}
        ]

    @app.post("/api/question-bank", status_code=201)
    async def create_question_bank_item(
        course_id: int,
        payload: QuestionBankItemInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        item = await db_call(
            "miniapp_create_question_bank_item",
            course_id,
            payload.question_type,
            payload.question_text,
            payload.explanation,
            payload.difficulty,
            payload.options,
            int(user["id"]),
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Course not found.")
        return item

    @app.delete("/api/question-bank/{question_id}")
    async def delete_question_bank_item(
        question_id: int,
        admin: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, str]:
        deleted = await db_call("miniapp_delete_question_bank_item", question_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Question not found.")
        return {"status": "deleted"}

    @app.post("/api/question-bank/import")
    async def import_question_bank_item(
        payload: QuestionBankImportInput,
        user: dict[str, Any] = Depends(admin_user),
    ) -> dict[str, Any]:
        quiz = await db_call(
            "miniapp_import_question_bank_item",
            payload.question_id,
            payload.quiz_id,
            payload.position,
        )
        if quiz is None:
            raise HTTPException(
                status_code=404,
                detail="Question or quiz not found.",
            )
        return quiz

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=204)

    static_dir = Path(__file__).resolve().parent.parent / "miniapp" / "dist"
    if static_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=static_dir, html=True),
            name="miniapp",
        )
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    host = os.environ.get("WEB_HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(create_app(load_config()), host=host, port=port)


if __name__ == "__main__":
    main()
