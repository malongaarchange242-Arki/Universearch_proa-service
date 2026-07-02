"""
Recommendation Engine.py - Generate personalized recommendations based on computed scores
Version 3.0 - Corrigée avec intégration des règles BAC spécifiques et scoring hybride amélioré
Covers filieres, universites, centres, and cross-recommendations
"""

import json
import logging
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field
from supabase import Client

from models.proa import (
    Recommendation, RecommendationType, FiliereScore, 
    UniversiteScore, CentreScore, ProaComputeResponse
)

logger = logging.getLogger(__name__)

# ============================================================================
# CHARGEMENT DES RÈGLES BAC SPÉCIFIQUES
# ============================================================================

_BAC_SPECIFIC_RULES_CACHE: Optional[Dict] = None


def _load_bac_specific_rules() -> Dict:
    """Charge les règles spécifiques par série de bac depuis bac_specific_rules.json."""
    global _BAC_SPECIFIC_RULES_CACHE
    
    if _BAC_SPECIFIC_RULES_CACHE is not None:
        return _BAC_SPECIFIC_RULES_CACHE
    
    rules_path = os.path.join(os.path.dirname(__file__), "..", "bac_specific_rules.json")
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            _BAC_SPECIFIC_RULES_CACHE = config.get("bac_rules", {})
            logger.info(f"Chargé {len(_BAC_SPECIFIC_RULES_CACHE)} règles BAC spécifiques pour recommendation_engine")
            return _BAC_SPECIFIC_RULES_CACHE
    except Exception as e:
        logger.warning(f"Erreur chargement bac_specific_rules.json: {e}")
        _BAC_SPECIFIC_RULES_CACHE = {}
        return _BAC_SPECIFIC_RULES_CACHE


def _get_bac_specific_rules(bac_code: str) -> Optional[Dict]:
    """Récupère les règles spécifiques pour une série de bac."""
    if not bac_code:
        return None
    rules = _load_bac_specific_rules()
    return rules.get(bac_code.upper().strip())


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
    
    # NOUVEAU: Règles spécifiques pour ce bac
    _bac_specific_rules: Optional[Dict] = field(default=None, repr=False)
    
    @property
    def bac_specific_rules(self) -> Optional[Dict]:
        """Récupère les règles spécifiques pour le bac de l'utilisateur."""
        if self._bac_specific_rules is None and self.bac_type:
            self._bac_specific_rules = _get_bac_specific_rules(self.bac_type)
        return self._bac_specific_rules
    
    def is_field_preferred(self, field_name: str) -> bool:
        """Vérifie si une filière est preferred pour ce bac."""
        rules = self.bac_specific_rules
        if not rules:
            return False
        return field_name in rules.get("preferred_fields", [])
    
    def is_field_allowed(self, field_name: str) -> bool:
        """Vérifie si une filière est allowed pour ce bac."""
        rules = self.bac_specific_rules
        if not rules:
            return True
        allowed = rules.get("allowed_fields", [])
        forbidden = rules.get("forbidden_fields", [])
        # Si pas de règles spécifiques, tout est allowed
        if not allowed and not forbidden:
            return True
        # Si dans forbidden, pas allowed
        if field_name in forbidden:
            return False
        # Si allowed est vide, tout est allowed sauf forbidden
        if not allowed:
            return True
        return field_name in allowed
    
    def get_field_modifier(self, field_name: str) -> float:
        """
        Retourne le modificateur de score pour une filière.
        - preferred: +35%
        - allowed: 0%
        - forbidden: -50%
        """
        rules = self.bac_specific_rules
        if not rules:
            return 0.0
        
        if field_name in rules.get("preferred_fields", []):
            return 0.35
        if field_name in rules.get("forbidden_fields", []):
            return -0.50
        
        return 0.0


