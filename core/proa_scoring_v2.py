"""
PROA Scoring V2 - Bridge between feature_engineering and PORA
Maintient la compatibilité avec l'existant tout en utilisant le nouveau scoring
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from supabase import Client

from core.feature_engineering import compute_recommended_fields
from core.proa_scoring import PoraScoring
from models.proa import FiliereScore, UniversiteScore, CentreScore, ProaComputeResponse

logger = logging.getLogger(__name__)


class ProaScoringV2:
    """
    Version améliorée de PORA scoring utilisant le nouveau feature_engineering.
    
    Améliorations:
    1. Scoring vectoriel dimensionnel (8 dimensions)
    2. Détection intelligente des clusters
    3. Compatibilité bac congolais
    4. Fallback robuste
    """
    
    def __init__(self, supabase: Client, use_hybrid: bool = True):
        self.supabase = supabase
        self.use_hybrid = use_hybrid
        self.pora_scoring = PoraScoring(supabase)
        
        logger.info(f"ProaScoringV2 initialisé (use_hybrid={use_hybrid})")
    
    def compute_filiere_scores_from_profile(
        self,
        profile: Dict[str, Any],
        top_n: int = 10
    ) -> Tuple[List[FiliereScore], Dict[str, Any]]:
        """
        Calcule les scores de filières à partir d'un profil utilisateur.
        
        Args:
            profile: Profil utilisateur avec domains et skills
            top_n: Nombre maximum de filières à retourner
            
        Returns:
            (filiere_scores, metadata)
        """
        logger.info("🎯 Computing filiere scores with V2 engine...")
        start_time = datetime.utcnow()
        
        # 1. Utiliser le nouveau moteur de recommandation
        result = compute_recommended_fields(profile, top_n=top_n)
        
        recommended_fields = result.get("recommended_fields", [])
        field_scores = result.get("field_scores", {})
        insight = result.get("insight", "")
        dominant_cluster = result.get("dominant_cluster")
        bac_type = result.get("bac_type")
        bac_track = result.get("bac_track")
        
        # 2. Convertir au format FiliereScore
        filiere_scores = []
        for i, field in enumerate(recommended_fields):
            filiere_score = FiliereScore(
                filiere_id=f"field_{i}",  # À remplacer par vrai ID si disponible
                filiere_name=field.get("field_name", ""),
                field=field.get("field_name", ""),
                cluster=field.get("cluster", dominant_cluster or "unknown"),
                score=field.get("decision_score", field.get("score", 0.0)),
                duration_years=None,
                domain_matches=[],
                top_domains=[],  # À enrichir
                domains_list=[],
                compatibility_level=self._get_compatibility_level(field.get("score", 0.0))
            )
            filiere_scores.append(filiere_score)
        
        # 3. Métadonnées
        metadata = {
            "scoring_method": "v2_vectoriel",
            "dominant_cluster": dominant_cluster,
            "bac_type": bac_type,
            "bac_track": bac_track,
            "insight": insight,
            "total_filieres_scored": len(recommended_fields),
            "computation_time_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
        }
        
        logger.info(f"✅ Computed {len(filiere_scores)} filiere scores")
        logger.info(f"   Dominant cluster: {dominant_cluster}")
        logger.info(f"   Time: {metadata['computation_time_ms']:.2f}ms")
        
        return filiere_scores, metadata
    
    def compute_universite_scores_v2(
        self,
        profile: Dict[str, Any],
        top_n: int = 10
    ) -> Tuple[List[UniversiteScore], Dict[str, Any]]:
        """
        Calcule les scores PORA pour les universités avec le nouveau scoring.
        
        Args:
            profile: Profil utilisateur
            top_n: Nombre maximum d'universités
            
        Returns:
            (universite_scores, stats)
        """
        # 1. D'abord calculer les scores de filières
        filiere_scores, _ = self.compute_filiere_scores_from_profile(profile, top_n=50)
        
        # 2. Extraire les domaines PROA du profil
        user_domains = self._extract_user_domains_from_profile(profile)
        
        # 3. Utiliser le PORA scoring existant avec les nouveaux scores
        universite_scores, stats = self.pora_scoring.compute_universite_scores(
            filiere_scores=filiere_scores,
            top_n=top_n,
            user_domains=user_domains,
            quiz_responses=None,  # Pas de quiz ici
            user_type=profile.get("user_type")
        )
        
        # 4. Enrichir avec les métadonnées du profil
        for uni_score in universite_scores:
            uni_score.pora_components = {
                "popularity": uni_score.popularity,
                "engagement": 0.0,
                "orientation": uni_score.filiere_match
            }
        
        stats["scoring_version"] = "v2"
        stats["use_hybrid"] = self.use_hybrid
        
        return universite_scores, stats
    
    def compute_centre_scores_v2(
        self,
        profile: Dict[str, Any],
        top_n: int = 10
    ) -> Tuple[List[CentreScore], Dict[str, Any]]:
        """
        Calcule les scores PORA pour les centres avec le nouveau scoring.
        """
        filiere_scores, _ = self.compute_filiere_scores_from_profile(profile, top_n=50)
        user_domains = self._extract_user_domains_from_profile(profile)
        
        centre_scores, stats = self.pora_scoring.compute_centre_scores(
            filiere_scores=filiere_scores,
            top_n=top_n,
            user_domains=user_domains,
            quiz_responses=None,
            user_type=profile.get("user_type")
        )
        
        stats["scoring_version"] = "v2"
        
        return centre_scores, stats
    
    def compute_complete_response(
        self,
        user_id: str,
        profile: Dict[str, Any],
        user_type: str = "bachelier"
    ) -> ProaComputeResponse:
        """
        Calcule la réponse PROA complète.
        
        Args:
            user_id: ID utilisateur
            profile: Profil utilisateur (domains, skills, context)
            user_type: Type d'utilisateur
            
        Returns:
            ProaComputeResponse complet
        """
        start_time = datetime.utcnow()
        
        # 1. Scores de filières
        filiere_scores, filiere_metadata = self.compute_filiere_scores_from_profile(profile)
        
        # 2. Scores universités
        universite_scores, uni_stats = self.compute_universite_scores_v2(profile)
        
        # 3. Scores centres
        centre_scores, centre_stats = self.compute_centre_scores_v2(profile)
        
        # 4. Construire la réponse
        response = ProaComputeResponse(
            user_id=user_id,
            timestamp=datetime.utcnow(),
            features={},  # À remplir si besoin
            domain_scores=[],  # À remplir si besoin
            filiere_scores=filiere_scores,
            universites=universite_scores,
            centres=centre_scores,
            recommendations={},  # À remplir
            total_questions=0,
            matched_questions=0,
            coverage=filiere_metadata.get("total_filieres_scored", 0) / 100.0,
            confidence=0.85,  # Score de confiance du nouveau moteur
            computation_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            bac_info={
                "bac_type": filiere_metadata.get("bac_type"),
                "bac_track": filiere_metadata.get("bac_track"),
                "bac_valid": filiere_metadata.get("bac_track") is not None
            },
            metrics={
                "filiere_scoring": filiere_metadata,
                "universite_scoring": uni_stats,
                "centre_scoring": centre_stats
            },
            scoring_method="v2_vectoriel",
            hybrid_scores_used=self.use_hybrid
        )
        
        logger.info(f"✅ Complete PROA response for {user_id} in {response.computation_time_ms:.2f}ms")
        
        return response
    
    def _get_compatibility_level(self, score: float) -> str:
        """Détermine le niveau de compatibilité"""
        if score >= 0.7:
            return "high"
        elif score >= 0.4:
            return "medium"
        return "low"
    
    def _extract_user_domains_from_profile(self, profile: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extrait les domaines PROA du profil utilisateur"""
        domains = profile.get("domains", {})
        if not isinstance(domains, dict):
            return []
        
        return [{"domain_name": domain, "weight": str(weight)} 
                for domain, weight in domains.items() 
                if weight > 0.3]


