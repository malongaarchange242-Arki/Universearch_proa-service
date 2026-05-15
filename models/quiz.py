"""
Quiz Models - Modèles de données pour le quiz d'orientation
Version 2.0 - Support du scoring V2, validation avancée, bac congolais
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, Dict, Optional, Union, List
from enum import Enum
from datetime import datetime


# ============================================================================
# ENUMS
# ============================================================================

class UserType(str, Enum):
    """Types d'utilisateurs"""
    BACHELIER = "bachelier"
    ETUDIANT = "etudiant"
    PARENT = "parent"


class OrientationType(str, Enum):
    """Types d'orientation"""
    FIELD = "field"
    CAREER = "career"
    INSTITUTION = "institution"
    GENERAL = "general"


class ScoringMethod(str, Enum):
    """Méthodes de scoring disponibles"""
    LEGACY = "legacy"
    RULE = "rule"
    ML = "ml"
    V2_VECTORIAL = "v2_vectorial"
    HYBRID = "hybrid"
    AUTO = "auto"


class BacTrack(str, Enum):
    """Tracks pour le bac congolais"""
    HUMANITIES = "humanities"
    SCIENCE = "science"
    TECHNICAL = "technical"
    INFORMATICS = "informatics"
    BUSINESS = "business"
    VOCATIONAL = "vocational"
    GENERAL = "general"


# ============================================================================
# MODÈLES DE BASE
# ============================================================================

