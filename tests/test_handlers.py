import unittest
from xml.etree import ElementTree

from notes_bot.handlers import (
    MAX_CHANNEL_MESSAGE_LENGTH,
    _telegram_text_length,
    format_channel_lesson,
    format_note_content,
    is_supported_document,
    parse_file_caption,
    parse_text_note,
)


class ParseFileCaptionTests(unittest.TestCase):
    def test_parses_subject_and_title(self):
        self.assertEqual(
            parse_file_caption("  Biology  |  Cell structure "),
            ("Biology", "Cell structure"),
        )

    def test_rejects_missing_or_empty_fields(self):
        for caption in (None, "", "Biology", "Biology | ", " | Cell structure"):
            with self.subTest(caption=caption):
                self.assertIsNone(parse_file_caption(caption))

    def test_rejects_oversized_fields(self):
        self.assertIsNone(parse_file_caption("B" * 61 + " | Cells"))
        self.assertIsNone(parse_file_caption("Biology | " + "C" * 101))


class ParseTextNoteTests(unittest.TestCase):
    def test_keeps_delimiters_in_note_body(self):
        self.assertEqual(
            parse_text_note("Biology | Cells | Membranes | transport"),
            ("Biology", "Cells", "Membranes | transport"),
        )

    def test_rejects_missing_fields_and_oversized_subject_or_title(self):
        self.assertIsNone(parse_text_note("Biology | Cells"))
        self.assertIsNone(parse_text_note("Biology | Cells | "))
        self.assertIsNone(parse_text_note("B" * 61 + " | Cells | Content"))
        self.assertIsNone(parse_text_note("Biology | " + "C" * 101 + " | Content"))

    def test_accepts_note_content_longer_than_3900_characters(self):
        content = "x" * 12_000
        self.assertEqual(
            parse_text_note(f"Biology | Cells | {content}"),
            ("Biology", "Cells", content),
        )


    def test_preserves_multiline_content(self):
        self.assertEqual(
            parse_text_note("Physics | Kinematics | v = u + at\ns = ut + 0.5at^2"),
            ("Physics", "Kinematics", "v = u + at\ns = ut + 0.5at^2"),
        )


class SupportedDocumentTests(unittest.TestCase):
    def test_accepts_supported_extensions_and_mime_types(self):
        examples = (
            ("application/pdf", "notes.pdf"),
            ("application/msword", "notes.doc"),
            (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "notes.docx",
            ),
            ("application/vnd.ms-powerpoint", "slides.ppt"),
            (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "slides.pptx",
            ),
            ("application/octet-stream", "notes.pdf"),
        )
        for mime_type, file_name in examples:
            with self.subTest(file_name=file_name):
                self.assertTrue(is_supported_document(mime_type, file_name))

    def test_rejects_unsupported_or_mismatched_documents(self):
        self.assertFalse(is_supported_document("text/plain", "notes.txt"))
        self.assertFalse(is_supported_document("application/msword", "notes.pdf"))


