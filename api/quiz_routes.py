from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from models.quiz import (
    UserType, QuizResponse, QuizQuestion, QuizMetadata, 
    QuizOption, QuizSubmissionRequest, OrientationType,
    ScoringMethod, QuizSubmissionResponse, OrientationComputeResponse
)
from models.proa import ProaComputeRequest
from db.quiz_repo import QuizRepository
from core.utils import normalize_and_validate, get_bac_track, is_valid_bac_code
from core.feature_engineering import build_features
from core.recommendation_engine import get_recommendations
from core.domain_scoring import DomainScoringEngine
from core.confidence_scoring import calculate_confidence, add_confidence_to_response
from core.output_formatter import ProaResponse
from core.monitoring import record_scoring_metric, ScoringMetrics

logger = logging.getLogger("orientation.quiz_api")
router = APIRouter(prefix="/orientation", tags=["quiz"])


def get_quiz_repo() -> QuizRepository:
    """Dependency injection for QuizRepository"""
    from db.repository import supabase
    return QuizRepository(supabase)


# ========================================
# ENDPOINT 1: GET QUIZ BY USER_TYPE
# ========================================

@router.get("/quiz/{user_type}", response_model=QuizResponse)
def get_quiz_by_user_type(
    user_type: UserType,
    quiz_repo: QuizRepository = Depends(get_quiz_repo),
    version: str = "2.0"
):
    """
    Load quiz adapted to user type - Version V2.
    
    ⚡ OPTIMIZED:
    - Single DB query to get questions + options
    - No N+1 problem (25 queries → 1 query!)
    - Support échelle 1-5
    
    Path Parameters:
      user_type: bachelier | etudiant | parent
      version: Version du quiz (1.0 ou 2.0)
    
    Returns:
      Quiz metadata + questions with options (1-5 scale)
    """
    try:
        logger.info(f"Fetching quiz for user_type={user_type.value} (version={version})")
        
        # 1. Get quiz metadata
        quiz = quiz_repo.get_quiz_by_user_type(user_type.value, version=version)
        if not quiz:
            logger.warning(f"Quiz not found for {user_type.value} version {version}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Quiz not found for user_type={user_type.value} version={version}"
            )
        
        # 2. Get questions WITH options (⚡ SINGLE QUERY!)
        questions_raw = quiz_repo.get_questions_with_options(quiz['id'])
        if not questions_raw:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No questions found for this quiz"
            )
        
        logger.info(f"Loaded {len(questions_raw)} questions with options (1 query, no N+1)")
        
        # 3. Build response with V2 enhancements
        questions = []
        for q in questions_raw:
            options_raw = q.get("orientation_quiz_options", [])
            
            # Support échelle 1-5
            options = [
                QuizOption(
                    id=opt['id'],
                    text=opt['text'],
                    value=opt.get('value', idx + 1)  # Default 1-5
                )
                for idx, opt in enumerate(options_raw)
            ]
            
            question = QuizQuestion(
                id=q['id'],
                question_code=q['question_code'],
                text=q['text'],
                domain=q.get('domain', 'general'),
                options=options,
                order_index=q.get('order_index', 0),
                category=q.get('category'),
                weight=float(q.get('weight', 1.0)),
                required=q.get('required', True)
            )
            questions.append(question)
        
        # 4. Build response
        quiz_metadata = QuizMetadata(
            id=quiz['id'],
            quiz_code=quiz['quiz_code'],
            user_type=UserType(quiz['user_type']),
            title=quiz['title'],
            description=quiz.get('description', ''),
            total_questions=len(questions),
            version=version,
            scoring_method=ScoringMethod.AUTO,
            created_at=quiz.get('created_at'),
            updated_at=quiz.get('updated_at')
        )
        
        response = QuizResponse(
            quiz=quiz_metadata,
            questions=questions,
            version="2.0"
        )
        
        logger.info(f"Quiz loaded successfully (V2)")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error loading quiz: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error loading quiz"
        )


# ========================================
# ENDPOINT 2: SUBMIT QUIZ (V2 avec scoring amélioré)
# ========================================

