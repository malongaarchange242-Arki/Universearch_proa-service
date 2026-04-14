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
# 🎯 CAREER RECOMMENDATIONS (NEW)
# Table : career_recommendations (à créer dans Supabase)
# -------------------------------------------------
def save_career_profile(
    user_id: str,
    career_recommendation: Dict[str, Any],
) -> Optional[str]:
    """
    Sauvegarde les recommandations de carrière pour un utilisateur.
    
    Args:
        user_id: ID utilisateur
        career_recommendation: Résultat de compute_career_recommendations()
    
    Returns:
        ID du record créé
    """
    if not career_recommendation or career_recommendation.get("status") != "success":
        logger.warning(f"Invalid career recommendation for user {user_id}")
        return None
    
    user_uuid = string_to_uuid(user_id)
    top_career = career_recommendation.get("recommended_career", {})
    
    data = {
        "user_id": user_uuid,
        "recommended_career_id": top_career.get("slug"),  # Utiliser slug comme ID carrière
        "recommended_career_name": top_career.get("name"),
        "score": top_career.get("score", 0.0),
        "match_quality": top_career.get("match_quality", "Unknown"),
        "top_3_careers": career_recommendation.get("top_3_careers", []),
        "strengths": career_recommendation.get("strengths", []),
        "dimension_scores": career_recommendation.get("dimension_scores", {}),
        "related_filieres": top_career.get("related_filieres", []),
        "message": career_recommendation.get("message", ""),
        "created_at": datetime.utcnow().isoformat(),
    }
    
    try:
        # Table: career_recommendations
        # Si elle n'existe pas, la création sera silencieuse (non-bloquante)
        result = supabase.table("career_recommendations").insert(data).execute()
        data_resp, error = _unwrap_result(result)
        
        if error:
            logger.warning(f"Could not save career recommendation (table may not exist): {error}")
            return None
        
        rec_id = data_resp[0]["id"] if data_resp else None
        logger.info(
            f"Career recommendation saved | user={user_id} (uuid={user_uuid}) | "
            f"career={top_career.get('name')} | score={top_career.get('score')} | rec_id={rec_id}"
        )
        return rec_id
    
    except Exception as e:
        logger.warning(f"Error saving career recommendation: {e}")
        # Non-bloquant; on loggue mais on n'interrompt pas le flow
        return None


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


# -------------------------------------------------
# Quiz et Questions
# -------------------------------------------------
def get_active_quiz() -> Optional[Dict[str, Any]]:
    """
    Récupère le quiz actif (is_active = true, version la plus récente).
    """
    try:
        result = (
            supabase.table("orientation_quizzes")
            .select("*")
            .eq("is_active", True)
            .order("version", desc=True)
            .limit(1)
            .execute()
        )
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        return data_resp[0] if data_resp else None
    
    except Exception as e:
        logger.exception("Erreur récupération quiz actif")
        raise


