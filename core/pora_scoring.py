"""
PORA Scoring Module - Calculate composite popularity + engagement + orientation match
PORA = 0.4 * popularity + 0.3 * engagement + 0.3 * orientation_match
"""

import logging
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from supabase import Client

from models.proa import UniversiteScore, CentreScore, FiliereScore

logger = logging.getLogger(__name__)


class PoraScoring:
    """
    Calculate PORA scores for universités and centres
    
    PORA Composite Formula:
    PORA = 0.4 * popularity + 0.3 * engagement + 0.3 * orientation_match
    
    Where:
    - popularity: followers / max_followers
    - engagement: (likes + views) / max_engagement  
    - orientation_match: best_filière_score at that institution
    """
    
    # Weights
    WEIGHT_POPULARITY = 0.4
    WEIGHT_ENGAGEMENT = 0.3
    WEIGHT_ORIENTATION = 0.3
    
    def __init__(self, supabase: Client, cache_ttl_seconds: int = 3600):
        self.supabase = supabase
        self.cache_ttl_seconds = cache_ttl_seconds
        self._universite_filiere_cache: Optional[Dict] = None
        self._centre_filiere_cache: Optional[Dict] = None
        self._cache_timestamp: Optional[datetime] = None
    
    # =========================================================================
    # DATA FETCHING
    # =========================================================================
    
    def _get_universite_filieres(self) -> Dict[str, List[str]]:
        """
        Get filieres offered by each université
        
        Query:
        ```sql
        SELECT DISTINCT
            u.id as universite_id,
            f.id as filiere_id
        FROM universites u
        JOIN universite_filieres uf ON u.id = uf.universite_id
        JOIN filieres f ON uf.filiere_id = f.id
        ```
        
        Returns:
        {
            "universite_uuid": ["filiere_uuid_1", "filiere_uuid_2", ...]
        }
        """
        if self._universite_filiere_cache and self._is_cache_valid():
            return self._universite_filiere_cache
        
        logger.info("📥 Fetching université-filière mappings")
        
        try:
            result = self.supabase.table("universite_filieres").select("""
                universite_id,
                filiere_id
            """).execute()
            
            mappings = {}
            for row in result.data:
                uni_id = row.get("universite_id")
                fil_id = row.get("filiere_id")
                
                if uni_id not in mappings:
                    mappings[uni_id] = []
                mappings[uni_id].append(fil_id)
            
            self._universite_filiere_cache = mappings
            self._cache_timestamp = datetime.utcnow()
            
            logger.info(f"✅ Loaded {len(mappings)} universities with filières")
            return mappings
            
        except Exception as e:
            logger.error(f"❌ Error fetching université filières: {e}")
            return {}
    
    def _get_centre_filieres(self) -> Dict[str, List[str]]:
        """
        Get filieres offered by each centre de formation
        """
        if self._centre_filiere_cache and self._is_cache_valid():
            return self._centre_filiere_cache
        
        logger.info("📥 Fetching centre-filière mappings")
        
        try:
            result = self.supabase.table("filieres_centre").select("""
                centre_id,
                filiere_id
            """).execute()
            
            mappings = {}
            for row in result.data:
                centre_id = row.get("centre_id")
                fil_id = row.get("filiere_id")
                
                if centre_id not in mappings:
                    mappings[centre_id] = []
                mappings[centre_id].append(fil_id)
            
            self._centre_filiere_cache = mappings
            return mappings
            
        except Exception as e:
            logger.error(f"❌ Error fetching centre filières: {e}")
            return {}
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        if not self._cache_timestamp:
            return False
        elapsed = (datetime.utcnow() - self._cache_timestamp).total_seconds()
        return elapsed < self.cache_ttl_seconds
    
    # =========================================================================
    # SCORE CALCULATIONS
    # =========================================================================
    
    def _calculate_popularity_score(
        self,
        followers_count: int,
        max_followers: int = 100000
    ) -> float:
        """
        Normalize followers to [0, 1]
        """
        if max_followers <= 0:
            return 0.0
        
        score = min(1.0, followers_count / max_followers)
        return round(score, 4)
    
    def _calculate_engagement_score(
        self,
        engagement_count: int,
        max_engagement: int = 500000
    ) -> float:
        """
        Normalize engagement (likes + views + interactions) to [0, 1]
        """
        if max_engagement <= 0:
            return 0.0
        
        score = min(1.0, engagement_count / max_engagement)
        return round(score, 4)
    
    def _get_best_filiere_match(
        self,
        institution_filiere_ids: List[str],
        filiere_scores: List[FiliereScore]
    ) -> float:
        """
        Find best filière match at this institution
        """
        institution_filiere_set = set(institution_filiere_ids)
        
        best_score = 0.0
        for filiere in filiere_scores:
            if filiere.filiere_id in institution_filiere_set:
                best_score = max(best_score, filiere.score)
        
        return best_score
    
    def compute_universite_scores(
        self,
        filiere_scores: List[FiliereScore],
        top_n: Optional[int] = None
    ) -> Tuple[List[UniversiteScore], Dict[str, any]]:
        """
        Compute PORA scores for universités
        
        Algorithm:
        1. Fetch all universités with followers + engagement
        2. For each université:
           a. Get offered filieres
           b. Find best filière match
           c. Calculate popularity score (followers)
           d. Calculate engagement score
           e. Calculate composite: PORA = 0.4*pop + 0.3*eng + 0.3*filière
        3. Rank by PORA score
        
        Returns:
            (universite_scores: List[UniversiteScore], stats: Dict)
        """
        logger.info("🎯 Computing université PORA scores...")
        start_time = datetime.utcnow()
        
        # Get filière mappings
        uni_filiere_map = self._get_universite_filieres()
        
        # Fetch universités
        try:
            result = self.supabase.table("universites").select("""
                id as universite_id,
                name,
                followers_count,
                engagement_count
            """).order("name").execute()
            
            universite_scores = []
            stats = {
                "total_universites": len(result.data),
                "scored": 0,
                "avg_pora": 0.0,
                "avg_popularity": 0.0,
                "avg_engagement": 0.0,
                "avg_orientation_match": 0.0
            }
            
            for uni_row in result.data:
                uni_id = uni_row.get("universite_id")
                uni_name = uni_row.get("name")
                followers = int(uni_row.get("followers_count", 0))
                engagement = int(uni_row.get("engagement_count", 0))
                
                # Get filieres at this université
                uni_filieres = uni_filiere_map.get(uni_id, [])
                
                # Calculate component scores
                popularity = self._calculate_popularity_score(followers)
                engagement_score = self._calculate_engagement_score(engagement)
                orientation_match = self._get_best_filiere_match(uni_filieres, filiere_scores)
                
                # Composite PORA
                pora_score = (
                    self.WEIGHT_POPULARITY * popularity +
                    self.WEIGHT_ENGAGEMENT * engagement_score +
                    self.WEIGHT_ORIENTATION * orientation_match
                )
                pora_score = round(pora_score, 4)
                
                # Create score object
                uni_score = UniversiteScore(
                    universite_id=uni_id,
                    universite_name=uni_name,
                    filiere_match=round(orientation_match, 4),
                    popularity=popularity,
                    filieres=uni_filieres,
                    pora_score=pora_score,
                    ranking=0  # Will be set after sorting
                )
                
                universite_scores.append(uni_score)
                stats["scored"] += 1
                
                logger.debug(f"✅ {uni_name:30s} PORA: {pora_score:.4f} (pop: {popularity:.2f}, eng: {engagement_score:.2f}, fil: {orientation_match:.2f})")
            
            # Sort and assign rankings
            universite_scores.sort(key=lambda x: x.pora_score, reverse=True)
            for i, score in enumerate(universite_scores, 1):
                score.ranking = i
            
            # Limit if requested
            if top_n:
                universite_scores = universite_scores[:top_n]
            
            # Statistics
            stats["avg_pora"] = (
                sum(u.pora_score for u in universite_scores) / len(universite_scores)
                if universite_scores else 0.0
            )
            stats["avg_popularity"] = (
                sum(u.popularity for u in universite_scores) / len(universite_scores)
                if universite_scores else 0.0
            )
            stats["avg_engagement"] = (
                sum(u.filiere_match for u in universite_scores) / len(universite_scores)
                if universite_scores else 0.0
            )
            
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            stats["computation_time_ms"] = round(elapsed_ms, 2)
            
            logger.info(f"📊 UNIVERSITÉ PORA STATS:")
            logger.info(f"   Total: {stats['total_universites']}")
            logger.info(f"   Avg PORA: {stats['avg_pora']:.4f}")
            logger.info(f"   Time: {stats['computation_time_ms']:.2f}ms")
            
            return universite_scores, stats
            
        except Exception as e:
            logger.error(f"❌ Error computing université scores: {e}")
            raise
    
    def compute_centre_scores(
        self,
        filiere_scores: List[FiliereScore],
        top_n: Optional[int] = None
    ) -> Tuple[List[CentreScore], Dict[str, any]]:
        """
        Compute PORA scores for centres de formation
        
        Same logic as universités but for centres
        """
        logger.info("🏫 Computing centre de formation PORA scores...")
        start_time = datetime.utcnow()
        
        centre_filiere_map = self._get_centre_filieres()
        
        try:
            result = self.supabase.table("centres_formation").select("""
                id as centre_id,
                name,
                universite_id,
                universites:universite_id (name),
                followers_count,
                engagement_count
            """).order("name").execute()
            
            centre_scores = []
            stats = {
                "total_centres": len(result.data),
                "scored": 0,
                "avg_pora": 0.0
            }
            
            for centre_row in result.data:
                centre_id = centre_row.get("centre_id")
                centre_name = centre_row.get("name")
                followers = int(centre_row.get("followers_count", 0))
                engagement = int(centre_row.get("engagement_count", 0))
                
                # Get université name
                uni_info = centre_row.get("universites")
                universite_name = uni_info.get("name") if uni_info else None
                
                # Get filieres at this centre
                centre_filieres = centre_filiere_map.get(centre_id, [])
                
                # Calculate scores
                popularity = self._calculate_popularity_score(followers)
                engagement_score = self._calculate_engagement_score(engagement)
                orientation_match = self._get_best_filiere_match(centre_filieres, filiere_scores)
                
                # PORA composite
                pora_score = (
                    self.WEIGHT_POPULARITY * popularity +
                    self.WEIGHT_ENGAGEMENT * engagement_score +
                    self.WEIGHT_ORIENTATION * orientation_match
                )
                pora_score = round(pora_score, 4)
                
                # Create score object
                centre_score = CentreScore(
                    centre_id=centre_id,
                    centre_name=centre_name,
                    universite_name=universite_name,
                    filiere_match=round(orientation_match, 4),
                    popularity=popularity,
                    engagement_score=engagement_score,
                    pora_score=pora_score,
                    ranking=0
                )
                
                centre_scores.append(centre_score)
                stats["scored"] += 1
                
                logger.debug(f"✅ {centre_name:30s} PORA: {pora_score:.4f}")
            
            # Sort and rank
            centre_scores.sort(key=lambda x: x.pora_score, reverse=True)
            for i, score in enumerate(centre_scores, 1):
                score.ranking = i
            
            if top_n:
                centre_scores = centre_scores[:top_n]
            
            stats["avg_pora"] = (
                sum(c.pora_score for c in centre_scores) / len(centre_scores)
                if centre_scores else 0.0
            )
            
            elapsed_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            stats["computation_time_ms"] = round(elapsed_ms, 2)
            
            logger.info(f"📊 CENTRE PORA STATS:")
            logger.info(f"   Total: {stats['total_centres']}")
            logger.info(f"   Avg PORA: {stats['avg_pora']:.4f}")
            logger.info(f"   Time: {stats['computation_time_ms']:.2f}ms")
            
            return centre_scores, stats
            
        except Exception as e:
            logger.error(f"❌ Error computing centre scores: {e}")
            raise
