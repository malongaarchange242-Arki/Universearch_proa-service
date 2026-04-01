# 🚀 PROA Deployment & Verification Guide

## 📋 Table des matières
1. [Pre-Check Checklist](#pre-check-checklist)
2. [Database Schema Verification](#database-schema-verification)
3. [Configuration Verification](#configuration-verification)
4. [Local Testing](#local-testing)
5. [Deployment Steps](#deployment-steps)
6. [Monitoring & Troubleshooting](#monitoring--troubleshooting)

---

## ✅ Pre-Check Checklist

### 1. Python Environment

```bash
# Check Python version
python --version
# Expected: Python 3.10+

# Check virtual environment
cd services/proa-service
source venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\Activate.ps1  # Windows

# Check dependencies
pip list | grep -E "fastapi|supabase|pydantic|requests"
# Expected: fastapi, supabase-py, pydantic, requests installed
```

### 2. Environment Variables

```bash
# Verify .env file exists
cat services/proa-service/.env

# Expected variables:
# SUPABASE_URL=https://xxx.supabase.co
# SUPABASE_SERVICE_ROLE_KEY=xxxx
# SUPABASE_ANON_KEY=xxxx (optional)
```

### 3. Port Availability

```bash
# Check if port 8000 is free
netstat -ano | findstr :8000  # Windows
lsof -i :8000  # Linux/Mac

# If port in use:
# Kill existing process or use different port
# uvicorn main:app --port 8001
```

### 4. Supabase Connection

```bash
# Test connection
curl -X GET "https://YOUR_SUPABASE_URL/rest/v1/health" \
  -H "apikey: YOUR_SERVICE_ROLE_KEY"

# Expected: 200 OK
# If fails: Check SUPABASE_URL and KEY in .env
```

---

## 🗄️ Database Schema Verification

### 1. Check Required Tables

```sql
-- Run this in Supabase SQL Editor

-- Table 1: orientation_quiz_questions
SELECT COUNT(*) FROM orientation_quiz_questions;
-- Expected: > 0 (should have 24+ questions)

-- Table 2: orientation_quiz_responses
SELECT COUNT(*) FROM orientation_quiz_responses;
-- Expected: 0 (initially, will grow as users take quiz)

-- Table 3: orientation_profiles
SELECT COUNT(*) FROM orientation_profiles;
-- Expected: 0 (initially)

-- Table 4: orientation_recommendations
SELECT COUNT(*) FROM orientation_recommendations;
-- Expected: 0 (initially)

-- Table 5: filieres
SELECT COUNT(*) FROM filieres;
-- Expected: > 100 (should have many programs)
```

### 2. Check Table Structure

```sql
-- Verify question_code format
SELECT DISTINCT question_code 
FROM orientation_quiz_questions 
LIMIT 10;

-- Expected format: q1, q2, q3, ... or Q1, Q2, Q3, ...
-- ⚠️ CRITICAL: Must match orientation_config.json!
```

### 3. Check Filieres Table

```sql
-- Sample filieres
SELECT id, nom, description 
FROM filieres 
LIMIT 5;

-- Expected: Programs like "Informatique", "Génie Civil", etc.
```

---

## ⚙️ Configuration Verification

### 1. Check orientation_config.json

```bash
cat services/proa-service/orientation_config.json
```

**Requirements:**
- ✅ `max_score`: 4 (matches quiz scale 1-4)
- ✅ `domains`: Dictionary with 16+ domains
- ✅ `skills`: Dictionary with 12+ skills
- ✅ Each domain/skill mapped to question codes
- ⚠️ **CRITICAL**: Question codes must match DB exactly!

**Example valid config:**
```json
{
  "max_score": 4,
  "domains": {
    "logic": ["q1", "q5"],           // Must match DB
    "technical": ["q2", "q6"],       // Must match DB
    "creativity": ["q3", "q7"]       // Must match DB
  }
}
```

**Common Issues:**
```
❌ WRONG: "domains": {"logic": ["Q1", "Q5"]}  (uppercase)
❌ WRONG: "domains": {"logic": ["Question1"]}  (wrong name)
✅ RIGHT: "domains": {"logic": ["q1", "q5"]}  (matches DB)
```

### 2. Sync Config with Database

```python
# services/proa-service/scripts/verify_config.py
import json
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# Load config
with open('orientation_config.json', 'r') as f:
    config = json.load(f)

# Get DB questions
url = f"{SUPABASE_URL}/rest/v1/orientation_quiz_questions?select=question_code"
headers = {
    "apikey": SUPABASE_SERVICE_ROLE_KEY,
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
}
response = requests.get(url, headers=headers)
db_questions = [q['question_code'] for q in response.json()]

# Check config questions
config_questions = set()
for qs in config.get('domains', {}).values():
    config_questions.update(qs)
for qs in config.get('skills', {}).values():
    config_questions.update(qs)

# Verify
db_set = set(db_questions)
config_set = config_questions

missing_in_db = config_set - db_set
missing_in_config = db_set - config_set

if missing_in_db:
    print(f"❌ Config has questions NOT in DB: {missing_in_db}")
if missing_in_config:
    print(f"⚠️ DB has questions NOT in config: {missing_in_config}")
if not missing_in_db and not missing_in_config:
    print(f"✅ Config perfectly synced with DB ({len(config_set)} questions)")
```

---

## 🧪 Local Testing

### 1. Start the Server

```bash
cd services/proa-service
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Expected output:
# INFO:     Uvicorn running on http://0.0.0.0:8000
# INFO:     Application startup complete
```

### 2. Test Health Endpoint

```bash
curl http://localhost:8000/health

# Expected:
# {"status": "ok", "timestamp": "2024-03-29T12:00:00Z"}
```

### 3. Test Quiz Questions

```bash
curl http://localhost:8000/orientation/questions?language=fr

# Expected:
# {
#   "quiz_id": "...",
#   "total_questions": 24,
#   "questions": [
#     {"id": "q1", "domain": "logic", "text": "...", ...},
#     ...
#   ]
# }
```

### 4. Test Complete Compute

```bash
curl -X POST http://localhost:8000/orientation/compute \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test@example.com",
    "quiz_version": "1.0",
    "responses": {
      "q1": 3, "q2": 4, "q3": 2, "q4": 3,
      "q5": 4, "q6": 3, "q7": 2, "q8": 3,
      "q9": 4, "q10": 3, "q11": 2, "q12": 3,
      "q13": 4, "q14": 3, "q15": 2, "q16": 3,
      "q17": 4, "q18": 3, "q19": 2, "q20": 3,
      "q21": 4, "q22": 3, "q23": 2, "q24": 3
    }
  }'

# Expected: 201 + full response with profile, confidence, recommendations
```

### 5. Test Score-Only

```bash
curl -X POST http://localhost:8000/orientation/score-only \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test@example.com",
    "responses": {"q1": 3, ...}
  }'

# Expected: {"user_id": "...", "score": 0.658}
```

### 6. Test History

```bash
curl http://localhost:8000/orientation/history/test@example.com

# Expected: {"count": 1, "history": [...]}
```

### 7. Test Error Cases

```bash
# Test 1: Empty responses (should fail)
curl -X POST http://localhost:8000/orientation/compute \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test@example.com", "responses": {}}'

# Expected: 400 error

# Test 2: Invalid response value (should fail)
curl -X POST http://localhost:8000/orientation/compute \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test@example.com",
    "responses": {"q1": 5}  # Value > 4
  }'

# Expected: 422 error
```

---

## 🚢 Deployment Steps

### Step 1: Build Docker Image

```bash
cd services/proa-service

# Build
docker build -t universearch-proa:latest .

# Test locally
docker run -p 8000:8000 \
  -e SUPABASE_URL="https://xxx.supabase.co" \
  -e SUPABASE_SERVICE_ROLE_KEY="xxxx" \
  universearch-proa:latest
```

### Step 2: Push to Registry

```bash
# Tag image
docker tag universearch-proa:latest YOUR_REGISTRY/universearch-proa:latest

# Login
docker login YOUR_REGISTRY

# Push
docker push YOUR_REGISTRY/universearch-proa:latest
```

### Step 3: Deploy to Render/Railway/Heroku

#### Option A: Render.com

```bash
# Create new Web Service
# → Connect GitHub repo
# → Select: services/proa-service directory
# → Build command: pip install -r requirements.txt
# → Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
# → Environment variables:
#   SUPABASE_URL=...
#   SUPABASE_SERVICE_ROLE_KEY=...
# → Deploy
```

#### Option B: Docker Compose

```yaml
version: '3.8'

services:
  proa:
    image: universearch-proa:latest
    ports:
      - "8000:8000"
    environment:
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_SERVICE_ROLE_KEY: ${SUPABASE_SERVICE_ROLE_KEY}
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Step 4: Verify Deployment

```bash
# Test production URL
curl https://universearch-proa-service.onrender.com/health

# Expected: {"status": "ok"}

# Test compute
curl -X POST https://universearch-proa-service.onrender.com/orientation/compute \
  -H "Content-Type: application/json" \
  -d '{"user_id": "prod-test@example.com", ...}'

# Expected: 201 + response
```

---

## 📊 Monitoring & Troubleshooting

### 1. Check Logs

```bash
# Local
tail -f venv/logs/orientation.log

# Production (Render)
# Dashboard → Logs tab

# Expected healthy logs:
# INFO: PROA compute | user=test | quiz=1.0 | #responses=24
# INFO: Features extraites: 28
# INFO: Profil créé: confidence=0.84
```

### 2. Monitor Performance

```python
# Add to routes.py
import time

start = time.time()
# ... processing ...
duration = time.time() - start
logger.info(f"Request completed in {duration:.2f}s")

# Expected: 0.5-1.0s per request
# If > 2s: Check Supabase latency
```

### 3. Common Errors & Solutions

#### Error 1: All features = 0.0

**Logs:**
```
❌ CRITICAL: ALL FEATURES ARE 0.0!
Config expects: ['q1', 'q2', ..., 'q24']
But got: ['Q19', 'Q20', ...]
```

**Solution:**
```bash
# 1. Check DB question codes
SELECT DISTINCT question_code FROM orientation_quiz_questions;

# 2. Update orientation_config.json to match
# OR normalize keys in feature_engineering.py
```

#### Error 2: Supabase 400/401

**Logs:**
```
Supabase error: 401 Unauthorized
```

**Solution:**
```bash
# Check .env
echo $SUPABASE_SERVICE_ROLE_KEY

# If empty:
# 1. Set in .env
# 2. Restart service
# 3. Verify via curl
curl -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
  https://YOUR_SUPABASE_URL/rest/v1/health
```

#### Error 3: Timeout (>5s response)

**Cause:** Supabase query slow

**Solution:**
```python
# Already cached:
_FILIERES_CACHE = None  # Persists in memory

# If still slow, add DB index:
CREATE INDEX idx_filieres_nom ON filieres(nom);
CREATE INDEX idx_filieres_description ON filieres USING GIN(description);
```

#### Error 4: Low confidence scores (<0.3)

**Diagnosis:**
```python
# Check variance-based calculation
positive_values = [v for v in vector if v > 0]
avg = sum(positive_values) / len(positive_values)
variance = sum((v - avg) ** 2 for v in positive_values) / len(positive_values)
print(f"Variance: {variance:.4f}")  # High = inconsistent
print(f"Variance-based confidence: {1 - min(variance, 1.0):.2f}")
```

**Fix:**
- Encourage users to answer consistently
- Add re-quiz prompt if <0.3
- Consider showing "Confidence too low, retake quiz?" message

#### Error 5: No recommendations generated

**Logs:**
```
No keywords extracted! Using fallback keywords
```

**Cause:** Profile has all low features (< 0.3)

**Solution:**
```python
# Already handled with fallback:
if not result:
    FALLBACK_KEYWORDS = [
        ("informatique", 0.7),
        ("gestion", 0.6),
        ...
    ]
    result = FALLBACK_KEYWORDS
```

### 4. Performance Profiling

```python
# Add timing to each step
import time

print("Step 1: Validation", end=" ")
t1 = time.time()
# ... validate ...
print(f"({time.time() - t1:.3f}s)")

print("Step 2: Features", end=" ")
t2 = time.time()
# ... build features ...
print(f"({time.time() - t2:.3f}s)")

# Expected breakdown:
# Validation: 0.01s
# Features: 0.05s
# Profile: 0.02s
# Confidence: 0.01s
# Recommendations: 0.50s (mostly Supabase)
# Total: 0.7s
```

### 5. Uptime Monitoring

```python
# Simple health check script
import requests
import time

while True:
    try:
        response = requests.get(
            'https://universearch-proa-service.onrender.com/health',
            timeout=5
        )
        if response.status_code == 200:
            print(f"✅ {time.ctime()} - Service OK")
        else:
            print(f"❌ {time.ctime()} - Status {response.status_code}")
    except Exception as e:
        print(f"❌ {time.ctime()} - Error: {e}")
    
    time.sleep(60)  # Check every minute
```

---

## 🔗 Integration Checklist

### With Flutter App

```yaml
Frontend (Flutter):
  ✅ Load questions: GET /orientation/questions
  ✅ Submit responses: POST /orientation/compute
  ✅ Display recommendations
  ✅ Send feedback: POST /orientation/feedback
  
Backend (PROA):
  ✅ Return correct response format
  ✅ Handle errors gracefully
  ✅ Return meaningful confidence scores
```

### With Gateway (GraphQL)

```yaml
Gateway (Node.js):
  ✅ Proxy /orientation/* routes
  ✅ Authenticate requests
  ✅ Log API calls
  
GraphQL Schema:
  ✅ Define ComputeOrientationInput
  ✅ Define OrientationProfile type
  ✅ Define Recommendation type
  
Resolver:
  ✅ Call PROA backend
  ✅ Return properly typed response
```

### With PORA (Go)

```yaml
PROA (Python):
  ✅ POST /orientation/score-only endpoint
  ✅ Return fast response (~50ms)
  ✅ Cache filieres for speed

PORA (Go):
  ✅ Call /score-only for ranking
  ✅ Combine with popularity score
  ✅ Merge results
```

---

## 📈 Scaling Recommendations

### Phase 1: Current (100-500 requests/day)
- ✅ Single PROA instance
- ✅ Supabase caching (filieres)
- ✅ No message queue needed

### Phase 2: Growth (1000-5000 requests/day)
- 🟡 Add Redis cache for profiles
- 🟡 Implement Kafka for async processing
- 🟡 Add monitoring (Prometheus, Datadog)

### Phase 3: Scale (10000+ requests/day)
- 🔴 Deploy load balancer
- 🔴 Multiple PROA instances
- 🔴 Separate read/write DB connections
- 🔴 ML model caching layer
- 🔴 GraphQL subscription for real-time results

---

## 📞 Support Contacts

**Issues?**
1. Check logs: `services/proa-service/venv/logs/`
2. Verify config sync: `orientation_config.json` vs DB
3. Test endpoint locally
4. Contact backend team with **logs + request payload**

---

**Last Updated**: 2024-03-29  
**Status**: Production Ready  
**Version**: 1.0
