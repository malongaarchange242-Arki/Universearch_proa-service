-- MIGRATION 4: Prevent duplicate question codes inside the same quiz
-- Goal:
--   1. Surface duplicate question_code values early
--   2. Enforce uniqueness at DB level for future inserts

-- Diagnostic query to run before applying the unique index:
-- SELECT
--   quiz_id,
--   LOWER(question_code) AS normalized_question_code,
--   COUNT(*) AS duplicate_count,
--   ARRAY_AGG(id ORDER BY order_index, created_at) AS question_ids
-- FROM orientation_quiz_questions
-- WHERE question_code IS NOT NULL
-- GROUP BY quiz_id, LOWER(question_code)
-- HAVING COUNT(*) > 1;

-- Enforce uniqueness per quiz on normalized codes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_orientation_quiz_questions_quiz_code_unique
ON orientation_quiz_questions (quiz_id, LOWER(question_code))
WHERE question_code IS NOT NULL;
