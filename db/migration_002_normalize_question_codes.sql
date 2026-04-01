-- ============================================
-- MIGRATION 2: Normalize question_code (Q1 → q1)
-- ============================================

-- ✅ STEP 1: Backup
CREATE TABLE IF NOT EXISTS orientation_quiz_questions_backup AS
SELECT * FROM orientation_quiz_questions;

-- ✅ STEP 2: Normalize to lowercase
UPDATE orientation_quiz_questions
SET question_code = LOWER(question_code)
WHERE question_code IS NOT NULL;

-- ✅ STEP 3: Verify no uppercase remains
SELECT COUNT(*) as uppercase_count
FROM orientation_quiz_questions
WHERE question_code ~ '[A-Z]';
-- Expected: 0

-- ✅ STEP 4: Add order_index if missing
ALTER TABLE orientation_quiz_questions
ADD COLUMN IF NOT EXISTS order_index INTEGER DEFAULT 0;

-- ✅ STEP 5: Set order_index from question_code
UPDATE orientation_quiz_questions
SET order_index = CAST(
  SUBSTRING(question_code FROM 2)::TEXT
)::INTEGER
WHERE question_code ~ '^q[0-9]+$' AND order_index = 0;

-- ✅ STEP 6: Create INDEX
CREATE INDEX IF NOT EXISTS idx_questions_order
ON orientation_quiz_questions(quiz_id, order_index);

-- ✅ STEP 7: Verify
SELECT question_code, order_index
FROM orientation_quiz_questions
ORDER BY order_index
LIMIT 25;
