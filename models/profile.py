"""
Profile Models - Modèles de données pour le profil utilisateur
Version 2.0 - Support du scoring V2, bac congolais, clusters et métadonnées
"""

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from typing import Dict, List, Optional, Any
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


class BacTrack(str, Enum):
    """Tracks pour le bac congolais"""
    HUMANITIES = "humanities"      # A, A1-A3, L
    SCIENCE = "science"             # C, D, S
    TECHNICAL = "technical"         # E, F1-F4
    INFORMATICS = "informatics"     # H, H1-H3
    BUSINESS = "business"           # G, G1-G3, BG
    VOCATIONAL = "vocational"       # P2-P7
    GENERAL = "general"             # BG


class ProfileSource(str, Enum):
    """Source du profil"""
    QUIZ = "quiz"
    IMPORT = "import"
    MANUAL = "manual"
    ML_PREDICTION = "ml_prediction"
    V2_VECTORIAL = "v2_vectorial"
    HYBRID = "hybrid"


class CompatibilityLevel(str, Enum):
    """Niveau de compatibilité"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


# ============================================================================
# MODÈLES DE BASE
# ============================================================================

class DomainScore(BaseModel):
    """Score pour un domaine PROA"""
    name: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    source: Optional[str] = None
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v) < 2:
            raise ValueError(f"Domain name too short: {v}")
        return v.lower().strip()


class SkillScore(BaseModel):
    """Score pour une compétence"""
    name: str
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)
    category: Optional[str] = None  # technical, soft, language, etc.
    
    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or len(v) < 2:
            raise ValueError(f"Skill name too short: {v}")
        return v.lower().strip()


class FeatureScore(BaseModel):
    """Score pour une feature du scoring V2"""
    name: str
    value: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0, default=1.0)
    contribution: float = Field(ge=0.0, le=1.0, default=0.0)


class DimensionVector(BaseModel):
    """Vecteur dimensionnel pour scoring V2"""
    tech: float = Field(0.0, ge=0.0, le=1.0)
    business: float = Field(0.0, ge=0.0, le=1.0)
    social: float = Field(0.0, ge=0.0, le=1.0)
    creativity: float = Field(0.0, ge=0.0, le=1.0)
    impact: float = Field(0.0, ge=0.0, le=1.0)
    flexibility: float = Field(0.0, ge=0.0, le=1.0)
    international: float = Field(0.0, ge=0.0, le=1.0)
    expertise: float = Field(0.0, ge=0.0, le=1.0)
    
    def to_dict(self) -> Dict[str, float]:
        return self.model_dump()
    
    def normalize(self) -> "DimensionVector":
        """Normalise le vecteur pour que la somme = 1"""
        total = sum(self.to_dict().values())
        if total > 0:
            for field in self.model_fields:
                setattr(self, field, getattr(self, field) / total)
        return self


class BacInfo(BaseModel):
    """Information sur le bac congolais"""
    code: str = Field(..., description="Code bac (C, D, A, etc.)")
    track: BacTrack = Field(..., description="Track détecté")
    is_valid: bool = True
    compatibility_scores: Dict[str, float] = Field(default_factory=dict)
    
    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        valid_codes = {"A", "A1", "A2", "A3", "B", "C", "D", "E", 
                       "F1", "F2", "F3", "F4", "G1", "G2", "G3", "BG",
                       "H1", "H2", "H3", "H4", "H5", "R1", "R2", "R3", 
                       "R4", "R5", "R6", "P2", "P3", "P4", "P5", "P6", "P7"}
        
        code_upper = v.upper().strip()
        if code_upper not in valid_codes:
            raise ValueError(f"Invalid bac code: {v}")
        return code_upper


class ProfileContext(BaseModel):
    """Contexte du profil utilisateur"""
    user_type: UserType = UserType.BACHELIER
    bac_info: Optional[BacInfo] = None
    quiz_version: str = "2.0"
    orientation_type: str = "field"
    session_id: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    location: Optional[str] = None


# ============================================================================
# MODÈLE PRINCIPAL ORIENTATION PROFILE
# ============================================================================

class OrientationProfile(BaseModel):
    """
    Profil d'orientation utilisateur - Version 2.0
    
    Améliorations:
    - Support du scoring vectoriel V2
    - Intégration bac congolais
    - Métadonnées enrichies
    - Clusters dominants
    """
    
    model_config = ConfigDict(extra="forbid")
    
    # Données de base
    domains: Dict[str, float] = Field(default_factory=dict, description="Scores par domaine PROA (0-1)")
    skills: Dict[str, float] = Field(default_factory=dict, description="Scores par compétence (0-1)")
    
    # Scoring V2
    dimension_vector: Optional[DimensionVector] = Field(None, description="Vecteur dimensionnel 8D")
    dominant_cluster: Optional[str] = Field(None, description="Cluster métier dominant")
    feature_scores: Optional[Dict[str, float]] = Field(None, description="Scores par feature")
    
    # Métadonnées
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Confiance globale (0-1)")
    source: ProfileSource = Field(ProfileSource.QUIZ, description="Source du profil")
    scoring_method: str = Field("v2_vectorial", description="Méthode de scoring utilisée")
    
    # Contexte
    context: Optional[ProfileContext] = None
    
    # Métriques de qualité
    feature_coverage: float = Field(0.0, ge=0.0, le=1.0, description="Couverture des features")
    computation_time_ms: float = Field(0.0, description="Temps de calcul en ms")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # ========================================================================
    # VALIDATEURS
    # ========================================================================
    
    @field_validator("domains", "skills")
    @classmethod
    def check_values(cls, values: Dict[str, float]) -> Dict[str, float]:
        """Valide que les scores sont dans [0,1]"""
        for k, v in values.items():
            if not isinstance(v, (int, float)):
                raise ValueError(f"{k} must be numeric, got {type(v)}")
            if not 0.0 <= v <= 1.0:
                raise ValueError(f"{k} hors intervalle [0,1], got {v}")
        return values
    
    @field_validator("dominant_cluster")
    @classmethod
    def validate_cluster(cls, v: Optional[str]) -> Optional[str]:
        """Valide le cluster dominant"""
        if v is None:
            return v
        
        valid_clusters = {
            "informatique", "engineering", "business", "droit", "social",
            "sante", "sciences", "geoscience", "arts_design", "agriculture"
        }
        
        if v not in valid_clusters:
            raise ValueError(f"Invalid dominant_cluster: {v}")
        return v
    
    @model_validator(mode="after")
    def validate_consistency(self) -> "OrientationProfile":
        """Valide la cohérence du profil"""
        # Si pas de domaines, confiance faible
        if not self.domains and self.confidence > 0.5:
            self.confidence = 0.3
        
        # Normaliser les domaines si nécessaire
        if self.domains:
            max_score = max(self.domains.values())
            if max_score > 1.0:
                self.domains = {k: v / max_score for k, v in self.domains.items()}
        
        return self
    
    # ========================================================================
    # MÉTHODES UTILITAIRES
    # ========================================================================
    
    def get_top_domains(self, n: int = 5) -> List[DomainScore]:
        """Retourne les N meilleurs domaines"""
        sorted_domains = sorted(self.domains.items(), key=lambda x: x[1], reverse=True)
        return [
            DomainScore(name=name, score=score, confidence=self.confidence)
            for name, score in sorted_domains[:n]
        ]
    
    def get_top_skills(self, n: int = 5) -> List[SkillScore]:
        """Retourne les N meilleures compétences"""
        sorted_skills = sorted(self.skills.items(), key=lambda x: x[1], reverse=True)
        return [
            SkillScore(name=name, score=score, confidence=self.confidence)
            for name, score in sorted_skills[:n]
        ]
    
    def get_compatibility_level(self) -> CompatibilityLevel:
        """Retourne le niveau de compatibilité global"""
        if not self.domains:
            return CompatibilityLevel.POOR
        
        avg_score = sum(self.domains.values()) / len(self.domains)
        
        if avg_score >= 0.8:
            return CompatibilityLevel.EXCELLENT
        elif avg_score >= 0.6:
            return CompatibilityLevel.GOOD
        elif avg_score >= 0.4:
            return CompatibilityLevel.FAIR
        else:
            return CompatibilityLevel.POOR
    
    def to_compact_dict(self) -> Dict[str, Any]:
        """Retourne une version compacte du profil pour API"""
        return {
            "domains": self.domains,
            "skills": self.skills,
            "dominant_cluster": self.dominant_cluster,
            "confidence": self.confidence,
            "top_domains": [d.name for d in self.get_top_domains(3)]
        }
    
    def to_vector(self) -> List[float]:
        """Convertit le profil en vecteur numérique pour ML"""
        vector = []
        
        # Ajouter les scores des domaines (triés par ordre alphabétique)
        for domain in sorted(self.domains.keys()):
            vector.append(self.domains[domain])
        
        # Ajouter les scores des compétences
        for skill in sorted(self.skills.keys()):
            vector.append(self.skills[skill])
        
        # Ajouter le vecteur dimensionnel si disponible
        if self.dimension_vector:
            vector.extend(list(self.dimension_vector.to_dict().values()))
        
        return vector
    
    def merge(self, other: "OrientationProfile", weight: float = 0.5) -> "OrientationProfile":
        """
        Fusionne deux profils avec pondération.
        
        Args:
            other: Autre profil à fusionner
            weight: Poids de ce profil (1-weight pour l'autre)
        """
        merged_domains = {}
        for domain, score in self.domains.items():
            merged_domains[domain] = score * weight
        for domain, score in other.domains.items():
            merged_domains[domain] = merged_domains.get(domain, 0) + score * (1 - weight)
        
        merged_skills = {}
        for skill, score in self.skills.items():
            merged_skills[skill] = score * weight
        for skill, score in other.skills.items():
            merged_skills[skill] = merged_skills.get(skill, 0) + score * (1 - weight)
        
        merged_confidence = (self.confidence * weight + other.confidence * (1 - weight))
        
        return OrientationProfile(
            domains=merged_domains,
            skills=merged_skills,
            confidence=merged_confidence,
            source=ProfileSource.HYBRID,
            context=self.context or other.context
        )
    
    def update_timestamp(self):
        """Met à jour le timestamp de modification"""
        self.updated_at = datetime.utcnow()


# ============================================================================
# MODÈLES POUR LA PERSISTANCE
# ============================================================================

class StoredProfile(OrientationProfile):
    """Profil stocké en base avec ID"""
    profile_id: str = Field(..., description="Identifiant unique du profil")
    user_id: str = Field(..., description="Identifiant de l'utilisateur")
    is_active: bool = Field(True, description="Profil actif")
    version: int = Field(1, description="Version du profil")
    
    model_config = ConfigDict(extra="allow")


class ProfileHistory(BaseModel):
    """Historique des profils pour un utilisateur"""
    user_id: str
    profiles: List[StoredProfile]
    total_count: int
    last_updated: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# MODÈLES POUR LES REQUÊTES API
# ============================================================================

class ProfileUpdateRequest(BaseModel):
    """Requête de mise à jour de profil"""
    domains: Optional[Dict[str, float]] = None
    skills: Optional[Dict[str, float]] = None
    context: Optional[ProfileContext] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    
    @field_validator("domains", "skills")
    @classmethod
    def validate_scores(cls, v: Optional[Dict[str, float]]) -> Optional[Dict[str, float]]:
        if v is None:
            return v
        for k, val in v.items():
            if not 0.0 <= val <= 1.0:
                raise ValueError(f"Score for {k} must be between 0 and 1")
        return v


class ProfileResponse(BaseModel):
    """Réponse API pour un profil"""
    status: str = "success"
    profile: OrientationProfile
    message: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    # Test du profil V2
    test_profile = OrientationProfile(
        domains={
            "computer_science": 0.85,
            "engineering": 0.72,
            "business": 0.45
        },
        skills={
            "python": 0.90,
            "problem_solving": 0.85,
            "teamwork": 0.70
        },
        dimension_vector=DimensionVector(
            tech=0.8,
            business=0.4,
            social=0.6,
            creativity=0.5,
            impact=0.3,
            flexibility=0.7,
            international=0.4,
            expertise=0.8
        ),
        dominant_cluster="informatique",
        confidence=0.85,
        source=ProfileSource.V2_VECTORIAL,
        context=ProfileContext(
            user_type=UserType.BACHELIER,
            bac_info=BacInfo(code="C", track=BacTrack.SCIENCE)
        )
    )
    
    print("✅ OrientationProfile V2 valid")
    print(f"   Top domains: {[d.name for d in test_profile.get_top_domains(3)]}")
    print(f"   Compatibility: {test_profile.get_compatibility_level().value}")
    print(f"   Vector length: {len(test_profile.to_vector())}")
    
    # Test fusion
    other_profile = OrientationProfile(
        domains={"design": 0.75, "arts": 0.70},
        skills={"creativity": 0.85},
        confidence=0.7
    )
    
    merged = test_profile.merge(other_profile, weight=0.6)
    print(f"\n✅ Fusion: {len(merged.domains)} domains, confidence={merged.confidence:.2%}")