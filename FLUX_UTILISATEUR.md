# 🎯 Flux Utilisateur Complet - Quiz → Ranking Personnalisé

## Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Browser)                          │
│                      quiz.html                                   │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   │ 1️⃣ POST /orientation/compute
                   ├─────────────────────────────────────────────→ PROA (FastAPI)
                   │                                                Port 8000
                   │ ← Profil + Scores
                   │
                   │ 2️⃣ GET /ranking/universites?user_id=XXX
                   ├─────────────────────────────────────────────→ PORA (Go)
                   │                                                Port 8080
                   │ ← Ranking enrichi avec profil
                   │
                   ↓
            User sees personalized ranking
```

---

## 📋 Étapes du Flux

### 1️⃣ **Page Quiz** (`quiz.html`)
- **Localisation**: `services/proa-service/quiz.html`
- **Accès**: `http://localhost:8000/quiz.html` (avec serveur static) ou ouvrir le fichier directement
- **Contient**: 12 questions d'orientation (Logique, Technique, Créativité, etc.)
- **Échelle**: 1 à 5 (Pas du tout → Complètement)

**Flux utilisateur**:
```
1. Entre son ID utilisateur (ex: user_123)
2. Répond aux 12 questions
3. Clique "Soumettre" → voir les résultats
```

---

### 2️⃣ **PROA: Compute Orientation** (Python FastAPI)
**Endpoint**: `POST /orientation/compute`

**Request**:
```json
{
  "user_id": "user_123",
  "quiz_version": "1.0",
  "responses": {
    "logic_1": 5.0,
    "technical_1": 4.0,
    "creativity_1": 3.0,
    ...
  }
}
```

**Response** (Status 201):
```json
{
  "user_id": "user_123",
  "quiz_version": "1.0",
  "profile": [0.83, 0.72, 0.65, 0.44, ...],
  "confidence": 0.87,
  "created_at": "2026-01-29T12:00:00Z"
}
```

**Ce qui se passe**:
- ✅ Valide les réponses (scores [1,5])
- ✅ Construit le vecteur d'orientation (12 dimensions)
- ✅ Calcule la confiance (variance des scores)
- ✅ Sauvegarde dans Supabase

---

### 3️⃣ **PORA: Ranking Enrichi** (Go Gin)
**Endpoint**: `GET /ranking/universites?user_id=user_123`

**Flow interne PORA**:
```
1. Récupère le ranking PORA global (basé sur followers/engagement)
2. Appelle PROA avec le user_id (orientation_client.go)
3. Récupère le profil d'orientation utilisateur
4. Pondère les scores: 60% PORA + 40% Orientation
5. Re-trie le classement
6. Retourne le ranking personnalisé
```

**Response**:
```json
[
  {
    "id": "uni_123",
    "nom": "Université XXX",
    "type": "universite",
    "score": 0.78,
    "rank": 1,
    "percentile": 95,
    "orientation_score": 0.82,
    "orientation_match": [0.83, 0.72, ...]
  },
  {...},
]
```

