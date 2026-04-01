# 🔍 Diagnostic Guide - Features = 0.0 Bug

## Senior Engineer Analysis

**Problem Statement:**
```
All users receive identical recommendations because build_features() returns 0.0 for all features.
Log shows: "NO MATCH! Expected ['q1','q5'], got keys: ['q19','q20','q21','q22','q23','q24']"
```

---

## 📊 Root Cause Analysis

There are **3 Possible Root Causes** (mutually exclusive):

### Cause 1: Supabase Has Wrong question_codes (45% probability)
```
Scenario:
- Supabase table orientation_quiz_questions has:
  | quiz_id | order_index | question_code |
  |---------|-------------|---------------|
  | abc123  | 1           | Q19           | ← WRONG! Should be Q1
  | abc123  | 2           | Q20           | ← WRONG! Should be Q2
  | ...     | ...         | ...           |

Result:
- Frontend sends: {q19: 2, q20: 3, q21: 1, ...}  (lowercase due to .toLowerCase())
- Backend expects: {q1: ..., q5: ..., q9: ...}
- NO MATCH → Features = 0.0
```

**How to detect:**
1. Open browser DevTools (F12)
2. Look for console log: `📦 Regroupement par quiz_id:`
3. Check what codes actually come from Supabase

**Fix:** Update Supabase:
```sql
UPDATE orientation_quiz_questions 
SET question_code = 'Q' || order_index::text
WHERE quiz_id = (SELECT id FROM orientation_quizzes WHERE type = 'student');

-- Verify:
SELECT quiz_id, COUNT(*), ARRAY_AGG(question_code ORDER BY order_index) as codes
FROM orientation_quiz_questions
GROUP BY quiz_id;
-- Should show: {Q1,Q2,...,Q24} and {Q1,Q2,Q3,Q4,Q5} (for parent if exists)
```

---

### Cause 2: Wrong Quiz Selected (20% probability)
```
Scenario:
- You have 2 quizzes in Supabase:
  • Quiz #1 (student):  24 questions (Q1-Q24)
  • Quiz #2 (parent):   5 questions (Q19-Q23)  ← Using parent codes!

- Frontend loads BOTH
- But you're reading FROM Quiz #2 instead of Quiz #1

Result:
- Only 5 responses sent
- Q19-Q23 sent instead of Q1-Q24
- NO MATCH
```

**How to detect:**
1. Look for console log: `✅ Données quiz chargées:`
2. Check: `student: 24` and `parent: 5` (should see this)
3. Then check: `📝 Quiz type selected: "student"` vs `"parent"`
4. If selected = "parent", you have the wrong quiz selected

**Fix:** Ensure the UI correctly lets users pick "student" quiz

---

### Cause 3: orientation_config.json Mismatch (35% probability)
```
Scenario:
- Supabase creates NEW questions with different codes (e.g., P1-P5 for parent)
- orientation_config.json still expects OLD structure (Q1-Q24)
- Config and Data are out of sync

Result:
- Perfect data in Supabase (P1, P2, P3, P4, P5)
- Config expects (Q1, Q5, Q9, ...)
- NO MATCH
```

**How to detect:**
1. Check backend logs in `🔍 BUILD_FEATURES DIAGNOSTIC`
2. Look for:
   - `📥 RECEIVED: [...]`
   - `📋 CONFIG EXPECTS: [...]`
3. If completely different format → Cause #3

**Fix:** Sync config with actual Supabase structure
```
Option A: Update orientation_config.json to match actual question codes
Option B: Update Supabase to match orientation_config.json
Option C: Create dynamic mapping
```

---

## 🧪 How to Diagnose (Step by Step)

### Step 1: Load the frontend
1. Open Quiz.html in browser
2. Open DevTools Console (F12)
3. The page will auto-load questions from Supabase

### Step 2: Check Supabase loading
Look for console logs containing:
```
🔍 SUPABASE DIAGNOSTIC
═════════════════════
📋 Total questions from Supabase: [NUMBER]
📦 Regroupement par quiz_id:
   Quiz ID [abc123]: 24 questions -> [q1, q2, ..., q24]
   Quiz ID [def456]: 5 questions -> [q19, q20, q21, q22, q23]
✅ Données quiz chargées:
   student: 24
   parent: 5
```

### Step 3: Take the quiz
1. Select "Student" mode (not "Parent")
2. Answer all questions
3. Submit

### Step 4: Check submission logs
Look for:
```
🔥 SUBMISSION DIAGNOSTIC
📝 Quiz type selected: "student"
📊 Questions in student quiz: 24
📋 Expected codes: [q1, q2, ..., q24]

✅ After mapping:
📊 responses count: 24
✅ Count matches! 24/24
```

❌ OR if mismatch:
```
🚨 MISMATCH DETECTED!
   Expected: 24 responses (student quiz)
   Got: 5 responses (parent quiz!)
   Missing: [q1, q2, ..., q18]
```

### Step 5: Check backend logs
In PROA terminal, look for:
```
🔍 BUILD_FEATURES DIAGNOSTIC
═════════════════════════════════════════════════════════
📥 RECEIVED (24 responses):
   Keys: [q1, q2, ..., q24]
📋 CONFIG EXPECTS:
   Domains: [logic, technical, creativity, ...]
   Question codes: [q1, q2, q3, q4, q5, q6, q7, q8, q9, ...]

📊 MATCH ANALYSIS:
   Expected questions: [q1, q2, q3, ..., q24]
   Received questions: [q1, q2, q3, ..., q24]
   Matching: [q1, q2, ..., q24] (24/24)
   Match quality: 100%

✅ RESULT:
   Total features: 16
   Non-zero: 16 → {'domain_logic': 0.75, 'domain_technical': 0.80, ...}
```