class QuizOption(BaseModel):
    """Single option for a question"""
    id: str
    text: str
    value: int = Field(ge=1, le=5, description="Score de 1 à 5")  # Support 1-5 maintenant
    domain: Optional[str] = Field(None, description="Domaine PROA associé")
    
    @field_validator("value")
    @classmethod
    def validate_value(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError(f"Value must be between 1 and 5, got {v}")
        return v


class QuizQuestion(BaseModel):
    """Single question with enhanced metadata"""
    id: str
    question_code: str
    text: str
    domain: str
    options: List[QuizOption]
    order_index: int
    category: Optional[str] = Field(None, description="Catégorie: technical, business, social, etc.")
    weight: float = Field(1.0, ge=0.1, le=2.0, description="Poids de la question")
    required: bool = Field(True, description="Question obligatoire")
    
    @field_validator("question_code")
    @classmethod
    def validate_question_code(cls, v: str) -> str:
        """Valide le format du code question (q1, q2, etc.)"""
        import re
        if not re.match(r'^q\d+$', v.lower()):
            raise ValueError(f"Question code must be like 'q1', 'q2', got {v}")
        return v.lower()


class QuizMetadata(BaseModel):
    """Quiz metadata enriched"""
    id: str
    quiz_code: str
    user_type: UserType
    title: str
    description: str
    total_questions: int
    version: str = Field("2.0", description="Version du quiz")
    scoring_method: ScoringMethod = Field(ScoringMethod.AUTO, description="Méthode de scoring recommandée")
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class QuizResponse(BaseModel):
    """Complete quiz response with enhanced metadata"""
    quiz: QuizMetadata
    questions: List[QuizQuestion]
    version: str = "2.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# MODÈLES DE SOUMISSION
# ============================================================================

class ResponseMetadata(BaseModel):
    """Métadonnées pour une réponse individuelle"""
    raw_value: Optional[int] = None
    selected_text: Optional[str] = None
    question_type: Optional[str] = None
    domain: Optional[str] = None
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class QuizSubmissionRequest(BaseModel):
    """Enhanced user quiz submission with V2 support"""
    user_id: str = Field(..., description="Identifiant unique de l'utilisateur")
    user_type: UserType = Field(..., description="Type d'utilisateur")
    quiz_code: str = Field(..., description="Code du quiz")
    responses: Dict[str, int] = Field(..., description="question_code → value (1-5)")
    
    # Champs optionnels pour scoring V2
    bac_code: Optional[str] = Field(None, description="Code bac congolais (A, C, D, etc.)")
    orientation_type: OrientationType = Field(OrientationType.FIELD, description="Type d'orientation")
    scoring_method: ScoringMethod = Field(ScoringMethod.AUTO, description="Méthode de scoring souhaitée")
    response_metadata: Optional[Dict[str, ResponseMetadata]] = Field(None, description="Métadonnées par réponse")
    
    # Métadonnées
    session_id: Optional[str] = Field(None, description="ID de session pour tracking")
    client_version: str = Field("2.0", description="Version du client")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user@example.com",
                "user_type": "bachelier",
                "quiz_code": "quiz_bachelier_2025_v2",
                "responses": {
                    "q1": 5,
                    "q2": 4,
                    "q3": 3,
                    "q24": 5
                },
                "bac_code": "C",
                "orientation_type": "field",
                "scoring_method": "auto"
            }
        }
    
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
    
    @field_validator("responses")
    @classmethod
    def validate_response_values(cls, v: Dict[str, int]) -> Dict[str, int]:
        """Valide que toutes les valeurs sont numériques et dans la plage 1-5"""
        for key, value in v.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"Response value for {key} must be numeric, got {type(value)}")
            if not (1 <= value <= 5):
                raise ValueError(f"Response value for {key} must be between 1 and 5, got {value}")
        return v
    
    @field_validator("bac_code")
    @classmethod
    def validate_bac_code(cls, v: Optional[str]) -> Optional[str]:
        """Valide le code bac congolais"""
        if v is None:
            return v
        
        valid_codes = {"A", "A1", "A2", "A3", "B", "C", "D", "E", 
                       "F1", "F2", "F3", "F4", "G1", "G2", "G3", "BG",
                       "H1", "H2", "H3", "H4", "H5", "R1", "R2", "R3", 
                       "R4", "R5", "R6", "P2", "P3", "P4", "P5", "P6", "P7"}
        
        code_upper = v.upper().strip()
        if code_upper not in valid_codes:
            # Tenter de normaliser
            import re
            match = re.match(r'^([A-Z])(\d*)$', code_upper)
            if match:
                letter = match.group(1)
                number = match.group(2)
                normalized = f"{letter}{number}" if number else letter
                if normalized in valid_codes:
                    return normalized
            
            # Codes spéciaux
            if code_upper == "C01":
                return "C"
            if code_upper.startswith("SERIE"):
                return None
            
            raise ValueError(f"Invalid bac code: {v}. Valid codes: {sorted(valid_codes)[:10]}...")
        
        return code_upper
    
    @field_validator("quiz_code")
    @classmethod
    def validate_quiz_code(cls, v: str) -> str:
        """Valide le format du code quiz"""
        if not v or len(v) < 5:
            raise ValueError(f"Invalid quiz_code: {v}")
        return v.lower().strip()
    
    @model_validator(mode="after")
    def validate_response_count(self) -> "QuizSubmissionRequest":
        """Valide le nombre de réponses"""
        expected_count = 24  # Quiz standard
        actual_count = len(self.responses)
        
        # Minimum requis
        if actual_count < expected_count * 0.5:  # Au moins 50%
            raise ValueError(f"Too few responses: {actual_count}, expected at least {expected_count * 0.5}")
        
        return self
    
    def get_normalized_responses(self) -> Dict[str, int]:
        """Retourne les réponses normalisées (q1, q2, etc.)"""
        normalized = {}
        for key, value in self.responses.items():
            # Normaliser la clé
            import re
            match = re.search(r'(\d+)', str(key).lower())
            if match:
                num = int(match.group(1))
                normalized[f"q{num}"] = value
            else:
                normalized[key.lower()] = value
        return normalized
    
    def get_bac_track(self) -> Optional[BacTrack]:
        """Retourne le track bac associé au code"""
        if not self.bac_code:
            return None
        
        bac_to_track = {
            "A": BacTrack.HUMANITIES, "A1": BacTrack.HUMANITIES, "A2": BacTrack.HUMANITIES, "A3": BacTrack.HUMANITIES,
            "B": BacTrack.BUSINESS,
            "C": BacTrack.SCIENCE, "D": BacTrack.SCIENCE,
            "E": BacTrack.TECHNICAL, "F1": BacTrack.TECHNICAL, "F2": BacTrack.TECHNICAL, 
            "F3": BacTrack.TECHNICAL, "F4": BacTrack.TECHNICAL,
            "G1": BacTrack.BUSINESS, "G2": BacTrack.BUSINESS, "G3": BacTrack.BUSINESS,
            "BG": BacTrack.GENERAL,
            "H1": BacTrack.HUMANITIES, "H2": BacTrack.HUMANITIES, "H3": BacTrack.HUMANITIES,
            "H4": BacTrack.HUMANITIES, "H5": BacTrack.HUMANITIES,
            "R1": BacTrack.HUMANITIES, "R2": BacTrack.HUMANITIES, "R3": BacTrack.HUMANITIES,
            "R4": BacTrack.HUMANITIES, "R5": BacTrack.HUMANITIES, "R6": BacTrack.HUMANITIES,
            "P2": BacTrack.VOCATIONAL, "P3": BacTrack.VOCATIONAL, "P4": BacTrack.VOCATIONAL,
            "P5": BacTrack.VOCATIONAL, "P6": BacTrack.VOCATIONAL, "P7": BacTrack.VOCATIONAL,
        }
        
        return bac_to_track.get(self.bac_code.upper())


# ============================================================================
# MODÈLES DE RÉPONSE POUR L'API
# ============================================================================

class OrientationComputeResponse(BaseModel):
    """Réponse standard pour /orientation/compute"""
    status: str = "success"
    user_id: str
    profile_id: Optional[str] = None
    quiz_version: str
    scoring_method: str
    confidence: float
    recommended_fields: List[Dict[str, Any]]
    field_scores: Dict[str, float] = {}
    insight: str = ""
    aiInsight: str = ""
    computation_time_ms: float = 0
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "user_id": "user123",
                "scoring_method": "v2_vectorial",
                "confidence": 0.85,
                "recommended_fields": [
                    {"field_name": "Génie Informatique", "score": 0.92, "reason": "Excellent match", "cluster": "informatique"}
                ],
                "insight": "Tu montres une forte affinité avec l'informatique"
            }
        }


