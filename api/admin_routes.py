from fastapi import APIRouter, HTTPException, status, Depends, Header, Query
import logging
from typing import Optional, Dict, Any, List
import os
from datetime import datetime

from models.quiz import UserType, OrientationType, ScoringMethod
from db.admin_repo import AdminRepository

logger = logging.getLogger("orientation.admin")
router = APIRouter(prefix="/admin/orientation", tags=["admin"])

# Read admin token from environment (.env)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "your_secret_admin_token")


def get_admin_repo() -> AdminRepository:
    """Dependency injection for AdminRepository"""
    from db.repository import supabase
    return AdminRepository(supabase)


# ========================================
# MIDDLEWARE: Admin Auth
# ========================================

def verify_admin_token(x_admin_token: Optional[str] = Header(None)):
    """Verify admin token from .env (NOT hardcoded!)"""
    if not x_admin_token:
        logger.warning("Admin access attempt without token")
        raise HTTPException(status_code=401, detail="Admin token required")
    
    if x_admin_token != ADMIN_TOKEN:
        logger.warning(f"Admin access attempt with invalid token")
        raise HTTPException(status_code=403, detail="Invalid token")
    
    logger.info("Admin authenticated")


# ========================================
# QUIZ MANAGEMENT
# ========================================

@router.post("/quiz", status_code=201)
def create_quiz(
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Create new quiz - Version V2.
    
    Request:
      {
        "quiz_code": "quiz_bachelier_2025_v2",
        "user_type": "bachelier",
        "title": "Quiz d'Orientation V2 - Filière",
        "description": "Découvrez les filières qui correspondent à votre profil",
        "total_questions": 24,
        "version": "2.0",
        "scoring_method": "v2_vectorial",
        "scale_min": 1,
        "scale_max": 5,
        "is_active": true
      }
    """
    try:
        logger.info(f"Creating quiz V2: {payload.get('quiz_code')}")
        
        quiz = admin_repo.create_quiz(
            quiz_code=payload['quiz_code'],
            user_type=payload['user_type'],
            title=payload['title'],
            description=payload.get('description', ''),
            total_questions=payload.get('total_questions', 24),
            version=payload.get('version', '2.0'),
            scoring_method=payload.get('scoring_method', 'v2_vectorial'),
            scale_min=payload.get('scale_min', 1),
            scale_max=payload.get('scale_max', 5),
            is_active=payload.get('is_active', True)
        )
        
        logger.info(f"Quiz created V2: {quiz['id']}")
        return {
            "status": "success",
            "message": "Quiz created successfully",
            "quiz": quiz
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error creating quiz: {str(e)}")


@router.get("/quiz", status_code=200)
def list_quizzes(
    user_type: Optional[str] = Query(None, description="Filter by user type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    version: Optional[str] = Query(None, description="Filter by version"),
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    List all quizzes with optional filters.
    """
    try:
        quizzes = admin_repo.list_quizzes(
            user_type=user_type,
            is_active=is_active,
            version=version
        )
        
        logger.info(f"Retrieved {len(quizzes)} quizzes")
        return {
            "status": "success",
            "total": len(quizzes),
            "quizzes": quizzes
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing quizzes: {str(e)}")


@router.get("/quiz/{quiz_id}", status_code=200)
def get_quiz(
    quiz_id: str,
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Get quiz by ID with full details.
    """
    try:
        quiz = admin_repo.get_quiz_full(quiz_id)
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        
        return {
            "status": "success",
            "quiz": quiz
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting quiz: {str(e)}")


@router.put("/quiz/{quiz_id}", status_code=200)
def update_quiz(
    quiz_id: str,
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Update quiz details.
    
    Request:
      {
        "title": "Updated Title",
        "description": "Updated description",
        "is_active": true,
        "version": "2.1"
      }
    """
    try:
        updated = admin_repo.update_quiz(quiz_id, payload)
        
        logger.info(f"Quiz updated: {quiz_id}")
        return {
            "status": "success",
            "message": "Quiz updated successfully",
            "quiz": updated
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating quiz: {str(e)}")


@router.delete("/quiz/{quiz_id}", status_code=200)
def delete_quiz(
    quiz_id: str,
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Soft delete quiz (set active=false) or hard delete if force=true.
    """
    try:
        force = False  # TODO: Add query param for force delete
        
        if force:
            admin_repo.hard_delete_quiz(quiz_id)
            message = "Quiz permanently deleted"
        else:
            admin_repo.soft_delete_quiz(quiz_id)
            message = "Quiz deactivated"
        
        logger.info(f"Quiz deleted: {quiz_id} (force={force})")
        return {
            "status": "success",
            "message": message
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting quiz: {str(e)}")


# ========================================
# QUESTION MANAGEMENT
# ========================================

@router.post("/question", status_code=201)
def add_question(
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Add question to quiz - V2 with enhanced fields.
    
    Request:
      {
        "quiz_id": "...",
        "question_code": "q1",
        "text": "J'aime résoudre des problèmes complexes",
        "domain": "logic",
        "category": "technical",
        "order_index": 1,
        "weight": 1.0,
        "required": true
      }
    """
    try:
        # Normalize question code
        question_code = str(payload['question_code']).lower().strip()
        
        question = admin_repo.create_question(
            quiz_id=payload['quiz_id'],
            question_code=question_code,
            text=payload['text'],
            domain=payload.get('domain', 'general'),
            category=payload.get('category'),
            order_index=payload.get('order_index', 1),
            weight=float(payload.get('weight', 1.0)),
            required=payload.get('required', True)
        )
        
        logger.info(f"Question added: {question_code} to quiz {payload['quiz_id']}")
        return {
            "status": "success",
            "message": "Question added successfully",
            "question": question
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding question: {str(e)}")


@router.put("/question/{question_id}", status_code=200)
def update_question(
    question_id: str,
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Update question details.
    """
    try:
        updated = admin_repo.update_question(question_id, payload)
        
        logger.info(f"Question updated: {question_id}")
        return {
            "status": "success",
            "message": "Question updated successfully",
            "question": updated
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating question: {str(e)}")


@router.delete("/question/{question_id}", status_code=200)
def delete_question(
    question_id: str,
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Delete question and its options.
    """
    try:
        admin_repo.delete_question(question_id)
        
        logger.info(f"Question deleted: {question_id}")
        return {
            "status": "success",
            "message": "Question deleted successfully"
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting question: {str(e)}")


# ========================================
# OPTION MANAGEMENT
# ========================================

@router.post("/option", status_code=201)
def add_option(
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Add option to question - V2 with enhanced fields.
    
    Request:
      {
        "question_id": "...",
        "text": "Tout à fait d'accord",
        "value": 5,
        "order_index": 1
      }
    """
    try:
        option = admin_repo.create_option(
            question_id=payload['question_id'],
            text=payload['text'],
            value=payload['value'],
            order_index=payload.get('order_index', 1)
        )
        
        logger.info(f"Option added: value={payload['value']} to question {payload['question_id']}")
        return {
            "status": "success",
            "message": "Option added successfully",
            "option": option
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding option: {str(e)}")


@router.put("/option/{option_id}", status_code=200)
def update_option(
    option_id: str,
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Update option details.
    """
    try:
        updated = admin_repo.update_option(option_id, payload)
        
        logger.info(f"Option updated: {option_id}")
        return {
            "status": "success",
            "message": "Option updated successfully",
            "option": updated
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error updating option: {str(e)}")


@router.delete("/option/{option_id}", status_code=200)
def delete_option(
    option_id: str,
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Delete option.
    """
    try:
        admin_repo.delete_option(option_id)
        
        logger.info(f"Option deleted: {option_id}")
        return {
            "status": "success",
            "message": "Option deleted successfully"
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting option: {str(e)}")


# ========================================
# DOMAIN MAPPING MANAGEMENT
# ========================================

@router.post("/domain-mapping", status_code=201)
def add_domain_mapping(
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Add domain mapping for a question.
    
    Request:
      {
        "question_code": "q1",
        "domain_id": "uuid",
        "weight": 0.8
      }
    """
    try:
        mapping = admin_repo.create_domain_mapping(
            question_code=payload['question_code'],
            domain_id=payload['domain_id'],
            weight=float(payload.get('weight', 1.0))
        )
        
        logger.info(f"Domain mapping added: {payload['question_code']} -> {payload['domain_id']}")
        return {
            "status": "success",
            "message": "Domain mapping added successfully",
            "mapping": mapping
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error adding domain mapping: {str(e)}")


@router.delete("/domain-mapping/{mapping_id}", status_code=200)
def delete_domain_mapping(
    mapping_id: str,
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Delete domain mapping.
    """
    try:
        admin_repo.delete_domain_mapping(mapping_id)
        
        logger.info(f"Domain mapping deleted: {mapping_id}")
        return {
            "status": "success",
            "message": "Domain mapping deleted successfully"
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting domain mapping: {str(e)}")


# ========================================
# BULK OPERATIONS
# ========================================

@router.post("/bulk/import-quiz", status_code=201)
def bulk_import_quiz(
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Bulk import quiz with all questions and options.
    
    Request:
      {
        "quiz": {...},
        "questions": [
          {
            "question_code": "q1",
            "text": "...",
            "domain": "logic",
            "options": [
              {"text": "Strongly disagree", "value": 1},
              {"text": "Strongly agree", "value": 5}
            ]
          }
        ]
      }
    """
    try:
        result = admin_repo.bulk_import_quiz(
            quiz_data=payload['quiz'],
            questions_data=payload.get('questions', [])
        )
        
        logger.info(f"Bulk import completed: quiz {result.get('quiz_id')}")
        return {
            "status": "success",
            "message": "Quiz imported successfully",
            "result": result
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error during bulk import: {str(e)}")


@router.post("/bulk/export-quiz/{quiz_id}", status_code=200)
def bulk_export_quiz(
    quiz_id: str,
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Export quiz with all questions and options.
    """
    try:
        export_data = admin_repo.bulk_export_quiz(quiz_id)
        
        logger.info(f"Quiz exported: {quiz_id}")
        return {
            "status": "success",
            "message": "Quiz exported successfully",
            "data": export_data
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error during export: {str(e)}")


# ========================================
# STATISTICS & MONITORING
# ========================================

@router.get("/stats", status_code=200)
def get_admin_stats(
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Get administrative statistics.
    """
    try:
        stats = admin_repo.get_admin_stats()
        
        return {
            "status": "success",
            "stats": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")


@router.get("/stats/quiz-usage", status_code=200)
def get_quiz_usage_stats(
    days: int = Query(30, description="Number of days to analyze"),
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Get quiz usage statistics.
    """
    try:
        usage = admin_repo.get_quiz_usage_stats(days=days)
        
        return {
            "status": "success",
            "days": days,
            "usage": usage
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting usage stats: {str(e)}")


# ========================================
# CACHE MANAGEMENT
# ========================================

@router.post("/cache/clear", status_code=200)
def clear_cache(
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Clear all caches (quiz mappings, etc.)
    """
    try:
        admin_repo.clear_all_caches()
        
        logger.info("Cache cleared by admin")
        return {
            "status": "success",
            "message": "Cache cleared successfully"
        }
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error clearing cache: {str(e)}")


# ========================================
# HEALTH CHECK
# ========================================

@router.get("/health", status_code=200)
def admin_health_check(
    token: str = Depends(verify_admin_token)
):
    """
    Admin health check endpoint.
    """
    return {
        "status": "healthy",
        "service": "proa-orientation-admin",
        "version": "2.0",
        "endpoints": [
            "POST /quiz",
            "GET /quiz",
            "GET /quiz/{quiz_id}",
            "PUT /quiz/{quiz_id}",
            "DELETE /quiz/{quiz_id}",
            "POST /question",
            "PUT /question/{question_id}",
            "DELETE /question/{question_id}",
            "POST /option",
            "PUT /option/{option_id}",
            "DELETE /option/{option_id}",
            "POST /domain-mapping",
            "DELETE /domain-mapping/{mapping_id}",
            "POST /bulk/import-quiz",
            "POST /bulk/export-quiz/{quiz_id}",
            "GET /stats",
            "GET /stats/quiz-usage",
            "POST /cache/clear"
        ],
        "timestamp": datetime.utcnow().isoformat()
    }