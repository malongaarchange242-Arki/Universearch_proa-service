from fastapi import APIRouter, HTTPException, status, Depends, Header
import logging
from typing import Optional, Dict, Any
import os

from models.quiz import UserType
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
# CREATE QUIZ
# ========================================

@router.post("/quiz", status_code=201)
def create_quiz(
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Create new quiz.
    
    Request:
      {
        "quiz_code": "quiz_bachelier_2024_v1",
        "user_type": "bachelier",
        "title": "Quiz d'Orientation - Filière",
        "description": "Découvrez les filières...",
        "total_questions": 24
      }
    """
    try:
        logger.info(f"Creating quiz: {payload.get('quiz_code')}")
        
        quiz = admin_repo.create_quiz(
            quiz_code=payload['quiz_code'],
            user_type=payload['user_type'],
            title=payload['title'],
            description=payload.get('description', ''),
            total_questions=payload.get('total_questions', 24)
        )
        
        logger.info(f"Quiz created: {quiz['id']}")
        return quiz
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Error creating quiz")


# ========================================
# ADD QUESTION
# ========================================

@router.post("/question", status_code=201)
def add_question(
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Add question to quiz.
    
    Request:
      {
        "quiz_id": "...",
        "question_code": "q1",
        "text": "J'aime résoudre...",
        "domain": "logic",
        "order_index": 1
      }
    """
    try:
        # Normalize to lowercase
        question_code = str(payload['question_code']).lower()
        
        question = admin_repo.create_question(
            quiz_id=payload['quiz_id'],
            question_code=question_code,
            text=payload['text'],
            domain=payload['domain'],
            order_index=payload.get('order_index', 1)
        )
        
        logger.info(f"Question added: {question_code}")
        return question
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Error adding question")


# ========================================
# ADD OPTION
# ========================================

@router.post("/option", status_code=201)
def add_option(
    payload: Dict[str, Any],
    admin_repo: AdminRepository = Depends(get_admin_repo),
    token: str = Depends(verify_admin_token)
):
    """
    Add option to question.
    
    Request:
      {
        "question_id": "...",
        "text": "Strongly agree",
        "value": 4
      }
    """
    try:
        option = admin_repo.create_option(
            question_id=payload['question_id'],
            text=payload['text'],
            value=payload['value']
        )
        
        logger.info(f"Option added: {payload['value']}")
        return option
    
    except Exception as e:
        logger.exception(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Error adding option")
