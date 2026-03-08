# PROA Service - Guide d'Utilisation Rapide

## 🚀 Démarrage

```bash
cd services/proa-service

# Installation dépendances
pip install -r requirements.txt
pip install pytest pytest-cov

# Configurer .env
export SUPABASE_URL="https://..."
export SUPABASE_SERVICE_ROLE_KEY="eyJ..."

# Lancer le serveur
uvicorn main:app --reload --port 8001
```

---

## 📝 Endpoints Disponibles

### 1. Calculer un Profil d'Orientation
```bash
POST /orientation/compute
Content-Type: application/json

{
  "user_id": "user_123",
  "quiz_version": "1.0",
  "responses": {
    "logic_1": 5.0,
    "technical_1": 4.0,
    "creativity_1": 3.0,
    "entrepreneurship_1": 4.0,
    "leadership_1": 3.0,
    "management_1": 4.0,
    "communication_1": 5.0,
    "teamwork_1": 4.0,
    "analysis_1": 3.0,
    "organization_1": 4.0,
    "resilience_1": 3.0,
    "negotiation_1": 2.0
  }
}
```

**Response (201):**
```json
{
  "user_id": "user_123",
  "quiz_version": "1.0",
  "profile": [0.15, 0.12, 0.08, 0.20, 0.11, 0.09, 0.10, 0.05, 0.06, 0.04],
  "confidence": 0.82,
  "features_count": 22,
  "created_at": "2026-01-29T10:30:00Z"
}
```

**Erreurs possibles:**
- `422` - Questions manquantes ou scores invalides [1-5]
- `500` - Erreur serveur

---

### 2. Score Seulement (Léger)
```bash
POST /orientation/score-only
{...same payload...}
```

**Response (200):**
```json
{
  "user_id": "user_123",
  "score": 0.62
}
```

---

### 3. Historique d'Orientation
```bash
GET /orientation/history/user_123?limit=10&days=30
```

**Response:**
```json
{
  "user_id": "user_123",
  "count": 3,
  "history": [
    {
      "id": "profile_1",
      "profile": [...],
      "confidence": 0.85,
      "created_at": "2026-01-29T10:30:00Z"
    },
    ...
  ]
}
```

---

### 4. Soumettre du Feedback
```bash
POST /orientation/feedback
{
  "user_id": "user_123",
  "satisfaction": 4,
  "changed_orientation": false,
  "success": true
}
```

---

### 5. Health Check Système
```bash
GET /orientation/health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-29T10:30:00Z",
  "alerts": [
    {
      "level": "warning",
      "message": "Satisfaction moyenne basse: 2.8/5",
      "data": {...},
      "timestamp": "2026-01-29T10:30:00Z"
    }
  ]
}
```

---

### 6. Progression Utilisateur
```bash
GET /orientation/progression/user_123
```

**Response:**
```json
{
  "user_id": "user_123",
  "progression": {
    "count": 5,
    "avg_confidence": 0.82,
    "min_confidence": 0.65,
    "max_confidence": 0.91,
    "trend": "improving",
    "last_profile": {...}
  }
}
```

---

## 🧪 Tests

### Lancer Tous les Tests
```bash
pytest tests/ -v
```

### Tests Spécifiques
```bash
# Feature engineering
pytest tests/test_feature_engineering.py -v

# Rule engine
pytest tests/test_rule_engine.py -v

# API
pytest tests/test_api_integration.py -v
```

### Avec Couverture
```bash
pytest tests/ --cov=core --cov=api --cov=db --cov-report=html
# Ouvre: htmlcov/index.html
```

---

## 🔧 Configuration (orientation_config.json)

```json
{
  "domain_threshold": 2,
  "max_score": 5,
  "normalize_vector": true,
  "domains": {
    "computer_science": ["logic_1", "technical_1"],
    "art": ["creativity_1"],
    "business": ["entrepreneurship_1", "leadership_1", "management_1"],
    ...
  },
  "skills": {
    "logic": ["logic_1"],
    "creativity": ["creativity_1"],
    ...
  }
}
```

**Paramètres:**
- `domain_threshold`: Score minimum pour activer un domaine (défaut: 2)
- `max_score`: Score maximum du quiz (défaut: 5)
- `normalize_vector`: Normaliser le vecteur final (défaut: true)

---

## 📊 Monitoring

### Vérifier la Santé
```bash
curl http://localhost:8001/orientation/health | jq
```

### Voir les Statistiques (7 derniers jours)
- Nombre de feedback
- Satisfaction moyenne
- Taux de succès
- Taux de changement d'orientation

### Détecter les Problèmes
- Satisfaction < 3.0 → **Warning**
- Taux de succès < 70% → **Warning**
- > 20 profils avec confiance < 30% → **Warning**

---

## 🐛 Debugging

### Logs
```bash
# Voir tous les logs
tail -f logs/proa.log

# Filtrer par level
grep "ERROR\|WARNING" logs/proa.log
```

### Exemple de Log
```
[2026-01-29 10:30:00] INFO: PROA compute | user=user_123 | quiz=1.0 | #responses=12 | confidence=0.82
[2026-01-29 10:30:01] INFO: Profil créé: confidence=0.82, vector_size=22
[2026-01-29 10:31:00] WARNING: Satisfaction moyenne basse: 2.8/5
```

---

## 🔗 Intégration PORA

PROA fournit des scores à PORA pour le ranking:

```python
# Dans PORA (Go)
score := proa_client.GetOrientationScore(user_id)
// → Utilise le score pour affiner le ranking
```

**Endpoint utilisé:**
```
POST /orientation/score-only
```

---

## 📋 Checklist de Déploiement

- [ ] Supabase configuré (tables créées)
- [ ] Variables d'environnement définies
- [ ] Tests passent (`pytest tests/ -v`)
- [ ] Couverture > 85% (`pytest --cov`)
- [ ] Health check retourne `"healthy"`
- [ ] Logs sans erreurs

---

## 🆘 Dépannage

### Erreur: "Supabase configuration manquante"
```bash
export SUPABASE_URL="..."
export SUPABASE_SERVICE_ROLE_KEY="..."
```

### Erreur: "Impossible de charger orientation_config.json"
→ Vérifier que le fichier existe et est valide JSON

### Tests échouent
```bash
# Vérifier les imports
python -c "from core.feature_engineering import build_features"

# Lancer avec plus de verbosité
pytest tests/ -vv -s
```

### Endpoint retourne 500
→ Vérifier les logs
```bash
python main.py 2>&1 | grep ERROR
```

---

## 📚 Ressources

- **Feature Engineering**: `core/feature_engineering.py`
- **Rule Engine**: `core/rule_engine.py`
- **Repository**: `db/repository.py`
- **Monitoring**: `core/monitoring.py`
- **API**: `api/routes.py`
- **Tests**: `tests/test_*.py`

