from fastapi import APIRouter, HTTPException, status, Depends
import logging
from pydantic import BaseModel
from typing import Dict, Any
import os
import json
import uuid  # 🎯 Pour générer session_id
from datetime import datetime

from core.rule_engine import compute_profile
from core.feature_engineering import build_features
from core.monitoring import get_health_status, analyze_user_progression
from core.recommendations import compute_recommended_fields, compute_recommended_institutions
from core.career_recommendations import compute_career_recommendations  # 🎯 NEW
from core.output_formatter import ProaResponse
from core.auth import get_current_user_profile, get_user_profile_dict  # 🔐 NEW - Authentification JWT
from models.profile import OrientationProfile
from models.quiz import QuizSubmission
from db.repository import (
    save_quiz_responses,
    save_orientation_profile,
    get_orientation_history,
    save_orientation_feedback,
    get_active_quiz,
    get_quiz_questions,
    get_random_questions_per_session,  # ✨ NEW - Questions dynamiques
    get_random_questions_simple,  # ✨ NEW - Fallback simple
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

        # 6️⃣ Sauvegarde profil (+ retour profile_id pour PORA)
        profile_id = save_orientation_profile(
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

        # ✅ Standardiser la réponse avec ProaResponse (+ profile_id pour traçabilité)
        return ProaResponse.compute_orientation(
            user_id=payload.user_id,
            profile=vector,
            confidence=confidence,
            recommended_fields=recommended.get("recommended_fields", []),
            quiz_version=payload.quiz_version,
            profile_id=profile_id,  # 🔗 PORA pourra tracer les recommandations
            field_scores=recommended.get("field_scores", {}),
            insight=recommended.get("insight", "")
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
# 🎯 CAREER RECOMMENDATIONS — NEW ENDPOINT
# -------------------------------------------------
@router.post("/career-recommendations", status_code=201)
def get_career_recommendations(payload: QuizSubmission):
    """
    Endpoint pour recommandations intelligentes de carrière.
    
    Transforme les réponses du quiz en profil de carrière.
    
    Input:
    {
        "user_id": "user123",
        "quiz_version": "2.0",
        "responses": {
            "Q1": 4,
            "Q2": 3,
            "Q3": 4,
            ...
        }
    }
    
    Output:
    {
        "status": "success",
        "recommended_career": {
            "name": "Développeur Informatique",
            "icon": "👨‍💻",
            "score": 0.78,
            "related_filieres": [...]
        },
        "top_3_careers": [...],
        "strengths": [
            {"dimension": "logique", "score": 0.82, "emoji": "🧠"}
        ],
        "dimension_scores": {...},
        "message": "..."
    }
    """
    try:
        logger.info(
            "🎯 Career recommendations | user=%s | quiz=%s | #responses=%d",
            payload.user_id,
            payload.quiz_version,
            len(payload.responses),
        )
        
        # Validation
        if not payload.responses or len(payload.responses) == 0:
            raise HTTPException(status_code=400, detail="Responses cannot be empty")
        
        # Calculer les recommandations de carrière avec contexte user_type
        result = compute_career_recommendations(
            quiz_responses=payload.responses,
            user_type=payload.user_type  # 🎯 Passer le user_type
        )
        
        if result.get("status") != "success":
            logger.error("Career computation failed: %s", result.get("message"))
            raise HTTPException(status_code=500, detail=result.get("message", "Computation failed"))
        
        # Log des résultats
        top_career = result.get("recommended_career", {})
        logger.info(
            "✅ Career computed | user=%s | user_type=%s | top_career=%s | score=%.2f",
            payload.user_id,
            payload.user_type,  # 🎯 Log user_type
            top_career.get("name"),
            top_career.get("score", 0)
        )
        
        # Optionnel: persister les résultats
        try:
            save_career_profile(
                user_id=payload.user_id,
                career_recommendation=result
            )
        except Exception as e:
            logger.warning("Failed to save career profile: %s", e)
            # Non-bloquant; retourner quand même les résultats
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Career computation error: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la recommandation de carrière"
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


# -------------------------------------------------
# 🎯 QUESTIONS DYNAMIQUES / NON-RÉPÉTITIVES
# -------------------------------------------------
@router.get("/questions/dynamic")
def get_dynamic_questions(
    user_type: str = "all",
    count_per_dimension: int = 2,
    difficulty: int = 1,
):
    """
    🎯 Récupère des questions aléatoires + équilibrées par session.
    
    ✨ Ça élimine l'ennui utilisateur en garantissant:
    - Questions DIFFÉRENTES à chaque session (anti-fatigue)
    - COUVERTURE ÉQUILIBRÉE des dimensions (logique, social, tech, etc.)
    - Scoring FIABLE grâce à l'équilibre dimensionnel
    
    Query Parameters:
    - user_type: 'all' | 'bachelier' | 'etudiant' | 'parent' (default: 'all')
    - count_per_dimension: Questions par dimension (default: 2)
    - difficulty: Niveau minimum [1-3] (default: 1)
    
    Example:
    /questions/dynamic?user_type=bachelier&count_per_dimension=2&difficulty=1
    
    Response:
    {
      "user_type": "bachelier",
      "session_id": "uuid-auto-generated",
      "questions": [
        {
          "id": "uuid",
          "question_code": "q_passion_tech",
          "question_text": "Je suis passionné par la technologie",
          "question_type": "likert",
          "dimension": "tech",
          "difficulty_level": 1
        },
        ...
      ],
      "dimension_coverage": {"tech": 2, "logique": 2, ...},
      "total_questions": 26
    }
    """
    try:
        # Récupérer les questions dynamiques
        questions = get_random_questions_per_session(
            user_type=user_type,
            count_per_dimension=count_per_dimension,
            difficulty=difficulty,
        )
        
        if not questions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aucune question trouvée pour cette session"
            )
        
        # Calculer la couverture dimensionnelle
        dimension_coverage = {}
        for q in questions:
            dimension = q.get("dimension", "general")
            dimension_coverage[dimension] = dimension_coverage.get(dimension, 0) + 1
        
        # Générer un session_id unique pour cette session
        session_id = str(uuid.uuid4())  # ✅ Utilise Python UUID directement
        
        logger.info(
            f"Session dynamique créée | user_type={user_type} | "
            f"questions={len(questions)} | dimensions={len(dimension_coverage)}"
        )
        
        return {
            "success": True,
            "user_type": user_type,
            "session_id": session_id or str(uuid.uuid4()),  # Fallback à Python UUID
            "questions": questions,
            "dimension_coverage": dimension_coverage,
            "total_questions": len(questions),
            "note": "😎 Chaque session = questions différentes! Quiz plus engageant, scoring plus fiable",
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur récupération questions dynamiques: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur serveur interne"
        )


# -------------------------------------------------
# Questions simples (fallback ou usage direct)
# -------------------------------------------------
@router.get("/questions/simple")
def get_simple_random_questions(user_type: str = "all", limit: int = 15):
    """
    🎯 Version simple: sélection aléatoire SANS garantie d'équilibre.
    
    À utiliser comme fallback si get_random_questions_per_session échoue.
    
    Query Parameters:
    - user_type: 'all' | 'bachelier' | 'etudiant' | 'parent'
    - limit: Nombre total de questions (default: 15)
    """
    try:
        questions = get_random_questions_simple(user_type=user_type, limit=limit)
        
        if not questions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aucune question trouvée"
            )
        
        return {
            "success": True,
            "user_type": user_type,
            "questions": questions,
            "total_questions": len(questions),
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur questions simples: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur serveur interne"
        )


# -------------------------------------------------
# 🧠 QUIZ ADAPTATIF VIA JWT — SYSTÈME INTELLIGENT
# -------------------------------------------------
def get_adaptive_quiz(user_type: str) -> Dict[str, Any]:
    """
    Génère un quiz adapté automatiquement selon le type d'utilisateur.

    Stratégie d'adaptation :
    - bachelier: 15 questions (exploration complète)
    - etudiant: 10 questions (réorientation/spécialisation)
    - parent: 5 questions (guidage stratégique)

    Args:
        user_type: Type d'utilisateur ('bachelier', 'etudiant', 'parent')

    Returns:
        Dict avec user_type et questions adaptées
    """
    try:
        # Configuration adaptative par type d'utilisateur
        quiz_configs = {
            "bachelier": {
                "question_count": 15,
                "mode": "exploration",
                "description": "Découverte complète de vos intérêts et aptitudes"
            },
            "etudiant": {
                "question_count": 10,
                "mode": "optimization",
                "description": "Réorientation ou spécialisation dans votre parcours"
            },
            "parent": {
                "question_count": 5,
                "mode": "guidance",
                "description": "Guidage stratégique pour l'orientation de votre enfant"
            }
        }

        # Configuration par défaut si type inconnu
        config = quiz_configs.get(user_type, quiz_configs["bachelier"])

        # Récupérer les questions depuis la base de données
        all_questions = get_quiz_questions()

        if not all_questions:
            logger.warning("Aucune question trouvée en base de données")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aucune question disponible"
            )

        # Sélectionner les questions adaptées
        if user_type == "bachelier":
            # Pour bachelier: questions équilibrées sur tous les domaines
            selected_questions = get_random_questions_per_session(
                user_type="all",
                count_per_dimension=3,  # 3 questions par dimension
                difficulty=1
            )
        elif user_type == "etudiant":
            # Pour étudiant: focus sur optimisation et spécialisation
            selected_questions = get_random_questions_per_session(
                user_type="etudiant",
                count_per_dimension=2,  # 2 questions par dimension
                difficulty=2  # Niveau légèrement supérieur
            )
        elif user_type == "parent":
            # Pour parent: questions essentielles seulement
            selected_questions = get_random_questions_simple(
                user_type="parent",
                count=5  # 5 questions essentielles
            )
        else:
            # Fallback: questions générales
            selected_questions = get_random_questions_simple(
                user_type="all",
                count=config["question_count"]
            )

        # Générer un ID de session unique pour ce quiz
        session_id = str(uuid.uuid4())

        logger.info(
            f"Quiz adaptatif généré | type={user_type} | questions={len(selected_questions)} | session={session_id}"
        )

        return {
            "user_type": user_type,
            "session_id": session_id,
            "question_count": len(selected_questions),
            "mode": config["mode"],
            "description": config["description"],
            "questions": selected_questions
        }

    except Exception as e:
        logger.exception(f"Erreur génération quiz adaptatif | type={user_type}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la génération du quiz adaptatif"
        )


