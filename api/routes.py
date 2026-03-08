from fastapi import APIRouter, HTTPException, status
import logging
from pydantic import BaseModel
from typing import Dict
import os
import json
from datetime import datetime

from core.rule_engine import compute_profile
from core.feature_engineering import build_features
from core.monitoring import get_health_status, analyze_user_progression
from core.recommendations import compute_recommended_fields
from models.profile import OrientationProfile
from models.quiz import QuizSubmission
from db.repository import (
    save_quiz_responses,
    save_orientation_profile,
    get_orientation_history,
    save_orientation_feedback,
)

logger = logging.getLogger("orientation.api")

router = APIRouter(prefix="/orientation", tags=["orientation"])

# -------------------------------------------------
# Chargement de la configuration externe
# -------------------------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "orientation_config.json")

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        ORIENTATION_CONFIG = json.load(f)
except Exception:
    logger.exception("Impossible de charger orientation_config.json")
    raise RuntimeError("Configuration orientation invalide")


# -------------------------------------------------
# Schémas Pydantic
# -------------------------------------------------
class OrientationFeedback(BaseModel):
    user_id: str
    satisfaction: int  # 1 → 5
    changed_orientation: bool = False
    success: bool | None = None


# -------------------------------------------------
# Endpoint principal — COMPUTE PROFIL (PROA)
# -------------------------------------------------
@router.post("/compute", status_code=201)
def compute_orientation(payload: QuizSubmission):
    """
    Endpoint principal pour calculer le profil d'orientation.
    
    Validations automatiques (via QuizSubmission Pydantic):
    - Toutes les questions requises présentes
    - Scores [1, MAX_SCORE]
    
    Retourne:
    - profile: vecteur d'orientation normalisé
    - confidence: confiance basée sur la variance
    """
    try:
        logger.info(
            "PROA compute | user=%s | quiz=%s | #responses=%d",
            payload.user_id,
            payload.quiz_version,
            len(payload.responses),
        )

        # Protection backend: refuser les soumissions sans réponses
        if not payload.responses or len(payload.responses) == 0:
            raise HTTPException(status_code=400, detail="Responses cannot be empty")

        # 1️⃣ Sauvegarde réponses brutes
        save_quiz_responses(
            user_id=payload.user_id,
            quiz_version=payload.quiz_version,
            responses=payload.responses,
        )

        # 2️⃣ Feature engineering réel
        features = build_features(payload.responses)
        logger.debug(f"Features extraites: {len(features)}")

        # 3️⃣ Construire profil OrientationProfile à partir des features
        # (mapping features → domains/skills)
        domains = {}
        skills = {}
        for key, value in features.items():
            if key.startswith("domain_"):
                domains[key.replace("domain_", "")] = value
            elif key.startswith("skill_"):
                skills[key.replace("skill_", "")] = value
        
        profile_obj = OrientationProfile(domains=domains, skills=skills)

        # 4️⃣ Calcul profil vectoriel
        vector = compute_profile(profile_obj)

        # 5️⃣ Calcul confiance (variance du vecteur)
        positive_values = [v for v in vector if v > 0]
        if positive_values:
            avg = sum(positive_values) / len(positive_values)
            variance = sum((v - avg) ** 2 for v in positive_values) / len(positive_values)
            confidence = round(1.0 - min(variance, 1.0), 4)  # Haute variance = basse confiance
        else:
            confidence = 0.0

        # 6️⃣ Sauvegarde profil
        save_orientation_profile(
            user_id=payload.user_id,
            profile=vector,
            confidence=confidence,
            engine="rule",
        )

        # 7️⃣ Calcul des filières recommandées (top N)
        try:
            recommended = compute_recommended_fields({"domains": domains, "skills": skills}, top_n=5)
        except Exception:
            logger.exception("Erreur calcul recommandations filières")
            recommended = {"recommended_fields": []}

        logger.info(f"Profil créé: confidence={confidence}, vector_size={len(vector)}")

        return {
            "user_id": payload.user_id,
            "quiz_version": payload.quiz_version,
            "profile": vector,
            "confidence": confidence,
            "features_count": len(features),
            "recommended_fields": recommended.get("recommended_fields", []),
            "created_at": datetime.utcnow(),
        }

    except ValueError as ve:
        # Erreur de validation (données invalides)
        logger.warning(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )
    except Exception as e:
        logger.exception(f"Erreur PROA compute: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur serveur interne"
        )