class QuizSubmissionResponse(BaseModel):
    """Réponse pour la soumission de quiz"""
    status: str = "success"
    user_id: str
    profile_id: str
    orientation: OrientationComputeResponse
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "user_id": "user123",
                "profile_id": "profile_abc123",
                "orientation": {
                    "status": "success",
                    "user_id": "user123",
                    "scoring_method": "v2_vectorial",
                    "confidence": 0.85,
                    "recommended_fields": []
                }
            }
        }


# ============================================================================
# MODÈLES POUR LE BATCH PROCESSING
# ============================================================================

class BatchQuizSubmission(BaseModel):
    """Soumission multiple de quiz (batch)"""
    submissions: List[QuizSubmissionRequest]
    batch_id: Optional[str] = None
    
    @field_validator("submissions")
    @classmethod
    def validate_batch_size(cls, v: List) -> List:
        """Limite la taille du batch"""
        if len(v) > 100:
            raise ValueError(f"Batch too large: {len(v)} max 100")
        return v


class BatchQuizResponse(BaseModel):
    """Réponse batch"""
    batch_id: str
    total: int
    successful: int
    failed: int
    results: List[OrientationComputeResponse]
    errors: List[Dict[str, Any]]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# MODÈLES POUR LE FEEDBACK
# ============================================================================

class FeedbackRequest(BaseModel):
    """Feedback utilisateur sur les recommandations"""
    user_id: str
    profile_id: str
    recommendation_id: str
    rating: int = Field(ge=1, le=5, description="Note de 1 à 5")
    comment: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: int) -> int:
        if not 1 <= v <= 5:
            raise ValueError(f"Rating must be between 1 and 5, got {v}")
        return v


# ============================================================================
# MODÈLES LEGACY (COMPATIBILITÉ)
# ============================================================================

class LegacyQuizSubmission(BaseModel):
    """Modèle legacy pour compatibilité ascendante"""
    user_id: str
    user_type: str = Field(default="all", description="Type d'utilisateur")
    quiz_version: str = "1.0"
    orientation_type: str = Field(default="field", description="Type d'orientation")
    responses: Dict[str, Union[int, float]]
    response_metadata: Optional[Dict[str, Dict[str, Any]]] = None
    
    @field_validator("responses", mode="before")
    @classmethod
    def validate_responses_not_null(cls, v):
        if v is None:
            raise ValueError("responses cannot be null")
        if not isinstance(v, dict):
            raise ValueError("responses must be a dictionary")
        if len(v) == 0:
            raise ValueError("responses cannot be empty")
        return v
    
    @field_validator("responses")
    @classmethod
    def validate_response_values(cls, v):
        for key, value in v.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"Response value for {key} must be numeric, got {type(value)}")
            # Legacy support 1-4
            if not (1 <= value <= 4):
                raise ValueError(f"Response value for {key} must be between 1 and 4, got {value}")
        return v
    
    @field_validator("orientation_type")
    @classmethod
    def validate_orientation_type(cls, v):
        if v not in ["field", "institution"]:
            raise ValueError("orientation_type doit être 'field' ou 'institution'")
        return v
    
    def migrate_to_v2(self) -> QuizSubmissionRequest:
        """Migre une soumission legacy vers V2"""
        return QuizSubmissionRequest(
            user_id=self.user_id,
            user_type=UserType(self.user_type) if self.user_type in ["bachelier", "etudiant", "parent"] else UserType.BACHELIER,
            quiz_code=f"quiz_{self.user_type}_{self.quiz_version}",
            responses={k: int(v) for k, v in self.responses.items()},
            orientation_type=OrientationType.FIELD if self.orientation_type == "field" else OrientationType.INSTITUTION,
            scoring_method=ScoringMethod.LEGACY
        )


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    # Test du modèle V2
    test_submission = QuizSubmissionRequest(
        user_id="test_user",
        user_type=UserType.BACHELIER,
        quiz_code="quiz_bachelier_v2",
        responses={"q1": 5, "q2": 4, "q3": 3, "q4": 5},
        bac_code="C",
        orientation_type=OrientationType.FIELD
    )
    
    print("✅ QuizSubmissionRequest valid")
    print(f"   User: {test_submission.user_id}")
    print(f"   Bac track: {test_submission.get_bac_track()}")
    print(f"   Normalized responses: {test_submission.get_normalized_responses()}")
    
    # Test migration legacy
    legacy = LegacyQuizSubmission(
        user_id="legacy_user",
        user_type="bachelier",
        responses={"Q1": 3, "Q2": 4, "Q3": 2}
    )
    
    migrated = legacy.migrate_to_v2()
    print(f"\n✅ Legacy migration: {migrated.quiz_code}")