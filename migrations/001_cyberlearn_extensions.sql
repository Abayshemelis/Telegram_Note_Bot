-- CyberLearn Studio schema extensions (additive only)
-- These tables extend the existing schema from schema.sql without modifying it.

-- Course categories for organizing courses
CREATE TABLE IF NOT EXISTS course_categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 60),
    description TEXT NOT NULL DEFAULT '',
    color TEXT NOT NULL DEFAULT '#4f46e5',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Modules within courses for organizing lessons
CREATE TABLE IF NOT EXISTS course_modules (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES miniapp_courses(id) ON DELETE CASCADE,
    title TEXT NOT NULL CHECK (char_length(title) BETWEEN 1 AND 120),
    description TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_course_modules_course_position
    ON course_modules (course_id, position);

-- Add position column to lessons for reordering support
ALTER TABLE miniapp_lessons
    ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_miniapp_lessons_course_position
    ON miniapp_lessons (course_id, position);

-- Lesson attachments (files linked to lessons)
CREATE TABLE IF NOT EXISTS lesson_attachments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_id BIGINT NOT NULL REFERENCES miniapp_lessons(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL CHECK (char_length(file_name) BETWEEN 1 AND 255),
    mime_type TEXT NOT NULL,
    file_size BIGINT NOT NULL DEFAULT 0,
    telegram_file_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_lesson_attachments_lesson_id
    ON lesson_attachments (lesson_id);

-- AI-generated content drafts (stored separately from human content)
CREATE TABLE IF NOT EXISTS ai_generations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_id BIGINT REFERENCES miniapp_lessons(id) ON DELETE SET NULL,
    quiz_id BIGINT REFERENCES miniapp_quizzes(id) ON DELETE SET NULL,
    source_text TEXT NOT NULL,
    generated_content TEXT NOT NULL,
    generation_type TEXT NOT NULL CHECK (generation_type IN (
        'structure_lesson', 'improve_content', 'generate_examples',
        'create_summary', 'extract_terms', 'generate_learning_objectives',
        'generate_quiz_suggestions'
    )),
    provider TEXT NOT NULL DEFAULT 'unknown',
    accepted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    accepted_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_ai_generations_lesson_id
    ON ai_generations (lesson_id);
CREATE INDEX IF NOT EXISTS idx_ai_generations_quiz_id
    ON ai_generations (quiz_id);

-- Scheduled publications
CREATE TABLE IF NOT EXISTS scheduled_publications (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lesson_id BIGINT NOT NULL REFERENCES miniapp_lessons(id) ON DELETE CASCADE,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'publishing', 'published', 'failed', 'cancelled')),
    channel_id TEXT NOT NULL,
    telegram_message_ids BIGINT[] NOT NULL DEFAULT '{}',
    error TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_scheduled_publications_status_scheduled_at
    ON scheduled_publications (status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_publications_lesson_id
    ON scheduled_publications (lesson_id);

-- Audit log for administrative actions
CREATE TABLE IF NOT EXISTS audit_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id BIGINT NOT NULL,
    action TEXT NOT NULL CHECK (char_length(action) BETWEEN 1 AND 100),
    target_type TEXT NOT NULL CHECK (char_length(target_type) BETWEEN 1 AND 50),
    target_id BIGINT,
    before_value JSONB,
    after_value JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_events_actor_id
    ON audit_events (actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_target
    ON audit_events (target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_created_at
    ON audit_events (created_at DESC);

-- Question bank for reusable quiz questions across courses
CREATE TABLE IF NOT EXISTS question_bank (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    course_id BIGINT NOT NULL REFERENCES miniapp_courses(id) ON DELETE CASCADE,
    question_type TEXT NOT NULL CHECK (question_type IN (
        'multiple_choice', 'true_false', 'multiple_answer',
        'matching', 'short_answer', 'fill_blank', 'ordering'
    )),
    question_text TEXT NOT NULL CHECK (char_length(question_text) BETWEEN 1 AND 1000),
    explanation TEXT NOT NULL DEFAULT '',
    difficulty TEXT NOT NULL DEFAULT 'medium'
        CHECK (difficulty IN ('easy', 'medium', 'hard')),
    created_by BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_question_bank_course_id
    ON question_bank (course_id);

CREATE TABLE IF NOT EXISTS question_bank_options (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    question_id BIGINT NOT NULL REFERENCES question_bank(id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position >= 0),
    option_text TEXT NOT NULL CHECK (char_length(option_text) BETWEEN 1 AND 500),
    match_text TEXT,
    is_correct BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (question_id, position)
);

CREATE INDEX IF NOT EXISTS idx_question_bank_options_question_id
    ON question_bank_options (question_id);

-- Quiz submissions to enforce 1 attempt per student and track scores
CREATE TABLE IF NOT EXISTS miniapp_quiz_submissions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quiz_id BIGINT NOT NULL REFERENCES miniapp_quizzes(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 1,
    answers JSONB NOT NULL DEFAULT '[]',
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (quiz_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_quiz_submissions_quiz_user
    ON miniapp_quiz_submissions (quiz_id, user_id);

-- Active quiz polls tracking
CREATE TABLE IF NOT EXISTS active_quiz_polls (
    poll_id TEXT PRIMARY KEY,
    quiz_id BIGINT NOT NULL REFERENCES miniapp_quizzes(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    user_name TEXT NOT NULL DEFAULT '',
    question_index INTEGER NOT NULL DEFAULT 0,
    correct_option_id INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_active_quiz_polls_quiz_user
    ON active_quiz_polls (quiz_id, user_id);

