from __future__ import annotations

import hashlib
import hmac
import json
import time
import unittest
from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi.testclient import TestClient
from telegram.error import BadRequest

from notes_bot.config import Config
from notes_bot.web import create_app, verify_telegram_init_data


BOT_TOKEN = "123456:test-token"
ADMIN_IDS = frozenset({42})


def signed_init_data(user_id: int = 42, *, auth_date: int | None = None) -> str:
    values = {
        "auth_date": str(int(time.time()) if auth_date is None else auth_date),
        "user": json.dumps(
            {"id": user_id, "first_name": "Admin"}, separators=(",", ":")
        ),
    }
    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(values.items())
    )
    secret_key = hmac.new(
        b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
    ).digest()
    values["hash"] = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(values)


class FakeDatabase:
    def __init__(self) -> None:
        self.finish_calls = []
        self.images: dict[int, dict] = {}
        self.next_image_id = 1
        self.lesson = {
            "id": 4,
            "title": "Ports",
            "course_title": "Networking",
            "source_content": "Original lesson material.",
            "content": "",
            "status": "draft",
        }
        self.approved_lesson = None
        self.notes = {
            12: {
                "id": 12,
                "title": "IP addressing",
                "subject_name": "Networking",
                "kind": "text",
                "content": "An IP address identifies a device on a network.",
                "already_imported": False,
            },
            13: {
                "id": 13,
                "title": "Network diagram",
                "subject_name": "Networking",
                "kind": "photo",
                "content": "telegram-file-id",
                "already_imported": False,
            },
        }
        self.imported_note_ids = set()
        self.courses = {
            1: {
                "id": 1,
                "title": "Networking",
                "description": "",
                "is_archived": False,
                "lesson_count": 0,
            }
        }
        self.course_lessons = [
            {"id": 4, "course_id": 1, "title": "Ports", "status": "draft"},
            {"id": 5, "course_id": 1, "title": "IP routing", "status": "draft"},
        ]
        self.quizzes = {}
        self.quiz_versions = {}
        self.next_quiz_version_id = 1
        self.settings = {"channel_id": "-10012345", "channel_title": "Test Channel"}
        self.audit_events = []
        self.ai_generations = []

    def miniapp_list_courses(self, include_archived=False):
        return [
            dict(course)
            for course in self.courses.values()
            if include_archived or not course["is_archived"]
        ]

    def miniapp_dashboard_summary(self):
        return {
            "course_count": 1,
            "quiz_count": len(self.quizzes),
            "lesson_count": 2,
            "draft_count": 1,
            "ready_count": 0,
            "published_count": 1,
            "failed_publish_count": 1,
            "recent_activity": [
                {
                    "job_id": 8,
                    "lesson_id": 4,
                    "lesson_title": "Ports",
                    "course_id": 1,
                    "course_title": "Networking",
                    "channel_id": "-10012345",
                    "status": "published",
                    "attempt_count": 1,
                    "telegram_message_ids": [501],
                    "error": None,
                    "updated_at": "2026-11-03T10:00:00+00:00",
                }
            ],
        }

    def miniapp_list_quizzes(self, course_id):
        return [
            {"id": quiz["id"], "course_id": course_id, "title": quiz["title"],
             "difficulty": quiz["difficulty"], "duration_minutes": quiz["duration_minutes"],
             "question_count": len(quiz["questions"])}
            for quiz in self.quizzes.values()
            if quiz["course_id"] == course_id
        ]

    def miniapp_create_quiz(self, course_id, title, admin_id):
        if course_id != 1 or self.courses[course_id]["is_archived"]:
            return None
        quiz_id = max(self.quizzes, default=0) + 1
        self.quizzes[quiz_id] = {
            "id": quiz_id,
            "course_id": course_id,
            "course_title": self.courses[course_id]["title"],
            "title": title,
            "instructions": "",
            "difficulty": "medium",
            "duration_minutes": None,
            "questions": [],
            "created_by": admin_id,
        }
        return dict(self.quizzes[quiz_id])

    def miniapp_get_quiz(self, quiz_id):
        quiz = self.quizzes.get(quiz_id)
        if quiz is None:
            return None
        result = deepcopy(quiz)
        versions = self.quiz_versions.get(quiz_id, [])
        result["latest_version"] = deepcopy(versions[-1]) if versions else None
        return result

    def miniapp_save_quiz(self, quiz_id, quiz_data):
        quiz = self.quizzes.get(quiz_id)
        if quiz is None:
            return None
        quiz.update(quiz_data)
        quiz["questions"] = quiz_data["questions"]
        return dict(quiz)

    def miniapp_approve_quiz(self, quiz_id, admin_id):
        quiz = self.quizzes.get(quiz_id)
        if quiz is None:
            return None
        versions = self.quiz_versions.setdefault(quiz_id, [])
        if versions and versions[-1]["status"] in {
            "approved", "publishing", "published", "partial"
        } and versions[-1]["snapshot"] == quiz:
            return None
        version = {
            "id": self.next_quiz_version_id,
            "version_number": len(versions) + 1,
            "snapshot": deepcopy(quiz),
            "approved_by": admin_id,
            "approved_at": "2026-11-03T10:00:00+00:00",
            "status": "approved",
            "telegram_message_ids": [],
            "error": None,
            "attempt_count": 0,
        }
        self.next_quiz_version_id += 1
        versions.append(version)
        return deepcopy(version)

    def miniapp_list_quiz_versions(self, quiz_id):
        return deepcopy(self.quiz_versions.get(quiz_id, []))

    def miniapp_claim_quiz_publish(self, quiz_id, channel_id):
        versions = self.quiz_versions.get(quiz_id, [])
        if not versions or versions[-1]["status"] not in {"approved", "failed"}:
            return None
        version = versions[-1]
        if version["snapshot"] != self.quizzes[quiz_id]:
            return None
        if version["status"] == "failed" and version["telegram_message_ids"]:
            return None
        version.update(
            status="publishing",
            channel_id=channel_id,
            attempt_count=version["attempt_count"] + 1,
        )
        return {
            "id": version["id"],
            "quiz_id": quiz_id,
            "version_number": version["version_number"],
            "snapshot": deepcopy(version["snapshot"]),
        }

    def miniapp_finish_quiz_publish(self, version_id, message_ids, error=None):
        for versions in self.quiz_versions.values():
            for version in versions:
                if version["id"] == version_id:
                    version.update(
                        status="partial" if error and message_ids else "failed" if error else "published",
                        telegram_message_ids=list(message_ids),
                        error=error,
                    )
                    return

    def miniapp_update_course(self, course_id, title, description):
        course = self.courses.get(course_id)
        if course is None:
            return None
        course.update(title=title, description=description)
        return dict(course)

    def miniapp_set_course_archived(self, course_id, is_archived):
        course = self.courses.get(course_id)
        if course is None:
            return None
        course["is_archived"] = is_archived
        return dict(course)

    def miniapp_list_lessons(self, course_id, query=""):
        return [
            dict(lesson)
            for lesson in self.course_lessons
            if lesson["course_id"] == course_id
            and query.casefold() in lesson["title"].casefold()
        ]

    def miniapp_search_notes(self, query="", limit=30):
        matching = [
            note
            for note in self.notes.values()
            if note["kind"] == "text"
            and (not query or query.casefold() in note["title"].casefold()
                 or query.casefold() in note["content"].casefold()
                 or query.casefold() in note["subject_name"].casefold())
        ]
        return [
            {**note, "already_imported": note["id"] in self.imported_note_ids}
            for note in matching[:limit]
        ]

    def miniapp_import_note(self, course_id, note_id, admin_id):
        if course_id != 1:
            return "course_not_found", None
        note = self.notes.get(note_id)
        if note is None:
            return "note_not_found", None
        if note["kind"] != "text":
            return "unsupported_note_type", None
        if not note["content"].strip():
            return "empty_note", None
        if note_id in self.imported_note_ids:
            return "already_imported", None
        self.imported_note_ids.add(note_id)
        lesson = {
            "id": 9,
            "course_id": course_id,
            "source_note_id": note_id,
            "title": note["title"],
            "source_content": note["content"],
            "content": note["content"],
            "status": "draft",
            "created_by": admin_id,
        }
        return "imported", lesson

    def miniapp_get_lesson(self, lesson_id):
        return dict(self.lesson) if lesson_id == self.lesson["id"] else None

    def miniapp_list_public_lessons(self):
        return [dict(self.lesson)]

    def miniapp_update_lesson(self, lesson_id, title, source_content, content):
        if lesson_id != self.lesson["id"]:
            return None
        self.lesson.update(
            title=title,
            source_content=source_content,
            content=content,
            status="draft",
        )
        return dict(self.lesson)

    def miniapp_delete_lesson(self, lesson_id):
        if self.lesson and lesson_id == self.lesson.get("id"):
            self.lesson = {}
            return True
        return False

    def miniapp_delete_quiz(self, quiz_id):
        if quiz_id in self.quizzes:
            del self.quizzes[quiz_id]
            return True
        return False

    def miniapp_approve_lesson(self, lesson_id, admin_id):
        if lesson_id != self.lesson["id"] or not self.lesson["content"].strip():
            return None
        self.lesson["status"] = "approved"
        self.approved_lesson = {
            "content": self.lesson["content"],
            "approved_by": admin_id,
        }
        return {"version_number": 1}

    def miniapp_claim_publish(self, lesson_id, channel_id):
        return {
            "title": "Ports",
            "course_title": "Networking",
            "content": "## Definition\nA port identifies an application endpoint.",
            "job_id": 8,
        }

    def get_setting(self, key):
        return self.settings.get(key)

    def set_setting(self, key, value):
        self.settings[key] = str(value)

    def get_all_settings(self):
        return dict(self.settings)

    def miniapp_create_audit_event(
        self, actor_id, action, target_type, target_id=None, before_value=None, after_value=None
    ):
        event = {
            "id": len(self.audit_events) + 1,
            "actor_id": actor_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "before_value": before_value,
            "after_value": after_value,
            "created_at": "2026-11-21T09:00:00+00:00",
        }
        self.audit_events.insert(0, event)
        return event

    def miniapp_list_audit_events(self, limit=100, offset=0):
        return self.audit_events[offset:offset + limit]

    def miniapp_finish_publish(
        self, lesson_id, job_id, message_ids, error=None
    ):
        self.finish_calls.append((lesson_id, job_id, message_ids, error))

    def miniapp_create_ai_generation(
        self, lesson_id, quiz_id, source_text, generated_content, generation_type, provider
    ):
        gen = {
            "id": len(self.ai_generations) + 1,
            "lesson_id": lesson_id,
            "quiz_id": quiz_id,
            "source_text": source_text,
            "generated_content": generated_content,
            "generation_type": generation_type,
            "provider": provider,
            "accepted": False,
            "created_at": "2026-11-21T09:00:00+00:00",
            "accepted_at": None,
        }
        self.ai_generations.append(gen)
        return gen

    def miniapp_list_ai_generations(self, lesson_id=None, quiz_id=None):
        return [
            g for g in self.ai_generations
            if (lesson_id is None or g["lesson_id"] == lesson_id)
            and (quiz_id is None or g["quiz_id"] == quiz_id)
        ]

    def miniapp_accept_ai_generation(self, generation_id):
        for g in self.ai_generations:
            if g["id"] == generation_id:
                g["accepted"] = True
                g["accepted_at"] = "2026-11-21T09:05:00+00:00"
                return g
        return None


    def miniapp_create_image(self, lesson_id, file_name, mime_type, data):
        img_id = self.next_image_id
        self.next_image_id += 1
        row = {
            "id": img_id,
            "lesson_id": lesson_id,
            "file_name": file_name,
            "mime_type": mime_type,
            "file_size": len(data),
            "data": data,
            "url": f"/api/images/{img_id}",
        }
        self.images[img_id] = row
        return {k: v for k, v in row.items() if k != "data"}

    def miniapp_get_image(self, image_id):
        return self.images.get(image_id)