**Sans user_id**: Retourne le ranking PORA global (pas d'enrichissement)

---

## 🚀 Test du Flux Complet

### Prérequis
```bash
# Terminal 1: PROA (FastAPI)
cd services/proa-service
python -m uvicorn main:app --reload --port 8000

# Terminal 2: PORA (Go)
cd services/pora-service
go run .
```

### Test Manuel
```bash
# 1️⃣ Ouvrir quiz.html dans le navigateur
file:///d:/Backup/UNIVERSEARCH%20BACKEND/services/proa-service/quiz.html

# Ou via un serveur HTTP simple:
cd services/proa-service
python -m http.server 8080

# Puis accéder: http://localhost:8080/quiz.html
```

### Test API (curl/Postman)
```bash
# 1️⃣ Soumettre un quiz
curl -X POST http://localhost:8000/orientation/compute \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_test_001",
    "quiz_version": "1.0",
    "responses": {
      "logic_1": 5,
      "technical_1": 4,
      "creativity_1": 3,
      "entrepreneurship_1": 2,
      "leadership_1": 4,
      "management_1": 3,
      "communication_1": 5,
      "teamwork_1": 4,
      "analysis_1": 4,
      "organization_1": 3,
      "resilience_1": 4,
      "negotiation_1": 2
    }
  }'

# 2️⃣ Récupérer le ranking global (sans user_id)
curl http://localhost:8080/ranking/universites

# 3️⃣ Récupérer le ranking ENRICHI pour l'utilisateur
curl "http://localhost:8080/ranking/universites?user_id=user_test_001"
```

---

## 📊 Exemple de Flux Complet

### Request PROA (Quiz réponses)
```json
POST /orientation/compute
{
  "user_id": "alice_prof",
  "quiz_version": "1.0",
  "responses": {
    "logic_1": 5,
    "technical_1": 5,
    "creativity_1": 4,
    "entrepreneurship_1": 3,
    "leadership_1": 4,
    "management_1": 5,
    "communication_1": 5,
    "teamwork_1": 4,
    "analysis_1": 5,
    "organization_1": 5,
    "resilience_1": 4,
    "negotiation_1": 4
  }
}
```

### Response PROA
```json
{
  "user_id": "alice_prof",
  "quiz_version": "1.0",
  "profile": [
    0.83,  # logic
    0.87,  # technical
    0.75,  # creativity
    0.58,  # entrepreneurship
    0.74,  # leadership
    0.89,  # management
    0.91,  # communication
    0.80,  # teamwork
    0.93,  # analysis
    0.95,  # organization
    0.78,  # resilience
    0.80   # negotiation
  ],
  "confidence": 0.92,
  "created_at": "2026-01-29T14:32:00Z"
}
```

### Request PORA (Ranking enrichi)
```
GET /ranking/universites?user_id=alice_prof
```

### Response PORA (Ranking personnalisé)
```json
[
  {
    "id": "uni_management_school",
    "nom": "Management School Paris",
    "type": "universite",
    "score": 0.89,
    "rank": 1,
    "percentile": 98,
    "orientation_score": 0.83,
    "orientation_match": [0.83, 0.87, 0.75, ...]
    // ✅ Top 1 car: très bon en management + communication
  },
  {
    "id": "uni_tech",
    "nom": "Tech University",
    "type": "universite",
    "score": 0.84,
    "rank": 2,
    "percentile": 95,
    "orientation_score": 0.89,
    "orientation_match": [...]
    // ✅ Top 2 car: excellent en technique + organisation
  },
  // ...
]
```

---

## 🔧 Configuration Importante

### PORA doit connaître PROA
**File**: `services/pora-service/.env`
```env
ORIENTATION_SERVICE_URL=http://localhost:8000
```

**Vérifié au démarrage** (config.go):
```go
if OrientationServiceURL != "" &&
    !strings.HasPrefix(OrientationServiceURL, "http://") {
    log.Fatalf("ORIENTATION_SERVICE_URL invalide")
}
```

### PROA doit connaître Supabase
**File**: `services/proa-service/.env`
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-key
```

---

## 📈 Améliorations Futures

### Phase 2: Feedback Utilisateur
```
POST /orientation/feedback
{
  "user_id": "alice_prof",
  "satisfaction": 4,  # 1-5
  "changed_orientation": false,
  "success": true
}
```
→ Enrichir PORA avec feedback pour améliorer le ranking

### Phase 3: ML Ranking
- Au lieu de pondération fixe (60% PORA + 40% Orientation)
- Utiliser un modèle ML pour apprendre les poids optimaux
- Inclure historique utilisateur (feedback) pour affiner

### Phase 4: Profil Persistant
- Voir l'historique de ses profils d'orientation
- Tracker l'évolution au fil du temps
- Comparaison avant/après certains événements

---

## 🧪 Test du Flux dans quiz.html

1. **Ouvrir** `quiz.html` dans le navigateur
2. **Entrer** un ID utilisateur (ex: `user_test_alice`)
3. **Répondre** aux 12 questions
4. **Cliquer** "Soumettre ✓"
5. **Voir**:
   - ✅ Profil d'orientation calculé par PROA
   - ✅ Top 5 universités ENRICHIES par le profil
   - ✅ Score de confiance
   - ✅ Match entre profil et universités

---

## 📝 Logs à Vérifier

### PROA (Python)
```
INFO:     POST /orientation/compute
[PROA] Quiz reçu: user_id=alice_prof, réponses=12
[PROA] Profil d'orientation calculé (confiance=0.92)
[PROA] ✅ Profil sauvegardé en DB
```

### PORA (Go)
```
[RANK USER] 📊 Calcul ranking personnalisé pour alice_prof
[PORA][API] Appel PROA: /orientation/compute
✅ Profil utilisateur reçu: confidence=0.92
[PORA] Enrichissement: 60% PORA + 40% Orientation
[PORA] ✅ Ranking personnalisé calculé
```

---

## 🎯 Résumé

| Étape | Service | Endpoint | Entrée | Sortie |
|-------|---------|----------|--------|--------|
| 1 | PROA | `POST /orientation/compute` | Quiz réponses | Profil + Confiance |
| 2 | PORA | `GET /ranking/universites?user_id=XXX` | User ID | Ranking enrichi |
| 3 | Frontend | `quiz.html` | - | Affiche résultats |

**Résultat**: L'utilisateur voit un classement d'universités **adapté à son profil**, pas un classement générique! 🚀
