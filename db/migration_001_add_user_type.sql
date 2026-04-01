-- ============================================
-- MIGRATION 1: Add user_type to orientation_quizzes
-- ============================================

-- ✅ STEP 1: Add user_type column
ALTER TABLE orientation_quizzes
ADD COLUMN IF NOT EXISTS user_type VARCHAR(50);

-- ✅ STEP 2: Add constraint
ALTER TABLE orientation_quizzes
ADD CONSTRAINT chk_user_type 
CHECK (user_type IN ('bachelier', 'etudiant', 'parent'));

-- ✅ STEP 3: Add UNIQUE constraint on quiz_code (prevent duplicates!)
ALTER TABLE orientation_quizzes
ADD CONSTRAINT unique_quiz_code UNIQUE (quiz_code);

-- ✅ STEP 4: Create INDEX for fast queries
CREATE INDEX IF NOT EXISTS idx_quizzes_user_type 
ON orientation_quizzes(user_type);

CREATE INDEX IF NOT EXISTS idx_quizzes_code_type 
ON orientation_quizzes(quiz_code, user_type);

-- ✅ STEP 5: Update existing quizzes (map to user_types)
UPDATE orientation_quizzes
SET user_type = 'bachelier'
WHERE user_type IS NULL AND (
  quiz_code ILIKE '%filiere%' 
  OR quiz_code ILIKE '%field%'
  OR description ILIKE '%filière%'
);

UPDATE orientation_quizzes
SET user_type = 'etudiant'
WHERE user_type IS NULL AND (
  quiz_code ILIKE '%evolution%'
  OR quiz_code ILIKE '%reconversion%'
);

UPDATE orientation_quizzes
SET user_type = 'parent'
WHERE user_type IS NULL AND (
  quiz_code ILIKE '%budget%'
  OR quiz_code ILIKE '%debit%'
);

-- Fallback
UPDATE orientation_quizzes
SET user_type = 'bachelier'
WHERE user_type IS NULL;

-- ✅ STEP 6: Make NOT NULL after data is populated
ALTER TABLE orientation_quizzes
ALTER COLUMN user_type SET NOT NULL;

-- ✅ STEP 7: Verify migration
SELECT user_type, COUNT(*) as count 
FROM orientation_quizzes 
GROUP BY user_type
ORDER BY user_type;
