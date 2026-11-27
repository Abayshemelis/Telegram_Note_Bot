from __future__ import annotations

from pathlib import Path
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from notes_bot.formatter import standardize_academic_markdown, standardize_title


SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schema.sql"
SCHEMA_EXTENSIONS_PATH = (
    Path(__file__).resolve().parent.parent / "migrations" / "001_cyberlearn_extensions.sql"
)


class Database:
    def __init__(self, database_url: str) -> None:
        self._pool = ConnectionPool(
            conninfo=database_url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            open=False,
        )

    def open(self) -> None:
        self._pool.open(wait=True)
        with self._pool.connection() as connection:
            connection.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
            if SCHEMA_EXTENSIONS_PATH.is_file():
                connection.execute(SCHEMA_EXTENSIONS_PATH.read_text(encoding="utf-8"))

    def close(self) -> None:
        self._pool.close()

    def add_user(self, telegram_id: int, name: str, is_admin: bool) -> None:
        role = "admin" if is_admin else "student"
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO users (telegram_id, name, role)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id) DO UPDATE
                SET name = EXCLUDED.name, role = EXCLUDED.role, is_active = TRUE
                """,
                (telegram_id, name, role),
            )

    def delete_user(self, telegram_id: int) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                "DELETE FROM users WHERE telegram_id = %s",
                (telegram_id,),
            )

    def get_subjects(self) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                "SELECT id, name FROM subjects ORDER BY name"
            ).fetchall()

    def add_subject(self, name: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO subjects (name)
                VALUES (%s)
                ON CONFLICT (name) DO NOTHING
                RETURNING id
                """,
                (name,),
            ).fetchone()
            return row is not None

    def get_notes(
        self, subject_id: int, limit: int = 5, offset: int = 0
    ) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT id, subject_id, title, kind, created_at
                FROM notes
                WHERE subject_id = %s
                ORDER BY id DESC
                LIMIT %s OFFSET %s
                """,
                (subject_id, limit, offset),
            ).fetchall()

    def get_note(self, note_id: int) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                "SELECT id, title, kind, content FROM notes WHERE id = %s",
                (note_id,),
            ).fetchone()

    def add_note(self, subject_id: int, title: str, kind: str, content: str) -> int:
        if kind == "text" and content:
            title = standardize_title(title, content)
            content = standardize_academic_markdown(content, title)
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO notes (subject_id, title, kind, content)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (subject_id, title, kind, content),
            ).fetchone()
            return row["id"]

    def search_notes(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT id, subject_id, title, kind
                FROM notes
                WHERE title ILIKE %s ESCAPE '\\'
                ORDER BY id DESC
                LIMIT %s
                """,
                (f"%{escaped_query}%", limit),
            ).fetchall()

    def get_student_ids(self) -> list[int]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT telegram_id
                FROM users
                WHERE is_active = TRUE AND role = 'student'
                ORDER BY telegram_id
                """
            ).fetchall()
            return [row["telegram_id"] for row in rows]

    def delete_note(self, note_id: int) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "DELETE FROM notes WHERE id = %s RETURNING id",
                (note_id,),
            ).fetchone()
            return row is not None

    def delete_subject(self, name: str) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "DELETE FROM subjects WHERE name = %s RETURNING id",
                (name,),
            ).fetchone()
            return row is not None

    def get_setting(self, key: str) -> str | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = %s",
                (key,),
            ).fetchone()
            return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value
                """,
                (key, value),
            )

    def get_all_settings(self) -> dict[str, str]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT key, value FROM settings"
            ).fetchall()
            return {row["key"]: row["value"] for row in rows}

    def set_settings(self, settings_dict: dict[str, str]) -> None:
        with self._pool.connection() as connection:
            for key, value in settings_dict.items():
                connection.execute(
                    """
                    INSERT INTO settings (key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value
                    """,
                    (key, str(value)),
                )

    def miniapp_list_courses(
        self, include_archived: bool = False
    ) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT c.id, c.title, c.description, c.is_archived,
                       c.created_at, c.updated_at,
                       COUNT(l.id)::INTEGER AS lesson_count
                FROM miniapp_courses AS c
                LEFT JOIN miniapp_lessons AS l ON l.course_id = c.id
                WHERE %s OR c.is_archived = FALSE
                GROUP BY c.id
                ORDER BY c.updated_at DESC, c.id DESC
                """,
                (include_archived,),
            ).fetchall()

    def miniapp_dashboard_summary(self) -> dict[str, Any]:
        with self._pool.connection() as connection:
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*)
                     FROM miniapp_courses
                     WHERE is_archived = FALSE) AS course_count,
                    (SELECT COUNT(*)
                     FROM miniapp_quizzes AS q
                     JOIN miniapp_courses AS qc ON qc.id = q.course_id
                     WHERE qc.is_archived = FALSE) AS quiz_count,
                    COUNT(l.id) AS lesson_count,
                    COUNT(l.id) FILTER (WHERE l.status = 'draft') AS draft_count,
                    COUNT(l.id) FILTER (WHERE l.status = 'approved') AS ready_count,
                    COUNT(l.id) FILTER (WHERE l.status = 'published') AS published_count,
                    (SELECT COUNT(*)
                     FROM miniapp_publish_jobs
                     WHERE status IN ('failed', 'partial')) AS failed_publish_count
                FROM miniapp_lessons AS l
                JOIN miniapp_courses AS c ON c.id = l.course_id
                WHERE c.is_archived = FALSE
                """
            ).fetchone()
            recent_activity = connection.execute(
                """
                SELECT j.id AS job_id, l.id AS lesson_id, l.title AS lesson_title,
                       c.id AS course_id, c.title AS course_title, j.channel_id,
                       j.status, j.attempt_count, j.telegram_message_ids, j.error,
                       j.updated_at
                FROM miniapp_publish_jobs AS j
                JOIN miniapp_lesson_versions AS v ON v.id = j.version_id
                JOIN miniapp_lessons AS l ON l.id = v.lesson_id
                JOIN miniapp_courses AS c ON c.id = l.course_id
                ORDER BY j.updated_at DESC, j.id DESC
                LIMIT 8
                """
            ).fetchall()
            return {**counts, "recent_activity": recent_activity}

    def miniapp_list_quizzes(self, course_id: int) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT q.id, q.course_id, q.title, q.difficulty,
                       q.duration_minutes, q.updated_at,
                       COUNT(qq.id)::INTEGER AS question_count,
                       latest.version_number,
                       latest.status AS version_status
                FROM miniapp_quizzes AS q
                LEFT JOIN miniapp_quiz_questions AS qq ON qq.quiz_id = q.id
                LEFT JOIN LATERAL (
                    SELECT version_number, status
                    FROM miniapp_quiz_versions
                    WHERE quiz_id = q.id
                    ORDER BY version_number DESC
                    LIMIT 1
                ) AS latest ON TRUE
                WHERE q.course_id = %s
                GROUP BY q.id, latest.version_number, latest.status
                ORDER BY q.updated_at DESC, q.id DESC
                """,
                (course_id,),
            ).fetchall()

    def list_available_quizzes(self) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT q.id, q.title, q.difficulty, q.duration_minutes,
                       c.title AS course_title,
                       COUNT(qq.id)::INTEGER AS question_count
                FROM miniapp_quizzes AS q
                JOIN miniapp_courses AS c ON c.id = q.course_id
                JOIN miniapp_quiz_questions AS qq ON qq.quiz_id = q.id
                WHERE c.is_archived = FALSE
                GROUP BY q.id, c.title
                HAVING COUNT(qq.id) > 0
                ORDER BY q.updated_at DESC, q.id DESC
                LIMIT 50
                """
            ).fetchall()

    def get_quiz_submission(self, quiz_id: int, user_id: int) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT id, quiz_id, user_id, user_name, score, total_questions,
                       answers, completed_at
                FROM miniapp_quiz_submissions
                WHERE quiz_id = %s AND user_id = %s
                """,
                (quiz_id, user_id),
            ).fetchone()

    def record_quiz_submission(
        self,
        quiz_id: int,
        user_id: int,
        user_name: str,
        score: int,
        total_questions: int,
        answers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                INSERT INTO miniapp_quiz_submissions
                    (quiz_id, user_id, user_name, score, total_questions, answers, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (quiz_id, user_id) DO UPDATE
                SET score = EXCLUDED.score,
                    total_questions = EXCLUDED.total_questions,
                    answers = EXCLUDED.answers,
                    completed_at = now()
                RETURNING id, quiz_id, user_id, user_name, score, total_questions,
                          answers, completed_at
                """,
                (quiz_id, user_id, (user_name or "")[:255], score, total_questions, Jsonb(answers)),
            ).fetchone()

    def get_quiz_stats(self, quiz_id: int) -> dict[str, Any]:
        with self._pool.connection() as connection:
            summary = connection.execute(
                """
                SELECT COUNT(id)::INTEGER AS total_participants,
                       COALESCE(ROUND(AVG(score::NUMERIC / NULLIF(total_questions, 0) * 100)), 0)::INTEGER AS avg_percentage
                FROM miniapp_quiz_submissions
                WHERE quiz_id = %s
                """,
                (quiz_id,),
            ).fetchone() or {"total_participants": 0, "avg_percentage": 0}
            top = connection.execute(
                """
                SELECT user_name, score, total_questions,
                       ROUND(score::NUMERIC / NULLIF(total_questions, 0) * 100)::INTEGER AS pct
                FROM miniapp_quiz_submissions
                WHERE quiz_id = %s
                ORDER BY score DESC, completed_at ASC
                LIMIT 3
                """,
                (quiz_id,),
            ).fetchall()
            return {
                "total_participants": summary["total_participants"],
                "avg_percentage": summary["avg_percentage"],
                "top_scorers": top,
            }

    def get_quiz_channel_card(self, quiz_id: int) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT q.id, q.title, q.instructions, q.duration_minutes,
                       v.channel_id, v.telegram_message_ids
                FROM miniapp_quizzes AS q
                JOIN miniapp_quiz_versions AS v ON v.quiz_id = q.id
                WHERE q.id = %s AND v.status = 'published' AND array_length(v.telegram_message_ids, 1) > 0
                ORDER BY v.version_number DESC
                LIMIT 1
                """,
                (quiz_id,),
            ).fetchone()

    def register_active_poll(
        self,
        poll_id: str,
        quiz_id: int,
        user_id: int,
        user_name: str,
        question_index: int,
        correct_option_id: int,
        total_questions: int,
    ) -> dict[str, Any]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                INSERT INTO active_quiz_polls
                    (poll_id, quiz_id, user_id, user_name, question_index, correct_option_id, total_questions, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (poll_id) DO UPDATE
                SET question_index = EXCLUDED.question_index,
                    correct_option_id = EXCLUDED.correct_option_id,
                    total_questions = EXCLUDED.total_questions,
                    created_at = now()
                RETURNING poll_id, quiz_id, user_id, user_name, question_index, correct_option_id, total_questions, created_at
                """,
                (poll_id, quiz_id, user_id, (user_name or "")[:255], question_index, correct_option_id, total_questions),
            ).fetchone()

    def pop_active_poll(self, poll_id: str) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                DELETE FROM active_quiz_polls
                WHERE poll_id = %s
                RETURNING poll_id, quiz_id, user_id, user_name, question_index, correct_option_id, total_questions, created_at
                """,
                (poll_id,),
            ).fetchone()

    def get_user_active_poll(self, quiz_id: int, user_id: int) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT poll_id, quiz_id, user_id, user_name, question_index, correct_option_id, total_questions, created_at
                FROM active_quiz_polls
                WHERE quiz_id = %s AND user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (quiz_id, user_id),
            ).fetchone()

    def clear_user_active_polls(self, quiz_id: int, user_id: int) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                """
                DELETE FROM active_quiz_polls
                WHERE quiz_id = %s AND user_id = %s
                """,
                (quiz_id, user_id),
            )


    def miniapp_create_quiz(
        self, course_id: int, title: str, admin_id: int
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            course = connection.execute(
                "SELECT id FROM miniapp_courses WHERE id = %s AND is_archived = FALSE",
                (course_id,),
            ).fetchone()
            if course is None:
                return None
            return connection.execute(
                """
                INSERT INTO miniapp_quizzes (course_id, title, created_by)
                VALUES (%s, %s, %s)
                RETURNING id, course_id, title, instructions, difficulty,
                          duration_minutes, created_at, updated_at
                """,
                (course_id, title, admin_id),
            ).fetchone()

    def miniapp_get_quiz(self, quiz_id: int) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            quiz = connection.execute(
                """
                SELECT q.id, q.course_id, c.title AS course_title, q.title,
                       q.instructions, q.difficulty, q.duration_minutes,
                       q.created_at, q.updated_at
                FROM miniapp_quizzes AS q
                JOIN miniapp_courses AS c ON c.id = q.course_id
                WHERE q.id = %s
                """,
                (quiz_id,),
            ).fetchone()
            if quiz is None:
                return None

            questions = connection.execute(
                """
                SELECT id, question_type, question_text, explanation,
                       difficulty, position
                FROM miniapp_quiz_questions
                WHERE quiz_id = %s
                ORDER BY position
                """,
                (quiz_id,),
            ).fetchall()
            for question in questions:
                question["options"] = connection.execute(
                    """
                    SELECT option_text, match_text, is_correct, position
                    FROM miniapp_quiz_options
                    WHERE question_id = %s
                    ORDER BY position
                    """,
                    (question["id"],),
                ).fetchall()
                question.pop("id")
            quiz["questions"] = questions
            latest = connection.execute(
                """
                SELECT id, version_number, snapshot, approved_by, approved_at,
                       status, channel_id, telegram_message_ids, error,
                       attempt_count, updated_at
                FROM miniapp_quiz_versions
                WHERE quiz_id = %s
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (quiz_id,),
            ).fetchone()
            quiz["latest_version"] = latest
            return quiz

    def miniapp_save_quiz(
        self, quiz_id: int, quiz_data: dict[str, Any]
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            quiz = connection.execute(
                """
                UPDATE miniapp_quizzes
                SET title = %s, instructions = %s, difficulty = %s,
                    duration_minutes = %s, updated_at = now()
                WHERE id = %s
                RETURNING id
                """,
                (
                    quiz_data["title"],
                    quiz_data["instructions"],
                    quiz_data["difficulty"],
                    quiz_data["duration_minutes"],
                    quiz_id,
                ),
            ).fetchone()
            if quiz is None:
                return None

            connection.execute(
                "DELETE FROM miniapp_quiz_questions WHERE quiz_id = %s",
                (quiz_id,),
            )
            for position, question in enumerate(quiz_data["questions"]):
                question_row = connection.execute(
                    """
                    INSERT INTO miniapp_quiz_questions
                        (quiz_id, position, question_type, question_text,
                         explanation, difficulty)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        quiz_id,
                        position,
                        question["question_type"],
                        question["question_text"],
                        question["explanation"],
                        question["difficulty"],
                    ),
                ).fetchone()
                for option_position, option in enumerate(question["options"]):
                    connection.execute(
                        """
                        INSERT INTO miniapp_quiz_options
                            (question_id, position, option_text, match_text, is_correct)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            question_row["id"],
                            option_position,
                            option["option_text"],
                            option["match_text"],
                            option["is_correct"],
                        ),
                    )

        return self.miniapp_get_quiz(quiz_id)

    def miniapp_delete_quiz(self, quiz_id: int) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "DELETE FROM miniapp_quizzes WHERE id = %s RETURNING id",
                (quiz_id,),
            ).fetchone()
            return row is not None

    def miniapp_approve_quiz(
        self, quiz_id: int, admin_id: int
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            quiz = connection.execute(
                """
                SELECT id, course_id, title, instructions, difficulty, duration_minutes
                FROM miniapp_quizzes
                WHERE id = %s
                FOR UPDATE
                """,
                (quiz_id,),
            ).fetchone()
            if quiz is None:
                return None

            latest = connection.execute(
                """
                SELECT status, snapshot
                FROM miniapp_quiz_versions
                WHERE quiz_id = %s
                ORDER BY version_number DESC
                LIMIT 1
                """,
                (quiz_id,),
            ).fetchone()
            if latest and latest["status"] == "publishing":
                return None

            questions = connection.execute(
                """
                SELECT id, question_type, question_text, explanation,
                       difficulty, position
                FROM miniapp_quiz_questions
                WHERE quiz_id = %s
                ORDER BY position
                """,
                (quiz_id,),
            ).fetchall()
            for question in questions:
                question["options"] = connection.execute(
                    """
                    SELECT option_text, match_text, is_correct
                    FROM miniapp_quiz_options
                    WHERE question_id = %s
                    ORDER BY position
                    """,
                    (question.pop("id"),),
                ).fetchall()

            snapshot = {**quiz, "questions": questions}
            if latest and latest["status"] in {"approved", "partial"}:
                if latest["snapshot"] == snapshot:
                    return None
            version_row = connection.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version
                FROM miniapp_quiz_versions
                WHERE quiz_id = %s
                """,
                (quiz_id,),
            ).fetchone()
            return connection.execute(
                """
                INSERT INTO miniapp_quiz_versions
                    (quiz_id, version_number, snapshot, approved_by)
                VALUES (%s, %s, %s, %s)
                RETURNING id, version_number, snapshot, approved_by, approved_at,
                          status, channel_id, telegram_message_ids, error,
                          attempt_count, updated_at
                """,
                (
                    quiz_id,
                    version_row["next_version"],
                    Jsonb(snapshot),
                    admin_id,
                ),
            ).fetchone()

    def miniapp_list_quiz_versions(self, quiz_id: int) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT id, version_number, approved_by, approved_at, status,
                       channel_id, telegram_message_ids, error, attempt_count,
                       updated_at
                FROM miniapp_quiz_versions
                WHERE quiz_id = %s
                ORDER BY version_number DESC
                """,
                (quiz_id,),
            ).fetchall()

    def miniapp_claim_quiz_publish(
        self, quiz_id: int, channel_id: str
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            version = connection.execute(
                """
                SELECT id, version_number, snapshot, status, telegram_message_ids
                FROM miniapp_quiz_versions
                WHERE quiz_id = %s
                ORDER BY version_number DESC
                LIMIT 1
                FOR UPDATE
                """,
                (quiz_id,),
            ).fetchone()
            if version is None or version["status"] not in {"approved", "failed"}:
                return None
            if version["status"] == "failed" and version["telegram_message_ids"]:
                return None
            if version["snapshot"].get("questions") is None:
                return None

            current_quiz = connection.execute(
                """
                SELECT id, course_id, title, instructions, difficulty, duration_minutes
                FROM miniapp_quizzes
                WHERE id = %s
                """,
                (quiz_id,),
            ).fetchone()
            questions = connection.execute(
                """
                SELECT id, question_type, question_text, explanation,
                       difficulty, position
                FROM miniapp_quiz_questions
                WHERE quiz_id = %s
                ORDER BY position
                """,
                (quiz_id,),
            ).fetchall()
            for question in questions:
                question["options"] = connection.execute(
                    """
                    SELECT option_text, match_text, is_correct
                    FROM miniapp_quiz_options
                    WHERE question_id = %s
                    ORDER BY position
                    """,
                    (question.pop("id"),),
                ).fetchall()
            current_snapshot = {**current_quiz, "questions": questions}
            if current_snapshot != version["snapshot"]:
                return None

            version = connection.execute(
                """
                UPDATE miniapp_quiz_versions
                SET status = 'publishing', channel_id = %s, error = NULL,
                    attempt_count = attempt_count + 1, updated_at = now()
                WHERE id = %s
                RETURNING id, version_number, snapshot
                """,
                (channel_id, version["id"]),
            ).fetchone()
            version["quiz_id"] = quiz_id
            return version

    def miniapp_finish_quiz_publish(
        self,
        version_id: int,
        message_ids: list[int],
        error: str | None = None,
    ) -> None:
        status = (
            "partial"
            if error and message_ids
            else "failed"
            if error
            else "published"
        )
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE miniapp_quiz_versions
                SET status = %s, telegram_message_ids = %s, error = %s,
                    updated_at = now()
                WHERE id = %s AND status = 'publishing'
                """,
                (status, message_ids, error, version_id),
            )

    def miniapp_create_course(
        self, title: str, description: str, admin_id: int
    ) -> dict[str, Any]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                INSERT INTO miniapp_courses (title, description, created_by)
                VALUES (%s, %s, %s)
                RETURNING id, title, description, created_at, updated_at
                """,
                (title, description, admin_id),
            ).fetchone()

    def miniapp_update_course(
        self, course_id: int, title: str, description: str
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                UPDATE miniapp_courses
                SET title = %s, description = %s, updated_at = now()
                WHERE id = %s
                RETURNING id, title, description, is_archived, created_at, updated_at
                """,
                (title, description, course_id),
            ).fetchone()

    def miniapp_set_course_archived(
        self, course_id: int, is_archived: bool
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                UPDATE miniapp_courses
                SET is_archived = %s, updated_at = now()
                WHERE id = %s
                RETURNING id, title, description, is_archived, created_at, updated_at
                """,
                (is_archived, course_id),
            ).fetchone()

    def miniapp_list_lessons(
        self, course_id: int, query: str = ""
    ) -> list[dict[str, Any]]:
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_query}%"
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT id, course_id, title, status, updated_at
                FROM miniapp_lessons
                WHERE course_id = %s
                  AND (%s = '' OR title ILIKE %s ESCAPE '\\'
                       OR source_content ILIKE %s ESCAPE '\\'
                       OR content ILIKE %s ESCAPE '\\')
                ORDER BY updated_at DESC, id DESC
                """,
                (course_id, query, pattern, pattern, pattern),
            ).fetchall()

    def miniapp_list_public_lessons(self) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT l.id, l.course_id, c.title AS course_title, l.title,
                       l.status, l.updated_at
                FROM miniapp_lessons AS l
                JOIN miniapp_courses AS c ON c.id = l.course_id
                WHERE l.status = 'published' AND c.is_archived = FALSE
                ORDER BY l.updated_at DESC, l.id DESC
                LIMIT 50
                """
            ).fetchall()

    def miniapp_create_lesson(
        self,
        course_id: int,
        title: str,
        source_content: str,
        content: str,
        admin_id: int,
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            course = connection.execute(
                "SELECT id FROM miniapp_courses WHERE id = %s AND is_archived = FALSE",
                (course_id,),
            ).fetchone()
            if course is None:
                return None
            return connection.execute(
                """
                INSERT INTO miniapp_lessons
                    (course_id, title, source_content, content, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, course_id, title, source_content, content, status,
                          created_at, updated_at
                """,
                (course_id, title, source_content, content, admin_id),
            ).fetchone()

    def miniapp_search_notes(self, query: str = "", limit: int = 30) -> list[dict[str, Any]]:
        escaped_query = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_query}%"
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT n.id, n.title, s.name AS subject_name, n.created_at,
                       EXISTS (
                           SELECT 1
                           FROM miniapp_lessons AS l
                           WHERE l.source_note_id = n.id
                       ) AS already_imported
                FROM notes AS n
                JOIN subjects AS s ON s.id = n.subject_id
                WHERE n.kind = 'text'
                  AND (%s = '' OR n.title ILIKE %s ESCAPE '\\'
                       OR n.content ILIKE %s ESCAPE '\\'
                       OR s.name ILIKE %s ESCAPE '\\')
                ORDER BY n.id DESC
                LIMIT %s
                """,
                (query, pattern, pattern, pattern, limit),
            ).fetchall()

    def miniapp_import_note(
        self, course_id: int, note_id: int, admin_id: int
    ) -> tuple[str, dict[str, Any] | None]:
        with self._pool.connection() as connection:
            course = connection.execute(
                "SELECT id FROM miniapp_courses WHERE id = %s AND is_archived = FALSE",
                (course_id,),
            ).fetchone()
            if course is None:
                return "course_not_found", None

            note = connection.execute(
                """
                SELECT n.id, n.title, n.kind, n.content
                FROM notes AS n
                WHERE n.id = %s
                """,
                (note_id,),
            ).fetchone()
            if note is None:
                return "note_not_found", None
            if note["kind"] != "text":
                return "unsupported_note_type", None
            if not note["content"].strip():
                return "empty_note", None

            clean_title = standardize_title(note["title"], note["content"])
            clean_content = standardize_academic_markdown(note["content"], clean_title)

            lesson = connection.execute(
                """
                INSERT INTO miniapp_lessons
                    (course_id, source_note_id, title, source_content, content, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_note_id) DO NOTHING
                RETURNING id, course_id, source_note_id, title, source_content,
                          content, status, created_at, updated_at
                """,
                (
                    course_id,
                    note_id,
                    clean_title,
                    clean_content,
                    clean_content,
                    admin_id,
                ),
            ).fetchone()
            if lesson is None:
                return "already_imported", None
            return "imported", lesson

    def miniapp_get_lesson(self, lesson_id: int) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT l.id, l.course_id, c.title AS course_title, l.title,
                       l.source_content, l.content, l.status, l.created_at,
                       l.updated_at
                FROM miniapp_lessons AS l
                JOIN miniapp_courses AS c ON c.id = l.course_id
                WHERE l.id = %s AND c.is_archived = FALSE
                """,
                (lesson_id,),
            ).fetchone()

    def miniapp_update_lesson(
        self, lesson_id: int, title: str, source_content: str, content: str
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                UPDATE miniapp_lessons
                SET title = %s, source_content = %s, content = %s,
                    status = 'draft', updated_at = now()
                WHERE id = %s AND status IN ('draft', 'failed', 'published')
                RETURNING id, course_id, title, source_content, content, status,
                          created_at, updated_at
                """,
                (title, source_content, content, lesson_id),
            ).fetchone()

    def miniapp_delete_lesson(self, lesson_id: int) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "DELETE FROM miniapp_lessons WHERE id = %s RETURNING id",
                (lesson_id,),
            ).fetchone()
            return row is not None

    def miniapp_approve_lesson(
        self, lesson_id: int, admin_id: int
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            lesson = connection.execute(
                """
                SELECT id, source_content, content, status
                FROM miniapp_lessons
                WHERE id = %s
                FOR UPDATE
                """,
                (lesson_id,),
            ).fetchone()
            if lesson is None or lesson["status"] not in {"draft", "failed"}:
                return None
            version_row = connection.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1 AS next_version
                FROM miniapp_lesson_versions
                WHERE lesson_id = %s
                """,
                (lesson_id,),
            ).fetchone()
            version = connection.execute(
                """
                INSERT INTO miniapp_lesson_versions
                    (lesson_id, version_number, source_content, content, approved_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, version_number, approved_at
                """,
                (
                    lesson_id,
                    version_row["next_version"],
                    lesson["source_content"],
                    lesson["content"],
                    admin_id,
                ),
            ).fetchone()
            connection.execute(
                "UPDATE miniapp_lessons SET status = 'approved', updated_at = now() WHERE id = %s",
                (lesson_id,),
            )
            return version

    def miniapp_claim_publish(
        self, lesson_id: int, channel_id: str
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            lesson = connection.execute(
                """
                SELECT l.id, l.title, c.title AS course_title,
                       v.id AS version_id, v.content
                FROM miniapp_lessons AS l
                JOIN miniapp_courses AS c ON c.id = l.course_id
                JOIN miniapp_lesson_versions AS v ON v.lesson_id = l.id
                WHERE l.id = %s AND l.status = 'approved'
                ORDER BY v.version_number DESC
                LIMIT 1
                FOR UPDATE OF l
                """,
                (lesson_id,),
            ).fetchone()
            if lesson is None:
                return None
            job = connection.execute(
                """
                INSERT INTO miniapp_publish_jobs (version_id, channel_id, status)
                VALUES (%s, %s, 'publishing')
                ON CONFLICT (version_id) DO NOTHING
                RETURNING id
                """,
                (lesson["version_id"], channel_id),
            ).fetchone()
            if job is None:
                existing = connection.execute(
                    """
                    SELECT id, status
                    FROM miniapp_publish_jobs
                    WHERE version_id = %s
                    """,
                    (lesson["version_id"],),
                ).fetchone()
                if existing["status"] != "failed":
                    return None
                job = connection.execute(
                    """
                    UPDATE miniapp_publish_jobs
                    SET channel_id = %s, status = 'publishing', error = NULL,
                        attempt_count = attempt_count + 1, updated_at = now()
                    WHERE id = %s AND status = 'failed'
                    RETURNING id
                    """,
                    (channel_id, existing["id"]),
                ).fetchone()
                if job is None:
                    return None
            else:
                connection.execute(
                    """
                    UPDATE miniapp_publish_jobs
                    SET attempt_count = attempt_count + 1, updated_at = now()
                    WHERE id = %s
                    """,
                    (job["id"],),
                )
            connection.execute(
                "UPDATE miniapp_lessons SET status = 'publishing', updated_at = now() WHERE id = %s",
                (lesson_id,),
            )
            lesson["job_id"] = job["id"]
            return lesson

    def miniapp_finish_publish(
        self,
        lesson_id: int,
        job_id: int,
        message_ids: list[int],
        error: str | None = None,
    ) -> None:
        status = (
            "partial"
            if error and message_ids
            else "failed"
            if error
            else "published"
        )
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE miniapp_publish_jobs
                SET status = %s, telegram_message_ids = %s, error = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (status, message_ids, error, job_id),
            )
            connection.execute(
                "UPDATE miniapp_lessons SET status = %s, updated_at = now() WHERE id = %s",
                ("failed" if error else "published", lesson_id),
            )

    def miniapp_list_versions(self, lesson_id: int) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT v.id, v.version_number, v.source_content, v.content,
                       v.approved_by, v.approved_at,
                       j.status AS publish_status, j.telegram_message_ids, j.error,
                       j.channel_id, j.attempt_count, j.updated_at AS published_at
                FROM miniapp_lesson_versions AS v
                LEFT JOIN miniapp_publish_jobs AS j ON j.version_id = v.id
                WHERE v.lesson_id = %s
                ORDER BY v.version_number DESC
                """,
                (lesson_id,),
            ).fetchall()

    # ------------------------------------------------------------------
    # Course categories
    # ------------------------------------------------------------------

    def miniapp_list_categories(self) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT c.id, c.name, c.description, c.color, c.created_at,
                       0::INTEGER AS course_count
                FROM course_categories AS c
                ORDER BY c.name
                """
            ).fetchall()

    def miniapp_create_category(
        self, name: str, description: str, color: str
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                INSERT INTO course_categories (name, description, color)
                VALUES (%s, %s, %s)
                RETURNING id, name, description, color, created_at
                """,
                (name, description, color),
            ).fetchone()

    def miniapp_update_category(
        self, category_id: int, name: str, description: str, color: str
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                UPDATE course_categories
                SET name = %s, description = %s, color = %s
                WHERE id = %s
                RETURNING id, name, description, color, created_at
                """,
                (name, description, color, category_id),
            ).fetchone()

    def miniapp_delete_category(self, category_id: int) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "DELETE FROM course_categories WHERE id = %s RETURNING id",
                (category_id,),
            ).fetchone()
            return row is not None

    # ------------------------------------------------------------------
    # Course modules
    # ------------------------------------------------------------------

    def miniapp_list_modules(self, course_id: int) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT m.id, m.course_id, m.title, m.description, m.position,
                       m.created_at, m.updated_at,
                       0::INTEGER AS lesson_count
                FROM course_modules AS m
                WHERE m.course_id = %s
                ORDER BY m.position, m.id
                """,
                (course_id,),
            ).fetchall()

    def miniapp_create_module(
        self, course_id: int, title: str, description: str, position: int
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            course = connection.execute(
                "SELECT id FROM miniapp_courses WHERE id = %s",
                (course_id,),
            ).fetchone()
            if course is None:
                return None
            return connection.execute(
                """
                INSERT INTO course_modules (course_id, title, description, position)
                VALUES (%s, %s, %s, %s)
                RETURNING id, course_id, title, description, position,
                          created_at, updated_at
                """,
                (course_id, title, description, position),
            ).fetchone()

    def miniapp_update_module(
        self, module_id: int, title: str, description: str, position: int
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                UPDATE course_modules
                SET title = %s, description = %s, position = %s,
                    updated_at = now()
                WHERE id = %s
                RETURNING id, course_id, title, description, position,
                          created_at, updated_at
                """,
                (title, description, position, module_id),
            ).fetchone()

    def miniapp_delete_module(self, module_id: int) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "DELETE FROM course_modules WHERE id = %s RETURNING id",
                (module_id,),
            ).fetchone()
            return row is not None

    def miniapp_reorder_modules(
        self, course_id: int, module_orders: list[tuple[int, int]]
    ) -> None:
        with self._pool.connection() as connection:
            for module_id, position in module_orders:
                connection.execute(
                    """
                    UPDATE course_modules
                    SET position = %s, updated_at = now()
                    WHERE id = %s AND course_id = %s
                    """,
                    (position, module_id, course_id),
                )

    # ------------------------------------------------------------------
    # Lesson attachments
    # ------------------------------------------------------------------

    def miniapp_list_attachments(self, lesson_id: int) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT id, lesson_id, file_name, mime_type, file_size,
                       telegram_file_id, created_at
                FROM lesson_attachments
                WHERE lesson_id = %s
                ORDER BY created_at DESC
                """,
                (lesson_id,),
            ).fetchall()

    def miniapp_create_attachment(
        self,
        lesson_id: int,
        file_name: str,
        mime_type: str,
        file_size: int,
        telegram_file_id: str,
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            lesson = connection.execute(
                "SELECT id FROM miniapp_lessons WHERE id = %s",
                (lesson_id,),
            ).fetchone()
            if lesson is None:
                return None
            return connection.execute(
                """
                INSERT INTO lesson_attachments
                    (lesson_id, file_name, mime_type, file_size, telegram_file_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, lesson_id, file_name, mime_type, file_size,
                          telegram_file_id, created_at
                """,
                (lesson_id, file_name, mime_type, file_size, telegram_file_id),
            ).fetchone()

    def miniapp_delete_attachment(self, attachment_id: int) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "DELETE FROM lesson_attachments WHERE id = %s RETURNING id",
                (attachment_id,),
            ).fetchone()
            return row is not None

    # ------------------------------------------------------------------
    # AI generations
    # ------------------------------------------------------------------

    def miniapp_create_ai_generation(
        self,
        lesson_id: int | None,
        quiz_id: int | None,
        source_text: str,
        generated_content: str,
        generation_type: str,
        provider: str,
    ) -> dict[str, Any]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                INSERT INTO ai_generations
                    (lesson_id, quiz_id, source_text, generated_content,
                     generation_type, provider)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, lesson_id, quiz_id, source_text, generated_content,
                          generation_type, provider, accepted, created_at,
                          accepted_at
                """,
                (
                    lesson_id,
                    quiz_id,
                    source_text,
                    generated_content,
                    generation_type,
                    provider,
                ),
            ).fetchone()

    def miniapp_list_ai_generations(
        self, lesson_id: int | None = None, quiz_id: int | None = None
    ) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            if lesson_id is not None:
                return connection.execute(
                    """
                    SELECT id, lesson_id, quiz_id, source_text, generated_content,
                           generation_type, provider, accepted, created_at,
                           accepted_at
                    FROM ai_generations
                    WHERE lesson_id = %s
                    ORDER BY created_at DESC
                    """,
                    (lesson_id,),
                ).fetchall()
            if quiz_id is not None:
                return connection.execute(
                    """
                    SELECT id, lesson_id, quiz_id, source_text, generated_content,
                           generation_type, provider, accepted, created_at,
                           accepted_at
                    FROM ai_generations
                    WHERE quiz_id = %s
                    ORDER BY created_at DESC
                    """,
                    (quiz_id,),
                ).fetchall()
            return connection.execute(
                """
                SELECT id, lesson_id, quiz_id, source_text, generated_content,
                       generation_type, provider, accepted, created_at,
                       accepted_at
                FROM ai_generations
                ORDER BY created_at DESC
                LIMIT 50
                """
            ).fetchall()

    def miniapp_accept_ai_generation(
        self, generation_id: int
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                UPDATE ai_generations
                SET accepted = TRUE, accepted_at = now()
                WHERE id = %s
                RETURNING id, lesson_id, quiz_id, source_text, generated_content,
                          generation_type, provider, accepted, created_at,
                          accepted_at
                """,
                (generation_id,),
            ).fetchone()

    # ------------------------------------------------------------------
    # Scheduled publications
    # ------------------------------------------------------------------

    def miniapp_list_scheduled_publications(
        self, status: str | None = None
    ) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            if status:
                return connection.execute(
                    """
                    SELECT s.id, s.lesson_id, l.title AS lesson_title,
                           c.title AS course_title, s.scheduled_at, s.status,
                           s.channel_id, s.telegram_message_ids, s.error,
                           s.attempt_count, s.created_by, s.created_at,
                           s.updated_at
                    FROM scheduled_publications AS s
                    JOIN miniapp_lessons AS l ON l.id = s.lesson_id
                    JOIN miniapp_courses AS c ON c.id = l.course_id
                    WHERE s.status = %s
                    ORDER BY s.scheduled_at
                    """,
                    (status,),
                ).fetchall()
            return connection.execute(
                """
                SELECT s.id, s.lesson_id, l.title AS lesson_title,
                       c.title AS course_title, s.scheduled_at, s.status,
                       s.channel_id, s.telegram_message_ids, s.error,
                       s.attempt_count, s.created_by, s.created_at,
                       s.updated_at
                FROM scheduled_publications AS s
                JOIN miniapp_lessons AS l ON l.id = s.lesson_id
                JOIN miniapp_courses AS c ON c.id = l.course_id
                ORDER BY s.scheduled_at
                """
            ).fetchall()

    def miniapp_due_scheduled_publications(
        self, now: str | None = None
    ) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            if now is None:
                from datetime import datetime, timezone

                now = datetime.now(timezone.utc).isoformat()
            return connection.execute(
                """
                SELECT s.id, s.lesson_id, l.title AS lesson_title,
                       c.title AS course_title, s.scheduled_at, s.status,
                       s.channel_id, s.created_by
                FROM scheduled_publications AS s
                JOIN miniapp_lessons AS l ON l.id = s.lesson_id
                JOIN miniapp_courses AS c ON c.id = l.course_id
                WHERE s.status = 'scheduled'
                  AND s.scheduled_at <= %s
                ORDER BY s.scheduled_at
                """,
                (now,),
            ).fetchall()

    def miniapp_create_scheduled_publication(
        self,
        lesson_id: int,
        scheduled_at: str,
        channel_id: str,
        created_by: int,
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            lesson = connection.execute(
                """
                SELECT l.id FROM miniapp_lessons AS l
                JOIN miniapp_courses AS c ON c.id = l.course_id
                WHERE l.id = %s AND c.is_archived = FALSE
                """,
                (lesson_id,),
            ).fetchone()
            if lesson is None:
                return None
            return connection.execute(
                """
                INSERT INTO scheduled_publications
                    (lesson_id, scheduled_at, channel_id, created_by)
                VALUES (%s, %s, %s, %s)
                RETURNING id, lesson_id, scheduled_at, status, channel_id,
                          telegram_message_ids, error, attempt_count,
                          created_by, created_at, updated_at
                """,
                (lesson_id, scheduled_at, channel_id, created_by),
            ).fetchone()

    def miniapp_update_scheduled_publication(
        self,
        publication_id: int,
        scheduled_at: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            updates = []
            params: list[Any] = []
            if scheduled_at is not None:
                updates.append("scheduled_at = %s")
                params.append(scheduled_at)
            if status is not None:
                updates.append("status = %s")
                params.append(status)
            if not updates:
                return None
            updates.append("updated_at = now()")
            params.append(publication_id)
            query = f"""
                UPDATE scheduled_publications
                SET {", ".join(updates)}
                WHERE id = %s
                RETURNING id, lesson_id, scheduled_at, status, channel_id,
                          telegram_message_ids, error, attempt_count,
                          created_by, created_at, updated_at
            """
            return connection.execute(query, params).fetchone()

    def miniapp_cancel_scheduled_publication(self, publication_id: int) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                UPDATE scheduled_publications
                SET status = 'cancelled', updated_at = now()
                WHERE id = %s AND status = 'scheduled'
                RETURNING id
                """,
                (publication_id,),
            ).fetchone()
            return row is not None

    # ------------------------------------------------------------------
    # Audit events
    # ------------------------------------------------------------------

    def miniapp_create_audit_event(
        self,
        actor_id: int,
        action: str,
        target_type: str,
        target_id: int | None = None,
        before_value: dict[str, Any] | None = None,
        after_value: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                INSERT INTO audit_events
                    (actor_id, action, target_type, target_id,
                     before_value, after_value)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, actor_id, action, target_type, target_id,
                          before_value, after_value, created_at
                """,
                (
                    actor_id,
                    action,
                    target_type,
                    target_id,
                    Jsonb(before_value) if before_value is not None else None,
                    Jsonb(after_value) if after_value is not None else None,
                ),
            ).fetchone()

    def miniapp_list_audit_events(
        self, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT id, actor_id, action, target_type, target_id,
                       before_value, after_value, created_at
                FROM audit_events
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            ).fetchall()

    # ------------------------------------------------------------------
    # Course delete with relationship checks
    # ------------------------------------------------------------------

    def miniapp_delete_course(self, course_id: int) -> str | None:
        """Delete a course if it has no lessons or modules.

        Returns None on success, or a reason string if deletion is blocked.
        """
        with self._pool.connection() as connection:
            lesson_count = connection.execute(
                "SELECT COUNT(*)::INTEGER FROM miniapp_lessons WHERE course_id = %s",
                (course_id,),
            ).fetchone()
            if lesson_count and lesson_count["count"] > 0:
                return "course_has_lessons"

            module_count = connection.execute(
                "SELECT COUNT(*)::INTEGER FROM course_modules WHERE course_id = %s",
                (course_id,),
            ).fetchone()
            if module_count and module_count["count"] > 0:
                return "course_has_modules"

            row = connection.execute(
                "DELETE FROM miniapp_courses WHERE id = %s RETURNING id",
                (course_id,),
            ).fetchone()
            return None if row else "course_not_found"

    # ------------------------------------------------------------------
    # Lesson duplication
    # ------------------------------------------------------------------

    def miniapp_duplicate_lesson(
        self, lesson_id: int, admin_id: int
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            lesson = connection.execute(
                """
                SELECT l.id, l.course_id, l.title, l.source_content, l.content,
                       l.status, l.created_at, l.updated_at
                FROM miniapp_lessons AS l
                JOIN miniapp_courses AS c ON c.id = l.course_id
                WHERE l.id = %s AND c.is_archived = FALSE
                """,
                (lesson_id,),
            ).fetchone()
            if lesson is None:
                return None
            return connection.execute(
                """
                INSERT INTO miniapp_lessons
                    (course_id, title, source_content, content, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, course_id, title, source_content, content, status,
                          created_at, updated_at
                """,
                (
                    lesson["course_id"],
                    f"{lesson['title']} (Copy)",
                    lesson["source_content"],
                    lesson["content"],
                    admin_id,
                ),
            ).fetchone()

    # ------------------------------------------------------------------
    # Lesson reordering
    # ------------------------------------------------------------------

    def miniapp_reorder_lessons(
        self, course_id: int, lesson_orders: list[tuple[int, int]]
    ) -> None:
        with self._pool.connection() as connection:
            for lesson_id, position in lesson_orders:
                connection.execute(
                    """
                    UPDATE miniapp_lessons
                    SET position = %s, updated_at = now()
                    WHERE id = %s AND course_id = %s
                    """,
                    (position, lesson_id, course_id),
                )

    # ------------------------------------------------------------------
    # Question bank (reusable quiz questions across courses)
    # ------------------------------------------------------------------

    def miniapp_list_question_bank(self, course_id: int) -> list[dict[str, Any]]:
        with self._pool.connection() as connection:
            return connection.execute(
                """
                SELECT qb.id, qb.course_id, qb.question_type, qb.question_text,
                       qb.explanation, qb.difficulty, qb.created_by, qb.created_at,
                       COUNT(qbo.id)::INTEGER AS option_count
                FROM question_bank AS qb
                LEFT JOIN question_bank_options AS qbo ON qbo.question_id = qb.id
                WHERE qb.course_id = %s
                GROUP BY qb.id
                ORDER BY qb.created_at DESC
                """,
                (course_id,),
            ).fetchall()

    def miniapp_get_question_bank_item(
        self, question_id: int
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            question = connection.execute(
                """
                SELECT id, course_id, question_type, question_text, explanation,
                       difficulty, created_by, created_at
                FROM question_bank
                WHERE id = %s
                """,
                (question_id,),
            ).fetchone()
            if question is None:
                return None
            options = connection.execute(
                """
                SELECT option_text, match_text, is_correct, position
                FROM question_bank_options
                WHERE question_id = %s
                ORDER BY position
                """,
                (question_id,),
            ).fetchall()
            question["options"] = options
            return question

    def miniapp_create_question_bank_item(
        self,
        course_id: int,
        question_type: str,
        question_text: str,
        explanation: str,
        difficulty: str,
        options: list[dict[str, Any]],
        created_by: int,
    ) -> dict[str, Any] | None:
        with self._pool.connection() as connection:
            course = connection.execute(
                "SELECT id FROM miniapp_courses WHERE id = %s",
                (course_id,),
            ).fetchone()
            if course is None:
                return None
            question = connection.execute(
                """
                INSERT INTO question_bank
                    (course_id, question_type, question_text, explanation,
                     difficulty, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, course_id, question_type, question_text,
                          explanation, difficulty, created_by, created_at
                """,
                (course_id, question_type, question_text, explanation,
                 difficulty, created_by),
            ).fetchone()
            for position, option in enumerate(options):
                connection.execute(
                    """
                    INSERT INTO question_bank_options
                        (question_id, position, option_text, match_text, is_correct)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        question["id"],
                        position,
                        option["option_text"],
                        option.get("match_text"),
                        option["is_correct"],
                    ),
                )
            return self.miniapp_get_question_bank_item(question["id"])

    def miniapp_delete_question_bank_item(self, question_id: int) -> bool:
        with self._pool.connection() as connection:
            row = connection.execute(
                "DELETE FROM question_bank WHERE id = %s RETURNING id",
                (question_id,),
            ).fetchone()
            return row is not None

    def miniapp_import_question_bank_item(
        self, question_id: int, quiz_id: int, position: int
    ) -> dict[str, Any] | None:
        """Copy a question bank item into a quiz as a new question."""
        with self._pool.connection() as connection:
            question = connection.execute(
                """
                SELECT question_type, question_text, explanation, difficulty
                FROM question_bank
                WHERE id = %s
                """,
                (question_id,),
            ).fetchone()
            if question is None:
                return None

            quiz = connection.execute(
                "SELECT id FROM miniapp_quizzes WHERE id = %s",
                (quiz_id,),
            ).fetchone()
            if quiz is None:
                return None

            question_row = connection.execute(
                """
                INSERT INTO miniapp_quiz_questions
                    (quiz_id, position, question_type, question_text,
                     explanation, difficulty)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    quiz_id,
                    position,
                    question["question_type"],
                    question["question_text"],
                    question["explanation"],
                    question["difficulty"],
                ),
            ).fetchone()

            options = connection.execute(
                """
                SELECT option_text, match_text, is_correct, position
                FROM question_bank_options
                WHERE question_id = %s
                ORDER BY position
                """,
                (question_id,),
            ).fetchall()
            for option_position, option in enumerate(options):
                connection.execute(
                    """
                    INSERT INTO miniapp_quiz_options
                        (question_id, position, option_text, match_text, is_correct)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        question_row["id"],
                        option_position,
                        option["option_text"],
                        option["match_text"],
                        option["is_correct"],
                    ),
                )
            return self.miniapp_get_quiz(quiz_id)