class FakeBot:
    def __init__(self) -> None:
        self.messages = []
        self.polls = []
        self.fail_poll_number = None

    async def get_me(self):
        return SimpleNamespace(username="test_note_bot", id=999)

    async def get_chat(self, chat_id):
        if str(chat_id) in {"-10012345", "@cyberlearn_channel", "@test_channel", "-10099999"}:
            return SimpleNamespace(id=-10012345, title="CyberLearn Channel", username="cyberlearn_channel")
        raise BadRequest("Chat not found")

    async def get_chat_member(self, chat_id, user_id):
        return SimpleNamespace(status="administrator")

    async def send_message(self, *, chat_id, text, parse_mode, reply_markup=None, **kwargs):
        self.messages.append((chat_id, text, parse_mode, reply_markup))
        return SimpleNamespace(message_id=500 + len(self.messages))

    async def send_poll(self, **kwargs):
        if self.fail_poll_number == len(self.polls) + 1:
            raise BadRequest("Simulated Telegram poll failure.")
        self.polls.append(kwargs)
        return SimpleNamespace(message_id=600 + len(self.polls))


class TelegramInitDataTests(unittest.TestCase):
    def test_accepts_valid_admin_signature(self):
        user = verify_telegram_init_data(
            signed_init_data(), BOT_TOKEN, ADMIN_IDS
        )
        self.assertEqual(user["id"], 42)

    def test_rejects_bad_signature_stale_data_and_non_admin(self):
        with self.assertRaises(HTTPException) as bad_signature:
            verify_telegram_init_data(
                signed_init_data() + "x", BOT_TOKEN, ADMIN_IDS
            )
        self.assertEqual(bad_signature.exception.status_code, 401)
        with self.assertRaises(HTTPException) as stale_data:
            verify_telegram_init_data(
                signed_init_data(auth_date=1), BOT_TOKEN, ADMIN_IDS
            )
        self.assertEqual(stale_data.exception.status_code, 401)
        with self.assertRaises(HTTPException) as non_admin:
            verify_telegram_init_data(
                signed_init_data(user_id=99), BOT_TOKEN, ADMIN_IDS
            )
        self.assertEqual(non_admin.exception.status_code, 403)


class MiniAppApiTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.bot = FakeBot()
        config = Config(
            bot_token=BOT_TOKEN,
            admin_ids=ADMIN_IDS,
            database_url="postgresql://unused:unused@localhost/unused",
        )
        self.client_context = TestClient(
            create_app(config, database=self.database, bot=self.bot)
        )
        self.client = self.client_context.__enter__()
        self.headers = {"X-Telegram-Init-Data": signed_init_data()}

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def test_api_requires_signed_telegram_admin_data(self):
        self.assertEqual(self.client.get("/api/courses").status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/courses",
                headers={"X-Telegram-Init-Data": signed_init_data(user_id=99)},
            ).status_code,
            403,
        )

    def test_admin_can_load_courses_and_publish_approved_lesson(self):
        courses = self.client.get("/api/courses", headers=self.headers)
        self.assertEqual(courses.status_code, 200)
        self.assertEqual(courses.json()[0]["title"], "Networking")

        published = self.client.post(
            "/api/lessons/4/publish", headers=self.headers
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["message_ids"], [501])
        self.assertEqual(len(self.bot.messages), 1)
        self.assertEqual(self.bot.messages[0][2], "HTML")
        self.assertEqual(
            self.database.finish_calls,
            [(4, 8, [501], None)],
        )

    def test_public_lesson_can_be_retrieved_without_auth(self):
        res = self.client.get("/api/public/lessons/4")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["title"], "Ports")
        self.assertIn("words", data)
        self.assertIn("reading_minutes", data)

    def test_public_lessons_list_can_be_retrieved_without_auth(self):
        res = self.client.get("/api/public/lessons")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Ports")

    def test_approval_uses_source_material_when_lesson_content_is_blank(self):
        response = self.client.post(
            "/api/lessons/4/approve", headers=self.headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self.database.approved_lesson["content"],
            "Original lesson material.",
        )

    def test_approval_rejects_lesson_without_source_or_content(self):
        self.database.lesson["source_content"] = ""

        response = self.client.post(
            "/api/lessons/4/approve", headers=self.headers
        )

        self.assertEqual(response.status_code, 422)
        self.assertIsNone(self.database.approved_lesson)

    def test_admin_can_search_existing_text_notes(self):
        response = self.client.get(
            "/api/notes?query=address", headers=self.headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [note["title"] for note in response.json()],
            ["IP addressing"],
        )
        self.assertEqual(
            self.client.get("/api/notes").status_code,
            401,
        )

    def test_import_copies_note_as_source_and_editable_draft(self):
        response = self.client.post(
            "/api/courses/1/notes/12/import", headers=self.headers
        )

        self.assertEqual(response.status_code, 201)
        lesson = response.json()
        self.assertEqual(lesson["source_note_id"], 12)
        self.assertEqual(lesson["title"], "IP addressing")
        self.assertEqual(
            lesson["source_content"],
            "An IP address identifies a device on a network.",
        )
        self.assertEqual(lesson["content"], lesson["source_content"])
        self.assertEqual(lesson["status"], "draft")

        duplicate = self.client.post(
            "/api/courses/1/notes/12/import", headers=self.headers
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_import_rejects_file_notes_and_missing_notes(self):
        unsupported = self.client.post(
            "/api/courses/1/notes/13/import", headers=self.headers
        )
        missing = self.client.post(
            "/api/courses/1/notes/999/import", headers=self.headers
        )

        self.assertEqual(unsupported.status_code, 422)
        self.assertEqual(missing.status_code, 404)

    def test_admin_can_update_and_archive_course_without_deleting_it(self):
        updated = self.client.put(
            "/api/courses/1",
            headers=self.headers,
            json={"title": "Computer Networking", "description": "Core concepts"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "Computer Networking")

        archived = self.client.patch(
            "/api/courses/1/archive",
            headers=self.headers,
            json={"is_archived": True},
        )
        self.assertEqual(archived.status_code, 200)
        self.assertTrue(archived.json()["is_archived"])
        self.assertEqual(
            self.client.get("/api/courses", headers=self.headers).json(),
            [],
        )
        self.assertEqual(
            len(
                self.client.get(
                    "/api/courses?include_archived=true",
                    headers=self.headers,
                ).json()
            ),
            1,
        )

        restored = self.client.patch(
            "/api/courses/1/archive",
            headers=self.headers,
            json={"is_archived": False},
        )
        self.assertEqual(restored.status_code, 200)
        self.assertFalse(restored.json()["is_archived"])

    def test_admin_can_search_lessons_in_selected_course(self):
        response = self.client.get(
            "/api/courses/1/lessons?query=ip", headers=self.headers
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [lesson["title"] for lesson in response.json()],
            ["IP routing"],
        )

    def test_dashboard_returns_real_summary_to_authenticated_admin(self):
        response = self.client.get("/api/dashboard", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        summary = response.json()
        self.assertEqual(summary["course_count"], 1)
        self.assertEqual(summary["lesson_count"], 2)
        self.assertEqual(summary["draft_count"], 1)
        self.assertEqual(summary["published_count"], 1)
        self.assertEqual(summary["failed_publish_count"], 1)
        self.assertEqual(summary["recent_activity"][0]["telegram_message_ids"], [501])
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)

    def test_admin_can_create_update_and_list_course_quizzes(self):
        created = self.client.post(
            "/api/courses/1/quizzes", headers=self.headers
        )
        self.assertEqual(created.status_code, 201)
        quiz_id = created.json()["id"]

        payload = {
            "title": "Networking Basics",
            "instructions": "Choose the best answer.",
            "difficulty": "easy",
            "duration_minutes": 15,
            "questions": [
                {
                    "question_type": "multiple_choice",
                    "question_text": "Which protocol assigns IP addresses?",
                    "explanation": "DHCP assigns network configuration.",
                    "difficulty": "easy",
                    "options": [
                        {"option_text": "DHCP", "is_correct": True},
                        {"option_text": "DNS", "is_correct": False},
                        {"option_text": "HTTP", "is_correct": False},
                        {"option_text": "FTP", "is_correct": False},
                    ],
                },
                {
                    "question_type": "true_false",
                    "question_text": "TCP is connection-oriented.",
                    "difficulty": "medium",
                    "options": [
                        {"option_text": "True", "is_correct": True},
                        {"option_text": "False", "is_correct": False},
                    ],
                },
            ],
        }
        updated = self.client.put(
            f"/api/quizzes/{quiz_id}", headers=self.headers, json=payload
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "Networking Basics")
        fetched = self.client.get(f"/api/quizzes/{quiz_id}", headers=self.headers)
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["duration_minutes"], 15)
        self.assertEqual(
            [question["question_type"] for question in updated.json()["questions"]],
            [
                "multiple_choice",
                "true_false",
            ],
        )
        self.assertEqual(
            updated.json()["questions"][0]["options"][0]["option_text"],
            "DHCP",
        )
        self.assertTrue(updated.json()["questions"][0]["options"][0]["is_correct"])

        # Unsupported formats must be rejected by API
        rejected = self.client.put(
            f"/api/quizzes/{quiz_id}",
            headers=self.headers,
            json={
                "title": "Bad format",
                "questions": [
                    {
                        "question_type": "matching",
                        "question_text": "Match protocols",
                        "options": [{"option_text": "A"}],
                    }
                ],
            },
        )
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(
            self.client.get(
                "/api/courses/1/quizzes", headers=self.headers
            ).json()[0]["question_count"],
            2,
        )

    def test_admin_can_delete_lesson(self):
        res = self.client.delete("/api/lessons/4", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "deleted", "id": 4})

        missing = self.client.delete("/api/lessons/4", headers=self.headers)
        self.assertEqual(missing.status_code, 404)

    def test_admin_can_delete_quiz(self):
        created = self.client.post("/api/courses/1/quizzes", headers=self.headers).json()
        quiz_id = created["id"]

        res = self.client.delete(f"/api/quizzes/{quiz_id}", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "deleted", "id": quiz_id})

        missing = self.client.delete(f"/api/quizzes/{quiz_id}", headers=self.headers)
        self.assertEqual(missing.status_code, 404)

    def test_quiz_validation_rejects_invalid_correct_answers(self):
        created = self.client.post(
            "/api/courses/1/quizzes", headers=self.headers
        )
        quiz_id = created.json()["id"]
        payload = {
            "title": "Invalid quiz",
            "questions": [
                {
                    "question_type": "multiple_choice",
                    "question_text": "Choose one.",
                    "options": [
                        {"option_text": "A", "is_correct": True},
                        {"option_text": "B", "is_correct": True},
                    ],
                }
            ],
        }
        response = self.client.put(
            f"/api/quizzes/{quiz_id}", headers=self.headers, json=payload
        )
        self.assertEqual(response.status_code, 422)

    def test_quiz_validation_rejects_malformed_matching_and_fill_blank(self):
        created = self.client.post(
            "/api/courses/1/quizzes", headers=self.headers
        )
        quiz_id = created.json()["id"]
        payload = {
            "title": "Invalid formats",
            "questions": [
                {
                    "question_type": "matching",
                    "question_text": "Match each item.",
                    "options": [
                        {"option_text": "A", "match_text": "One"},
                        {"option_text": "B"},
                    ],
                }
            ],
        }
        response = self.client.put(
            f"/api/quizzes/{quiz_id}", headers=self.headers, json=payload
        )
        self.assertEqual(response.status_code, 422)

        payload["questions"][0] = {
            "question_type": "fill_blank",
            "question_text": "The answer is Paris.",
            "options": [{"option_text": "Paris", "is_correct": True}],
        }
        response = self.client.put(
            f"/api/quizzes/{quiz_id}", headers=self.headers, json=payload
        )
        self.assertEqual(response.status_code, 422)

        payload["questions"][0]["question_type"] = "true_false"
        payload["questions"][0]["options"] = [
            {"option_text": "Yes", "is_correct": True},
            {"option_text": "No", "is_correct": False},
        ]
        response = self.client.put(
            f"/api/quizzes/{quiz_id}", headers=self.headers, json=payload
        )
        self.assertEqual(response.status_code, 422)

        payload["questions"][0]["question_type"] = "multiple_answer"
        payload["questions"][0]["options"] = [
            {"option_text": "A", "is_correct": False},
            {"option_text": "B", "is_correct": False},
        ]
        response = self.client.put(
            f"/api/quizzes/{quiz_id}", headers=self.headers, json=payload
        )
        self.assertEqual(response.status_code, 422)

        payload["duration_minutes"] = 601
        payload["questions"][0] = {
            "question_type": "true_false",
            "question_text": "The answer is true.",
            "options": [
                {"option_text": "True", "is_correct": True},
                {"option_text": "False", "is_correct": False},
            ],
        }
        response = self.client.put(
            f"/api/quizzes/{quiz_id}", headers=self.headers, json=payload
        )
        self.assertEqual(response.status_code, 422)

    def create_publishable_quiz(self):
        created = self.client.post(
            "/api/courses/1/quizzes", headers=self.headers
        )
        self.assertEqual(created.status_code, 201)
        quiz_id = created.json()["id"]
        response = self.client.put(
            f"/api/quizzes/{quiz_id}",
            headers=self.headers,
            json={
                "title": "Networking Check",
                "instructions": "Choose the best answer.",
                "duration_minutes": 15,
                "questions": [
                    {
                        "question_type": "multiple_choice",
                        "question_text": "Which protocol resolves domain names?",
                        "explanation": "DNS maps domain names to IP addresses.",
                        "options": [
                            {"option_text": "DNS", "is_correct": True},
                            {"option_text": "DHCP", "is_correct": False},
                        ],
                    },
                    {
                        "question_type": "true_false",
                        "question_text": "TCP is connection-oriented.",
                        "options": [
                            {"option_text": "True", "is_correct": True},
                            {"option_text": "False", "is_correct": False},
                        ],
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        return quiz_id

    def test_quiz_can_be_approved_and_published_as_telegram_polls(self):
        quiz_id = self.create_publishable_quiz()
        approved = self.client.post(
            f"/api/quizzes/{quiz_id}/approve", headers=self.headers
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["version_number"], 1)

        published = self.client.post(
            f"/api/quizzes/{quiz_id}/publish", headers=self.headers
        )
        self.assertEqual(published.status_code, 200)
        self.assertEqual(published.json()["status"], "published")
        self.assertIn("Time limit: 15 minutes", self.bot.messages[0][1])
        self.assertEqual(len(self.bot.polls), 2)
        self.assertEqual(self.bot.polls[0]["type"], "quiz")
        self.assertEqual(self.bot.polls[0]["correct_option_id"], 0)
        self.assertEqual(self.bot.polls[0]["open_period"], 600)
        self.assertEqual(self.bot.polls[1]["question"], "TCP is connection-oriented.")
        self.assertEqual(self.bot.polls[1]["open_period"], 600)
        history = self.client.get(
            f"/api/quizzes/{quiz_id}/versions", headers=self.headers
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()[0]["status"], "published")
        self.assertEqual(history.json()[0]["telegram_message_ids"], [501, 601, 602])

    def test_single_question_quiz_without_separate_instructions_skips_intro(self):
        created = self.client.post(
            "/api/courses/1/quizzes", headers=self.headers
        )
        quiz_id = created.json()["id"]
        # When instructions repeat the question text or are empty
        self.client.put(
            f"/api/quizzes/{quiz_id}",
            headers=self.headers,
            json={
                "title": "Quick Check",
                "instructions": "Which port does HTTPS use?",
                "duration_minutes": 1,
                "questions": [
                    {
                        "question_type": "multiple_choice",
                        "question_text": "Which port does HTTPS use?",
                        "explanation": "HTTPS runs on TCP port 443.",
                        "options": [
                            {"option_text": "443", "is_correct": True},
                            {"option_text": "80", "is_correct": False},
                        ],
                    }
                ],
            },
        )
        self.client.post(f"/api/quizzes/{quiz_id}/approve", headers=self.headers)
        published = self.client.post(f"/api/quizzes/{quiz_id}/publish", headers=self.headers)
        self.assertEqual(published.status_code, 200)
        # Sends the channel card with the Start Timed Quiz button and the poll
        self.assertEqual(len(self.bot.messages), 1)
        self.assertEqual(self.bot.polls[-1]["open_period"], 60)  # 1 min = 60 seconds
        self.assertEqual(self.bot.polls[-1]["question"], "Which port does HTTPS use?")

    def test_quiz_approval_rejects_formats_not_supported_by_telegram_polls(self):
        created = self.client.post(
            "/api/courses/1/quizzes", headers=self.headers
        )
        quiz_id = created.json()["id"]
        # Simulate an existing quiz record in the database with an unsupported legacy format
        self.database.quizzes[quiz_id]["questions"] = [
            {
                "question_type": "matching",
                "question_text": "Match each protocol with its role.",
                "options": [
                    {"option_text": "DNS", "match_text": "Name resolution", "is_correct": False},
                    {"option_text": "DHCP", "match_text": "IP address assignment", "is_correct": False},
                ],
            }
        ]
        response = self.client.post(
            f"/api/quizzes/{quiz_id}/approve", headers=self.headers
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("only multiple-choice and true/false", response.json()["detail"])

    def test_partial_quiz_delivery_is_recorded_and_not_automatically_retried(self):
        quiz_id = self.create_publishable_quiz()
        approved = self.client.post(
            f"/api/quizzes/{quiz_id}/approve", headers=self.headers
        )
        self.assertEqual(approved.status_code, 200)
        self.bot.fail_poll_number = 2

        response = self.client.post(
            f"/api/quizzes/{quiz_id}/publish", headers=self.headers
        )
        self.assertEqual(response.status_code, 502)
        history = self.client.get(
            f"/api/quizzes/{quiz_id}/versions", headers=self.headers
        ).json()
        self.assertEqual(history[0]["status"], "partial")
        self.assertEqual(history[0]["telegram_message_ids"], [501, 601])
        self.assertIn("Simulated Telegram poll failure", history[0]["error"])
        retry = self.client.post(
            f"/api/quizzes/{quiz_id}/publish", headers=self.headers
        )
        self.assertEqual(retry.status_code, 409)
        duplicate_approval = self.client.post(
            f"/api/quizzes/{quiz_id}/approve", headers=self.headers
        )
        self.assertEqual(duplicate_approval.status_code, 409)

        updated = self.client.put(
            f"/api/quizzes/{quiz_id}",
            headers=self.headers,
            json={
                "title": "Networking Check revised",
                "instructions": "Choose the best answer.",
                "questions": [
                    {
                        "question_type": "multiple_choice",
                        "question_text": "Which protocol resolves domain names?",
                        "explanation": "DNS maps domain names to IP addresses.",
                        "options": [
                            {"option_text": "DNS", "is_correct": True},
                            {"option_text": "DHCP", "is_correct": False},
                        ],
                    },
                    {
                        "question_type": "true_false",
                        "question_text": "TCP is connection-oriented.",
                        "options": [
                            {"option_text": "True", "is_correct": True},
                            {"option_text": "False", "is_correct": False},
                        ],
                    },
                ],
            },
        )
        self.assertEqual(updated.status_code, 200)
        new_version = self.client.post(
            f"/api/quizzes/{quiz_id}/approve", headers=self.headers
        )
        self.assertEqual(new_version.status_code, 200)
        self.assertEqual(new_version.json()["version_number"], 2)

    def test_true_false_quiz_validation(self):
        created = self.client.post("/api/courses/1/quizzes", headers=self.headers)
        quiz_id = created.json()["id"]

        # Valid True/False question
        valid_payload = {
            "title": "TF Quiz",
            "questions": [
                {
                    "question_type": "true_false",
                    "question_text": "Python is dynamically typed.",
                    "options": [
                        {"option_text": "True", "is_correct": True},
                        {"option_text": "False", "is_correct": False},
                    ],
                }
            ],
        }
        res = self.client.put(f"/api/quizzes/{quiz_id}", headers=self.headers, json=valid_payload)
        self.assertEqual(res.status_code, 200)

        # Rejects if 0 options correct
        no_correct = {
            "title": "TF Quiz",
            "questions": [
                {
                    "question_type": "true_false",
                    "question_text": "Python is dynamically typed.",
                    "options": [
                        {"option_text": "True", "is_correct": False},
                        {"option_text": "False", "is_correct": False},
                    ],
                }
            ],
        }
        res = self.client.put(f"/api/quizzes/{quiz_id}", headers=self.headers, json=no_correct)
        self.assertEqual(res.status_code, 422)

        # Rejects if both correct
        both_correct = {
            "title": "TF Quiz",
            "questions": [
                {
                    "question_type": "true_false",
                    "question_text": "Python is dynamically typed.",
                    "options": [
                        {"option_text": "True", "is_correct": True},
                        {"option_text": "False", "is_correct": True},
                    ],
                }
            ],
        }
        res = self.client.put(f"/api/quizzes/{quiz_id}", headers=self.headers, json=both_correct)
        self.assertEqual(res.status_code, 422)

        # Rejects if options are not True and False
        wrong_labels = {
            "title": "TF Quiz",
            "questions": [
                {
                    "question_type": "true_false",
                    "question_text": "Python is dynamically typed.",
                    "options": [
                        {"option_text": "Yes", "is_correct": True},
                        {"option_text": "No", "is_correct": False},
                    ],
                }
            ],
        }
        res = self.client.put(f"/api/quizzes/{quiz_id}", headers=self.headers, json=wrong_labels)
        self.assertEqual(res.status_code, 422)

    def test_multiple_choice_quiz_validation(self):
        created = self.client.post("/api/courses/1/quizzes", headers=self.headers)
        quiz_id = created.json()["id"]

        # Valid Multiple Choice with 4 options
        valid_mc = {
            "title": "MC Quiz",
            "questions": [
                {
                    "question_type": "multiple_choice",
                    "question_text": "What is 2+2?",
                    "options": [
                        {"option_text": "3", "is_correct": False},
                        {"option_text": "4", "is_correct": True},
                        {"option_text": "5", "is_correct": False},
                        {"option_text": "6", "is_correct": False},
                    ],
                }
            ],
        }
        res = self.client.put(f"/api/quizzes/{quiz_id}", headers=self.headers, json=valid_mc)
        self.assertEqual(res.status_code, 200)

        # Rejects if no answer selected
        no_correct_mc = {
            "title": "MC Quiz",
            "questions": [
                {
                    "question_type": "multiple_choice",
                    "question_text": "What is 2+2?",
                    "options": [
                        {"option_text": "3", "is_correct": False},
                        {"option_text": "4", "is_correct": False},
                        {"option_text": "5", "is_correct": False},
                        {"option_text": "6", "is_correct": False},
                    ],
                }
            ],
        }
        res = self.client.put(f"/api/quizzes/{quiz_id}", headers=self.headers, json=no_correct_mc)
        self.assertEqual(res.status_code, 422)

        # Rejects if blank option
        blank_opt = {
            "title": "MC Quiz",
            "questions": [
                {
                    "question_type": "multiple_choice",
                    "question_text": "What is 2+2?",
                    "options": [
                        {"option_text": "", "is_correct": False},
                        {"option_text": "4", "is_correct": True},
                    ],
                }
            ],
        }
        res = self.client.put(f"/api/quizzes/{quiz_id}", headers=self.headers, json=blank_opt)
        self.assertEqual(res.status_code, 422)

    def test_user_explicit_correct_answer_published_to_telegram(self):
        created = self.client.post("/api/courses/1/quizzes", headers=self.headers)
        quiz_id = created.json()["id"]

        # User explicitly chooses choice C (index 2) for MC, and False (index 1) for TF
        payload = {
            "title": "Explicit Selection Quiz",
            "instructions": "Answer the polls.",
            "questions": [
                {
                    "question_type": "multiple_choice",
                    "question_text": "Which port is HTTPS?",
                    "options": [
                        {"option_text": "21", "is_correct": False},
                        {"option_text": "80", "is_correct": False},
                        {"option_text": "443", "is_correct": True},
                        {"option_text": "8080", "is_correct": False},
                    ],
                },
                {
                    "question_type": "true_false",
                    "question_text": "UDP guarantees packet delivery.",
                    "options": [
                        {"option_text": "True", "is_correct": False},
                        {"option_text": "False", "is_correct": True},
                    ],
                },
            ],
        }
        res = self.client.put(f"/api/quizzes/{quiz_id}", headers=self.headers, json=payload)
        self.assertEqual(res.status_code, 200)

        approved = self.client.post(f"/api/quizzes/{quiz_id}/approve", headers=self.headers)
        self.assertEqual(approved.status_code, 200)

        published = self.client.post(f"/api/quizzes/{quiz_id}/publish", headers=self.headers)
        self.assertEqual(published.status_code, 200)

        # Verify polls published to Telegram
        mc_poll = self.bot.polls[-2]
        tf_poll = self.bot.polls[-1]

        # MC poll must have 4 options and correct_option_id=2 (port 443)
        self.assertEqual(mc_poll["type"], "quiz")
        self.assertEqual(mc_poll["options"], ["21", "80", "443", "8080"])
        self.assertEqual(mc_poll["correct_option_id"], 2)

        # TF poll must have True, False and correct_option_id=1 (False)
        self.assertEqual(tf_poll["type"], "quiz")
        self.assertEqual(tf_poll["options"], ["True", "False"])
        self.assertEqual(tf_poll["correct_option_id"], 1)

    def test_quiz_approval_and_publish_require_admin_authentication(self):
        self.assertEqual(self.client.post("/api/quizzes/1/approve").status_code, 401)
        self.assertEqual(self.client.post("/api/quizzes/1/publish").status_code, 401)

    def test_quiz_endpoints_require_admin_authentication(self):
        self.assertEqual(
            self.client.post("/api/courses/1/quizzes").status_code,
            401,
        )
        self.assertEqual(
            self.client.get("/api/courses/1/quizzes").status_code,
            401,
        )
        self.assertEqual(self.client.get("/api/quizzes/1").status_code, 401)

    def test_get_and_update_settings(self):
        # 1. Fetch current settings
        res = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["channel_id"], "-10012345")
        self.assertEqual(data["delivery_mode"], "card")
        self.assertTrue(data["require_approval"])

        # 2. Update settings
        update_payload = {
            "channel_id": "-10099999",
            "channel_title": "Updated Channel",
            "delivery_mode": "full_text",
            "branding_signature": "Custom Academy",
            "quiz_anonymous": False,
            "quiz_default_duration": 15,
            "quiz_pass_percentage": 85,
        }
        res2 = self.client.put("/api/settings", headers=self.headers, json=update_payload)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["status"], "saved")

        # 3. Verify updated settings
        res3 = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(res3.status_code, 200)
        data3 = res3.json()
        self.assertEqual(data3["channel_id"], "-10099999")
        self.assertEqual(data3["channel_title"], "Updated Channel")
        self.assertEqual(data3["delivery_mode"], "full_text")
        self.assertEqual(data3["branding_signature"], "Custom Academy")
        self.assertFalse(data3["quiz_anonymous"])
        self.assertEqual(data3["quiz_default_duration"], 15)
        self.assertEqual(data3["quiz_pass_percentage"], 85)

        # 4. Verify audit event was logged
        audit_res = self.client.get("/api/audit", headers=self.headers)
        self.assertEqual(audit_res.status_code, 200)
        logs = audit_res.json()
        self.assertTrue(any(log["action"] == "update_settings" for log in logs))

    def test_verify_channel(self):
        # Valid channel
        res = self.client.post(
            "/api/settings/verify-channel",
            headers=self.headers,
            json={"channel": "@cyberlearn_channel"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["id"], "-10012345")
        self.assertTrue(data["is_admin"])

        # Invalid channel
        res_bad = self.client.post(
            "/api/settings/verify-channel",
            headers=self.headers,
            json={"channel": "@invalid_channel_xyz"},
        )
        self.assertEqual(res_bad.status_code, 400)

    def test_ai_settings_update_and_test_endpoint(self):
        # 1. Update AI settings to Grok
        update_payload = {
            "ai_provider": "grok",
            "ai_provider_api_key": "xai-test-key-12345",
            "ai_provider_model": "grok-2-latest",
        }
        res = self.client.put("/api/settings", headers=self.headers, json=update_payload)
        self.assertEqual(res.status_code, 200)

        # 2. Verify settings return Grok configuration
        get_res = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertEqual(data["ai_provider"], "grok")
        self.assertEqual(data["ai_provider_model"], "grok-2-latest")
        self.assertTrue(data["ai_provider_has_key"])

        # 3. Test missing API key returns 422
        res_missing = self.client.post(
            "/api/settings/test-ai",
            headers=self.headers,
            json={"ai_provider_api_key": ""},
        )
        self.assertEqual(res_missing.status_code, 422)

        # 4. Test test-ai endpoint with mock httpx
        with unittest.mock.patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = unittest.mock.AsyncMock()
            mock_response = unittest.mock.MagicMock()
            mock_response.raise_for_status = unittest.mock.MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "AI connection verified successfully!"}}]
            }
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            res_test = self.client.post(
                "/api/settings/test-ai",
                headers=self.headers,
                json={
                    "ai_provider": "grok",
                    "ai_provider_api_key": "xai-test-key-12345",
                    "ai_provider_model": "grok-2-latest",
                },
            )
            self.assertEqual(res_test.status_code, 200)
            test_data = res_test.json()
            self.assertTrue(test_data["ok"])
            self.assertEqual(test_data["provider"], "grok")
            self.assertIn("verified", test_data["reply"])

        # 5. Test Groq configuration and test-ai endpoint
        groq_payload = {
            "ai_provider": "groq",
            "ai_provider_api_key": "gsk_test_key_12345",
            "ai_provider_model": "openai/gpt-oss-120b",
        }
        res_groq = self.client.put("/api/settings", headers=self.headers, json=groq_payload)
        self.assertEqual(res_groq.status_code, 200)

        get_groq = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(get_groq.status_code, 200)
        groq_data = get_groq.json()
        self.assertEqual(groq_data["ai_provider"], "groq")
        self.assertEqual(groq_data["ai_provider_model"], "openai/gpt-oss-120b")
        self.assertEqual(groq_data["ai_provider_url"], "https://api.groq.com/openai/v1/chat/completions")

        with unittest.mock.patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = unittest.mock.AsyncMock()
            mock_response = unittest.mock.MagicMock()
            mock_response.raise_for_status = unittest.mock.MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "Groq AI connection verified successfully!"}}]
            }
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            res_groq_test = self.client.post(
                "/api/settings/test-ai",
                headers=self.headers,
                json={
                    "ai_provider": "groq",
                    "ai_provider_api_key": "gsk_test_key_12345",
                    "ai_provider_model": "openai/gpt-oss-120b",
                },
            )
            self.assertEqual(res_groq_test.status_code, 200)
            self.assertTrue(res_groq_test.json()["ok"])
            self.assertEqual(res_groq_test.json()["provider"], "groq")

        # 6. Test fetch-models endpoint
        with unittest.mock.patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = unittest.mock.AsyncMock()
            mock_response = unittest.mock.MagicMock()
            mock_response.raise_for_status = unittest.mock.MagicMock()
            mock_response.json.return_value = {
                "data": [
                    {"id": "llama-3.1-8b-instant", "active": True},
                    {"id": "llama-3.1-70b-versatile", "active": True},
                    {"id": "whisper-large-v3", "active": True},
                ]
            }
            mock_client.get.return_value = mock_response
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            res_models = self.client.post(
                "/api/settings/fetch-models",
                headers=self.headers,
                json={
                    "ai_provider": "groq",
                    "ai_provider_api_key": "gsk_test_key_12345",
                },
            )
            self.assertEqual(res_models.status_code, 200)
            data_models = res_models.json()
            self.assertTrue(data_models["ok"])
            self.assertIn("llama-3.1-8b-instant", data_models["models"])
            self.assertIn("llama-3.1-70b-versatile", data_models["models"])
            self.assertNotIn("whisper-large-v3", data_models["models"])

    def test_dual_provider_keys_switching_without_repasting(self):
        # 1. Save both Groq and Gemini keys independently
        payload = {
            "ai_provider": "groq",
            "groq_api_key": "gsk_groq_saved_key_abc123",
            "groq_model": "openai/gpt-oss-120b",
            "gemini_api_key": "AQ.gemini_saved_key_xyz789",
            "gemini_model": "gemini-3.8-flash",
        }
        res = self.client.put("/api/settings", headers=self.headers, json=payload)
        self.assertEqual(res.status_code, 200)

        # 2. Verify settings return both keys preserved and Groq as active
        res_get = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(res_get.status_code, 200)
        data = res_get.json()
        self.assertEqual(data["ai_provider"], "groq")
        self.assertEqual(data["ai_provider_api_key"], "gsk_groq_saved_key_abc123")
        self.assertEqual(data["groq_api_key"], "gsk_groq_saved_key_abc123")
        self.assertEqual(data["gemini_api_key"], "AQ.gemini_saved_key_xyz789")
        self.assertTrue(data["groq_has_key"])
        self.assertTrue(data["gemini_has_key"])

        # 3. Switch active provider to Gemini with zero key entered
        switch_res = self.client.put("/api/settings", headers=self.headers, json={"ai_provider": "gemini"})
        self.assertEqual(switch_res.status_code, 200)

        # 4. Verify Gemini is now active and its saved key is automatically activated
        res_get2 = self.client.get("/api/settings", headers=self.headers)
        self.assertEqual(res_get2.status_code, 200)
        data2 = res_get2.json()
        self.assertEqual(data2["ai_provider"], "gemini")
        self.assertEqual(data2["ai_provider_api_key"], "AQ.gemini_saved_key_xyz789")
        self.assertEqual(data2["ai_provider_model"], "gemini-3.8-flash")
        # Groq key is still safely stored!
        self.assertEqual(data2["groq_api_key"], "gsk_groq_saved_key_abc123")

        # 5. Switch back to Groq with zero key entered
        switch_back = self.client.put("/api/settings", headers=self.headers, json={"ai_provider": "groq"})
        self.assertEqual(switch_back.status_code, 200)

        res_get3 = self.client.get("/api/settings", headers=self.headers)
        data3 = res_get3.json()
        self.assertEqual(data3["ai_provider"], "groq")
        self.assertEqual(data3["ai_provider_api_key"], "gsk_groq_saved_key_abc123")
        self.assertEqual(data3["gemini_api_key"], "AQ.gemini_saved_key_xyz789")


    def test_upload_and_fetch_lesson_image(self) -> None:
        import base64

        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        b64 = base64.b64encode(png_bytes).decode("ascii")
        res = self.client.post(
            "/api/images",
            json={
                "lesson_id": 4,
                "file_name": "diagram.png",
                "mime_type": "image/png",
                "data_base64": f"data:image/png;base64,{b64}",
            },
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 201)
        payload = res.json()
        self.assertEqual(payload["url"], "/api/images/1")

        # Public GET works without admin header
        get_res = self.client.get("/api/images/1")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.content, png_bytes)

    def test_browser_admin_token_auth(self) -> None:
        from notes_bot.web import create_browser_admin_token

        admin_id = next(iter(ADMIN_IDS))
        token = create_browser_admin_token(
            BOT_TOKEN, admin_id, "Abay", "abay_admin"
        )
        res = self.client.get("/api/me", headers={"X-Admin-Token": token})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["id"], admin_id)

        # Non-admin user ID is rejected even if validly signed
        bad_token = create_browser_admin_token(BOT_TOKEN, 999, "Student", "stu")
        bad_res = self.client.get("/api/me", headers={"X-Admin-Token": bad_token})
        self.assertEqual(bad_res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
