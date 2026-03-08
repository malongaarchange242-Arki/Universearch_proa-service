# models/quiz.py

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Dict
import os
import json
import logging

logger = logging.getLogger("orientation.quiz")

# Charger la configuration
CONFIG_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "orientation_config.json",
)

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        ORIENTATION_CONFIG = json.load(f)
except Exception:
    logger.exception("Impossible de charger orientation_config.json")
    ORIENTATION_CONFIG = {}

# Extraire toutes les questions attendues
EXPECTED_QUESTIONS = set()
for questions in ORIENTATION_CONFIG.get("skills", {}).values():
    EXPECTED_QUESTIONS.update(questions)
for questions in ORIENTATION_CONFIG.get("domains", {}).values():
    EXPECTED_QUESTIONS.update(questions)

MAX_SCORE = ORIENTATION_CONFIG.get("max_score", 5)


class QuizSubmission(BaseModel):
    """
    Schéma strict pour soumettre un quiz complété.
    
    Validations:
    - user_id: non vide
    - quiz_version: correspond à une version connue
    - responses: toutes les questions requises, scores [1, MAX_SCORE]
    """
    model_config = ConfigDict(extra="ignore")
    
    user_id: str = Field(..., min_length=1, description="Identifiant utilisateur")
    quiz_version: str = Field(default="1.0", description="Version du quiz")
    responses: Dict[str, float] = Field(..., description="Réponses {question_id: score}")
    
    @field_validator("responses")
    @classmethod
    def validate_responses(cls, values: Dict[str, float]):
        """Vérifie que chaque réponse est valide [1, MAX_SCORE]"""
        if not values:
            raise ValueError("Au moins une réponse est requise")
        
        for question_id, score in values.items():
            if not isinstance(score, (int, float)):
                raise ValueError(f"{question_id}: le score doit être un nombre")
            
            if not (1.0 <= score <= float(MAX_SCORE)):
                raise ValueError(f"{question_id}: score {score} hors intervalle [1, {MAX_SCORE}]")
        
        return values
    
    @model_validator(mode="after")
    def validate_all_questions_answered(self):
        """Vérifie que toutes les questions requises sont répondues"""
        missing = EXPECTED_QUESTIONS - set(self.responses.keys())
        if missing:
            raise ValueError(f"Questions manquantes: {', '.join(sorted(missing))}")
        
        extra = set(self.responses.keys()) - EXPECTED_QUESTIONS
        if extra:
            logger.warning(f"Questions inattendues (ignorées): {', '.join(sorted(extra))}")
        
        return self
