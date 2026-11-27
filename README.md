# Telegram Notes Bot

A Python Telegram bot for a teacher to share study notes with students. It uses
Telegram's stored `file_id` values for documents and photos, and PostgreSQL for
users, subjects, and notes.

## Features

- `/start` registers or updates a student.
- `/subjects` browses subjects and paginated note lists.
- `/search <word>` searches note titles.
- `/delete_me` deletes the user's registration data.
- Admin-only `/addsubject`, `/deletesubject`, `/addnote`, `/deletenote`, file upload, and `/announce` commands.
- Text notes are published as compact Telegram HTML lessons with a subject/topic header, recognizable headings, definition/example callouts, lists, quotes, and code blocks. Formatting preserves the supplied technical content and does not invent course facts. Long lessons are split into Telegram-safe messages; a discussion prompt appears at the end. Uploaded PDFs, Word documents, PowerPoint presentations, and photos are published in their original format.
- CyberLearn Studio Mini App provides an admin dashboard with persisted course/lesson and delivery counts, recent publishing activity, course and lesson management, separate source and editable content, Telegram preview, explicit version approval, channel publishing, and delivery history. AI drafting is not enabled.
- The Mini App can search and import existing text notes from the bot database into a selected course. Importing copies the note unchanged as source material and an editable lesson draft; the original bot note remains unchanged.
- The Mini App includes a quiz builder for multiple-choice, true/false, multiple-answer, matching, short-answer, fill-in-the-blank, and ordering questions, with difficulty, optional time limits, explanations, ordering, and an admin answer-key preview. Multiple-choice and true/false quiz versions can be previewed, approved, and published as Telegram interactive quiz polls; other formats remain draft-only because Telegram quiz polls do not support them.
- Students receive an alert when a note is added.
- Database access uses parameterized SQL and a bounded connection pool.
- Tokens and database credentials are read from `.env`, which is ignored by Git.

Admin authorization is based only on numeric Telegram user IDs in `ADMIN_IDS`.
The database role is not used as an authorization check.

## Requirements

- Python 3.11 or newer
- PostgreSQL 15 or newer, reachable from the machine running the bot
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your numeric Telegram user ID

## Setup

1. Create a PostgreSQL database and a dedicated, non-superuser account for the
   bot. Keep PostgreSQL off the public internet.
2. Create and activate a virtual environment:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```sh
   python -m pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env`, then set the real values:

   ```dotenv
   BOT_TOKEN=your_token_from_BotFather
   ADMIN_IDS=your_numeric_telegram_id
   DATABASE_URL=postgresql://botuser:password@localhost:5432/notesbot
   ```

   For a remote PostgreSQL provider, use the provider's SSL-enabled connection
   URL. URL-encode special characters in the database username or password.
   Never paste real tokens or passwords into source control or chat.

5. Start the bot:

   ```sh
   python -m notes_bot.main
   ```

6. To connect a channel, add the bot as an administrator with permission to
   post messages, then send `/setchannel @your_channel` (or its numeric channel
   ID for a private channel) to the bot as an admin. You can also forward a
   channel post to the bot or use `/channel` to check the saved connection.
   Bot-created text notes are published there as formatted Telegram posts;
   uploaded documents and photos keep their original format.

The database schema is applied at startup. The first run requires the database
to exist and the configured database user to have permission to create tables
and indexes in it.

## CyberLearn Studio Mini App

The Mini App uses the existing bot token, admin allowlist, PostgreSQL database,
channel setting, and Telegram lesson formatter. Start the bot and the web
backend as two separate processes.

1. Build the Mini App frontend:

   ```sh
   cd miniapp
   npm install
   npm run build
   cd ..
   ```

2. Set `MINI_APP_URL` in `.env` to the public **HTTPS** URL that serves this app.
   The backend listens on `127.0.0.1:8000`; place a TLS-terminating reverse
   proxy in front of it and proxy requests to that local address. Keep the bot
   token and database URL on the server; never add them to frontend code.
3. Run the existing bot in one terminal:

   ```sh
   source .venv/bin/activate
   python -m notes_bot.main
   ```

4. Run the Mini App API in another terminal:

   ```sh
   source .venv/bin/activate
   python -m notes_bot.web
   ```

5. Open the bot in Telegram using an administrator account. Use the
   **CyberLearn Studio** chat menu button. The backend verifies Telegram's signed
   Mini App `initData` and checks `ADMIN_IDS` on every API request. A normal
   browser or unsigned request cannot authenticate.
6. Create or select a course. Edit its title and description, or archive it to
   hide it from active courses; archived courses can be restored. Search lessons
   in the selected course by title or content. Unsaved lesson edits trigger a
   confirmation before leaving the lesson or navigating away.
7. Use **Import bot note** to find an existing text note, or create a lesson
   manually. Imported notes are copied into source material and the editable
   publishing draft; the bot note itself is not modified. Preview the lesson,
   approve the exact version, and publish it. The bot must already have posting
   permission in the channel linked with `/setchannel`. Documents and photos
   are not importable as lesson text.
8. Select **Quizzes** to create and edit knowledge checks for the selected
   course. Choose a format before adding each question: multiple-choice,
   true/false, multiple-answer, matching pairs, short answer, fill in the blank,
   or ordering. Mark the correct answers or pairs, optionally add explanations
   and a time limit, reorder questions/items, and preview the answer key before
   saving. Approve a saved multiple-choice/true-false version, then publish it
   to the linked channel as one interactive Telegram poll per question.
   Matching, short-answer, fill-in-the-blank, ordering, and multiple-answer
   formats cannot be approved for this poll-based delivery and remain
   draft-only. A configured time limit is announced as a suggested completion
   time because Telegram does not enforce one timer across multiple polls.
   Version and delivery history record sent message IDs and partial failures;
   partial sends are not automatically retried. Edit the quiz and approve a
   changed version to publish again after a partial delivery.

The first startup applies the additive Mini App tables from `schema.sql`.
Publishing is restricted to the channel already stored by the bot; the app
does not accept an arbitrary channel destination. If a multi-part Telegram send
fails part-way through, delivery history records the partial result so it is
visible before a new version is retried.

## Use

Students use `/start`, then `/subjects` or `/search <word>`. They can remove
their registration data with `/delete_me`; using `/start` registers them again.

The configured admin uses:

- `/addsubject Biology`
- `/deletesubject Biology`
- `/addnote Biology | Cell structure | The cell membrane controls transport.`
- `/deletenote 1`
- Upload a document or photo with caption `Biology | Cell structure`
- `/announce The next class starts at 10:00.`

Subjects and titles are limited to 60 and 100 characters. Text notes have no
application-level length limit; Telegram limits each incoming message, while
published lessons are split into Telegram-sized messages. File uploads accept PDF, Word (`.doc`/`.docx`), and PowerPoint
(`.ppt`/`.pptx`) documents, as well as images. Uploaded documents and images
are published to the linked channel in their original format; text notes are
formatted as Telegram HTML posts.
Announcement and file-alert delivery is sequential and reports failed
recipients instead of stopping the whole operation.

## Tests

```sh
python -m unittest discover -s tests -v
```

The bot starts with long polling, which is suitable for local development and
small deployments. For production, run it as a dedicated non-root service,
keep `.env` readable only by that service account, enable automatic restarts,
and set up regular PostgreSQL backups. Do not expose PostgreSQL's port to the
internet.