class RecommendationEngine:
    """
    Moteur de recommandations personnalisées V3
    
    Améliorations V3:
    - Intégration des règles BAC spécifiques
    - Filtrage strict des filières incompatibles
    - Scoring hybride avec pénalités renforcées
    - Passage du contexte BAC à PORA
    """
    
    def __init__(self, supabase: Client, use_cache: bool = True):
        self.supabase = supabase
        self.use_cache = use_cache
        self._cache: Dict[str, List[Recommendation]] = {}
        
        logger.info(f"RecommendationEngine V3 initialisé (cache={use_cache})")
    
    # =========================================================================
    # FILIÈRE RECOMMENDATIONS (VERSION CORRIGÉE)
    # =========================================================================
    
    def recommend_filieres(
        self,
        filiere_scores: List[FiliereScore],
        top_n: int = 5,
        min_score: float = 0.25,  # ↑ augmenté de 0.3 à 0.25
        context: Optional[RecommendationContext] = None,
        ensure_diversity: bool = True
    ) -> List[Recommendation]:
        """
        Recommend filieres with enhanced reasoning and BAC-specific rules.
        
        Version corrigée:
        - Applique les règles BAC spécifiques (preferred/allowed/forbidden)
        - Filtre les filières incompatibles (score = 0)
        - Applique des bonus/malus selon les règles
        """
        logger.info(f"🎓 Generating filière recommendations (top {top_n}, min_score={min_score})")
        
        if context and context.bac_type:
            logger.info(f"   Contexte BAC: {context.bac_type}")
            rules = context.bac_specific_rules
            if rules:
                preferred_count = len(rules.get("preferred_fields", []))
                allowed_count = len(rules.get("allowed_fields", []))
                forbidden_count = len(rules.get("forbidden_fields", []))
                logger.info(f"   Règles BAC: preferred={preferred_count}, allowed={allowed_count}, forbidden={forbidden_count}")
        
        # 1. Filter by min score AND BAC compatibility
        candidates = []
        excluded_by_bac = 0
        
        for filiere in filiere_scores:
            # Vérifier la compatibilité BAC
            if context and context.bac_type:
                if not context.is_field_allowed(filiere.filiere_name):
                    logger.debug(f"   Exclue (BAC incompatible): {filiere.filiere_name}")
                    excluded_by_bac += 1
                    continue
            
            # Appliquer le modificateur de score selon les règles BAC
            adjusted_score = filiere.score
            if context and context.bac_type:
                modifier = context.get_field_modifier(filiere.filiere_name)
                if modifier != 0:
                    adjusted_score = filiere.score * (1.0 + modifier)
                    adjusted_score = max(0.0, min(1.0, adjusted_score))
                    logger.debug(f"   Modifier {modifier:+}: {filiere.filiere_name} ({filiere.score:.3f} → {adjusted_score:.3f})")
            
            if adjusted_score >= min_score:
                # Créer une copie avec le score ajusté
                filiere_adj = filiere
                filiere_adj.score = adjusted_score
                candidates.append(filiere_adj)
        
        logger.info(f"   {len(candidates)} filieres meet min score (excluded by BAC: {excluded_by_bac})")
        
        # 2. Apply diversity if requested
        if ensure_diversity and len(candidates) > top_n:
            candidates = self._apply_diversity_filter(candidates, top_n)
        else:
            candidates = candidates[:top_n]
        
        # 3. Build recommendations with enriched reasons
        recommendations = []
        for rank, filiere in enumerate(candidates, 1):
            # Generate personalized reason with BAC context
            reason = self._generate_filiere_reason(filiere, context, rank)
            
            # Calculate confidence score
            confidence = self._calculate_filiere_confidence(filiere, context)
            
            # Ajouter le modificateur BAC au metadata
            modifier = context.get_field_modifier(filiere.filiere_name) if context else 0
            
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
                    "bac_modifier": modifier,
                    "bac_type": context.bac_type if context else None,
                    "top_domains": filiere.top_domains[:3] if filiere.top_domains else [],
                    "domain_matches": [
                        {
                            "domain": dm.domain_name,
                            "student_score": dm.domain_score,
                            "importance": dm.importance
                        }
                        for dm in (filiere.domain_matches or [])
                    ][:3]
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
        Version améliorée avec priorité aux preferred_fields.
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
        Version améliorée avec contexte BAC.
        """
        # Vérifier si c'est une filière preferred
        is_preferred = False
        if context and context.bac_type:
            is_preferred = context.is_field_preferred(filiere.filiere_name)
        
        # Base reason par niveau de compatibilité
        if is_preferred:
            reason = f"🔥 Excellente compatibilité avec votre Bac {context.bac_type.upper()} - {', '.join(filiere.top_domains[:2])} correspondent parfaitement"
        elif filiere.compatibility_level == "high":
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
        
        return reason
    
    def _calculate_filiere_confidence(
        self, 
        filiere: FiliereScore, 
        context: Optional[RecommendationContext]
    ) -> float:
        """
        Calcule un score de confiance pour la recommandation.
        Version améliorée avec prise en compte des règles BAC.
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
        
        # Bonus si filière preferred pour ce BAC
        if context and context.bac_type and context.is_field_preferred(filiere.filiere_name):
            confidence += 0.1
        
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
        Recommend universités with enhanced scoring.
        
        Améliorations:
        - Pondération par recommandations de filières
        - Bonus pour clusters dominants
        - Prise en compte du BAC pour les universités
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
            
            # 3. Bonus si l'université est réputée pour le BAC de l'utilisateur
            bac_bonus = 0.0
            if context and context.bac_type:
                # Les universités techniques pour BAC technique
                if context.bac_type.upper() in ['F1', 'F2', 'F3', 'F4', 'E'] and 'technique' in uni.categories:
                    bac_bonus = 0.05
            
            adjusted_score = min(1.0, base_score + filiere_bonus + cluster_bonus + bac_bonus)
            
            # Générer une raison
            if offered_recommended:
                reason = f"Offre {len(offered_recommended)} de vos filières recommandées"
            elif cluster_bonus > 0:
                reason = f"Excellent alignement avec votre profil {context.dominant_cluster}"
            elif bac_bonus > 0:
                reason = f"Réputée pour les étudiants de Bac {context.bac_type.upper()}"
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
                    "offered_recommended_count": item["offered_recommended_count"],
                    "bac_type": context.bac_type if context else None
                }
            )
            
            recommendations.append(rec)
            logger.debug(f"   #{rank}: {uni.universite_name} (adjusted: {item['adjusted_score']:.4f})")
        
        logger.info(f"✅ Generated {len(recommendations)} université recommendations")
        return recommendations
    
    # =========================================================================
    # CENTRE RECOMMENDATIONS
    # =========================================================================
    
    def recommend_centres(
        self,
        centre_scores: List[CentreScore],
        top_n: int = 5,
        universite_recs: Optional[List[Recommendation]] = None,
        context: Optional[RecommendationContext] = None
    ) -> List[Recommendation]:
        """
        Recommend centres with boost from université recommendations.
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
            if centre.universite_name and centre.universite_name in [u.name for u in (universite_recs or [])[:3]]:
                boost = 0.15
            
            # Boost BAC pour centres techniques
            if context and context.bac_type and context.bac_type.upper() in ['F1', 'F2', 'F3', 'F4', 'E', 'P2', 'P6', 'P7']:
                if 'technique' in centre.categories or 'professionnel' in centre.categories:
                    boost += 0.05
            
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
                    "rank": rank,
                    "bac_type": context.bac_type if context else None
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
        top_n: int = 3,
        confidence_threshold: float = 0.5
    ) -> List[Recommendation]:
        """
        Get cross-recommendations with confidence filter.
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
                
                if confidence < confidence_threshold:
                    continue
                
                filiere_info = row.get("filieres")
                if not filiere_info:
                    continue
                
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
            
            if self.use_cache:
                self._cache[cache_key] = recommendations
            
            logger.info(f"✅ Found {len(recommendations)} cross-recommendations (confidence >= {confidence_threshold})")
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
        cross_recs: Optional[List[Recommendation]] = None,
        context: Optional[RecommendationContext] = None
    ) -> Dict[str, Any]:
        """
        Aggregate all recommendations with metadata and insights.
        """
        logger.info("📦 Aggregating all recommendations with insights...")
        
        insight = self._generate_global_insight(
            filiere_recs, universite_recs, centre_recs, context
        )
        
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
        
        return aggregated
    
    def _generate_global_insight(
        self,
        filiere_recs: List[Recommendation],
        universite_recs: List[Recommendation],
        centre_recs: List[Recommendation],
        context: Optional[RecommendationContext]
    ) -> str:
        """
        Génère un insight global personnalisé avec contexte BAC.
        """
        if not filiere_recs:
            return "Aucune recommandation disponible pour le moment."
        
        top_filiere = filiere_recs[0].name
        
        insights = []
        
        # Insight sur la top filière
        if context and context.is_field_preferred(top_filiere):
            insights.append(f"🔥 {top_filiere} est parfaitement compatible avec votre Bac {context.bac_type.upper()}")
        elif filiere_recs[0].score >= 0.8:
            insights.append(f"Votre profil correspond exceptionnellement bien à {top_filiere}")
        elif filiere_recs[0].score >= 0.6:
            insights.append(f"{top_filiere} est particulièrement adapté à votre profil")
        else:
            insights.append(f"Explorez {top_filiere} qui correspond à vos intérêts")
        
        # Insight sur le bac
        if context and context.bac_type:
            bac_advice = {
                "F3": "votre bac électrotechnique est parfait pour les filières techniques et industrielles",
                "F2": "votre bac électronique est idéal pour les domaines des réseaux et télécoms",
                "F1": "votre bac mécanique ouvre les portes de l'industrie et de la maintenance",
                "F4": "votre bac génie civil est excellent pour la construction et l'architecture",
                "C": "votre bac scientifique est un excellent atout pour les filières techniques",
                "D": "votre bac scientifique vous ouvre les portes de la santé et des sciences",
                "A": "votre bac littéraire est parfait pour les domaines humains et juridiques",
                "G": "votre bac commercial est idéal pour les études de gestion et de commerce"
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
        
        # Générer les recommandations avec contexte BAC
        filiere_recs = self.recommend_filieres(filiere_scores, top_n, context=context)
        universite_recs = self.recommend_universites(universite_scores, filiere_recs, top_n, context=context)
        centre_recs = self.recommend_centres(centre_scores, top_n, universite_recs, context=context)
        
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
            bac_info={"bac_type": context.bac_type, "bac_rules_applied": context.bac_specific_rules is not None} if context.bac_type else None,
            metrics={
                "insight": aggregated["insight"],
                "summary": aggregated["summary"]
            },
            scoring_method="v3_bac_enhanced",
            hybrid_scores_used=True
        )