class ChannelLessonFormattingTests(unittest.TestCase):
    def test_formats_sections_and_examples_without_dropping_content(self):
        content = (
            "## Main idea\n"
            "Cells control transport.\n\n"
            "Definition: A membrane surrounds the cell.\n"
            "Example: Water moves through the membrane.\n"
            "> Remember this point.\n"
            "- Selective transport\n"
            "```python\n"
            "print('cell')\n"
            "```"
        )

        self.assertEqual(
            format_note_content(content),
            [
                ("heading", "Main idea"),
                ("paragraph", "Cells control transport."),
                ("spacer", ""),
                ("callout", "Definition: A membrane surrounds the cell."),
                ("callout", "Example: Water moves through the membrane."),
                ("quote", "Remember this point."),
                ("bullet", "Selective transport"),
                ("code", "print('cell')"),
            ],
        )

    def test_formats_mobile_friendly_html_and_escapes_source_text(self):
        lesson = format_channel_lesson(
            "Networking",
            "Ports & protocols",
            "## Definition\nA **port** identifies a service. See https://example.com/a?x=1&y=2.\n"
            "```bash\nnc -vz example.com 443\n```",
        )
        rendered = "\n".join(lesson)

        for part in lesson:
            ElementTree.fromstring(f"<root>{part}</root>")
        self.assertIn("🌐 <b>Networking</b>", rendered)
        self.assertIn("🎯 <b>Ports &amp; protocols</b>", rendered)
        self.assertIn("<b>📖 01 | Definition</b>", rendered)
        self.assertIn("<b>port</b>", rendered)
        self.assertIn("https://example.com/a?x=1&amp;y=2", rendered)
        self.assertIn("<pre>nc -vz example.com 443</pre>", rendered)
        self.assertIn("🧠 <b>QUICK CHECK</b>", rendered)
        self.assertIn("What real-world example can you connect", rendered)
        self.assertIn("💬 <b>Your turn:</b>", rendered)

    def test_splits_long_lessons_into_valid_size_messages_and_keeps_all_content(self):
        content = "\n\n".join(
            f"## Section {index}\n" + ("Networking & routing facts. " * 35)
            for index in range(1, 6)
        )

        messages = format_channel_lesson("Networking", "Routing", content)

        self.assertGreater(len(messages), 1)
        self.assertTrue(
            all(len(message) <= MAX_CHANNEL_MESSAGE_LENGTH for message in messages)
        )
        self.assertIn("CONTINUED", messages[1])
        self.assertIn("Section 5", messages[-1])
        self.assertIn("💬 <b>Your turn:</b>", messages[-1])
        self.assertEqual(sum(message.count("<pre>") for message in messages), 0)

    def test_splits_escaped_content_without_losing_special_characters(self):
        content = ("<tag> & value " * 250)
        messages = format_channel_lesson("Programming", "Escaping", content)
        self.assertGreater(len(messages), 1)
        self.assertTrue(
            all(len(message) <= MAX_CHANNEL_MESSAGE_LENGTH for message in messages)
        )
        self.assertIn("&lt;tag&gt; &amp; value", "\n".join(messages))

    def test_splits_by_telegram_utf16_length_for_emoji(self):
        messages = format_channel_lesson("General", "Emoji length", "🧠" * 3900)

        self.assertGreater(len(messages), 1)
        self.assertTrue(
            all(
                max(len(message), _telegram_text_length(message))
                <= MAX_CHANNEL_MESSAGE_LENGTH
                for message in messages
            )
        )


class QuizBotInteractiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_with_quiz_deep_link_prompts_ready(self):
        from unittest.mock import AsyncMock, MagicMock
        from notes_bot.handlers import start

        update = MagicMock()
        update.effective_user.id = 101
        update.effective_user.full_name = "Alice"
        message = AsyncMock()
        update.effective_message = message

        context = MagicMock()
        context.args = ["quiz_42"]
        context.application.bot_data = {"admin_ids": frozenset()}

        quiz_data = {
            "id": 42,
            "title": "Linux Permissions",
            "instructions": "Answer carefully",
            "duration_minutes": 1,
            "questions": [
                {
                    "question_text": "What does chown do?",
                    "options": [{"option_text": "Change owner", "is_correct": True}],
                }
            ],
        }

        with unittest.mock.patch("notes_bot.handlers._db_call", new=AsyncMock(side_effect=[None, quiz_data, None, None])):
            await start(update, context)

        message.reply_text.assert_called_once()
        sent_text = message.reply_text.call_args[0][0]
        self.assertIn("Linux Permissions", sent_text)
        self.assertIn("Time limit:</b> 1 minute", sent_text)
        markup = message.reply_text.call_args[1]["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "quiz_start:42:0")

    async def test_start_with_completed_quiz_blocks_retake(self):
        from unittest.mock import AsyncMock, MagicMock
        from datetime import datetime, timezone
        from notes_bot.handlers import start

        update = MagicMock()
        update.effective_user.id = 101
        update.effective_user.full_name = "Alice"
        message = AsyncMock()
        update.effective_message = message

        context = MagicMock()
        context.args = ["quiz_42"]
        context.application.bot_data = {"admin_ids": frozenset()}

        quiz_data = {
            "id": 42,
            "title": "Linux Permissions",
            "instructions": "",
            "duration_minutes": 1,
            "questions": [{"question_text": "Q1", "options": []}],
        }
        submission = {
            "score": 1,
            "total_questions": 1,
            "completed_at": datetime(2026, 11, 8, 10, 30, tzinfo=timezone.utc),
        }

        with unittest.mock.patch("notes_bot.handlers._db_call", new=AsyncMock(side_effect=[None, quiz_data, submission])):
            await start(update, context)

        message.reply_text.assert_called_once()
        sent_text = message.reply_text.call_args[0][0]
        self.assertIn("already completed this quiz", sent_text)
        self.assertIn("1 / 1 (100%)", sent_text)
        self.assertIn("Only one attempt is permitted", sent_text)

    async def test_poll_answer_records_submission_and_updates_channel(self):
        from unittest.mock import AsyncMock, MagicMock
        from notes_bot.handlers import on_poll_answer

        update = MagicMock()
        answer = MagicMock()
        answer.poll_id = "poll_999"
        answer.option_ids = [0]
        update.poll_answer = answer

        context = MagicMock()
        context.bot = AsyncMock()
        context.application.bot_data = {
            "active_quiz_polls": {
                "poll_999": {
                    "quiz_id": 42,
                    "user_id": 101,
                    "user_name": "Alice",
                    "question_index": 0,
                    "correct_option_id": 0,
                    "total_questions": 1,
                }
            },
            "quiz_sessions": {},
        }

        db_calls = []
        async def mock_db(ctx, method, *args):
            db_calls.append((method, args))
            if method == "get_quiz_channel_card":
                return {
                    "title": "Linux Permissions",
                    "duration_minutes": 1,
                    "channel_id": "@testchannel",
                    "telegram_message_ids": [777],
                }
            if method == "get_quiz_stats":
                return {
                    "total_participants": 5,
                    "avg_percentage": 100,
                    "top_scorers": [{"user_name": "Alice", "pct": 100, "score": 1, "total_questions": 1}],
                }
            return None

        with unittest.mock.patch("notes_bot.handlers._db_call", side_effect=mock_db):
            await on_poll_answer(update, context)

        # Verified db recording
        record_call = next(call for call in db_calls if call[0] == "record_quiz_submission")
        self.assertEqual(record_call[1][0], 42)  # quiz_id
        self.assertEqual(record_call[1][1], 101) # user_id
        self.assertEqual(record_call[1][3], 1)   # score = 1

        # Verified channel card edit
        context.bot.edit_message_text.assert_called_once()
        channel_text = context.bot.edit_message_text.call_args[1]["text"]
        self.assertIn("5 students completed", channel_text)
        self.assertIn("Average Score:</b> 100%", channel_text)

    async def test_quiz_start_button_sends_non_anonymous_poll(self):
        from unittest.mock import AsyncMock, MagicMock
        from notes_bot.handlers import on_button

        query = AsyncMock()
        query.data = "quiz_start:42:0"
        query.from_user.id = 101
        query.from_user.full_name = "Alice"

        update = MagicMock()
        update.callback_query = query

        context = MagicMock()
        context.bot = AsyncMock()
        mock_poll_msg = MagicMock()
        mock_poll_msg.poll.id = "poll_999"
        context.bot.send_poll.return_value = mock_poll_msg
        context.application.bot_data = {}

        quiz_data = {
            "id": 42,
            "title": "Linux Permissions",
            "duration_minutes": 1,
            "questions": [
                {
                    "question_text": "What does chown do?",
                    "options": [{"option_text": "Change owner", "is_correct": True}],
                }
            ],
        }

        db_calls = []
        async def mock_db(ctx, method, *args):
            db_calls.append((method, args))
            if method == "get_quiz_submission":
                return None
            if method == "get_user_active_poll":
                return None
            if method == "miniapp_get_quiz":
                return quiz_data
            return None

        with unittest.mock.patch("notes_bot.handlers._db_call", side_effect=mock_db):
            await on_button(update, context)

        context.bot.send_poll.assert_called_once()
        poll_kwargs = context.bot.send_poll.call_args[1]
        self.assertFalse(poll_kwargs["is_anonymous"])
        self.assertEqual(poll_kwargs["open_period"], 60)
        self.assertEqual(poll_kwargs["chat_id"], 101)


if __name__ == "__main__":
    unittest.main()
