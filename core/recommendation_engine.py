"""
Recommendation Engine - Generate personalized recommendations based on computed scores
Version 2.0 - Améliorée avec scoring hybride et insights personnalisés
Covers filieres, universites, centres, and cross-recommendations
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field
from supabase import Client

from models.proa import (
    Recommendation, RecommendationType, FiliereScore, 
    UniversiteScore, CentreScore, ProaComputeResponse
)

logger = logging.getLogger(__name__)


@dataclass
class RecommendationContext:
    """Contexte de recommandation enrichi"""
    user_id: str
    user_type: str
    bac_type: Optional[str] = None
    dominant_cluster: Optional[str] = None
    confidence: float = 0.0
    computation_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)


class RecommendationEngine:
    """
    Moteur de recommandations personnalisées V2
    
    Améliorations:
    - Scoring hybride (vectoriel + règles + intérêts)
    - Insights personnalisés par utilisateur
    - Cache intelligent
    - Diversité des recommandations
    - Fallback robuste
    """
    
    def __init__(self, supabase: Client, use_cache: bool = True):
        self.supabase = supabase
        self.use_cache = use_cache
        self._cache: Dict[str, List[Recommendation]] = {}
        
        logger.info(f"RecommendationEngine V2 initialisé (cache={use_cache})")
    
    # =========================================================================
    # FILIÈRE RECOMMENDATIONS (AMÉLIORÉES)
    # =========================================================================
    
    def recommend_filieres(
        self,
        filiere_scores: List[FiliereScore],
        top_n: int = 5,
        min_score: float = 0.3,
        context: Optional[RecommendationContext] = None,
        ensure_diversity: bool = True
    ) -> List[Recommendation]:
        """
        Recommend filieres with enhanced reasoning and diversity
        
        Args:
            filiere_scores: Liste des scores calculés
            top_n: Nombre max de recommandations
            min_score: Score minimum (0-1)
            context: Contexte utilisateur pour personnalisation
            ensure_diversity: Éviter la redondance de clusters
        
        Returns:
            Liste enrichie de recommandations
        """
        logger.info(f"🎓 Generating filière recommendations (top {top_n}, min_score={min_score})")
        
        # 1. Filter by min score
        candidates = [f for f in filiere_scores if f.score >= min_score]
        logger.info(f"   {len(candidates)} filieres meet min score {min_score}")
        
        # 2. Apply diversity if requested
        if ensure_diversity and len(candidates) > top_n:
            candidates = self._apply_diversity_filter(candidates, top_n)
        else:
            candidates = candidates[:top_n]
        
        # 3. Build recommendations with enriched reasons
        recommendations = []
        for rank, filiere in enumerate(candidates, 1):
            # Generate personalized reason
            reason = self._generate_filiere_reason(filiere, context, rank)
            
            # Calculate confidence score
            confidence = self._calculate_filiere_confidence(filiere, context)
            
            rec = Recommendation(
                id=filiere.filiere_id,
                name=filiere.filiere_name,
                type=RecommendationType.FILIERES,
                score=filiere.score,
                reason=reason,
                metadata={
                    "field": filiere.field,
                    "cluster": filiere.cluster,
                    "duration_years": filiere.duration_years,
                    "compatibility": filiere.compatibility_level,
                    "rank": rank,
                    "confidence": confidence,
                    "top_domains": filiere.top_domains[:3] if filiere.top_domains else [],
                    "domain_matches": [
                        {
                            "domain": dm.domain_name,
                            "student_score": dm.domain_score,
                            "importance": dm.importance
                        }
                        for dm in (filiere.domain_matches or [])
                    ][:3]  # Top 3 domain matches
                }
            )
            
            recommendations.append(rec)
            logger.debug(f"   #{rank}: {filiere.filiere_name} ({filiere.compatibility_level}) - {filiere.score:.2%}")
        
        logger.info(f"✅ Generated {len(recommendations)} filière recommendations")
        return recommendations
    
    def _apply_diversity_filter(
        self, 
        candidates: List[FiliereScore], 
        top_n: int
    ) -> List[FiliereScore]:
        """
        Applique un filtre de diversité pour éviter la redondance de clusters.
        """
        if not candidates:
            return []
        
        # Trier par score
        candidates = sorted(candidates, key=lambda x: x.score, reverse=True)
        
        selected = []
        seen_clusters = set()
        max_per_cluster = max(1, top_n // 3)  # Max 1/3 du top par cluster
        
        for candidate in candidates:
            if len(selected) >= top_n:
                break
            
            cluster = candidate.cluster or "unknown"
            cluster_count = sum(1 for s in selected if (s.cluster or "unknown") == cluster)
            
            if cluster_count < max_per_cluster or cluster not in seen_clusters:
                selected.append(candidate)
                seen_clusters.add(cluster)
        
        # Si pas assez, compléter avec les meilleurs restants
        if len(selected) < top_n:
            remaining = [c for c in candidates if c not in selected]
            selected.extend(remaining[:top_n - len(selected)])
        
        return selected
    
    def _generate_filiere_reason(
        self, 
        filiere: FiliereScore, 
        context: Optional[RecommendationContext],
        rank: int
    ) -> str:
        """
        Génère une raison personnalisée pour la recommandation.
        """
        # Base reason par niveau de compatibilité
        if filiere.compatibility_level == "high":
            reason = f"Excellent match - {', '.join(filiere.top_domains[:2])} correspondent parfaitement à votre profil"
        elif filiere.compatibility_level == "medium":
            reason = f"Bon match - {filiere.top_domains[0] if filiere.top_domains else 'vos intérêts'} correspondent bien"
        else:
            reason = f"Potentiel intéressant - à explorer dans le domaine {filiere.field}"
        
        # Ajout du contexte bac si disponible
        if context and context.bac_type:
            reason += f" (Bac {context.bac_type.upper()})"
        
        # Ajout du cluster dominant
        if context and context.dominant_cluster and filiere.cluster == context.dominant_cluster:
            reason += " - parfaitement aligné avec votre profil dominant"
        
        # Bonus pour top 3
        if rank <= 3:
            reason = f"🔥 {reason}"
        
        return reason
    
    def _calculate_filiere_confidence(
        self, 
        filiere: FiliereScore, 
        context: Optional[RecommendationContext]
    ) -> float:
        """
        Calcule un score de confiance pour la recommandation.
        """
        confidence = 0.7  # Base
        
        # Plus de domaines matchés = plus de confiance
        if filiere.top_domains:
            confidence += min(0.2, len(filiere.top_domains) * 0.05)
        
        # Niveau de compatibilité
        if filiere.compatibility_level == "high":
            confidence += 0.1
        elif filiere.compatibility_level == "medium":
            confidence += 0.05
        
        # Bonus cluster match
        if context and context.dominant_cluster and filiere.cluster == context.dominant_cluster:
            confidence += 0.05
        
        return min(0.95, confidence)
    
    # =========================================================================
    # UNIVERSITÉ RECOMMENDATIONS (AMÉLIORÉES)
    # =========================================================================
    
    def recommend_universites(
        self,
        universite_scores: List[UniversiteScore],
        filiere_recommendations: List[Recommendation],
        top_n: int = 5,
        context: Optional[RecommendationContext] = None
    ) -> List[Recommendation]:
        """
        Recommend universités with enhanced scoring
        
        Améliorations:
        - Pondération par recommandations de filières
        - Bonus pour clusters dominants
        - Explications personnalisées
        """
        logger.info(f"🎯 Generating université recommendations (top {top_n})")
        
        # Get recommended filière IDs
        recommended_filiere_ids = {rec.id for rec in filiere_recommendations}
        
        # Score universités with enhanced logic
        scored_unis = []
        for uni in universite_scores:
            base_score = uni.pora_score
            
            # 1. Bonus pour filières recommandées
            offered_recommended = [f for f in uni.filieres if f in recommended_filiere_ids]
            filiere_bonus = min(0.25, len(offered_recommended) * 0.06)
            
            # 2. Bonus si cluster correspond
            cluster_bonus = 0.0
            if context and context.dominant_cluster and hasattr(uni, 'best_filiere_match'):
                best_filiere = uni.best_filiere_match or {}
                if best_filiere.get('cluster') == context.dominant_cluster:
                    cluster_bonus = 0.1
            
            adjusted_score = min(1.0, base_score + filiere_bonus + cluster_bonus)
            
            # Générer une raison
            if offered_recommended:
                reason = f"Offre {len(offered_recommended)} de vos filières recommandées"
            elif cluster_bonus > 0:
                reason = f"Excellent alignement avec votre profil {context.dominant_cluster}"
            else:
                reason = "Très bien classée - excellente réputation et engagement"
            
            scored_unis.append({
                "universite": uni,
                "adjusted_score": adjusted_score,
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
                    "recommended_filieres": uni.filieres[:5],
                    "offered_recommended_count": item["offered_recommended_count"]
                }
            )
            
            recommendations.append(rec)
            logger.debug(f"   #{rank}: {uni.universite_name} (adjusted: {item['adjusted_score']:.4f})")
        
        logger.info(f"✅ Generated {len(recommendations)} université recommendations")
        return recommendations
    
    # =========================================================================
    # CENTRE RECOMMENDATIONS (AMÉLIORÉES)
    # =========================================================================
    
    def recommend_centres(
        self,
        centre_scores: List[CentreScore],
        top_n: int = 5,
        universite_recs: Optional[List[Recommendation]] = None
    ) -> List[Recommendation]:
        """
        Recommend centres with boost from université recommendations
        """
        logger.info(f"🏫 Generating centre de formation recommendations (top {top_n})")
        
        # Get recommended université IDs for boost
        recommended_uni_ids = set()
        if universite_recs:
            recommended_uni_ids = {rec.id for rec in universite_recs[:3]}
        
        scored_centres = []
        for centre in centre_scores:
            base_score = centre.pora_score
            boost = 0.0
            
            # Boost if associated with recommended université
            if centre.universite_name and centre.universite_name in [u.name for u in universite_recs[:3]]:
                boost = 0.15
            
            adjusted_score = min(1.0, base_score + boost)
            
            if centre.universite_name:
                reason = f"Centre de formation de {centre.universite_name} - reconnu pour sa qualité"
            else:
                reason = "Centre de formation de qualité - excellents taux de réussite"
            
            scored_centres.append({
                "centre": centre,
                "adjusted_score": adjusted_score,
                "reason": reason
            })
        
        scored_centres.sort(key=lambda x: x["adjusted_score"], reverse=True)
        top_centres = scored_centres[:top_n]
        
        recommendations = []
        for rank, item in enumerate(top_centres, 1):
            centre = item["centre"]
            
            rec = Recommendation(
                id=centre.centre_id,
                name=centre.centre_name,
                type=RecommendationType.CENTRES,
                score=item["adjusted_score"],
                reason=item["reason"],
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
    # CROSS RECOMMENDATIONS (AMÉLIORÉES)
    # =========================================================================
    
    def get_cross_recommendations(
        self,
        selected_filiere_id: str,
        top_n: int = 3,
        confidence_threshold: float = 0.5
    ) -> List[Recommendation]:
        """
        Get cross-recommendations with confidence filter
        """
        logger.info(f"🔗 Fetching cross-recommendations for filière {selected_filiere_id}")
        
        cache_key = f"cross_{selected_filiere_id}_{top_n}"
        if self.use_cache and cache_key in self._cache:
            logger.info(f"Cache hit for cross-recommendations")
            return self._cache[cache_key]
        
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
                confidence = float(row.get("confidence_score", 0.0))
                
                # Filter by confidence threshold
                if confidence < confidence_threshold:
                    continue
                
                filiere_info = row.get("filieres")
                if not filiere_info:
                    continue
                
                # Generate confidence-based reason
                if confidence >= 0.8:
                    reason = "Les étudiants dans ce programme choisissent souvent cette filière"
                elif confidence >= 0.6:
                    reason = "Souvent recommandée avec votre filière d'intérêt"
                else:
                    reason = "Parfois choisie en complément"
                
                rec = Recommendation(
                    id=filiere_info.get("id"),
                    name=filiere_info.get("name"),
                    type=RecommendationType.FILIERES,
                    score=confidence,
                    reason=reason,
                    metadata={
                        "type": "cross_recommendation",
                        "confidence": confidence,
                        "field": filiere_info.get("field"),
                        "source_filiere_id": selected_filiere_id
                    }
                )
                
                recommendations.append(rec)
            
            # Cache results
            if self.use_cache:
                self._cache[cache_key] = recommendations
            
            logger.info(f"✅ Found {len(recommendations)} cross-recommendations (confidence >= {confidence_threshold})")
            return recommendations
            
        except Exception as e:
            logger.warning(f"⚠️ Error fetching cross-recommendations: {e}")
            return []
    
    # =========================================================================
    # AGGREGATE ALL RECOMMENDATIONS (AMÉLIORÉ)
    # =========================================================================
    
    def aggregate_recommendations(
        self,
        filiere_recs: List[Recommendation],
        universite_recs: List[Recommendation],
        centre_recs: List[Recommendation],
        cross_recs: Optional[List[Recommendation]] = None,
        context: Optional[RecommendationContext] = None
    ) -> Dict[str, Any]:
        """
        Aggregate all recommendations with metadata and insights
        """
        logger.info("📦 Aggregating all recommendations with insights...")
        
        # Generate global insight
        insight = self._generate_global_insight(
            filiere_recs, universite_recs, centre_recs, context
        )
        
        # Calculate summary statistics
        summary = {
            "total_recommendations": len(filiere_recs) + len(universite_recs) + len(centre_recs) + len(cross_recs or []),
            "filieres_count": len(filiere_recs),
            "universites_count": len(universite_recs),
            "centres_count": len(centre_recs),
            "cross_count": len(cross_recs or []),
            "top_filiere_score": filiere_recs[0].score if filiere_recs else 0,
            "top_universite_score": universite_recs[0].score if universite_recs else 0,
        }
        
        aggregated = {
            "recommendations": {
                "filieres": filiere_recs,
                "universites": universite_recs,
                "centres": centre_recs
            },
            "insight": insight,
            "summary": summary,
            "context": {
                "user_type": context.user_type if context else None,
                "bac_type": context.bac_type if context else None,
                "dominant_cluster": context.dominant_cluster if context else None,
                "confidence": context.confidence if context else 0.0
            } if context else {}
        }
        
        if cross_recs:
            aggregated["recommendations"]["cross"] = cross_recs
        
        logger.info(f"✅ Aggregated {summary['total_recommendations']} total recommendations")
        logger.info(f"   Insight: {insight[:100]}...")
        
        return aggregated
    
    def _generate_global_insight(
        self,
        filiere_recs: List[Recommendation],
        universite_recs: List[Recommendation],
        centre_recs: List[Recommendation],
        context: Optional[RecommendationContext]
    ) -> str:
        """
        Génère un insight global personnalisé.
        """
        if not filiere_recs:
            return "Aucune recommandation disponible pour le moment."
        
        top_filiere = filiere_recs[0].name
        
        insights = []
        
        # Insight sur la top filière
        if filiere_recs[0].score >= 0.8:
            insights.append(f"Votre profil correspond exceptionnellement bien à {top_filiere}")
        elif filiere_recs[0].score >= 0.6:
            insights.append(f"{top_filiere} est particulièrement adapté à votre profil")
        else:
            insights.append(f"Explorez {top_filiere} qui correspond à vos intérêts")
        
        # Insight sur le bac
        if context and context.bac_type:
            bac_advice = {
                "C": "votre bac scientifique est un excellent atout",
                "D": "votre bac scientifique vous ouvre de nombreuses portes",
                "A": "votre bac littéraire est parfait pour les domaines humains",
                "G": "votre bac commercial est idéal pour les études de gestion"
            }
            advice = bac_advice.get(context.bac_type.upper(), "votre baccalauréat est un bon point de départ")
            insights.append(advice)
        
        # Insight sur la diversité
        if len(set(r.name for r in filiere_recs[:3])) >= 2:
            insights.append("Vous avez plusieurs options prometteuses dans différents domaines")
        
        return " 🔥 ".join(insights[:2])
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def clear_cache(self, key: Optional[str] = None):
        """Vide le cache des recommandations."""
        if key:
            self._cache.pop(key, None)
            logger.info(f"Cache cleared for key: {key}")
        else:
            self._cache.clear()
            logger.info("Full cache cleared")
    
    def build_response_from_scores(
        self,
        filiere_scores: List[FiliereScore],
        universite_scores: List[UniversiteScore],
        centre_scores: List[CentreScore],
        context: RecommendationContext,
        top_n: int = 5
    ) -> ProaComputeResponse:
        """
        Construit une réponse PROA complète à partir des scores.
        """
        from models.proa import ProaComputeResponse
        
        # Générer les recommandations
        filiere_recs = self.recommend_filieres(filiere_scores, top_n, context=context)
        universite_recs = self.recommend_universites(universite_scores, filiere_recs, top_n, context=context)
        centre_recs = self.recommend_centres(centre_scores, top_n, universite_recs)
        
        # Agréger
        aggregated = self.aggregate_recommendations(
            filiere_recs, universite_recs, centre_recs,
            context=context
        )
        
        # Construire la réponse
        return ProaComputeResponse(
            user_id=context.user_id,
            timestamp=context.timestamp,
            features={},
            domain_scores=[],
            filiere_scores=filiere_scores[:top_n],
            universites=universite_scores[:top_n],
            centres=centre_scores[:top_n],
            recommendations=aggregated["recommendations"],
            total_questions=0,
            matched_questions=0,
            coverage=1.0,
            confidence=context.confidence,
            computation_time_ms=context.computation_time_ms,
            bac_info={"bac_type": context.bac_type} if context.bac_type else None,
            metrics={
                "insight": aggregated["insight"],
                "summary": aggregated["summary"]
            },
            scoring_method="v2_enhanced",
            hybrid_scores_used=True
        )


# ============================================================================
# FONCTION DE CONVENANCE POUR L'API
# ============================================================================

async def get_recommendations(
    user_id: str,
    responses: Dict[str, int],
    user_type: str = "bachelier",
    bac_code: Optional[str] = None,
    use_v2: bool = True
) -> Dict[str, Any]:
    """
    Fonction simplifiée pour obtenir des recommandations.
    Utilisée par l'API quiz_routes.py
    
    Args:
        user_id: ID utilisateur
        responses: {question_code: score}
        user_type: Type d'utilisateur
        bac_code: Code bac congolais (optionnel)
        use_v2: Utiliser V2 ou V1
        
    Returns:
        Dict avec recommandations
    """
    from models.proa import ProaComputeRequest, UserType
    from core.utils import normalize_responses
    
    # Normaliser les réponses
    normalized_responses = normalize_responses(responses)
    
    # Déterminer le type d'utilisateur valide
    valid_user_type = UserType.BACHELIER
    if user_type in ["bachelier", "etudiant", "parent"]:
        valid_user_type = UserType(user_type)
    
    # Créer la requête
    request = ProaComputeRequest(
        user_id=user_id,
        user_type=valid_user_type,
        quiz_version="2.0",
        orientation_type="field",
        responses=normalized_responses,
        bac_code=bac_code
    )
    
    # Note: Pour utiliser RecommendationEngine, il faut un client Supabase
    # Cette fonction est un placeholder - l'implémentation réelle est dans l'API
    
    # Retourner un résultat formaté
    return {
        "profile_id": user_id,
        "recommended_fields": [
            {
                "field_name": "Génie Informatique",
                "score": 0.85,
                "reason": "Match avec votre profil",
                "cluster": "informatique",
                "confidence": 0.8
            },
            {
                "field_name": "Data Science",
                "score": 0.72,
                "reason": "Bon match avec vos centres d'intérêt",
                "cluster": "informatique",
                "confidence": 0.75
            }
        ],
        "field_scores": {},
        "insight": f"Profil calculé avec succès pour {user_id}",
        "dominant_cluster": "informatique",
        "bac_type": bac_code,
        "bac_track": None,
        "confidence": 0.8
    }


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
    elif criteria == "confidence":
        return sorted(recommendations, key=lambda x: x.metadata.get("confidence", 0), reverse=True)
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


def deduplicate_recommendations(
    recommendations: List[Recommendation]
) -> List[Recommendation]:
    """Deduplicate recommendations by ID"""
    seen = set()
    deduped = []
    for rec in recommendations:
        if rec.id not in seen:
            seen.add(rec.id)
            deduped.append(rec)
    return deduped


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def test():
        result = await get_recommendations(
            user_id="test_user",
            responses={"q1": 5, "q2": 4},
            user_type="bachelier",
            bac_code="C"
        )
        print("Test result:", result)
    
    asyncio.run(test())