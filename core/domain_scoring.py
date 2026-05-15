"""
Domain Scoring Module - Calculate domain scores from quiz responses
Version 2.0 - Support du scoring V2, bac congolais, analyse dimensionnelle
Uses question_domain_mapping table for DB-driven configuration
"""

import logging
import statistics
import math
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from supabase import Client

from models.proa import DomainScore, FeatureScore
from core.utils import normalize_responses, get_bac_track

logger = logging.getLogger(__name__)


@dataclass
class DomainAnalysis:
    """Analyse détaillée d'un domaine"""
    name: str
    score: float
    confidence: float
    question_count: int
    coverage: float
    variance: float
    trend: str  # "increasing", "decreasing", "stable"
    contributions: List[Dict[str, Any]] = field(default_factory=list)


class DomainScoringEngine:
    """
    Calculate domain scores based on:
    - question_domain_mapping: question_code → domain → weight
    - Normalized responses [0, 1]
    - Weighted aggregation per domain
    - Support bac congolais et scoring dimensionnel V2
    """
    
    def __init__(self, supabase: Client, cache_ttl_seconds: int = 3600):
        self.supabase = supabase
        self.cache_ttl_seconds = cache_ttl_seconds
        self._domain_mapping_cache: Optional[Dict] = None
        self._domain_info_cache: Optional[Dict] = None
        self._cache_timestamp: Optional[datetime] = None
    
    # =========================================================================
    # FETCH DOMAIN MAPPINGS (DB-DRIVEN) - VERSION AMÉLIORÉE
    # =========================================================================
    
    def _get_domain_mappings(self) -> Dict[str, List[Dict]]:
        """
        Fetch question_code → domain mappings from DB with enhanced info
        
        Returns:
        {
            "q1": [
                {"domain_id": "uuid", "domain_name": "logic", "weight": 0.75, "category": "cognitive"},
                ...
            ],
            ...
        }
        """
        # Check cache
        if self._domain_mapping_cache is not None and self._is_cache_valid():
            logger.info("✅ Domain mapping cache HIT")
            return self._domain_mapping_cache
        
        logger.info("📥 Fetching domain mappings from DB (nested select)")
        
        try:
            # Récupérer les mappings
            result = self.supabase.table("question_domain_mapping").select("""
                question_code,
                weight,
                domaines:domain_id (id, name, category, parent_domain)
            """).order("question_code").execute()
            
            # Récupérer les infos des domaines
            domains_result = self.supabase.table("domaines").select("""
                id, name, category, parent_domain, description, cluster
            """).execute()
            
            # Stocker les infos des domaines
            self._domain_info_cache = {}
            for domain in domains_result.data:
                self._domain_info_cache[domain.get("id")] = {
                    "name": domain.get("name"),
                    "category": domain.get("category", "general"),
                    "parent_domain": domain.get("parent_domain"),
                    "description": domain.get("description", ""),
                    "cluster": domain.get("cluster", "unknown")
                }
            
            # Parse result into structure
            mappings = {}
            for row in result.data:
                q_code = row.get("question_code")
                weight = float(row.get("weight", 1.0))
                domain_info = row.get("domaines")
                
                if not domain_info:
                    logger.warning(f"⚠️ No domain info for {q_code}")
                    continue
                
                domain_id = domain_info.get("id")
                domain_name = domain_info.get("name")
                domain_category = domain_info.get("category", "general")
                
                if q_code not in mappings:
                    mappings[q_code] = []
                
                mappings[q_code].append({
                    "domain_id": domain_id,
                    "domain_name": domain_name,
                    "domain_category": domain_category,
                    "weight": weight
                })
            
            # Cache result
            self._domain_mapping_cache = mappings
            self._cache_timestamp = datetime.utcnow()
            
            logger.info(f"✅ Loaded {len(mappings)} questions with domain mappings")
            logger.info(f"   Total domains: {len(self._domain_info_cache) if self._domain_info_cache else 0}")
            return mappings
            
        except Exception as e:
            logger.error(f"❌ Error fetching domain mappings: {e}")
            raise
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid (TTL)"""
        if not self._cache_timestamp:
            return False
        elapsed = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return elapsed < self.cache_ttl_seconds
    
    # =========================================================================
    # DOMAIN SCORE CALCULATION (V2 AMÉLIORÉE)
    # =========================================================================
    
    def compute_domain_scores(
        self,
        responses: Dict[str, int],
        feature_scores: Optional[Dict[str, FeatureScore]] = None,
        bac_code: Optional[str] = None,
        dimension_scores: Optional[Dict[str, float]] = None
    ) -> Tuple[List[DomainScore], Dict[str, Any]]:
        """
        Compute domain scores from responses - Version V2 améliorée
        
        Algorithm:
        1. Normalize responses [1-5] → [0-1]
        2. For each question, get domain mappings
        3. For each domain, aggregate: Σ(response * weight)
        4. Normalize by total weight per domain
        5. Calculate confidence based on coverage and consistency
        6. Apply bac compatibility adjustment
        7. Correlate with dimension scores if available
        
        Args:
            responses: {q1: 3, q2: 4, ...} (Likert 1-5)
            feature_scores: For cross-reference (optional)
            bac_code: Code bac congolais (optionnel)
            dimension_scores: Scores dimensionnels pour corrélation
        
        Returns:
            (domain_scores: List[DomainScore], stats: Dict)
        """
        logger.info("🧠 Computing domain scores V2...")
        start_time = datetime.utcnow()
        
        # Normalize responses (supporte 1-5 maintenant)
        normalized = self._normalize_responses_v2(responses)
        logger.info(f"📊 Normalized {len(normalized)} responses to [0-1] range")
        
        # Get domain mappings
        domain_mappings = self._get_domain_mappings()
        
        # Calculate domain scores
        domain_aggregates = self._aggregate_domain_scores(normalized, domain_mappings)
        
        # Build DomainScore objects with enhanced metrics
        domain_scores = []
        domain_analyses = []
        
        stats = {
            "total_domains": len(domain_aggregates),
            "avg_questions_per_domain": 0.0,
            "avg_confidence": 0.0,
            "domains_full_coverage": 0,
            "domains_partial_coverage": 0,
            "domains_low_coverage": 0,
            "bac_adjustment_applied": bac_code is not None,
            "dimension_correlation": 0.0
        }
        
        for domain_name, agg in domain_aggregates.items():
            # Normalize score
            if agg["total_weight"] > 0:
                normalized_score = agg["total_score"] / agg["total_weight"]
                normalized_score = min(1.0, max(0.0, normalized_score))
            else:
                normalized_score = 0.0
            
            # Calculate variance of contributions
            contributions_scores = [c["contribution"] for c in agg["contributions"]]
            variance = statistics.variance(contributions_scores) if len(contributions_scores) > 1 else 0.0
            
            # Analyze trend
            trend = self._analyze_trend(contributions_scores) if len(contributions_scores) >= 3 else "stable"
            
            # Confidence based on coverage and consistency
            expected_questions = 24
            coverage = agg["count"] / expected_questions if expected_questions > 0 else 0.0
            consistency_score = self._calculate_consistency(contributions_scores)
            confidence = min(1.0, (coverage * 0.6 + consistency_score * 0.4))
            
            # Apply bac adjustment if available
            bac_multiplier = 1.0
            if bac_code:
                bac_multiplier = self._get_bac_domain_multiplier(bac_code, domain_name)
                normalized_score = min(1.0, normalized_score * bac_multiplier)
            
            # Track coverage
            if coverage >= 0.8:
                stats["domains_full_coverage"] += 1
            elif coverage >= 0.5:
                stats["domains_partial_coverage"] += 1
            else:
                stats["domains_low_coverage"] += 1
            
            # Create DomainScore object with enhanced data
            domain_score = DomainScore(
                domain_id=agg["domain_id"],
                domain_name=domain_name,
                score=round(normalized_score, 4),
                feature_scores=[],
                total_weight=round(agg["total_weight"], 2),
                confidence=round(confidence, 4)
            )
            
            domain_scores.append(domain_score)
            
            # Store analysis for debugging
            domain_analyses.append(DomainAnalysis(
                name=domain_name,
                score=normalized_score,
                confidence=confidence,
                question_count=agg["count"],
                coverage=coverage,
                variance=variance,
                trend=trend,
                contributions=agg["contributions"][:5]  # Top 5 contributions
            ))
            
            logger.debug(f"✅ {domain_name:20s} score: {normalized_score:.4f} | "
                        f"confidence: {confidence:.4f} | trend: {trend}")
        
        # Calculate statistics
        if domain_scores:
            stats["avg_confidence"] = sum(d.confidence for d in domain_scores) / len(domain_scores)
            stats["avg_questions_per_domain"] = (
                sum(agg["count"] for agg in domain_aggregates.values()) / len(domain_aggregates)
            )
        
        # Correlate with dimension scores if available
        if dimension_scores:
            correlation = self._correlate_with_dimensions(domain_scores, dimension_scores)
            stats["dimension_correlation"] = round(correlation, 4)
        
        # Sort by score (descending)
        domain_scores.sort(key=lambda x: x.score, reverse=True)
        
        # Timing
        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        stats["computation_time_ms"] = round(elapsed_ms, 2)
        
        logger.info(f"📈 DOMAIN SCORING STATS V2:")
        logger.info(f"   Total domains: {stats['total_domains']}")
        logger.info(f"   Full coverage: {stats['domains_full_coverage']}")
        logger.info(f"   Partial coverage: {stats['domains_partial_coverage']}")
        logger.info(f"   Low coverage: {stats['domains_low_coverage']}")
        logger.info(f"   Avg confidence: {stats['avg_confidence']:.4f}")
        logger.info(f"   Bac adjustment: {stats['bac_adjustment_applied']}")
        logger.info(f"   Time: {stats['computation_time_ms']:.2f}ms")
        
        return domain_scores, stats
    
    def _normalize_responses_v2(self, responses: Dict[str, int]) -> Dict[str, float]:
        """
        Normalise les réponses (supporte échelle 1-5)
        """
        normalized = {}
        for key, value in responses.items():
            if isinstance(value, (int, float)):
                # Normalisation 1-5 → 0-1
                normalized_value = (value - 1) / 4.0
                normalized[key.lower()] = max(0.0, min(1.0, normalized_value))
            else:
                normalized[key.lower()] = 0.5
        return normalized
    
    def _aggregate_domain_scores(
        self,
        normalized: Dict[str, float],
        domain_mappings: Dict[str, List[Dict]]
    ) -> Dict[str, Dict]:
        """
        Agrège les scores par domaine
        """
        domain_aggregates = {}
        
        for q_code, response_value in normalized.items():
            # Normaliser le code question
            q_normalized = q_code.lower()
            if q_normalized.startswith('question_'):
                q_normalized = q_normalized.replace('question_', 'q')
            
            if q_normalized not in domain_mappings:
                logger.debug(f"⚠️ {q_normalized} not in domain mappings")
                continue
            
            # Get domains for this question
            for domain_info in domain_mappings[q_normalized]:
                domain_name = domain_info["domain_name"]
                weight = domain_info["weight"]
                
                # Weighted contribution
                weighted_score = response_value * weight
                
                # Aggregate
                if domain_name not in domain_aggregates:
                    domain_aggregates[domain_name] = {
                        "domain_id": domain_info["domain_id"],
                        "total_score": 0.0,
                        "total_weight": 0.0,
                        "count": 0,
                        "contributions": []
                    }
                
                domain_aggregates[domain_name]["total_score"] += weighted_score
                domain_aggregates[domain_name]["total_weight"] += weight
                domain_aggregates[domain_name]["count"] += 1
                domain_aggregates[domain_name]["contributions"].append({
                    "question": q_normalized,
                    "response": response_value,
                    "weight": weight,
                    "contribution": weighted_score
                })
        
        return domain_aggregates
    
    def _calculate_consistency(self, scores: List[float]) -> float:
        """
        Calcule la cohérence des contributions
        """
        if not scores or len(scores) < 2:
            return 0.7
        
        try:
            variance = statistics.variance(scores)
            # Plus la variance est faible, plus c'est cohérent
            # Variance idéale entre 0.05 et 0.15
            if variance < 0.03:
                return 0.6  # Trop uniforme
            elif variance <= 0.08:
                return 0.85
            elif variance <= 0.15:
                return 0.95
            elif variance <= 0.25:
                return 0.75
            else:
                return 0.55
        except:
            return 0.7
    
    def _analyze_trend(self, scores: List[float]) -> str:
        """
        Analyse la tendance des contributions
        """
        if len(scores) < 3:
            return "stable"
        
        # Diviser en 3 segments
        segment_size = len(scores) // 3
        if segment_size == 0:
            return "stable"
        
        first_avg = statistics.mean(scores[:segment_size])
        last_avg = statistics.mean(scores[-segment_size:])
        
        diff = last_avg - first_avg
        
        if diff > 0.15:
            return "increasing"
        elif diff < -0.15:
            return "decreasing"
        else:
            return "stable"
    
    def _get_bac_domain_multiplier(self, bac_code: str, domain_name: str) -> float:
        """
        Calcule le multiplicateur basé sur le bac pour un domaine
        """
        bac_track = get_bac_track(bac_code)
        if not bac_track:
            return 1.0
        
        # Mapping domaines -> bonus par track bac
        domain_bonus = {
            "science": {
                "computer_science": 1.15,
                "engineering": 1.10,
                "mathematics": 1.20,
                "physics": 1.15,
                "chemistry": 1.10
            },
            "technical": {
                "engineering": 1.20,
                "technology": 1.15,
                "computer_science": 1.10,
                "mechanics": 1.15
            },
            "business": {
                "business": 1.20,
                "finance": 1.15,
                "management": 1.10,
                "marketing": 1.10
            },
            "humanities": {
                "literature": 1.20,
                "languages": 1.15,
                "social_sciences": 1.10,
                "law": 1.10
            },
            "informatics": {
                "computer_science": 1.25,
                "information_technology": 1.20,
                "data_science": 1.15,
                "networks": 1.15
            }
        }
        
        bonus = domain_bonus.get(bac_track, {}).get(domain_name, 1.0)
        
        # Ajuster pour les domaines génériques
        if bonus == 1.0 and bac_track == "science" and "science" in domain_name.lower():
            bonus = 1.10
        elif bonus == 1.0 and bac_track == "business" and "business" in domain_name.lower():
            bonus = 1.10
        
        return bonus
    
    def _correlate_with_dimensions(
        self,
        domain_scores: List[DomainScore],
        dimension_scores: Dict[str, float]
    ) -> float:
        """
        Calcule la corrélation entre scores de domaines et dimensions
        """
        if not domain_scores or not dimension_scores:
            return 0.0
        
        # Mapping simplifié domaines → dimensions
        domain_to_dimension = {
            "computer_science": "tech",
            "engineering": "tech",
            "business": "business",
            "finance": "business",
            "marketing": "business",
            "social": "social",
            "psychology": "social",
            "design": "creativity",
            "arts": "creativity",
            "environment": "impact",
            "medicine": "impact",
            "international": "international",
            "research": "expertise",
            "analysis": "expertise"
        }
        
        correlations = []
        for domain in domain_scores:
            dim = domain_to_dimension.get(domain.domain_name)
            if dim and dim in dimension_scores:
                # Plus le score est proche, meilleure la corrélation
                diff = abs(domain.score - dimension_scores[dim])
                correlation = 1.0 - min(1.0, diff)
                correlations.append(correlation)
        
        return statistics.mean(correlations) if correlations else 0.5
    
    # =========================================================================
    # MÉTHODES COMPLÉMENTAIRES
    # =========================================================================
    
    def get_domain_cluster(self, domain_name: str) -> str:
        """
        Retourne le cluster PROA d'un domaine
        """
        if not self._domain_info_cache:
            self._get_domain_mappings()
        
        for domain_id, info in (self._domain_info_cache or {}).items():
            if info.get("name") == domain_name:
                return info.get("cluster", "unknown")
        
        # Fallback basé sur le nom
        cluster_mapping = {
            "computer": "informatique",
            "software": "informatique",
            "data": "informatique",
            "engineering": "engineering",
            "mechanical": "engineering",
            "electrical": "engineering",
            "business": "business",
            "finance": "business",
            "marketing": "business",
            "law": "droit",
            "legal": "droit",
            "social": "social",
            "psychology": "social",
            "medicine": "sante",
            "health": "sante",
            "science": "sciences",
            "math": "sciences"
        }
        
        for key, cluster in cluster_mapping.items():
            if key in domain_name.lower():
                return cluster
        
        return "unknown"
    
    def get_domain_category(self, domain_name: str) -> str:
        """
        Retourne la catégorie d'un domaine
        """
        if not self._domain_info_cache:
            self._get_domain_mappings()
        
        for domain_id, info in (self._domain_info_cache or {}).items():
            if info.get("name") == domain_name:
                return info.get("category", "general")
        
        return "general"
    
    def clear_cache(self):
        """Vide le cache des mappings"""
        self._domain_mapping_cache = None
        self._domain_info_cache = None
        self._cache_timestamp = None
        logger.info("Domain mapping cache cleared")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_top_domains(domain_scores: List[DomainScore], top_n: int = 3) -> List[str]:
    """Get top N domain names by score"""
    return [d.domain_name for d in domain_scores[:top_n]]


def get_domain_by_name(domain_scores: List[DomainScore], name: str) -> Optional[DomainScore]:
    """Get domain score by name"""
    for score in domain_scores:
        if score.domain_name.lower() == name.lower():
            return score
    return None


def get_domains_by_cluster(
    domain_scores: List[DomainScore],
    cluster: str,
    engine: DomainScoringEngine
) -> List[DomainScore]:
    """Filtre les domaines par cluster"""
    return [
        d for d in domain_scores
        if engine.get_domain_cluster(d.domain_name) == cluster
    ]


def aggregate_by_cluster(
    domain_scores: List[DomainScore],
    engine: DomainScoringEngine
) -> Dict[str, float]:
    """Agrège les scores par cluster PROA"""
    cluster_scores = {}
    cluster_counts = {}
    
    for domain in domain_scores:
        cluster = engine.get_domain_cluster(domain.domain_name)
        if cluster not in cluster_scores:
            cluster_scores[cluster] = 0.0
            cluster_counts[cluster] = 0
        
        cluster_scores[cluster] += domain.score
        cluster_counts[cluster] += 1
    
    # Moyenne par cluster
    for cluster in cluster_scores:
        if cluster_counts[cluster] > 0:
            cluster_scores[cluster] /= cluster_counts[cluster]
    
    return dict(sorted(cluster_scores.items(), key=lambda x: x[1], reverse=True))


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    from unittest.mock import MagicMock
    
    # Mock Supabase client
    mock_supabase = MagicMock()
    
    # Simuler des réponses
    test_responses = {
        "q1": 5, "q2": 4, "q3": 5, "q4": 3, "q5": 4,
        "q6": 2, "q7": 3, "q8": 4, "q9": 5, "q10": 4
    }
    
    # Créer l'engine (sans DB réelle pour test)
    engine = DomainScoringEngine(mock_supabase)
    
    # Simuler des mappings
    engine._domain_mapping_cache = {
        "q1": [{"domain_id": "d1", "domain_name": "computer_science", "domain_category": "tech", "weight": 0.8}],
        "q2": [{"domain_id": "d2", "domain_name": "engineering", "domain_category": "tech", "weight": 0.7}],
        "q3": [{"domain_id": "d3", "domain_name": "business", "domain_category": "business", "weight": 0.9}],
    }
    
    # Tester
    dimension_scores = {"tech": 0.8, "business": 0.6, "social": 0.4}
    
    scores, stats = engine.compute_domain_scores(
        test_responses,
        bac_code="C",
        dimension_scores=dimension_scores
    )
    
    print("\n📊 Domain Scores V2 Test Results")
    print("=" * 50)
    print(f"Stats: {stats}")
    print("\nDomains:")
    for score in scores[:5]:
        print(f"  {score.domain_name}: {score.score:.2%} (conf: {score.confidence:.2%})")
    
    # Test aggregation by cluster
    clusters = aggregate_by_cluster(scores, engine)
    print(f"\n📈 Cluster aggregation: {clusters}")