@router.post("/compute", status_code=200, response_model=OrientationComputeResponse)
async def compute_orientation(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    quiz_repo: QuizRepository = Depends(get_quiz_repo)
):
    """
    Compute orientation profile with V2 scoring engine.
    
    ✨ V2 IMPROVEMENTS:
    - Support échelle 1-5
    - Bac congolais integration
    - Scoring vectoriel dimensionnel
    - Confidence scoring amélioré
    - Support codes sémantiques
    
    Request:
      {
        "user_id": "user@example.com",
        "user_type": "bachelier",
        "quiz_code": "quiz_bachelier_2025_v2",
        "responses": {"q1": 5, "q2": 4, ..., "q24": 3},
        "bac_code": "C",
        "scoring_method": "auto",
        "session_id": "session_123",
        "response_metadata": {...}
      }
    
    Response:
      {
        "status": "success",
        "user_id": "...",
        "profile_id": "...",
        "scoring_method": "v2_vectorial",
        "confidence": 0.92,
        "recommended_fields": [...],
        "insight": "...",
        "computation_time_ms": 145
      }
    """
    start_time = datetime.utcnow()
    
    try:
        user_id = payload.get('user_id')
        user_type = payload.get('user_type', 'bachelier')
        quiz_code = payload.get('quiz_code', 'quiz_bachelier_v2')
        responses_raw = payload.get('responses', {})
        bac_code = payload.get('bac_code')
        scoring_method = payload.get('scoring_method', 'auto')
        session_id = payload.get('session_id')
        response_metadata = payload.get('response_metadata')
        
        logger.info(f"🚀 Computing orientation V2 for user={user_id}, type={user_type}")
        if bac_code:
            logger.info(f"   Bac code: {bac_code}")
        
        # 1. Validate required fields
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="user_id is required"
            )
        
        if not responses_raw:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Responses cannot be empty"
            )
        
        # 2. Normalize & validate responses (support 1-5)
        try:
            normalized_responses = normalize_and_validate(responses_raw)
            logger.info(f"✅ Responses normalized: {len(normalized_responses)} entries")
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )
        
        # 3. Validate bac code if provided
        bac_track = None
        if bac_code:
            if not is_valid_bac_code(bac_code):
                logger.warning(f"Invalid bac code: {bac_code}, continuing without bac adjustment")
                bac_code = None
            else:
                bac_track = get_bac_track(bac_code)
                logger.info(f"✅ Bac validated: {bac_code} ({bac_track})")
        
        # 4. Build features with V2 engine
        features_result = build_features(
            responses=normalized_responses,
            orientation_type="field",
            response_metadata=response_metadata,
            bac_code=bac_code,
            return_dimensions=True
        )
        
        features = features_result.get("features", {})
        dimension_vector = features_result.get("dimension_vector", {})
        
        logger.info(f"📊 Features computed: {len(features)} domains")
        logger.info(f"   Dimension vector: {dimension_vector}")
        
        # 5. Calculate confidence score
        confidence_result = calculate_confidence(
            responses=normalized_responses,
            expected_question_count=24,
            dimension_scores=dimension_vector,
            domain_scores=features_result.get("domain_scores", {}),
            bac_code=bac_code,
            use_ml=True
        )
        
        confidence_score = confidence_result.get("confidence_score", 0.7)
        logger.info(f"🎯 Confidence score: {confidence_score:.2%} ({confidence_result.get('reliability_label')})")
        
        # 6. Get recommendations with V2 engine
        recommendations = await get_recommendations(
            user_id=user_id,
            responses=normalized_responses,
            user_type=user_type,
            bac_code=bac_code,
            use_v2=True
        )
        
        # 7. Format response with V2 formatter
        response = ProaResponse.compute_orientation(
            user_id=user_id,
            profile=list(dimension_vector.values()) if dimension_vector else [],
            confidence=confidence_score,
            recommended_fields=recommendations.get("recommended_fields", []),
            quiz_version="2.0",
            profile_id=recommendations.get("profile_id"),
            field_scores=recommendations.get("field_scores", {}),
            insight=recommendations.get("insight", ""),
            scoring_method="v2_vectorial",
            computation_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            context={
                "user_type": user_type,
                "bac_type": bac_code,
                "bac_track": bac_track,
                "dominant_cluster": recommendations.get("dominant_cluster"),
                "confidence": confidence_score,
                "scoring_version": "2.0"
            }
        )
        
        # 8. Add confidence metadata
        response = add_confidence_to_response(response, confidence_result)
        
        # 9. Save to history in background
        background_tasks.add_task(
            _save_orientation_history,
            user_id=user_id,
            session_id=session_id,
            responses=normalized_responses,
            features=features,
            dimension_vector=dimension_vector,
            confidence_result=confidence_result,
            recommendations=recommendations,
            bac_code=bac_code
        )
        
        # 10. Record metrics
        background_tasks.add_task(
            record_scoring_metric,
            ScoringMetrics(
                method="v2_vectorial",
                confidence=confidence_score,
                computation_time_ms=response.get("computation_time_ms", 0),
                domains_count=len(features),
                skills_count=len([k for k in features.keys() if k.startswith("skill_")]),
                feature_coverage=len(features) / 20 if features else 0,
                has_bac=bac_code is not None,
                dominant_cluster=recommendations.get("dominant_cluster")
            )
        )
        
        logger.info(f"✅ Orientation computed in {response.get('computation_time_ms', 0):.0f}ms")
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error computing orientation: {e}")
        return ProaResponse.error(
            message=str(e),
            code="COMPUTATION_ERROR",
            user_id=payload.get('user_id')
        )


# ========================================
# ENDPOINT 3: GET QUIZ BY CODE (V2)
# ========================================

