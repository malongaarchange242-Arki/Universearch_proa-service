# db/repository.py

import os
import logging
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from supabase import create_client, Client

logger = logging.getLogger("orientation.db")
logger.setLevel(logging.INFO)

# Namespace déterministe pour convertir des user strings en UUID v5
UNIVERSEARCH_NAMESPACE = uuid.UUID('550e8400-e29b-41d4-a716-446655440000')

def string_to_uuid(value: str) -> str:
    """Convertir une string en UUID v5 déterministe (retourne str)."""
    try:
        # Si c'est déjà un UUID valide, renvoyer tel quel
        _ = uuid.UUID(value)
        return value
    except Exception:
        return str(uuid.uuid5(UNIVERSEARCH_NAMESPACE, value))

# -------------------------------------------------
# Connexion Supabase
# -------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise RuntimeError("Supabase configuration manquante")

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)


def _unwrap_result(result):
    """Retourne tuple (data, error) en supportant plusieurs shapes de réponse.
    Le client supabase peut renvoyer un objet avec attributs ou un dict.
    """
    data = None
    error = None

    try:
        if hasattr(result, "data"):
            data = getattr(result, "data")
    except Exception:
        data = None

    if data is None and isinstance(result, dict):
        data = result.get("data")

    try:
        if hasattr(result, "error"):
            error = getattr(result, "error")
    except Exception:
        error = None

    if error is None and isinstance(result, dict):
        error = result.get("error")

    return data, error

# -------------------------------------------------
# Sauvegarde réponses brutes quiz
# Table : orientation_quiz_responses
# -------------------------------------------------
def save_quiz_responses(
    user_id: str,
    quiz_version: str,
    responses: Dict[str, float],
) -> str:
    """
    Sauvegarde les réponses brutes du quiz.
    
    Returns:
        ID de la soumission
    """
    # Convertir user_id en UUID si nécessaire
    user_uuid = string_to_uuid(user_id)

    data = {
        "user_id": user_uuid,
        "quiz_version": quiz_version,
        "responses": responses,
        "created_at": datetime.utcnow().isoformat(),
    }

    try:
        result = supabase.table("orientation_quiz_responses").insert(data).execute()
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        submission_id = data_resp[0]["id"] if data_resp else None
        logger.info(f"Quiz responses sauvegardées | user={user_id} (uuid={user_uuid}) | submission_id={submission_id}")
        return submission_id or user_uuid

    except Exception as e:
        logger.exception("Erreur sauvegarde orientation_quiz_responses")
        raise

# -------------------------------------------------
# Sauvegarde profil final (avec versioning)
# Table : orientation_profiles
# -------------------------------------------------
def save_orientation_profile(
    user_id: str,
    profile: List[float],
    confidence: float,
    engine: str = "rule",
    quiz_submission_id: Optional[str] = None,
) -> str:
    """
    Sauvegarde le profil d'orientation avec versioning.
    
    Returns:
        ID du profil créé
    """
    user_uuid = string_to_uuid(user_id)

    data = {
        "user_id": user_uuid,
        "profile": profile,
        "confidence": confidence,
        "engine": engine,
        "quiz_submission_id": quiz_submission_id,
        "created_at": datetime.utcnow().isoformat(),
        "version": 1,  # Pour le versioning futur
    }

    try:
        result = supabase.table("orientation_profiles").insert(data).execute()
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        profile_id = data_resp[0]["id"] if data_resp else None
        logger.info(f"Profil orientation sauvegardé | user={user_id} (uuid={user_uuid}) | profile_id={profile_id} | confidence={confidence}")
        return profile_id or user_uuid

    except Exception as e:
        logger.exception("Erreur sauvegarde orientation_profiles")
        raise

# -------------------------------------------------
# Historique profils utilisateur (avec limite)
# -------------------------------------------------
def get_orientation_history(
    user_id: str,
    limit: int = 10,
    days: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Récupère l'historique des profils d'orientation.
    
    Args:
        user_id: identifiant utilisateur
        limit: nombre de profils à retourner
        days: si spécifié, limiter aux N derniers jours
    """
    try:
        query = (
            supabase.table("orientation_profiles")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        
        if days:
            since = datetime.utcnow() - timedelta(days=days)
            query = query.gte("created_at", since.isoformat())
        
        result = query.execute()
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        return data_resp or []

    except Exception as e:
        logger.exception(f"Erreur récupération historique orientation | user={user_id}")
        raise

# -------------------------------------------------
# Récupérer le profil le plus récent
# -------------------------------------------------
def get_latest_orientation_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """Récupère le dernier profil d'orientation de l'utilisateur"""
    try:
        result = (
            supabase.table("orientation_profiles")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        return data_resp[0] if data_resp else None
    
    except Exception as e:
        logger.exception(f"Erreur récupération latest profile | user={user_id}")
        raise

# -------------------------------------------------
# Feedback utilisateur
# Table : orientation_feedback
# -------------------------------------------------
def save_orientation_feedback(
    user_id: str,
    satisfaction: int,
    changed_orientation: bool,
    success: Optional[bool] = None,
) -> None:
    """
    Sauvegarde le feedback utilisateur pour améliorer les modèles.
    """
    data = {
        "user_id": user_id,
        "satisfaction": satisfaction,
        "changed_orientation": changed_orientation,
        "success": success,
        "created_at": datetime.utcnow().isoformat(),
    }

    try:
        result = supabase.table("orientation_feedback").insert(data).execute()
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        logger.info(f"Feedback orientation sauvegardé | user={user_id} | satisfaction={satisfaction}")

    except Exception as e:
        logger.exception("Erreur sauvegarde orientation_feedback")
        raise

# -------------------------------------------------
# Statistiques (pour monitoring)
# -------------------------------------------------
def get_feedback_statistics(days: int = 30) -> Dict[str, Any]:
    """
    Récupère les statistiques de feedback des N derniers jours.
    """
    try:
        since = datetime.utcnow() - timedelta(days=days)
        
        result = (
            supabase.table("orientation_feedback")
            .select("satisfaction,success,changed_orientation")
            .gte("created_at", since.isoformat())
            .execute()
        )
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        data = data_resp or []
        
        if not data:
            return {
                "count": 0,
                "avg_satisfaction": 0.0,
                "success_rate": 0.0,
                "changed_rate": 0.0,
            }
        
        satisfactions = [d["satisfaction"] for d in data if d["satisfaction"]]
        successes = [d["success"] for d in data if d["success"] is not None]
        changed = [d["changed_orientation"] for d in data if d["changed_orientation"]]
        
        return {
            "count": len(data),
            "avg_satisfaction": sum(satisfactions) / len(satisfactions) if satisfactions else 0.0,
            "success_rate": sum(1 for s in successes if s) / len(successes) if successes else 0.0,
            "changed_rate": sum(1 for c in changed if c) / len(changed) if changed else 0.0,
        }
    
    except Exception as e:
        logger.exception("Erreur statistiques feedback")
        raise

# -------------------------------------------------
# Profils par confiance (pour monitoring)
# -------------------------------------------------
def get_profiles_by_confidence(
    min_confidence: float = 0.5,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Récupère les profils avec une confiance >= min_confidence.
    Utile pour détecter les modèles peu fiables.
    """
    try:
        result = (
            supabase.table("orientation_profiles")
            .select("*")
            .lte("confidence", min_confidence)  # confidence <= min (les moins fiables)
            .order("confidence", desc=True)
            .limit(limit)
            .execute()
        )
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        return data_resp or []
    
    except Exception as e:
        logger.exception("Erreur récupération profiles par confiance")
        raise

