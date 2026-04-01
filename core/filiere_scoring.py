"""
Filière Scoring Module - Match quiz responses to academic programs
Uses filiere_domaines table to weight domain contributions to each filière
"""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from supabase import Client

from models.proa import FiliereScore, DomainScore, FiliereDomainMapping, FiliereRow

logger = logging.getLogger(__name__)


class FiliereEngineScore:
    """
    Calculate filière scores based on:
    - domain_scores: Per-domain matching scores
    - filiere_domaines: Domain importance weights per filière
    - Compatibility mapping: how well student's domains match filière requirements
    """
    
    def __init__(self, supabase: Client, cache_ttl_seconds: int = 3600):
        self.supabase = supabase
        self.cache_ttl_seconds = cache_ttl_seconds
        self._filiere_domain_cache: Optional[Dict] = None
        self._filieres_cache: Optional[List] = None
        self._cache_timestamp: Optional[datetime] = None
    
    # =========================================================================
    # FETCH DATA (DB-DRIVEN)
    # =========================================================================
    
    def _get_filiere_domain_mappings(self) -> Dict[str, List[Dict]]:
        """
        Fetch filière-domain relationships with importance weights
        
        Query:
        ```sql
        SELECT
            f.id as filiere_id,
            f.name as filiere_name,
            f.field,
            d.id as domain_id,
            d.name as domain_name,
            fd.importance as importance_weight
        FROM filieres f
        JOIN filiere_domaines fd ON f.id = fd.filiere_id
        JOIN domaines d ON fd.domain_id = d.id
        ORDER BY f.name
        ```
        
        Returns:
        {
            "filiere_uuid": [
                {
                    "filiere_name": "Analyse & Data Science",
                    "field": "STEM",
                    "domain_id": "uuid",
                    "domain_name": "logic",
                    "importance": 0.9
                },
                ...
            ]
        }
        """
        # Check cache
        if self._filiere_domain_cache is not None and self._is_cache_valid():
            logger.info("✅ Filière domain mapping cache HIT")
            return self._filiere_domain_cache
        
        logger.info("📥 Fetching filière-domain mappings (nested select)")
        
        try:
            # Nested select: filieres → filiere_domaines → domaines
            result = self.supabase.table("filieres").select("""
                id as filiere_id,
                name as filiere_name,
                field,
                duration_years,
                filiere_domaines (
                    importance,
                    domaines:domain_id (id, name)
                )
            """).order("name").execute()
            
            # Parse result
            mappings = {}
            
            for filiere_row in result.data:
                filiere_id = filiere_row.get("filiere_id")
                filiere_name = filiere_row.get("filiere_name")
                field = filiere_row.get("field")
                duration_years = filiere_row.get("duration_years")
                domain_relations = filiere_row.get("filiere_domaines", [])
                
                if not domain_relations:
                    logger.debug(f"⚠️ {filiere_name} has no domain mappings")
                    continue
                
                # Store filière info
                mappings[filiere_id] = {
                    "filiere_name": filiere_name,
                    "field": field,
                    "duration_years": duration_years,
                    "domain_mappings": []
                }
                
                # Store domain mappings
                for relation in domain_relations:
                    domain_info = relation.get("domaines")
                    if not domain_info:
                        continue
                    
                    importance = float(relation.get("importance", 1.0))
                    
                    mappings[filiere_id]["domain_mappings"].append({
                        "domain_id": domain_info.get("id"),
                        "domain_name": domain_info.get("name"),
                        "importance": importance
                    })
            
            # Cache
            self._filiere_domain_cache = mappings
            self._cache_timestamp = datetime.utcnow()
            
            logger.info(f"✅ Loaded {len(mappings)} filieres with domain mappings")
            return mappings
            
        except Exception as e:
            logger.error(f"❌ Error fetching filière domain mappings: {e}")
            raise
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        if not self._cache_timestamp:
            return False
        elapsed = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return elapsed < self.cache_ttl_seconds
    
    # =========================================================================
    # FILIÈRE SCORING
    # =========================================================================
    
    def compute_filiere_scores(
        self,
        domain_scores: List[DomainScore],
        top_n: Optional[int] = None
    ) -> Tuple[List[FiliereScore], Dict[str, any]]:
        """
        Compute filière scores based on domain matches
        
        Algorithm:
        1. For each filière, get domain importance weights
        2. For each domain, find student's score
        3. Weighted sum: Σ(student_domain_score * importance_weight)
        4. Normalize by total importance (can exceed 1.0 if over-matched)
        5. Classify compatibility: excellent/good/fair/poor
        6. Rank by score
        
        Args:
            domain_scores: List of DomainScore objects
            top_n: Return only top N filieres (optional)
        
        Returns:
            (filiere_scores: List[FiliereScore], stats: Dict)
        """
        logger.info("🎓 Computing filière scores...")
        start_time = datetime.utcnow()
        
        # Create domain lookup
        domain_dict = {d.domain_name.lower(): d for d in domain_scores}
        
        # Get filière-domain mappings
        filiere_mappings = self._get_filiere_domain_mappings()
        
        # Calculate scores
        filiere_scores = []
        stats = {
            "total_filieres": len(filiere_mappings),
            "filieres_scored": 0,
            "avg_score": 0.0,
            "excellent_count": 0,
            "good_count": 0,
            "fair_count": 0,
            "poor_count": 0
        }
        
        for filiere_id, filiere_info in filiere_mappings.items():
            filiere_name = filiere_info["filiere_name"]
            field = filiere_info["field"]
            duration_years = filiere_info.get("duration_years")
            domain_mappings = filiere_info.get("domain_mappings", [])
            
            if not domain_mappings:
                logger.debug(f"⚠️ {filiere_name} has no domain mappings, skipping")
                continue
            
            # Calculate composite score
            total_weighted_score = 0.0
            total_importance = 0.0
            domain_matches = []
            top_domains = []
            
            for domain_mapping in domain_mappings:
                domain_name = domain_mapping["domain_name"].lower()
                importance = domain_mapping["importance"]
                
                # Get student's domain score (default to 0 if not matched)
                domain_score = domain_dict.get(domain_name)
                student_score = domain_score.score if domain_score else 0.0
                
                # Weighted contribution
                weighted_contribution = student_score * importance
                total_weighted_score += weighted_contribution
                total_importance += importance
                
                # Track match
                if domain_score:
                    domain_matches.append(FiliereDomainMapping(
                        domain_id=domain_mapping["domain_id"],
                        domain_name=domain_name,
                        domain_score=student_score,
                        importance=importance,
                        contribution=round(weighted_contribution, 4)
                    ))
                    top_domains.append(domain_name)
            
            # Normalize score by total importance
            if total_importance > 0:
                normalized_score = total_weighted_score / total_importance
                normalized_score = min(1.0, max(0.0, normalized_score))
            else:
                normalized_score = 0.0
            
            # Determine compatibility level
            if normalized_score >= 0.8:
                compatibility = "excellent"
                stats["excellent_count"] += 1
            elif normalized_score >= 0.6:
                compatibility = "good"
                stats["good_count"] += 1
            elif normalized_score >= 0.4:
                compatibility = "fair"
                stats["fair_count"] += 1
            else:
                compatibility = "poor"
                stats["poor_count"] += 1
            
            # Create FiliereScore
            filiere_score = FiliereScore(
                filiere_id=filiere_id,
                filiere_name=filiere_name,
                field=field,
                duration_years=duration_years,
                score=round(normalized_score, 4),
                domain_matches=domain_matches,
                top_domains=top_domains[:3],  # Top 3 domains
                compatibility_level=compatibility
            )
            
            filiere_scores.append(filiere_score)
            stats["filieres_scored"] += 1
            
            logger.debug(f"✅ {filiere_name:30s} score: {normalized_score:.4f} ({compatibility})")
        
        # Sort by score (descending)
        filiere_scores.sort(key=lambda x: x.score, reverse=True)
        
        # Limit results if requested
        if top_n:
            filiere_scores = filiere_scores[:top_n]
        
        # Statistics
        stats["avg_score"] = (
            sum(f.score for f in filiere_scores) / len(filiere_scores)
            if filiere_scores else 0.0
        )
        
        elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        stats["computation_time_ms"] = round(elapsed_ms, 2)
        
        logger.info(f"📊 FILIÈRE SCORING STATS:")
        logger.info(f"   Scored: {stats['filieres_scored']} / {stats['total_filieres']}")
        logger.info(f"   Excellent: {stats['excellent_count']} | Good: {stats['good_count']} | Fair: {stats['fair_count']} | Poor: {stats['poor_count']}")
        logger.info(f"   Avg score: {stats['avg_score']:.4f}")
        logger.info(f"   Time: {stats['computation_time_ms']:.2f}ms")
        
        return filiere_scores, stats


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_top_filieres(
    filiere_scores: List[FiliereScore],
    top_n: int = 5
) -> List[FiliereScore]:
    """Get top N filieres by score"""
    return filiere_scores[:top_n]


def get_filieres_by_field(
    filiere_scores: List[FiliereScore],
    field: str
) -> List[FiliereScore]:
    """Get filieres in specific field"""
    return [f for f in filiere_scores if f.field and f.field.lower() == field.lower()]


def get_excellent_matches(filiere_scores: List[FiliereScore]) -> List[FiliereScore]:
    """Get excellent compatibility matches"""
    return [f for f in filiere_scores if f.compatibility_level == "excellent"]


def get_good_matches(filiere_scores: List[FiliereScore]) -> List[FiliereScore]:
    """Get good compatibility matches"""
    return [f for f in filiere_scores if f.compatibility_level in ["excellent", "good"]]