def get_quiz_questions(quiz_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Récupère les questions d'un quiz, ordonnées par order_index.
    Inclut les options si présentes.
    """
    try:
        # Récupérer les questions
        if quiz_id:
            result = (
                supabase.table("orientation_quiz_questions")
                .select("*")
                .eq("quiz_id", quiz_id)
                .order("order_index", desc=False)
                .execute()
            )
        else:
            result = (
                supabase.table("orientation_quiz_questions")
                .select("*")
                .order("quiz_id", desc=False)
                .order("order_index", desc=False)
                .execute()
            )
        questions_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        questions = questions_resp or []
        
        # Pour chaque question, récupérer les options
        for question in questions:
            options_result = (
                supabase.table("orientation_quiz_options")
                .select("*")
                .eq("question_id", question["id"])
                .order("option_value", desc=False)
                .execute()
            )
            options_resp, options_error = _unwrap_result(options_result)
            if options_error:
                logger.warning(f"Erreur récupération options pour question {question['id']}: {options_error}")
                question["options"] = []
            else:
                question["options"] = options_resp or []
        
        return questions
    
    except Exception as e:
        logger.exception(f"Erreur récupération questions pour quiz {quiz_id}")
        raise


# -------------------------------------------------
# Poids des questions pour feature engineering
# Table : orientation_question_weights
# -------------------------------------------------
def get_question_feature_weights() -> Dict[str, float]:
    """
    Récupère les poids des questions depuis la DB.
    
    Returns:
        Dict[question_id: str, weight: float]
    """
    try:
        result = (
            supabase.table("orientation_question_feature_weights")
            .select("question_id, weight")
            .execute()
        )
        data_resp, error = _unwrap_result(result)
        if error:
            logger.warning(f"Erreur récupération poids questions: {error}")
            return {}  # Retourner dict vide en cas d'erreur
        
        weights = {row["question_id"]: float(row["weight"]) for row in (data_resp or [])}
        logger.info(f"Poids questions récupérés: {len(weights)} entrées")
        return weights
    
    except Exception as e:
        logger.exception("Erreur récupération poids questions")
        return {}  # Fallback vers poids par défaut


# -------------------------------------------------
# Feedback amélioré avec métriques PROA
# -------------------------------------------------
def save_orientation_feedback(
    user_id: str,
    satisfaction: int,
    changed_orientation: bool,
    success: Optional[bool] = None,
    recommended_fields: Optional[List[str]] = None,
    recommended_institutions: Optional[List[str]] = None,
    confidence_score: Optional[float] = None,
    orientation_type: Optional[str] = None,
) -> None:
    """
    Sauvegarde le feedback utilisateur avec métriques PROA améliorées.
    """
    data = {
        "user_id": user_id,
        "satisfaction": satisfaction,
        "changed_orientation": changed_orientation,
        "success": success,
        "recommended_fields": recommended_fields,
        "recommended_institutions": recommended_institutions,
        "confidence_score": confidence_score,
        "orientation_type": orientation_type,
        "created_at": datetime.utcnow().isoformat(),
    }

    try:
        result = supabase.table("orientation_feedback").insert(data).execute()
        data_resp, error = _unwrap_result(result)
        if error:
            raise RuntimeError(error)

        logger.info(f"Feedback PROA amélioré sauvegardé | user={user_id} | satisfaction={satisfaction} | confidence={confidence_score}")

    except Exception as e:
        logger.exception("Erreur sauvegarde orientation_feedback amélioré")
        raise


# -------------------------------------------------
# Questions dynamiques / Non-répétitives
# -------------------------------------------------
def get_random_questions_per_session(
    user_type: str = "all",
    count_per_dimension: int = 2,
    difficulty: int = 1,
) -> List[Dict[str, Any]]:
    """
    🎯 Récupère des questions aléatoires et équilibrées par dimension.
    
    Cette fonction garantit:
    - Questions différentes à chaque session (anti-fatigue)
    - Couverture équilibrée des dimensions (logique, social, etc.)
    - Sélection cible: N questions par dimension
    
    Args:
        user_type (str): 'all', 'bachelier', 'etudiant', or 'parent'
        count_per_dimension (int): Nombre de questions par dimension (défaut: 2)
        difficulty (int): Niveau minimum de difficulté [1-3]
    
    Returns:
        List[Dict]: Questions avec id, question_code, question_text, dimension, etc.
    
    Example:
        >>> questions = get_random_questions_per_session('bachelier', 2, 1)
        >>> len(questions)  # ~26 questions (13 dimensions × 2)
    """
    try:
        # Appeler la fonction SQL PostgreSQL
        result = supabase.rpc(
            "get_random_questions",
            {
                "p_user_type": user_type,
                "p_count_per_dimension": count_per_dimension,
                "p_difficulty": difficulty,
            }
        ).execute()
        
        data_resp, error = _unwrap_result(result)
        if error:
            logger.warning(f"Erreur appel get_random_questions | error={error}")
            # Fallback: retourner Questions simples
            return get_random_questions_simple(user_type=user_type)
        
        questions = data_resp or []
        unique_codes = set()
        unique_questions = []
        for q in questions:
            code = q.get('question_code')
            if code in unique_codes:
                logger.warning(f"Duplicate question_code removed from dynamic set: {code}")
                continue
            unique_codes.add(code)
            unique_questions.append(q)

        if len(unique_questions) != len(questions):
            logger.warning(
                f"Questions dynamiques dédupliquées | original={len(questions)} | unique={len(unique_questions)}"
            )

        questions = unique_questions
        logger.info(
            f"Questions dynamiques récupérées | user_type={user_type} | "
            f"count={len(questions)} | dimensions_expected={count_per_dimension}"
        )
        
        return questions
    
    except Exception as e:
        logger.exception(f"Erreur récupération questions dynamiques: {str(e)}")
        # Fallback: retourner quelques questions simples
        return get_random_questions_simple(user_type=user_type, limit=15)


def get_random_questions_simple(
    user_type: str = "all",
    limit: int = 15,
) -> List[Dict[str, Any]]:
    """
    🎯 Version simple: sélection aléatoire sans garantie d'équilibre dimensionnel.
    
    Fallback si la fonction SQL n'est pas disponible.
    
    Args:
        user_type (str): 'all', 'bachelier', 'etudiant', or 'parent'
        limit (int): Nombre de questions à retourner
    
    Returns:
        List[Dict]: Questions aléatoires
    """
    try:
        result = supabase.rpc(
            "get_random_questions_simple",
            {
                "p_user_type": user_type,
                "p_limit": limit,
            }
        ).execute()
        
        data_resp, error = _unwrap_result(result)
        if error:
            logger.warning(f"Erreur get_random_questions_simple | error={error}")
            return []
        
        questions = data_resp or []
        logger.info(f"Questions aléatoires simples récupérées | count={len(questions)}")
        
        return questions
    
    except Exception as e:
        logger.exception(f"Erreur récupération questions simples: {str(e)}")
        return []

