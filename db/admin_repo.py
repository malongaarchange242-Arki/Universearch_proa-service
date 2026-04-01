import logging
from typing import Dict, Any
from datetime import datetime
from supabase import Client

logger = logging.getLogger("orientation.admin_repo")


class AdminRepository:
    """Admin operations for quiz management (SYNC - Supabase is sync!)"""
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    def create_quiz(
        self,
        quiz_code: str,
        user_type: str,
        title: str,
        description: str,
        total_questions: int
    ) -> Dict[str, Any]:
        """Create new quiz"""
        try:
            data = {
                "quiz_code": quiz_code,
                "user_type": user_type,
                "title": title,
                "description": description,
                "total_questions": total_questions,
                "status": "draft",
                "version": 1,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = self.supabase.table("orientation_quizzes").insert(data).execute()
            response_data = result.data if hasattr(result, 'data') else result.get('data')
            
            if not response_data:
                raise RuntimeError("Failed to create quiz")
            
            logger.info(f"Quiz created: {quiz_code}")
            return response_data[0]
        
        except Exception as e:
            logger.error(f"Error creating quiz: {e}")
            raise
    
    def create_question(
        self,
        quiz_id: str,
        question_code: str,
        text: str,
        domain: str,
        order_index: int
    ) -> Dict[str, Any]:
        """Add question to quiz"""
        try:
            data = {
                "quiz_id": quiz_id,
                "question_code": question_code.lower(),
                "text": text,
                "domain": domain,
                "order_index": order_index,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = self.supabase.table("orientation_quiz_questions").insert(data).execute()
            response_data = result.data if hasattr(result, 'data') else result.get('data')
            
            if not response_data:
                raise RuntimeError("Failed to create question")
            
            return response_data[0]
        
        except Exception as e:
            logger.error(f"Error creating question: {e}")
            raise
    
    def create_option(
        self,
        question_id: str,
        text: str,
        value: int
    ) -> Dict[str, Any]:
        """Add option to question"""
        try:
            data = {
                "question_id": question_id,
                "text": text,
                "value": value,
                "created_at": datetime.utcnow().isoformat()
            }
            
            result = self.supabase.table("orientation_quiz_options").insert(data).execute()
            response_data = result.data if hasattr(result, 'data') else result.get('data')
            
            if not response_data:
                raise RuntimeError("Failed to create option")
            
            return response_data[0]
        
        except Exception as e:
            logger.error(f"Error creating option: {e}")
            raise
