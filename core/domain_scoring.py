"""
Domain Scoring Module - Calculate domain scores from quiz responses
Uses question_domain_mapping table for DB-driven configuration
"""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from supabase import Client

from models.proa import DomainScore, FeatureScore
from core.utils import normalize_responses, normalize_answer_value

logger = logging.getLogger(__name__)


class DomainScoringEngine:
    """
    Calculate domain scores based on:
    - question_domain_mapping: question_code → domain → weight
    - Normalized responses [0, 1]
    - Weighted aggregation per domain
    """
    
    def __init__(self, supabase: Client, cache_ttl_seconds: int = 3600):
        self.supabase = supabase
        self.cache_ttl_seconds = cache_ttl_seconds
        self._domain_mapping_cache: Optional[Dict] = None
        self._cache_timestamp: Optional[datetime] = None
    
    # =========================================================================
    # FETCH DOMAIN MAPPINGS (DB-DRIVEN)
    # =========================================================================
    
    def _get_domain_mappings(self) -> Dict[str, List[Dict]]:
        """
        Fetch question_code → domain mappings from DB
        
        Query structure:
        ```sql
        SELECT
            question_code,
            domain_id,
            domain_name,
            weight
        FROM question_domain_mapping
        JOIN domaines d ON domain_id = d.id
        ORDER BY question_code, domain_id
        ```
        
        Returns:
        {
            "q1": [
                {"domain_id": "uuid", "domain_name": "logic", "weight": 0.75},
                {"domain_id": "uuid", "domain_name": "technical", "weight": 0.60}
            ],
            "q2": [...],
            ...
        }
        """
        # Check cache
        if self._domain_mapping_cache is not None:
            if self._is_cache_valid():
                logger.info("✅ Domain mapping cache HIT")
                return self._domain_mapping_cache
        
        # Fetch from DB with nested select
        logger.info("📥 Fetching domain mappings from DB (nested select)")
        
        try:
            result = self.supabase.table("question_domain_mapping").select("""
                question_code,
                weight,
                domaines:domain_id (id, name)
            """).order("question_code").execute()
            
            # Parse result into structure
            mappings = {}
            for row in result.data:
                q_code = row.get("question_code")
                weight = float(row.get("weight", 1.0))
                domain_info = row.get("domaines")
                
                if not domain_info:
                    logger.warning(f"⚠️ No domain info for {q_code}")
                    continue
                
                if q_code not in mappings:
                    mappings[q_code] = []
                
                mappings[q_code].append({
                    "domain_id": domain_info.get("id"),
                    "domain_name": domain_info.get("name"),
                    "weight": weight
                })
            
            # Cache result
            self._domain_mapping_cache = mappings
            self._cache_timestamp = datetime.utcnow()
            
            logger.info(f"✅ Loaded {len(mappings)} questions with domain mappings")
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
    # DOMAIN SCORE CALCULATION
    # =========================================================================
    
    def compute_domain_scores(
        self,
        responses: Dict[str, int],
        feature_scores: Optional[Dict[str, FeatureScore]] = None
    ) -> Tuple[List[DomainScore], Dict[str, Any]]:
        """
        Compute domain scores from responses
        
        Algorithm:
        1. Normalize responses [1-4] → [0-1]
        2. For each question, get domain mappings
        3. For each domain, aggregate: Σ(response * weight)
        4. Normalize by total weight per domain
        5. Calculate confidence based on coverage
        
        Args:
            responses: {q1: 3, q2: 4, ...} (Likert 1-4)
            feature_scores: For cross-reference (optional)
        
        Returns:
            (domain_scores: List[DomainScore], stats: Dict)
        """
        logger.info("🧠 Computing domain scores...")
        start_time = datetime.utcnow()
        
        # Normalize responses
        normalized = normalize_responses(responses)
        logger.info(f"📊 Normalized {len(normalized)} responses to [0-1] range")
        
        # Get domain mappings
        domain_mappings = self._get_domain_mappings()
        
        # Calculate domain scores
        domain_aggregates = {}  # {domain_name: {total_score, total_weight, count}}
        
        for q_code, response_value in normalized.items():
            if q_code not in domain_mappings:
                logger.debug(f"⚠️ {q_code} not in domain mappings")
                continue
            
            # Get domains for this question
            for domain_info in domain_mappings[q_code]:
                domain_name = domain_info["domain_name"]
                weight = domain_info["weight"]
                
                # Weighted contribution: response * weight
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
                    "question": q_code,
                    "response": response_value,
                    "weight": weight,
                    "contribution": weighted_score
                })
        
        # Normalize scores
        domain_scores = []
        stats = {
            "total_domains": len(domain_aggregates),
            "avg_questions_per_domain": 0.0,
            "avg_confidence": 0.0,
            "domains_full_coverage": 0,
            "domains_partial_coverage": 0,
            "domains_low_coverage": 0
        }
        
        for domain_name, agg in domain_aggregates.items():
            # Normalize: divide by total weight
            if agg["total_weight"] > 0:
                normalized_score = agg["total_score"] / agg["total_weight"]
                normalized_score = min(1.0, max(0.0, normalized_score))  # Clamp [0, 1]
            else:
                normalized_score = 0.0
            
            # Confidence based on coverage
            expected_questions = 24  # Standard PROA has 24 questions
            coverage = agg["count"] / expected_questions if expected_questions > 0 else 0.0
            confidence = min(1.0, coverage)
            
            # Track coverage
            if coverage >= 0.8:
                stats["domains_full_coverage"] += 1
            elif coverage >= 0.5:
                stats["domains_partial_coverage"] += 1
            else:
                stats["domains_low_coverage"] += 1
            
            # Create DomainScore object
            domain_score = DomainScore(
                domain_id=agg["domain_id"],
                domain_name=domain_name,
                score=round(normalized_score, 4),
                feature_scores=[],  # Optional: populate if features linked
                total_weight=round(agg["total_weight"], 2),
                confidence=round(confidence, 4)
            )
            
            domain_scores.append(domain_score)
            logger.info(f"✅ {domain_name:20s} score: {normalized_score:.4f} (confidence: {confidence:.4f})")
        
        # Calculate statistics
        stats["avg_questions_per_domain"] = (
            sum(agg["count"] for agg in domain_aggregates.values()) / len(domain_aggregates)
            if domain_aggregates else 0.0
        )
        stats["avg_confidence"] = (
            sum(d.confidence for d in domain_scores) / len(domain_scores)
            if domain_scores else 0.0
        )
        
        # Sort by score (descending)
        domain_scores.sort(key=lambda x: x.score, reverse=True)
        
        # Timing
        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        stats["computation_time_ms"] = round(elapsed_ms, 2)
        
        logger.info(f"📈 DOMAIN SCORING STATS:")
        logger.info(f"   Total domains: {stats['total_domains']}")
        logger.info(f"   Full coverage: {stats['domains_full_coverage']}")
        logger.info(f"   Partial coverage: {stats['domains_partial_coverage']}")
        logger.info(f"   Low coverage: {stats['domains_low_coverage']}")
        logger.info(f"   Avg confidence: {stats['avg_confidence']:.4f}")
        logger.info(f"   Time: {stats['computation_time_ms']:.2f}ms")
        
        return domain_scores, stats


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