# ============================================================================
# UTILITAIRE DE TEST
# ============================================================================

def test_proa_scoring_v2():
    """Test rapide du nouveau scoring"""
    sample_profile = {
        "domains": {
            "computer_science": 0.8,
            "technical": 0.7,
            "logic": 0.75,
            "marketing": 0.2
        },
        "skills": {
            "python": 0.9,
            "data_analysis": 0.8,
            "teamwork": 0.6
        },
        "context": {
            "bac_type": "C",
            "user_type": "bachelier"
        }
    }
    
    # Simuler une connexion Supabase (à remplacer)
    from unittest.mock import MagicMock
    mock_supabase = MagicMock()
    
    scorer = ProaScoringV2(mock_supabase, use_hybrid=True)
    
    # Calculer les scores
    filiere_scores, metadata = scorer.compute_filiere_scores_from_profile(sample_profile, top_n=5)
    
    print("\n" + "="*60)
    print("PROA SCORING V2 - TEST")
    print("="*60)
    print(f"\n📊 Métadonnées:")
    print(f"   Dominant cluster: {metadata.get('dominant_cluster')}")
    print(f"   Bac type: {metadata.get('bac_type')}")
    print(f"   Insight: {metadata.get('insight')}")
    
    print(f"\n🎯 Top 5 Filères:")
    for i, fs in enumerate(filiere_scores, 1):
        print(f"   {i}. {fs.filiere_name} - Score: {fs.score:.2%} ({fs.compatibility_level})")
    
    return filiere_scores, metadata


if __name__ == "__main__":
    test_proa_scoring_v2()