---

## ✅ Solution Workflow

### If Match Quality = 100% ✅
**NO FIX NEEDED** - Everything works!
- Features will be non-zero
- Recommendations will be personalized
- System is healthy

---

### If Match Quality < 100% ❌

#### Option A: Fix Supabase (Recommended)
**Why:** Single source of truth, clean architecture
```sql
-- 1. Backup current data
CREATE TABLE orientation_quiz_questions_backup AS SELECT * FROM orientation_quiz_questions;

-- 2. Fix the codes
UPDATE orientation_quiz_questions 
SET question_code = 'Q' || order_index::text
WHERE quiz_id = (SELECT id FROM orientation_quizzes WHERE name = 'Student Quiz');

-- 3. Verify
SELECT quiz_id, question_code, question_text, order_index FROM orientation_quiz_questions;

-- 4. Restart PROA service
-- Application: restart Python server
```

#### Option B: Fix orientation_config.json (If Supabase is the source of truth)
```json
{
  "max_score": 4,
  "domains": {
    "logic": ["p1", "p3"],           // Use actual codes from Supabase
    "technical": ["p2", "p4"],
    "communication": ["p5"]
  },
  "skills": {
    "logic": ["p1"],
    ...
  }
}
```

#### Option C: Dynamic Mapping (Most Flexible)
Create a smart mapping that adapts to whatever codes are in Supabase:
```python
# In build_features():
# Don't hardcode domain mappings
# Instead: query what domains each question belongs to from Supabase

# Requires:
# - Supabase table: question_domain_mapping (question_id, domain_name)
# - Backend query to read this mapping dynamically
```

---

## ⚠️ Prevention for Future

### Best Practice Architecture:
```
Supabase (Source of Truth)
  ├─ orientation_quiz_questions
  │  ├─ id (UUID)
  │  ├─ quiz_id
  │  ├─ question_code ← MUST be q1, q2, ... or q1_student, q2_student
  │  ├─ question_text
  │  └─ order_index
  │
  └─ question_domain_mapping
     ├─ question_id → domain_name
     ├─ "q1" → "logic"
     ├─ "q5" → "logic"
     ├─ "q2" → "technical"
     └─ ...

Backend (Reads from Supabase)
  └─ Dynamically builds domains_config from question_domain_mapping

Frontend (Displays what Supabase gives)
  └─ No hardcoding, reads questions from Supabase API
```

### Validation to Add:
```python
# In build_features() at startup:
def validate_config():
    """Ensure config matches Supabase data"""
    supabase_codes = fetch_all_question_codes_from_supabase()
    config_codes = [q for qs in domains_config.values() for q in qs]
    
    if set(supabase_codes) != set(config_codes):
        logger.error(
            f"CONFIG MISMATCH!\n"
            f"  Supabase has: {supabase_codes}\n"
            f"  Config expects: {config_codes}\n"
            f"  Missing in config: {set(supabase_codes) - set(config_codes)}\n"
            f"  Extra in config: {set(config_codes) - set(supabase_codes)}"
        )
```

---

## 📋 Checklist to Run Now

- [ ] Open browser DevTools (F12)
- [ ] Check console for `📦 Regroupement par quiz_id:`
- [ ] Document what quiz_ids exist and their question codes
- [ ] Check: does "student" quiz have 24 questions?
- [ ] Check: do codes start with "q1", "q2", ... or "Q1", "Q2"?
- [ ] Restart PROA: `uvicorn main:app --reload`
- [ ] Take quiz again, capture full console logs
- [ ] Compare backend logs with frontend logs
- [ ] Identify which of 3 causes matches your situation
- [ ] Apply appropriate fix
- [ ] Verify: features > 0 in recommendations
- [ ] Verify: different users get different recommendations

---

## 🎯 Expected Outcome After Fix

```
✅ Frontend console:
   Match quality: 100%
   Responses count: 24
   Codes: [q1, q2, ..., q24]

✅ Backend console:
   Match analysis: 100% match
   Features generated: 16 non-zero
   No emergency fallback triggered

✅ User experience:
   • User A (logic): Gets CS/Engineering recommendations
   • User B (creative): Gets Design/Marketing recommendations
   • User C (business): Gets Finance/Management recommendations
```

---

## 🆘 If Still Not Working

1. **Collect full logs:**
   - Browser console (F12)
   - PROA terminal output
   - Screenshot or copy-paste both

2. **Create diagnostic file:**
   ```javascript
   // In Console, run:
   JSON.stringify({
     quiz_student_length: data.student?.length || 0,
     quiz_parent_length: data.parent?.length || 0,
     student_codes: data.student?.map(q => q.code),
     parent_codes: data.parent?.map(q => q.code),
     timestamp: new Date().toISOString()
   }, null, 2)
   ```

3. **Share:** Full logs + diagnostic output

---

## 📚 References

- **File:** `d:\UNIVERSEARCH BACKEND\services\proa-service\orientation_config.json`
- **File:** `d:\UNIVERSEARCH BACKEND\Frontend\Quiz.html`
- **File:** `d:\UNIVERSEARCH BACKEND\services\proa-service\core\feature_engineering.py`
- **Supabase:** Check `orientation_quiz_questions` table structure

---

**Last Updated:** March 25, 2026
**Status:** Ready for diagnosis