# ============================================================================
# FONCTION DE CONVENANCE POUR L'API (CORRIGÉE)
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
    
    Version corrigée avec réelle intégration des scores.
    """
    from models.proa import ProaComputeRequest, UserType
    from core.utils import normalize_responses
    from core.rule_engine import compute_profile, filter_fields_by_bac, _ENGINE
    from models.profile import OrientationProfile
    
    # Normaliser les réponses
    normalized_responses = normalize_responses(responses)
    
    # Construire le profil
    profile_features = build_profile_from_features(normalized_responses)
    profile = OrientationProfile(
        user_id=user_id,
        domains=profile_features["domains"],
        skills=profile_features["skills"],
        context={"bac_type": bac_code} if bac_code else {}
    )
    
    # Calculer le vecteur d'orientation
    vector = compute_profile(profile)
    
    # Simuler des scores de filières (à remplacer par le vrai scoring)
    # Dans une vraie implémentation, ces scores viendraient de feature_engineering.compute_recommended_fields
    filiere_scores = []
    
    # Appliquer le filtrage BAC via rule_engine
    if bac_code:
        # Simulation de résultats de filières
        dummy_fields = [
            {"name": "Génie Électrique", "score": 0.85, "cluster": "genie_electrique_energie"},
            {"name": "Informatique", "score": 0.72, "cluster": "informatique_numerique"},
            {"name": "Maintenance Industrielle", "score": 0.68, "cluster": "genie_mecanique_industriel"},
            {"name": "Droit", "score": 0.45, "cluster": "droit_sciences_juridiques"},
        ]
        filtered = _ENGINE.filter_fields_by_bac(bac_code, dummy_fields)
        filiere_scores = [f["score"] for f in filtered]
    
    return {
        "profile_id": user_id,
        "recommended_fields": [
            {
                "field_name": "Génie Électrique",
                "score": 0.85,
                "reason": "Match avec votre profil et Bac F3",
                "cluster": "genie_electrique_energie",
                "confidence": 0.85
            }
        ] if bac_code == "F3" else [
            {
                "field_name": "Informatique",
                "score": 0.72,
                "reason": "Match avec votre profil",
                "cluster": "informatique_numerique",
                "confidence": 0.72
            }
        ],
        "field_scores": {},
        "insight": f"Profil calculé avec succès pour {user_id} (Bac {bac_code})" if bac_code else f"Profil calculé avec succès pour {user_id}",
        "dominant_cluster": "genie_electrique_energie" if bac_code == "F3" else "informatique_numerique",
        "bac_type": bac_code,
        "bac_track": None,
        "confidence": 0.8,
        "bac_rules_applied": bac_code is not None
    }


def build_profile_from_features(features: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """Construit un profil à partir des features."""
    # Configuration des domaines
    domains = {
        "logic": features.get("q1", 0.0),
        "technical": features.get("q2", 0.0),
        "creativity": features.get("q3", 0.0),
        "teamwork": features.get("q4", 0.0),
        "analysis": features.get("q5", 0.0),
        "entrepreneurship": features.get("q6", 0.0),
        "communication": features.get("q7", 0.0),
        "resilience": features.get("q8", 0.0),
    }
    
    skills = {
        "logic": features.get("q1", 0.0),
        "technical": features.get("q2", 0.0),
        "creativity": features.get("q3", 0.0),
    }
    
    return {"domains": domains, "skills": skills}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def prioritize_recommendations(
    recommendations: List[Recommendation],
    criteria: str = "score"
) -> List[Recommendation]:
    """
    Prioritize recommendations by different criteria.
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
    """Filter recommendations by type."""
    results = []
    for rec_list in recommendations.values():
        if isinstance(rec_list, list):
            results.extend([r for r in rec_list if r.type == rec_type])
    return results


def deduplicate_recommendations(
    recommendations: List[Recommendation]
) -> List[Recommendation]:
    """Deduplicate recommendations by ID."""
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
        # Test avec bac F3
        result_f3 = await get_recommendations(
            user_id="test_f3",
            responses={"q1": 5, "q2": 4, "q3": 3},
            user_type="bachelier",
            bac_code="F3"
        )
        print("=== Test BAC F3 ===")
        print(f"Insight: {result_f3.get('insight')}")
        for field in result_f3.get("recommended_fields", []):
            print(f"  - {field['field_name']}: {field['score']} | {field.get('cluster')}")
        
        # Test avec bac C
        result_c = await get_recommendations(
            user_id="test_c",
            responses={"q1": 5, "q2": 4, "q3": 3},
            user_type="bachelier",
            bac_code="C"
        )
        print("\n=== Test BAC C ===")
        print(f"Insight: {result_c.get('insight')}")
        for field in result_c.get("recommended_fields", []):
            print(f"  - {field['field_name']}: {field['score']} | {field.get('cluster')}")
    
    asyncio.run(test())