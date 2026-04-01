import logging
from typing import List, Optional, Dict, Any
from supabase import Client

logger = logging.getLogger("orientation.quiz_repo")


class QuizRepository:
    """Handles all quiz database operations"""
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    def get_quiz_by_user_type(self, user_type: str) -> Optional[Dict[str, Any]]:
        """Fetch quiz for specific user_type (SYNC - Supabase is sync!)"""
        try:
            result = self.supabase.table("orientation_quizzes").select("*").eq(
                "user_type", user_type
            ).eq(
                "status", "published"
            ).order("version", desc=True).limit(1).execute()
            
            data = result.data if hasattr(result, 'data') else result.get('data')
            
            if not data or len(data) == 0:
                logger.warning(f"No quiz found for user_type={user_type}")
                return None
            
            logger.info(f"Quiz loaded: {data[0].get('quiz_code')}")
            return data[0]
        
        except Exception as e:
            logger.error(f"Error fetching quiz: {e}")
            raise
    
    def get_questions_with_options(self, quiz_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all questions WITH their options in ONE query (avoid N+1!)
        
        Supabase nested select:
          - Questions with their related options
          - All in a single DB call
          - Performance: 25 queries → 1 query!
        """
        try:
            # ⚡ OPTIMIZED: Nested select to get questions + options in 1 query
            result = self.supabase.table("orientation_quiz_questions").select(
                """
                id,
                question_code,
                text,
                domain,
                order_index,
                orientation_quiz_options (
                    id,
                    text,
                    value
                )
                """
            ).eq(
                "quiz_id", quiz_id
            ).order("order_index", desc=False).execute()
            
            data = result.data if hasattr(result, 'data') else result.get('data')
            
            if not data:
                logger.warning(f"No questions found for quiz_id={quiz_id}")
                return []
            
            logger.info(f"Loaded {len(data)} questions with options in 1 query (no N+1!)")
            return data
        
        except Exception as e:
            logger.error(f"Error fetching questions with options: {e}")
            raise
