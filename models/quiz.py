from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, Optional, Union, List
from enum import Enum


class UserType(str, Enum):
    BACHELIER = "bachelier"
    ETUDIANT = "etudiant"
    PARENT = "parent"


class QuizOption(BaseModel):
    """Single option for a question"""
    id: str
    text: str
    value: int = Field(ge=1, le=4)


class QuizQuestion(BaseModel):
    """Single question"""
    id: str
    question_code: str
    text: str
    domain: str
    options: List[QuizOption]
    order_index: int


class QuizMetadata(BaseModel):
    """Quiz metadata"""
    id: str
    quiz_code: str
    user_type: UserType
    title: str
    description: str
    total_questions: int


class QuizResponse(BaseModel):
    """Complete quiz response"""
    quiz: QuizMetadata
    questions: List[QuizQuestion]


class QuizSubmissionRequest(BaseModel):
    """User quiz submission"""
    user_id: str
    user_type: UserType
    quiz_code: str
    responses: dict = Field(description="question_code → value (1-4)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user@example.com",
                "user_type": "bachelier",
                "quiz_code": "quiz_bachelier_2024_v1",
                "responses": {
                    "q1": 3,
                    "q2": 4,
                    "q3": 2,
                    "q24": 3
                }
            }
        }


# Legacy model for backward compatibility
class QuizSubmission(BaseModel):
    user_id: str
    user_type: str = Field(default="all", description="Type d'utilisateur: 'all', 'bachelier', 'étudiant', 'parent'")
    quiz_version: str = "1.0"
    orientation_type: str = Field(default="field", description="Type d'orientation: 'field' ou 'institution'")
    responses: Dict[str, Union[int, float]]
    response_metadata: Optional[Dict[str, Dict[str, Any]]] = Field(
        default=None,
        description="Metadonnees facultatives de reponse (raw_value, selected_text, question_type, etc.)",
    )

    @field_validator("responses", mode="before")
    @classmethod
    def validate_responses_not_null(cls, v):
        """Rejette les responses nulles ou vides"""
        if v is None:
            raise ValueError("responses cannot be null")
        if not isinstance(v, dict):
            raise ValueError("responses must be a dictionary")
        if len(v) == 0:
            raise ValueError("responses cannot be empty")
        return v

    @field_validator("responses", mode="after")
    @classmethod
    def validate_response_values(cls, v):
        """Valide que toutes les valeurs sont numériques"""
        for key, value in v.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"Response value for {key} must be numeric, got {type(value)}")
            if not (1 <= value <= 4):
                raise ValueError(f"Response value for {key} must be between 1 and 4, got {value}")
        return v

    @field_validator("orientation_type")
    @classmethod
    def validate_orientation_type(cls, v):
        if v not in ["field", "institution"]:
            raise ValueError("orientation_type doit être 'field' ou 'institution'")
        return v
