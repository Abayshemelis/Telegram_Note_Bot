CREATE TABLE IF NOT EXISTS users (
    telegram_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'admin')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS subjects (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 60)
);

CREATE TABLE IF NOT EXISTS notes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_id BIGINT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 100),
    kind TEXT NOT NULL CHECK (kind IN ('text', 'document', 'photo')),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_notes_subject_id_id
    ON notes (subject_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_notes_title_lower
    ON notes (lower(title));

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS miniapp_courses (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
    description TEXT NOT NULL DEFAULT '',
    created_by BIGINT NOT NULL,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS miniapp_lessons (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES miniapp_courses(id) ON DELETE CASCADE,
    source_note_id BIGINT UNIQUE REFERENCES notes(id) ON DELETE SET NULL,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160),
    source_content TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'approved', 'publishing', 'published', 'failed')),
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE miniapp_lessons
    ADD COLUMN IF NOT EXISTS source_note_id BIGINT UNIQUE
    REFERENCES notes(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_miniapp_lessons_course_updated
    ON miniapp_lessons (course_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS miniapp_lesson_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_id BIGINT NOT NULL REFERENCES miniapp_lessons(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    source_content TEXT NOT NULL,
    content TEXT NOT NULL,
    approved_by BIGINT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lesson_id, version_number)
);

CREATE TABLE IF NOT EXISTS miniapp_publish_jobs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id BIGINT NOT NULL UNIQUE
        REFERENCES miniapp_lesson_versions(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'publishing', 'published', 'failed', 'partial')),
    telegram_message_ids BIGINT[] NOT NULL DEFAULT '{}',
    error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS miniapp_quizzes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES miniapp_courses(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160),
    instructions TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT 'medium'
        CHECK (difficulty IN ('easy', 'medium', 'hard')),
    duration_minutes INTEGER CHECK (duration_minutes BETWEEN 1 AND 600),
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_miniapp_quizzes_course_updated
    ON miniapp_quizzes (course_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS miniapp_quiz_questions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_id BIGINT NOT NULL REFERENCES miniapp_quizzes(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    question_type TEXT NOT NULL
        CONSTRAINT miniapp_quiz_question_type_check
        CHECK (question_type IN (
            'multiple_choice', 'true_false', 'multiple_answer',
            'matching', 'short_answer', 'fill_blank', 'ordering'
        )),
    question_text TEXT NOT NULL CHECK (char_length(question_text) BETWEEN 1 AND 1000),
    explanation TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT 'medium'
        CHECK (difficulty IN ('easy', 'medium', 'hard')),
    UNIQUE (quiz_id, position)
);

CREATE TABLE IF NOT EXISTS miniapp_quiz_options (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES miniapp_quiz_questions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    option_text TEXT NOT NULL CHECK (char_length(option_text) BETWEEN 1 AND 500),
    is_correct BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (question_id, position)
);

ALTER TABLE miniapp_quiz_questions
    DROP CONSTRAINT IF EXISTS miniapp_quiz_questions_question_type_check;
ALTER TABLE miniapp_quiz_questions
    DROP CONSTRAINT IF EXISTS miniapp_quiz_question_type_check;
ALTER TABLE miniapp_quiz_questions
    ADD CONSTRAINT miniapp_quiz_question_type_check
    CHECK (question_type IN (
        'multiple_choice', 'true_false', 'multiple_answer',
        'matching', 'short_answer', 'fill_blank', 'ordering'
    ));

ALTER TABLE miniapp_quiz_options
    ADD COLUMN IF NOT EXISTS match_text TEXT;

CREATE TABLE IF NOT EXISTS miniapp_quiz_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_id BIGINT NOT NULL REFERENCES miniapp_quizzes(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL CHECK (version_number > 0),
    snapshot JSONB NOT NULL,
    approved_by BIGINT NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'approved'
        CHECK (status IN ('approved', 'publishing', 'published', 'failed', 'partial')),
    channel_id TEXT,
    telegram_message_ids BIGINT[] NOT NULL DEFAULT '{}',
    error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (quiz_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_miniapp_quiz_versions_quiz
    ON miniapp_quiz_versions (quiz_id, version_number DESC);
