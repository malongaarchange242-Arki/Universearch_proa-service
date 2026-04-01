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
from core.recommendations import compute_recommended_fields, compute_recommended_institutions
from core.output_formatter import ProaResponse
from models.profile import OrientationProfile
from models.quiz import QuizSubmission
from db.repository import (
    save_quiz_responses,
    save_orientation_profile,
    get_orientation_history,
    save_orientation_feedback,
    get_active_quiz,
    get_quiz_questions,
    supabase,  # ✅ Importer le client Supabase
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

        # 2️⃣ Feature engineering réel (✨ MAINTENANT PILOTÉ PAR LA DB!)
        features = build_features(payload.responses, payload.orientation_type)
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

        # Améliorer la confiance avec ratio réponses/total
        total_questions = len(ORIENTATION_CONFIG.get("domains", {})) + len(ORIENTATION_CONFIG.get("skills", {}))
        answered_questions = len(payload.responses)
        if total_questions > 0:
            confidence = round(confidence * (answered_questions / total_questions), 4)

        # 6️⃣ Sauvegarde profil
        save_orientation_profile(
            user_id=payload.user_id,
            profile=vector,
            confidence=confidence,
            engine="rule",
        )

        # 7️⃣ Calcul des filières recommandées (top N)
        try:
            if payload.orientation_type == "institution":
                recommended = compute_recommended_institutions({"domains": domains, "skills": skills}, top_n=5)
            else:
                recommended = compute_recommended_fields({"domains": domains, "skills": skills}, top_n=5)
        except Exception:
            logger.exception("Erreur calcul recommandations")
            recommended = {"recommended_fields": []} if payload.orientation_type == "field" else {"recommended_institutions": []}

        logger.info(f"Profil créé: confidence={confidence}, vector_size={len(vector)}")

        # ✅ Standardiser la réponse avec ProaResponse
        return ProaResponse.compute_orientation(
            user_id=payload.user_id,
            profile=vector,
            confidence=confidence,
            recommended_fields=recommended.get("recommended_fields", []),
            quiz_version=payload.quiz_version
        )

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
# Récupération des questions du quiz
# -------------------------------------------------
@router.get("/questions")
def get_questions_endpoint():
    """
    Récupère les questions du quiz d'orientation depuis la base de données.
    
    Retourne la liste des questions avec leur domaine et catégorie.
    """
    try:
        # Récupérer toutes les questions (pas de filtrage par quiz actif pour l'instant)
        db_questions = get_quiz_questions()
        
        if not db_questions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aucune question trouvée"
            )
        
        # Mapper les données DB au format attendu
        questions = []
        for q in db_questions:
            question_code = q["question_code"]
            # Pour les questions DB, domaine par défaut
            domain = 'general'
            category = 'General'
            
            questions.append({
                "id": question_code,
                "domain": domain,
                "text": q["question_text"],
                "category": category
            })
        
        logger.info(f"Récupération de {len(questions)} questions depuis la DB")
        
        return {
            "questions": questions
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur récupération questions: {str(e)}")
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