@router.get("/quiz")
def get_adaptive_quiz_via_jwt(user_profile = Depends(get_current_user_profile)):
    """
    🧠 Endpoint intelligent pour obtenir un quiz adapté automatiquement.

    Le système détecte automatiquement le type d'utilisateur depuis le JWT
    et génère un quiz personnalisé sans aucun choix manuel.

    Headers requis:
    - Authorization: Bearer <jwt_token>

    Stratégie d'adaptation automatique :
    - bachelier → 15 questions (exploration)
    - etudiant → 10 questions (réorientation)
    - parent → 5 questions (guidage)

    Response:
    {
        "user_type": "bachelier",
        "session_id": "uuid",
        "question_count": 15,
        "mode": "exploration",
        "description": "...",
        "questions": [...]
    }
    """
    try:
        # Récupérer le type d'utilisateur depuis le profil
        user_type = user_profile.user_type or "bachelier"  # Default to bachelier

        logger.info(
            f"🧠 Quiz adaptatif demandé | user={user_profile.id} | type={user_type}"
        )

        # Générer le quiz adapté
        quiz_data = get_adaptive_quiz(user_type)

        return quiz_data

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur quiz adaptatif | user={user_profile.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la génération du quiz adaptatif"
        )


# -------------------------------------------------
# 🔐 RECOMMENDATIONS VIA JWT — POUR FLUTTER
# -------------------------------------------------
@router.get("/recommendations")
def get_recommendations_via_jwt(
    user_profile = Depends(get_current_user_profile),
    orientation_type: str = "field",
    top_n: int = 5
):
    """
    🔐 Endpoint sécurisé pour obtenir des recommandations personnalisées via JWT.

    Le profil utilisateur est automatiquement récupéré depuis le token JWT
    dans l'Authorization header.

    Headers requis:
    - Authorization: Bearer <jwt_token>

    Query Parameters:
    - orientation_type: 'field' ou 'institution' (default: 'field')
    - top_n: Nombre de recommandations (default: 5)

    Response:
    {
        "user_id": "uuid",
        "user_profile": {...},
        "recommendations": {
            "recommended_fields": [...],
            "field_scores": {...},
            "insight": "..."
        },
        "timestamp": "2024-01-01T12:00:00Z"
    }
    """
    try:
        logger.info(
            f"🔐 JWT Recommendations | user={user_profile.id} | type={orientation_type} | top_n={top_n}"
        )

        # Convertir le profil utilisateur en format compatible avec les recommandations
        profile_dict = get_user_profile_dict(user_profile)

        # Générer les recommandations basées sur le profil utilisateur
        if orientation_type == "institution":
            recommendations = compute_recommended_institutions(profile_dict, top_n=top_n)
        else:
            recommendations = compute_recommended_fields(profile_dict, top_n=top_n)

        # Préparer la réponse
        response = {
            "user_id": user_profile.id,
            "user_profile": profile_dict,
            "recommendations": recommendations,
            "orientation_type": orientation_type,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        logger.info(
            f"✅ Recommendations générées | user={user_profile.id} | count={len(recommendations.get('recommended_fields', []))}"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur génération recommandations JWT | user={user_profile.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la génération des recommandations"
        )


# -------------------------------------------------
# 👤 PROFIL UTILISATEUR VIA JWT — POUR FLUTTER
# -------------------------------------------------
@router.get("/profile")
def get_user_profile_via_jwt(user_profile = Depends(get_current_user_profile)):
    """
    🔐 Endpoint pour récupérer le profil utilisateur depuis JWT.

    Utilisé par le frontend PORA pour détecter automatiquement
    le type d'utilisateur et lancer le bon quiz.

    Headers requis:
    - Authorization: Bearer <jwt_token>

    Response:
    {
        "user_id": "uuid",
        "user_type": "bachelier", // "bachelier" | "etudiant" | "parent"
        "email": "user@example.com",
        "nom": "Dupont",
        "prenom": "Jean"
    }
    """
    try:
        logger.info(f"👤 Profil demandé | user={user_profile.id}")

        return {
            "user_id": user_profile.id,
            "user_type": user_profile.user_type or "bachelier",  # Default to bachelier
            "email": user_profile.email,
            "nom": user_profile.nom,
            "prenom": user_profile.prenom,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Erreur récupération profil | user={user_profile.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erreur lors de la récupération du profil"
        )
