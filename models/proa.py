"""
PROA Data Models - Type definitions for Scoring System
Orientation académique - Feature engineering & recommendation engine
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# ============================================================================
# ENUMS
# ============================================================================

class UserType(str, Enum):
    """User types for orientation"""
    BACHELIER = "bachelier"
    ETUDIANT = "etudiant"
    PARENT = "parent"


class RecommendationType(str, Enum):
    """Types of recommendations"""
    FILIERES = "filieres"
    UNIVERSITES = "universites"
    CENTRES = "centres"


# ============================================================================
# FEATURES & DOMAINS
# ============================================================================

@dataclass
class FeatureScore:
    """Individual feature score"""
    name: str
    score: float  # [0, 1]
    weight: float
    contribution: float  # score * weight
    question_count: int


@dataclass
class DomainScore:
    """Domain score - aggregation of features"""
    domain_id: str
    domain_name: str
    score: float  # [0, 1]
    feature_scores: List[FeatureScore]
    total_weight: float
    confidence: float  # based on coverage


@dataclass
class FiliereDomainMapping:
    """Domain contribution to filière"""
    domain_id: str
    domain_name: str
    domain_score: float
    importance: float  # weight in filière
    contribution: float  # domain_score * importance


@dataclass
class FiliereScore:
    """Filière score based on domain match"""
    filiere_id: str
    filiere_name: str
    field: str
    duration_years: Optional[int]
    score: float  # [0, 1]
    domain_matches: List[FiliereDomainMapping]
    top_domains: List[str]
    compatibility_level: str  # "excellent" | "good" | "fair" | "poor"


@dataclass
class UniversiteScore:
    """Université PORA score"""
    universite_id: str
    universite_name: str
    filiere_match: float  # best filière score match
    popularity: float  # [0, 1]
    filieres: List[str]
    pora_score: float  # composite
    ranking: int


@dataclass
class CentreScore:
    """Centre de formation PORA score"""
    centre_id: str
    centre_name: str
    universite_name: Optional[str]
    filiere_match: float
    popularity: float
    engagement_score: float
    pora_score: float
    ranking: int


@dataclass
class Recommendation:
    """Single recommendation"""
    id: str
    name: str
    type: RecommendationType
    score: float
    reason: str
    metadata: Dict[str, Any]


@dataclass
class ProaComputeRequest:
    """PROA Compute Request"""
    user_id: str
    user_type: UserType
    quiz_version: str
    orientation_type: str  # "field" | "career" | "general"
    responses: Dict[str, int]  # {q1: 3, q2: 4, ...}
    context: Optional[Dict[str, Any]] = None


@dataclass
class ProaComputeResponse:
    """PROA Compute Response - complete scoring result"""
    user_id: str
    timestamp: datetime
    
    # Raw scores
    features: Dict[str, FeatureScore]
    domain_scores: List[DomainScore]
    filiere_scores: List[FiliereScore]
    
    # PORA rankings
    universites: List[UniversiteScore]
    centres: List[CentreScore]
    
    # Recommendations
    recommendations: Dict[str, List[Recommendation]]
    
    # Metadata
    total_questions: int
    matched_questions: int
    coverage: float  # matched / total
    confidence: float  # overall confidence [0, 1]
    computation_time_ms: float
    
    # Quality metrics
    metrics: Dict[str, Any]


# ============================================================================
# CACHE & PERFORMANCE
# ============================================================================

@dataclass
class CacheEntry:
    """Cache entry with TTL"""
    data: Any
    timestamp: datetime
    ttl_seconds: int
    
    def is_expired(self) -> bool:
        elapsed = (datetime.utcnow() - self.timestamp).total_seconds()
        return elapsed > self.ttl_seconds


@dataclass
class ComputationStats:
    """Computation statistics for monitoring"""
    user_id: str
    user_type: str
    start_time: datetime
    end_time: Optional[datetime]
    
    # Counts
    total_responses: int
    valid_responses: int
    missing_responses: int
    invalid_responses: int
    
    # Coverage
    domain_coverage: float
    feature_coverage: float
    filiere_coverage: float
    
    # Performance
    db_query_count: int
    cache_hits: int
    cache_misses: int
    
    @property
    def computation_time_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0.0


# ============================================================================
# DATABASE RESULT MODELS
# ============================================================================

class QuestionFeatureWeightRow:
    """Row from orientation_question_feature_weights"""
    def __init__(self, data: dict):
        self.question_code = data.get("question_code")
        self.feature_name = data.get("feature_name")
        self.weight = float(data.get("weight", 1.0))


class QuestionDomainMappingRow:
    """Row from question_domain_mapping"""
    def __init__(self, data: dict):
        self.question_code = data.get("question_code")
        self.domain_id = data.get("domain_id")
        self.domain_name = data.get("domain_name")
        self.weight = float(data.get("weight", 1.0))


class FiliereDomainRow:
    """Row from filiere_domaines"""
    def __init__(self, data: dict):
        self.filiere_id = data.get("filiere_id")
        self.filiere_name = data.get("filiere_name")
        self.domain_id = data.get("domain_id")
        self.domain_name = data.get("domain_name")
        self.importance = float(data.get("importance", 1.0))


class FiliereRow:
    """Row from filieres"""
    def __init__(self, data: dict):
        self.filiere_id = data.get("filiere_id") or data.get("id")
        self.name = data.get("name")
        self.field = data.get("field")
        self.description = data.get("description")
        self.duration_years = data.get("duration_years")


class UniversiteRow:
    """Row from universites"""
    def __init__(self, data: dict):
        self.universite_id = data.get("universite_id") or data.get("id")
        self.name = data.get("name")
        self.followers_count = int(data.get("followers_count", 0))
        self.engagement_count = int(data.get("engagement_count", 0))


class CentreRow:
    """Row from centres_formation"""
    def __init__(self, data: dict):
        self.centre_id = data.get("centre_id") or data.get("id")
        self.name = data.get("name")
        self.universite_id = data.get("universite_id")
        self.universite_name = data.get("universite_name")
        self.followers_count = int(data.get("followers_count", 0))
        self.engagement_count = int(data.get("engagement_count", 0))