@router.get("/quiz/by-code/{quiz_code}", response_model=QuizResponse)
def get_quiz_by_code(
    quiz_code: str,
    quiz_repo: QuizRepository = Depends(get_quiz_repo)
):
    """
    Get quiz by its code (e.g., "quiz_bachelier_2025_v2").
    Useful for direct quiz access without knowing user_type.
    """
    try:
        logger.info(f"Fetching quiz by code: {quiz_code}")
        
        quiz = quiz_repo.get_quiz_by_code(quiz_code)
        if not quiz:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Quiz not found for code={quiz_code}"
            )
        
        questions_raw = quiz_repo.get_questions_with_options(quiz['id'])
        if not questions_raw:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No questions found for this quiz"
            )
        
        questions = []
        for q in questions_raw:
            options_raw = q.get("orientation_quiz_options", [])
            options = [
                QuizOption(
                    id=opt['id'],
                    text=opt['text'],
                    value=opt.get('value', idx + 1)
                )
                for idx, opt in enumerate(options_raw)
            ]
            
            questions.append(QuizQuestion(
                id=q['id'],
                question_code=q['question_code'],
                text=q['text'],
                domain=q.get('domain', 'general'),
                options=options,
                order_index=q.get('order_index', 0),
                category=q.get('category'),
                weight=float(q.get('weight', 1.0))
            ))
        
        quiz_metadata = QuizMetadata(
            id=quiz['id'],
            quiz_code=quiz['quiz_code'],
            user_type=UserType(quiz['user_type']),
            title=quiz['title'],
            description=quiz.get('description', ''),
            total_questions=len(questions),
            version=quiz.get('version', '2.0'),
            scoring_method=ScoringMethod.AUTO
        )
        
        return QuizResponse(
            quiz=quiz_metadata,
            questions=questions,
            version="2.0"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error loading quiz by code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error loading quiz"
        )


# ========================================
# ENDPOINT 4: GET QUIZ VERSIONS
# ========================================

@router.get("/quiz/versions")
def get_quiz_versions(
    quiz_repo: QuizRepository = Depends(get_quiz_repo)
):
    """
    Get available quiz versions for each user type.
    """
    try:
        versions = {
            "bachelier": ["1.0", "2.0"],
            "etudiant": ["1.0", "2.0"],
            "parent": ["1.0"]
        }
        
        # Try to get actual versions from DB
        try:
            result = quiz_repo.get_available_versions()
            if result:
                versions = result
        except Exception:
            pass
        
        return {
            "status": "success",
            "versions": versions,
            "default": "2.0",
            "scales": {
                "1.0": {"min": 1, "max": 4, "description": "Échelle 1-4 (legacy)"},
                "2.0": {"min": 1, "max": 5, "description": "Échelle 1-5 (recommandée)"}
            }
        }
        
    except Exception as e:
        logger.exception(f"Error getting quiz versions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error getting quiz versions"
        )


# ========================================
# ENDPOINT 5: HEALTH CHECK
# ========================================

@router.get("/health")
def health_check():
    """
    Health check endpoint for the orientation service.
    """
    return {
        "status": "healthy",
        "service": "proa-orientation",
        "version": "2.0",
        "features": {
            "scoring_v2": True,
            "bac_support": True,
            "semantic_questions": True,
            "confidence_scoring": True
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# ========================================
# BACKGROUND TASKS
# ========================================

async def _save_orientation_history(
    user_id: str,
    session_id: Optional[str],
    responses: Dict[str, int],
    features: Dict[str, float],
    dimension_vector: Dict[str, float],
    confidence_result: Dict[str, Any],
    recommendations: Dict[str, Any],
    bac_code: Optional[str]
):
    """
    Sauvegarde l'historique d'orientation en arrière-plan.
    """
    try:
        from db.repository import supabase
        
        history_entry = {
            "user_id": user_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "responses": responses,
            "features": features,
            "dimension_vector": dimension_vector,
            "confidence_score": confidence_result.get("confidence_score"),
            "reliability_label": confidence_result.get("reliability_label"),
            "recommended_fields": [
                {
                    "name": f.get("field_name"),
                    "score": f.get("score"),
                    "cluster": f.get("cluster")
                }
                for f in recommendations.get("recommended_fields", [])[:5]
            ],
            "dominant_cluster": recommendations.get("dominant_cluster"),
            "bac_code": bac_code,
            "scoring_method": "v2_vectorial",
            "version": "2.0"
        }
        
        result = supabase.table("orientation_history").insert(history_entry).execute()
        logger.debug(f"History saved for user {user_id}")
        
    except Exception as e:
        logger.warning(f"Could not save orientation history: {e}")


# ========================================
# LEGACY ENDPOINT (Compatibility)
# ========================================

@router.post("/compute-legacy", status_code=201)
def compute_orientation_legacy(payload: Dict[str, Any]):
    """
    Legacy endpoint for backward compatibility (V1).
    Use /compute for V2.
    """
    logger.warning("Legacy compute endpoint called - consider migrating to V2")
    
    try:
        if not payload.get('responses'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Responses cannot be empty"
            )
        
        normalized_responses = normalize_and_validate(payload['responses'])
        user_type = payload.get('user_type', 'bachelier')
        
        return {
            "status": "success",
            "user_id": payload.get('user_id'),
            "user_type": user_type,
            "message": "Legacy orientation computed (V1)",
            "warning": "This endpoint is deprecated. Please use /compute for V2 features.",
            "debug": {
                "responses_count": len(normalized_responses),
                "user_type": user_type
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error in legacy compute: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error computing orientation"
        )