"""
Recommendation Engine - Generate personalized recommendations based on computed scores
Covers filieres, universites, centres, and cross-recommendations
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from supabase import Client

from models.proa import (
    Recommendation, RecommendationType, FiliereScore, 
    UniversiteScore, CentreScore
)

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """
    Generate personalized recommendations from computed scores
    
    Strategies:
    1. Filière recommendations: Top N by score
    2. Université recommendations: Top N by PORA score, filtered by offered filieres
    3. Centre recommendations: Top N by PORA score
    4. Cross recommendations: Using formation_recommandations_cross table
    """
    
    def __init__(self, supabase: Client):
        self.supabase = supabase
    
    # =========================================================================
    # FILIÈRE RECOMMENDATIONS
    # =========================================================================
    
    def recommend_filieres(
        self,
        filiere_scores: List[FiliereScore],
        top_n: int = 5,
        min_score: float = 0.3
    ) -> List[Recommendation]:
        """
        Recommend filieres based on student's domain matches
        
        Filters:
        - Top N by score
        - Minimum compatibility score
        
        Returns:
            List[Recommendation] with metadata
        """
        logger.info(f"🎓 Generating filière recommendations (top {top_n})")
        
        # Filter by min score
        candidates = [f for f in filiere_scores if f.score >= min_score]
        logger.info(f"   {len(candidates)} filieres meet min score {min_score}")
        
        # Take top N
        top_filieres = candidates[:top_n]
        
        recommendations = []
        for rank, filiere in enumerate(top_filieres, 1):
            # Determine reason based on compatibility
            if filiere.compatibility_level == "excellent":
                reason = f"Excellent match - your top domains {filiere.top_domains} strongly align"
            elif filiere.compatibility_level == "good":
                reason = f"Good match - domains {filiere.top_domains} are well-aligned"
            elif filiere.compatibility_level == "fair":
                reason = f"Fair match - some domains ({filiere.top_domains[0]} especially) match well"
            else:
                reason = f"Potential match - {filiere.field} field worth exploring"
            
            rec = Recommendation(
                id=filiere.filiere_id,
                name=filiere.filiere_name,
                type=RecommendationType.FILIERES,
                score=filiere.score,
                reason=reason,
                metadata={
                    "field": filiere.field,
                    "duration_years": filiere.duration_years,
                    "compatibility": filiere.compatibility_level,
                    "rank": rank,
                    "top_domains": filiere.top_domains,
                    "domain_matches": [
                        {
                            "domain": dm.domain_name,
                            "student_score": dm.domain_score,
                            "importance": dm.importance
                        }
                        for dm in filiere.domain_matches
                    ]
                }
            )
            
            recommendations.append(rec)
            logger.debug(f"   #{rank}: {filiere.filiere_name} ({filiere.compatibility_level})")
        
        logger.info(f"✅ Generated {len(recommendations)} filière recommendations")
        return recommendations
    
    # =========================================================================
    # UNIVERSITÉ RECOMMENDATIONS
    # =========================================================================
    
    def recommend_universites(
        self,
        universite_scores: List[UniversiteScore],
        filiere_recommendations: List[Recommendation],
        top_n: int = 5
    ) -> List[Recommendation]:
        """
        Recommend universités based on:
        - PORA score (popularity + engagement + orientation fit)
        - Offers student's recommended filieres
        - Ranking
        """
        logger.info(f"🎯 Generating université recommendations (top {top_n})")
        
        # Get recommended filière IDs
        recommended_filiere_ids = {
            rec.id for rec in filiere_recommendations
        }
        
        # Score universités: boost if they offer recommended filieres
        scored_unis = []
        for uni in universite_scores:
            score = uni.pora_score
            
            # Bonus: how many recommended filieres does this université offer?
            offered_recommended = [
                f for f in uni.filieres if f in recommended_filiere_ids
            ]
            
            if offered_recommended:
                # Boost score if offers recommended filieres
                filiere_bonus = min(0.2, len(offered_recommended) * 0.05)  # Max 0.2 bonus
                score = min(1.0, score + filiere_bonus)
                
                reason = f"Offers {len(offered_recommended)} of your top filieres"
            else:
                reason = "Highly ranked - excellent reputation and engagement"
            
            scored_unis.append({
                "universite": uni,
                "adjusted_score": score,
                "offered_recommended_count": len(offered_recommended),
                "reason": reason
            })
        
        # Sort by adjusted score
        scored_unis.sort(key=lambda x: x["adjusted_score"], reverse=True)
        
        # Take top N
        top_unis = scored_unis[:top_n]
        
        recommendations = []
        for rank, item in enumerate(top_unis, 1):
            uni = item["universite"]
            
            rec = Recommendation(
                id=uni.universite_id,
                name=uni.universite_name,
                type=RecommendationType.UNIVERSITES,
                score=item["adjusted_score"],
                reason=item["reason"],
                metadata={
                    "pora_score": uni.pora_score,
                    "popularity": uni.popularity,
                    "filieres_count": len(uni.filieres),
                    "rank": rank,
                    "recommended_filieres": uni.filieres[:5]  # Top 5
                }
            )
            
            recommendations.append(rec)
            logger.debug(f"   #{rank}: {uni.universite_name} (PORA: {uni.pora_score:.4f})")
        
        logger.info(f"✅ Generated {len(recommendations)} université recommendations")
        return recommendations
    
    # =========================================================================
    # CENTRE RECOMMENDATIONS
    # =========================================================================
    
    def recommend_centres(
        self,
        centre_scores: List[CentreScore],
        top_n: int = 5
    ) -> List[Recommendation]:
        """
        Recommend centres de formation based on:
        - PORA score
        - Associated université
        - Engagement metrics
        """
        logger.info(f"🏫 Generating centre de formation recommendations (top {top_n})")
        
        # Take top N by PORA
        top_centres = centre_scores[:top_n]
        
        recommendations = []
        for rank, centre in enumerate(top_centres, 1):
            reason = f"Top rated center - strong engagement and high quality training"
            if centre.universite_name:
                reason = f"{centre.universite_name} training center - excellent reputation"
            
            rec = Recommendation(
                id=centre.centre_id,
                name=centre.centre_name,
                type=RecommendationType.CENTRES,
                score=centre.pora_score,
                reason=reason,
                metadata={
                    "universite": centre.universite_name,
                    "pora_score": centre.pora_score,
                    "popularity": centre.popularity,
                    "engagement": centre.engagement_score,
                    "rank": rank
                }
            )
            
            recommendations.append(rec)
            logger.debug(f"   #{rank}: {centre.centre_name} (PORA: {centre.pora_score:.4f})")
        
        logger.info(f"✅ Generated {len(recommendations)} centre recommendations")
        return recommendations
    
    # =========================================================================
    # CROSS RECOMMENDATIONS
    # =========================================================================
    
    def get_cross_recommendations(
        self,
        selected_filiere_id: str,
        top_n: int = 3
    ) -> List[Recommendation]:
        """
        Get cross-recommendations from formation_recommandations_cross table
        
        Useful for: "Students who chose X also chose Y"
        """
        logger.info(f"🔗 Fetching cross-recommendations for filière {selected_filiere_id}")
        
        try:
            result = self.supabase.table("formation_recommandations_cross").select("""
                filiere_source_id,
                filiere_recommande_id,
                confidence_score,
                filieres:filiere_recommande_id (id, name, field)
            """).eq("filiere_source_id", selected_filiere_id).order(
                "confidence_score", desc=True
            ).limit(top_n).execute()
            
            recommendations = []
            for row in result.data:
                filiere_info = row.get("filieres")
                if not filiere_info:
                    continue
                
                confidence = float(row.get("confidence_score", 0.0))
                
                rec = Recommendation(
                    id=filiere_info.get("id"),
                    name=filiere_info.get("name"),
                    type=RecommendationType.FILIERES,
                    score=confidence,
                    reason="Students in similar programs often choose this",
                    metadata={
                        "type": "cross_recommendation",
                        "confidence": confidence,
                        "field": filiere_info.get("field")
                    }
                )
                
                recommendations.append(rec)
            
            logger.info(f"✅ Found {len(recommendations)} cross-recommendations")
            return recommendations
            
        except Exception as e:
            logger.warning(f"⚠️ Error fetching cross-recommendations: {e}")
            return []
    
    # =========================================================================
    # AGGREGATE ALL RECOMMENDATIONS
    # =========================================================================
    
    def aggregate_recommendations(
        self,
        filiere_recs: List[Recommendation],
        universite_recs: List[Recommendation],
        centre_recs: List[Recommendation],
        cross_recs: Optional[List[Recommendation]] = None
    ) -> Dict[str, List[Recommendation]]:
        """
        Aggregate all recommendations into organized structure
        """
        logger.info("📦 Aggregating all recommendations...")
        
        aggregated = {
            "filieres": filiere_recs,
            "universites": universite_recs,
            "centres": centre_recs
        }
        
        if cross_recs:
            aggregated["cross_recommendations"] = cross_recs
        
        total = len(filiere_recs) + len(universite_recs) + len(centre_recs) + len(cross_recs or [])
        logger.info(f"✅ Aggregated {total} total recommendations")
        
        return aggregated


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def prioritize_recommendations(
    recommendations: List[Recommendation],
    criteria: str = "score"
) -> List[Recommendation]:
    """
    Prioritize recommendations by different criteria
    """
    if criteria == "score":
        return sorted(recommendations, key=lambda x: x.score, reverse=True)
    elif criteria == "name":
        return sorted(recommendations, key=lambda x: x.name)
    else:
        return recommendations


def filter_recommendations_by_type(
    recommendations: Dict[str, List[Recommendation]],
    rec_type: RecommendationType
) -> List[Recommendation]:
    """Filter recommendations by type"""
    results = []
    for rec_list in recommendations.values():
        if isinstance(rec_list, list):
            results.extend([r for r in rec_list if r.type == rec_type])
    return results
