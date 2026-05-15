"""
Scorer - Moteur de scoring d'orientation
Version 2.0 - Support du scoring hybride (rules + ML + vectoriel)
"""

import logging
import time
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime

from config import ENGINE_MODE
from core import rule_engine, ml_engine
from core.recommendations import compute_recommended_fields
from models.proa import UserType, ProaComputeRequest
from models.profile import OrientationProfile

logger = logging.getLogger("orientation.scorer")


@dataclass
class ScoringResult:
    """Résultat complet du scoring avec métriques"""
    profile: OrientationProfile
    confidence: float
    scoring_method: str
    computation_time_ms: float
    feature_coverage: float
    domain_scores: Dict[str, float] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class Scorer:
    """
<<<<<<< HEAD
    Moteur de scoring V2 avec support hybride
    
    Améliorations:
    - Choix intelligent entre rule-based, ML et vectoriel
    - Métriques de performance et de qualité
    - Fallback automatique
    - Support bac congolais
    """
    
    def __init__(self, mode: Optional[str] = None):
        """
        Initialise le scorer.
        
        Args:
            mode: Force un mode spécifique ('rule', 'ml', 'v2', 'auto')
                  Par défaut utilise ENGINE_MODE de config
        """
        self.mode = mode or ENGINE_MODE
        self.stats = {
            "total_calls": 0,
            "avg_time_ms": 0,
            "method_usage": {"rule": 0, "ml": 0, "v2": 0, "hybrid": 0}
        }
        logger.info(f"Scorer V2 initialisé (mode={self.mode})")
    
    def compute_orientation(
        self,
        features: Dict[str, Any],
        user_id: Optional[str] = None,
        user_type: Optional[str] = None,
        bac_code: Optional[str] = None,
        responses: Optional[Dict[str, int]] = None,
        force_method: Optional[str] = None
    ) -> Tuple[OrientationProfile, float, Dict[str, Any]]:
        """
        Calcule le profil d'orientation avec métriques enrichies.
        
        Args:
            features: Dictionnaire des features normalisées
            user_id: ID utilisateur pour traçabilité
            user_type: Type d'utilisateur (bachelier/etudiant/parent)
            bac_code: Code bac congolais
            responses: Réponses brutes du quiz (pour scoring V2)
            force_method: Force une méthode spécifique
        
        Returns:
            Tuple[OrientationProfile, float, Dict]: Profil, confiance, métadonnées
        """
        start_time = time.time()
        self.stats["total_calls"] += 1
        
        method = force_method or self._select_method(features)
        
        try:
            if method == "v2" and responses:
                profile, confidence, metadata = self._compute_v2(
                    features, user_id, user_type, bac_code, responses
                )
            elif method == "ml":
                profile, confidence, metadata = self._compute_ml(features)
            elif method == "rule":
                profile, confidence, metadata = self._compute_rule(features)
            elif method == "hybrid":
                profile, confidence, metadata = self._compute_hybrid(features, responses)
            else:
                # Fallback sur rule engine
                logger.warning(f"Méthode {method} non reconnue, fallback rule")
                profile, confidence, metadata = self._compute_rule(features)
            
            # Métriques de performance
            computation_time = (time.time() - start_time) * 1000
            self.stats["avg_time_ms"] = (
                (self.stats["avg_time_ms"] * (self.stats["total_calls"] - 1) + computation_time)
                / self.stats["total_calls"]
            )
            self.stats["method_usage"][method] = self.stats["method_usage"].get(method, 0) + 1
            
            metadata.update({
                "computation_time_ms": round(computation_time, 2),
                "method": method,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            logger.info(
                f"Profil calculé: method={method}, confidence={confidence:.2%}, "
                f"time={computation_time:.2f}ms"
            )
            
            return profile, confidence, metadata
            
        except Exception as exc:
            logger.error(f"Erreur avec méthode {method}: {exc}")
            
            # Fallback attempt
            if method != "rule":
                logger.info("Tentative fallback sur rule engine")
                try:
                    profile, confidence, metadata = self._compute_rule(features)
                    metadata["fallback_from"] = method
                    metadata["fallback_reason"] = str(exc)
                    return profile, confidence * 0.8, metadata
                except Exception as fallback_exc:
                    logger.error(f"Fallback également échoué: {fallback_exc}")
            
            raise
    
    def _select_method(self, features: Dict[str, Any]) -> str:
        """
        Sélectionne intelligemment la méthode de scoring.
        """
        # Si mode forcé
        if self.mode in ["rule", "ml", "v2", "hybrid"]:
            return self.mode
        
        # Mode auto: choisir selon les données
        feature_count = len(features)
        has_ml_features = any(k in features for k in ["domains", "skills", "embedding"])
        
        if has_ml_features and feature_count > 10:
            return "ml"
        elif feature_count > 5:
            return "rule"
        else:
            return "rule"
    
    def _compute_rule(
        self, 
        features: Dict[str, Any]
    ) -> Tuple[OrientationProfile, float, Dict[str, Any]]:
        """
        Calcule avec le moteur rule-based.
        """
        logger.debug("Computing with rule engine")
        profile_dict = rule_engine.compute_profile(features)
        profile = OrientationProfile(**profile_dict)

        # Calcul de confiance basé sur la couverture
        confidence = self._calculate_confidence(features, profile_dict)

        metadata = {
            "engine": "rule",
            "feature_count": len(features),
            "confidence_factors": {
                "coverage": confidence,
                "rule_matches": len(profile_dict.get("domains", {}))
            }
        }

        return profile, confidence, metadata

    def _compute_ml(
        self, 
        features: Dict[str, Any]
    ) -> Tuple[OrientationProfile, float, Dict[str, Any]]:
        """
        Calcule avec le moteur ML.
        """
        logger.debug("Computing with ML engine")
        profile_dict = ml_engine.compute_profile(features)
        profile = OrientationProfile(**profile_dict)
        
        # Confiance ML (généralement plus élevée)
        confidence = min(0.95, 0.7 + (len(profile_dict.get("domains", {})) * 0.05))
        
        metadata = {
            "engine": "ml",
            "feature_count": len(features),
            "model_version": getattr(ml_engine, "VERSION", "unknown")
        }
        
        return profile, confidence, metadata
    
    def _compute_v2(
        self,
        features: Dict[str, Any],
        user_id: Optional[str],
        user_type: Optional[str],
        bac_code: Optional[str],
        responses: Dict[str, int]
    ) -> Tuple[OrientationProfile, float, Dict[str, Any]]:
        """
        Calcule avec le scoring vectoriel V2.
        """
        logger.debug("Computing with V2 vectorial engine")
        
        # Construire le profil pour feature_engineering
        profile_data = {
            "domains": features.get("domains", {}),
            "skills": features.get("skills", {}),
            "context": {
                "user_type": user_type or "bachelier",
                "bac_code": bac_code,
                "quiz_responses": responses
            }
        }
        
        # Utiliser le nouveau moteur V2
        result = compute_recommended_fields(profile_data, top_n=10)
        
        # Convertir en OrientationProfile
        profile_dict = {
            "domains": profile_data["domains"],
            "skills": profile_data["skills"],
            "recommended_fields": result.get("recommended_fields", []),
            "dominant_cluster": result.get("dominant_cluster"),
            "bac_track": result.get("bac_track")
        }
        
        profile = OrientationProfile(**profile_dict)
        
        # Confiance basée sur le scoring V2
        confidence = min(0.9, 0.6 + (len(result.get("recommended_fields", [])) * 0.04))
        
        metadata = {
            "engine": "v2_vectorial",
            "dominant_cluster": result.get("dominant_cluster"),
            "bac_track": result.get("bac_track"),
            "insight": result.get("insight"),
            "fields_count": len(result.get("recommended_fields", []))
        }
        
        return profile, confidence, metadata
    
    def _compute_hybrid(
        self,
        features: Dict[str, Any],
        responses: Optional[Dict[str, int]] = None
    ) -> Tuple[OrientationProfile, float, Dict[str, Any]]:
        """
        Calcule avec une approche hybride (pondération rule + ML).
        """
        logger.debug("Computing with hybrid engine")
        
        # Calcul rule-based
        rule_profile_dict = rule_engine.compute_profile(features)
        rule_profile = OrientationProfile(**rule_profile_dict)
        
        # Calcul ML si possible
        ml_profile_dict = None
        try:
            ml_profile_dict = ml_engine.compute_profile(features)
            ml_profile = OrientationProfile(**ml_profile_dict)
        except Exception as e:
            logger.warning(f"ML engine failed in hybrid mode: {e}")
            ml_profile_dict = rule_profile_dict
        
        # Pondération: 60% rule, 40% ML
        hybrid_domains = {}
        rule_weight = 0.6
        ml_weight = 0.4
        
        # Fusion des domaines
        for domain, score in rule_profile_dict.get("domains", {}).items():
            hybrid_domains[domain] = score * rule_weight
        
        if ml_profile_dict:
            for domain, score in ml_profile_dict.get("domains", {}).items():
                hybrid_domains[domain] = hybrid_domains.get(domain, 0) + score * ml_weight
        
        # Normalisation
        if hybrid_domains:
            max_score = max(hybrid_domains.values())
            if max_score > 0:
                hybrid_domains = {k: v / max_score for k, v in hybrid_domains.items()}
        
        profile_dict = {
            "domains": hybrid_domains,
            "skills": rule_profile_dict.get("skills", {}),
            "recommended_fields": rule_profile_dict.get("recommended_fields", [])
        }
        
        profile = OrientationProfile(**profile_dict)
        
        # Confiance hybride (moyenne pondérée)
        rule_confidence = self._calculate_confidence(features, rule_profile_dict)
        ml_confidence = 0.7 if ml_profile_dict else 0.0
        confidence = (rule_confidence * rule_weight + ml_confidence * ml_weight)
        
        metadata = {
            "engine": "hybrid",
            "rule_weight": rule_weight,
            "ml_weight": ml_weight,
            "rule_confidence": rule_confidence,
            "ml_confidence": ml_confidence
        }
        
        return profile, confidence, metadata
    
    def _calculate_confidence(
        self,
        features: Dict[str, Any],
        profile_dict: Dict[str, Any]
    ) -> float:
        """
        Calcule un score de confiance basé sur la qualité des données.
        """
        confidence = 0.5  # Base
        
        # Couverture des features
        feature_count = len(features)
        if feature_count > 0:
            confidence += min(0.3, feature_count / 50)  # Max +0.3 pour 50+ features
        
        # Nombre de domaines détectés
        domains_count = len(profile_dict.get("domains", {}))
        if domains_count > 0:
            confidence += min(0.2, domains_count / 10)  # Max +0.2 pour 10+ domaines
        
        # Présence de compétences
        skills_count = len(profile_dict.get("skills", {}))
        if skills_count > 0:
            confidence += min(0.1, skills_count / 20)  # Max +0.1
        
        return min(0.95, confidence)
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'utilisation du scorer."""
        return {
            **self.stats,
            "mode": self.mode,
            "success_rate": self.stats["total_calls"] > 0
        }
    
    def reset_stats(self):
        """Réinitialise les statistiques."""
        self.stats = {
            "total_calls": 0,
            "avg_time_ms": 0,
            "method_usage": {"rule": 0, "ml": 0, "v2": 0, "hybrid": 0}
        }
        logger.info("Stats reset")


# ============================================================================
# SINGLETON ET FONCTION DE CONVENANCE
# ============================================================================

_global_scorer: Optional[Scorer] = None


def get_scorer(mode: Optional[str] = None) -> Scorer:
    """Retourne l'instance globale du scorer (singleton)."""
    global _global_scorer
    if _global_scorer is None or mode is not None:
        _global_scorer = Scorer(mode)
    return _global_scorer


def compute_orientation(
    features: Dict[str, Any],
    user_id: Optional[str] = None,
    user_type: Optional[str] = None,
    bac_code: Optional[str] = None,
    responses: Optional[Dict[str, int]] = None
) -> Tuple[OrientationProfile, float]:
    """
    Fonction de convenance pour calculer l'orientation.
    Utilise le scorer global avec mode auto.
    
    Args:
        features: Features normalisées
        user_id: ID utilisateur (optionnel)
        user_type: Type d'utilisateur (optionnel)
        bac_code: Code bac (optionnel)
        responses: Réponses quiz (pour V2)
    
    Returns:
        Tuple[OrientationProfile, float]: Profil et confiance
    """
    scorer = get_scorer()
    profile, confidence, _ = scorer.compute_orientation(
        features=features,
        user_id=user_id,
        user_type=user_type,
        bac_code=bac_code,
        responses=responses
    )
    return profile, confidence


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    # Test du scorer
    test_features = {
        "domains": {"computer_science": 0.8, "technical": 0.7},
        "skills": {"python": 0.9, "data_analysis": 0.8},
        "question_responses": {"q1": 5, "q2": 4, "q3": 5}
    }
    
    scorer = Scorer(mode="auto")
    
    profile, confidence, metadata = scorer.compute_orientation(
        features=test_features,
        user_id="test_user",
        user_type="bachelier",
        bac_code="C",
        responses=test_features.get("question_responses")
    )
    
    print(f"\n📊 Résultat du scoring:")
    print(f"   Méthode: {metadata.get('method')}")
    print(f"   Confiance: {confidence:.2%}")
    print(f"   Temps: {metadata.get('computation_time_ms')}ms")
    print(f"   Domaines: {list(profile.domains.keys())[:5]}")
    
    print(f"\n📈 Statistiques: {scorer.get_stats()}")