# -------------------------------------------------
# Endpoint SCORE ONLY — utilisé par PORA
# -------------------------------------------------
@router.post("/score-only")
def compute_orientation_score_only(payload: QuizSubmission):
    """
    Calcule uniquement le score d'orientation (utilisé par PORA).
    """
    try:
        features = build_features(payload.responses)
        
        domains = {}
        skills = {}
        for key, value in features.items():
            if key.startswith("domain_"):
                domains[key.replace("domain_", "")] = value
            elif key.startswith("skill_"):
                skills[key.replace("skill_", "")] = value
        
        profile_obj = OrientationProfile(domains=domains, skills=skills)
        vector = compute_profile(profile_obj)
        
        positive_values = [v for v in vector if v > 0]
        score = (
            round(sum(positive_values) / len(positive_values), 4)
            if positive_values
            else 0.0
        )

        return {
            "user_id": payload.user_id,
            "score": score,
        }

    except ValueError as ve:
        logger.warning(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )
    except Exception as e:
        logger.exception(f"Erreur PROA score-only: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur serveur interne"
        )


# -------------------------------------------------
# Historique orientation utilisateur
# -------------------------------------------------
@router.get("/history/{user_id}")
def get_orientation_history_endpoint(user_id: str, limit: int = 10):
    try:
        history = get_orientation_history(user_id=user_id, limit=limit)

        return {
            "user_id": user_id,
            "count": len(history),
            "history": history,
        }

    except Exception as e:
        logger.exception(f"Erreur récupération historique | user={user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur serveur interne"
        )


# -------------------------------------------------
# Feedback utilisateur
# -------------------------------------------------
@router.post("/feedback")
def submit_orientation_feedback(payload: OrientationFeedback):
    try:
        if not 1 <= payload.satisfaction <= 5:
            raise ValueError("satisfaction doit être entre 1 et 5")
        
        save_orientation_feedback(
            user_id=payload.user_id,
            satisfaction=payload.satisfaction,
            changed_orientation=payload.changed_orientation,
            success=payload.success,
        )

        return {"status": "feedback_saved"}

    except ValueError as ve:
        logger.warning(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(ve)
        )
    except Exception as e:
        logger.exception(f"Erreur feedback orientation | user={payload.user_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur serveur interne"
        )


# -------------------------------------------------
# Monitoring et diagnostique
# -------------------------------------------------
@router.get("/health", tags=["monitoring"])
def health_check():
    """
    Vérifie la santé globale du système PROA.
    
    Checks:
    - Statistiques de feedback (7 derniers jours)
    - Profils avec basse confiance
    - Alertes système
    """
    try:
        status_data = get_health_status()
        status_code = 200 if status_data["status"] == "healthy" else 503
        return status_data
    except Exception as e:
        logger.exception("Erreur health check")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur serveur interne"
        )


@router.get("/progression/{user_id}", tags=["monitoring"])
def user_progression(user_id: str):
    """
    Analyse la progression d'un utilisateur.
    
    Retourne:
    - Nombre de profils
    - Confiance moyenne / min / max
    - Trend (improving / degrading / stable)
    """
    try:
        progression = analyze_user_progression(user_id)
        return {
            "user_id": user_id,
            "progression": progression,
        }
    except Exception as e:
        logger.exception(f"Erreur progression | user={user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur serveur interne"
        )
