"""
PROA Data Models - Type definitions for Scoring System
Orientation académique - Feature engineering & recommendation engine
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
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
    cluster: Optional[str] = None          # Cluster métier (informatique, business, etc.)
    duration_years: Optional[int] = None
    score: float  # [0, 1]
    domain_matches: List[FiliereDomainMapping] = None
    top_domains: List[str] = None
    domains_list: Optional[List[str]] = None  # Liste des domaines pour filtrage bac
    compatibility_level: str = "fair"  # "excellent" | "good" | "fair" | "poor"
    
    def __post_init__(self):
        if self.domain_matches is None:
            self.domain_matches = []
        if self.top_domains is None:
            self.top_domains = []
        if self.domains_list is None:
            self.domains_list = []


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
    best_filiere_match: Optional[Dict[str, Any]] = None  # ← AJOUTÉ : meilleure filière avec détails
    pora_components: Optional[Dict[str, float]] = None   # ← AJOUTÉ : composants individuels PORA
    
    def __post_init__(self):
        if self.pora_components is None:
            self.pora_components = {
                "popularity": self.popularity,
                "engagement": 0.0,  # À remplir si disponible
                "orientation": self.filiere_match
            }


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
    best_filiere_match: Optional[Dict[str, Any]] = None  # ← AJOUTÉ : meilleure filière avec détails
    pora_components: Optional[Dict[str, float]] = None   # ← AJOUTÉ : composants individuels PORA
    
    def __post_init__(self):
        if self.pora_components is None:
            self.pora_components = {
                "popularity": self.popularity,
                "engagement": self.engagement_score,
                "orientation": self.filiere_match
            }


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
    bac_code: Optional[str] = None       # Code bac congolais (A, C, D, E, F1-F4, G1-G3, BG, H1-H5, R1-R6, P2-P7)
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
    
    # Bac info
    bac_info: Optional[Dict[str, Any]] = None  # {bac_code, bac_valid, bac_sector, bac_description, bac_icon}
    
    # Quality metrics
    metrics: Dict[str, Any]
    
    # Scoring metadata (← AJOUTÉ)
    scoring_method: Optional[str] = None  # "legacy" | "hybrid" | "semantic"
    hybrid_scores_used: bool = False


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
    
    # Hybrid scoring stats (← AJOUTÉ)
    hybrid_scoring_used: bool = False
    semantic_scores_count: int = 0
    rule_scores_count: int = 0
    interest_scores_count: int = 0
    
    @property
    def computation_time_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds() * 1000
        return 0.0


# ============================================================================
# HYBRID SCORING MODELS (← NOUVEAU)
# ============================================================================

@dataclass
class SemanticScore:
    """Score sémantique pour une filière"""
    filiere_id: str
    similarity_score: float  # 0-1
    model_used: str  # "sentence-bert" | "tfidf"
    confidence: float
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class RuleBasedScore:
    """Score basé sur les règles métier"""
    filiere_id: str
    rule_score: float  # 0-1
    rules_applied: List[str] = field(default_factory=list)
    rule_weights: Dict[str, float] = field(default_factory=dict)


@dataclass
class InterestBasedScore:
    """Score basé sur les intérêts utilisateur"""
    filiere_id: str
    interest_score: float  # 0-1
    domain_weights: Dict[str, float] = field(default_factory=dict)
    coverage: float = 0.0  # Couverture des domaines d'intérêt


@dataclass
class HybridScoreResult:
    """Résultat complet du scoring hybride"""
    filiere_id: str
    filiere_name: str
    total_score: float  # 0-1
    confidence: float  # 0-1
    semantic: Optional[SemanticScore] = None
    rule_based: Optional[RuleBasedScore] = None
    interest_based: Optional[InterestBasedScore] = None
    recommendations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def level(self) -> str:
        """Niveau de compatibilité"""
        if self.total_score >= 0.7:
            return "high"
        elif self.total_score >= 0.4:
            return "medium"
        return "low"


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
        self.cluster = data.get("cluster")  # ← AJOUTÉ


class UniversiteRow:
    """Row from universites"""
    def __init__(self, data: dict):
        self.universite_id = data.get("universite_id") or data.get("id")
        self.name = data.get("name")
        self.followers_count = int(data.get("followers_count", 0))
        self.engagement_count = int(data.get("engagement_count", 0))
        self.best_filiere_match = None  # ← AJOUTÉ


class CentreRow:
    """Row from centres_formation"""
    def __init__(self, data: dict):
        self.centre_id = data.get("centre_id") or data.get("id")
        self.name = data.get("name")
        self.universite_id = data.get("universite_id")
        self.universite_name = data.get("universite_name")
        self.followers_count = int(data.get("followers_count", 0))
        self.engagement_count = int(data.get("engagement_count", 0))
        self.best_filiere_match = None  # ← AJOUTÉ


# ============================================================================
# BAC CONGOLAIS MODELS (← NOUVEAU)
# ============================================================================

@dataclass
class BacInfo:
    """Information sur le bac congolais"""
    bac_code: str  # A, C, D, E, F1-F4, G1-G3, BG, H1-H5, R1-R6, P2-P7
    bac_name: str  # "Baccalauréat Scientifique - Option Mathématiques"
    bac_sector: str  # "Scientifique" | "Littéraire" | "Technique" | "Pédagogique" | "Professionnel"
    bac_description: str
    bac_icon: Optional[str] = None  # URL ou code d'icône
    
    # Filtres par secteur
    allowed_clusters: List[str] = field(default_factory=list)  # "informatique", "business", etc.
    allowed_fields: List[str] = field(default_factory=list)
    excluded_fields: List[str] = field(default_factory=list)
    
    # Statistiques
    eligibility_score: float = 1.0  # 0-1, score d'éligibilité pour certaines filières
    is_valid: bool = True


# ============================================================================
# FILIERE CLUSTER MAPPING (← NOUVEAU)
# ============================================================================

@dataclass
class FiliereCluster:
    """Mapping entre domaine_id et cluster PROA"""
    domaine_id: str
    cluster_name: str  # "informatique", "business", "engineering", "droit", "social", "geoscience", "agriculture", "arts_design"
    cluster_display_name: str  # "Informatique & Data", "Business & Gestion", etc.
    detection_method: str  # "direct_map" | "nlp_fallback" | "manual"
    confidence: float  # 0-1
    
    
# ============================================================================
# UTILITY FUNCTIONS (← NOUVEAU)
# ============================================================================

def create_empty_proa_response(user_id: str) -> ProaComputeResponse:
    """Crée une réponse PROA vide avec des valeurs par défaut"""
    return ProaComputeResponse(
        user_id=user_id,
        timestamp=datetime.utcnow(),
        features={},
        domain_scores=[],
        filiere_scores=[],
        universites=[],
        centres=[],
        recommendations={},
        total_questions=0,
        matched_questions=0,
        coverage=0.0,
        confidence=0.0,
        computation_time_ms=0.0,
        bac_info=None,
        metrics={},
        scoring_method=None,
        hybrid_scores_used=False
    )


def get_cluster_display_name(cluster_name: str) -> str:
    """Retourne le nom d'affichage pour un cluster"""
    cluster_names = {
        "informatique": "Informatique & Data",
        "business": "Business & Gestion",
        "engineering": "Ingénierie & Industrie",
        "droit": "Droit & Juridique",
        "social": "Sciences Humaines & Sociales",
        "geoscience": "Géosciences & Mines",
        "agriculture": "Agriculture & Agroalimentaire",
        "arts_design": "Arts, Design & Architecture",
        "sante": "Santé & Médical",
        "unknown": "Non classé"
    }
    return cluster_names.get(cluster_name, cluster_name.capitalize())