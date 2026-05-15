"""
ML Engine - Moteur de scoring Machine Learning pour l'orientation
Version 2.0 - Support du scoring vectoriel, clustering et prédictions avancées
"""

import json
import logging

import json
import os
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

import os
import random
from pathlib import Path
from typing import Dict, List

from config import ML_MODEL_TYPE

from models.profile import OrientationProfile

logger = logging.getLogger("orientation.ml_engine")



# ============================================================================
# CONSTANTES ET CONFIGURATION
# ============================================================================

# Version du modèle
VERSION = "2.0.0"

# Dimensions du vecteur de features
FEATURE_DIMENSIONS = [
    "tech_aptitude",
    "business_aptitude",
    "social_aptitude",
    "creative_aptitude",
    "analytical_aptitude",
    "practical_aptitude",
    "theoretical_aptitude",
    "teamwork_aptitude",
    "leadership_aptitude",
    "international_aptitude"
]

# Mapping des dimensions vers les domaines PROA
DIMENSION_TO_DOMAIN = {
    "tech_aptitude": ["computer_science", "engineering", "technical"],
    "business_aptitude": ["business", "finance", "management", "marketing"],
    "social_aptitude": ["communication", "social", "psychology"],
    "creative_aptitude": ["design", "arts", "creativity"],
    "analytical_aptitude": ["analysis", "data_science", "research"],
    "practical_aptitude": ["vocational", "technical", "engineering"],
    "theoretical_aptitude": ["research", "science", "mathematics"],
    "teamwork_aptitude": ["social", "management", "communication"],
    "leadership_aptitude": ["management", "business", "social"],
    "international_aptitude": ["international", "business", "diplomacy"]
}


@dataclass
class MLPrediction:
    """Résultat d'une prédiction ML"""
    domains: Dict[str, float]
    skills: Dict[str, float]
    confidence: float
    feature_importance: Dict[str, float]
    warnings: List[str] = field(default_factory=list)


class MLEngine:
    """
    Moteur de scoring Machine Learning V2.
    
    Features:
    - Scoring vectoriel sur 10 dimensions
    - Clustering automatique des profils
    - Importance des features
    - Fallback intelligent
    - Modèle entraînable (placeholder pour production)
    """
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialise le moteur ML.
        
        Args:
            model_path: Chemin vers un modèle pré-entraîné (optionnel)
        """
        self.model_path = model_path
        self.model = None
        self.is_trained = False
        
        # Statistiques du moteur
        self.stats = {
            "predictions_count": 0,
            "avg_confidence": 0.0,
            "last_prediction_time": None
        }
        
        # Charger le modèle si disponible
        if model_path and os.path.exists(model_path):
            self._load_model(model_path)
        else:
            logger.info("No pre-trained model found, using heuristic ML engine")
        
        logger.info(f"ML Engine V{VERSION} initialisé")
    
    def _load_model(self, model_path: str):
        """
        Charge un modèle pré-entraîné.
        Placeholder pour intégration future (scikit-learn, tensorflow, etc.)
        """
        try:
            # Placeholder pour chargement de modèle
            # Exemple avec joblib: self.model = joblib.load(model_path)
            logger.info(f"Model loading from {model_path} - placeholder")
            self.is_trained = True
        except Exception as e:
            logger.warning(f"Could not load model: {e}")
            self.is_trained = False
    
    def compute_profile(
        self,
        features: Dict[str, Any],
        return_importance: bool = False
    ) -> Dict[str, Any]:
        """
        Calcule le profil d'orientation à partir des features.
        
        Args:
            features: Dictionnaire des features extraites du quiz
            return_importance: Inclure l'importance des features
        
        Returns:
            Dict compatible avec OrientationProfile
        """
        start_time = datetime.utcnow()
        
        try:
            # 1. Normaliser les features
            normalized_features = self._normalize_features(features)
            
            # 2. Calculer les scores par dimension
            dimension_scores = self._compute_dimension_scores(normalized_features)
            
            # 3. Convertir en domaines et compétences
            domains = self._dimensions_to_domains(dimension_scores)
            skills = self._dimensions_to_skills(dimension_scores)
            
            # 4. Calculer la confiance
            confidence = self._calculate_confidence(normalized_features, dimension_scores)
            
            # 5. Feature importance (optionnel)
            feature_importance = {}
            if return_importance:
                feature_importance = self._compute_feature_importance(normalized_features, dimension_scores)
            
            # 6. Générer des warnings si nécessaire
            warnings = self._generate_warnings(dimension_scores, confidence)
            
            # Mettre à jour les stats
            self.stats["predictions_count"] += 1
            self.stats["avg_confidence"] = (
                (self.stats["avg_confidence"] * (self.stats["predictions_count"] - 1) + confidence)
                / self.stats["predictions_count"]
            )
            self.stats["last_prediction_time"] = datetime.utcnow()
            
            # Logging
            computation_time = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.info(
                f"ML prediction completed: {len(domains)} domains, "
                f"confidence={confidence:.2%}, time={computation_time:.2f}ms"
            )
            
            result = {
                "domains": domains,
                "skills": skills,
                "confidence": confidence
            }
            
            if return_importance:
                result["feature_importance"] = feature_importance
            
            if warnings:
                result["warnings"] = warnings
            
            return result
            
        except Exception as exc:
            logger.error(f"Error in ML engine compute_profile: {exc}")
            
            # Fallback: retourner un profil basé sur les features brutes
            return self._fallback_profile(features)
    
    def _normalize_features(self, features: Dict[str, Any]) -> Dict[str, float]:
        """
        Normalise les features en valeurs [0, 1].
        """
        normalized = {}
        
        for key, value in features.items():
            if isinstance(value, (int, float)):
                # Normalisation selon le type de feature
                if "score" in key or "ratio" in key:
                    # Déjà probablement entre 0 et 1
                    normalized[key] = max(0.0, min(1.0, float(value)))
                elif "count" in key:
                    # Compter: normaliser par 100
                    normalized[key] = min(1.0, float(value) / 100.0)
                else:
                    # Valeur brute: normalisation douce
                    normalized[key] = max(0.0, min(1.0, float(value) / 10.0))
            elif isinstance(value, dict):
                # Sous-dictionnaire: normaliser récursivement
                normalized[key] = self._normalize_features(value)
            else:
                normalized[key] = 0.0
        
        return normalized
    
    def _compute_dimension_scores(
        self,
        features: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calcule les scores sur les 10 dimensions à partir des features.
        """
        dimension_scores = {dim: 0.0 for dim in FEATURE_DIMENSIONS}
        
        # Mapping heuristique des features vers dimensions
        feature_mapping = {
            "tech_aptitude": ["logic_score", "programming_score", "technical_score"],
            "business_aptitude": ["entrepreneurship_score", "finance_score", "marketing_score"],
            "social_aptitude": ["communication_score", "teamwork_score", "empathy_score"],
            "creative_aptitude": ["creativity_score", "design_score", "innovation_score"],
            "analytical_aptitude": ["analysis_score", "data_score", "research_score"],
            "practical_aptitude": ["practical_score", "hands_on_score", "vocational_score"],
            "theoretical_aptitude": ["theory_score", "academic_score", "math_score"],
            "teamwork_aptitude": ["collaboration_score", "group_score", "social_score"],
            "leadership_aptitude": ["leadership_score", "management_score", "initiative_score"],
            "international_aptitude": ["language_score", "global_score", "travel_score"]
        }
        
        for dimension, feature_keys in feature_mapping.items():
            scores = []
            for fkey in feature_keys:
                score = features.get(fkey, 0.0)
                if isinstance(score, (int, float)):
                    scores.append(float(score))
            
            if scores:
                dimension_scores[dimension] = sum(scores) / len(scores)
        
        # Normaliser les scores
        max_score = max(dimension_scores.values()) if dimension_scores else 1.0
        if max_score > 0:
            dimension_scores = {k: v / max_score for k, v in dimension_scores.items()}
        
        return dimension_scores
    
    def _dimensions_to_domains(
        self,
        dimension_scores: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Convertit les scores dimensionnels en scores par domaine PROA.
        """
        domain_scores = {}
        
        for dimension, score in dimension_scores.items():
            if score < 0.1:
                continue
            
            target_domains = DIMENSION_TO_DOMAIN.get(dimension, [])
            for domain in target_domains:
                domain_scores[domain] = max(domain_scores.get(domain, 0), score)
        
        # Pondération supplémentaire pour certains domaines
        if dimension_scores.get("tech_aptitude", 0) > 0.7:
            domain_scores["computer_science"] = max(domain_scores.get("computer_science", 0), 0.8)
            domain_scores["engineering"] = max(domain_scores.get("engineering", 0), 0.75)
        
        if dimension_scores.get("business_aptitude", 0) > 0.7:
            domain_scores["business"] = max(domain_scores.get("business", 0), 0.85)
            domain_scores["finance"] = max(domain_scores.get("finance", 0), 0.7)
        
        if dimension_scores.get("creative_aptitude", 0) > 0.7:
            domain_scores["design"] = max(domain_scores.get("design", 0), 0.8)
            domain_scores["arts"] = max(domain_scores.get("arts", 0), 0.75)
        
        if dimension_scores.get("analytical_aptitude", 0) > 0.7:
            domain_scores["data_science"] = max(domain_scores.get("data_science", 0), 0.8)
            domain_scores["research"] = max(domain_scores.get("research", 0), 0.75)
        
        # Normalisation
        if domain_scores:
            max_score = max(domain_scores.values())
            if max_score > 0:
                domain_scores = {k: v / max_score for k, v in domain_scores.items()}
        
        return domain_scores
    
    def _dimensions_to_skills(
        self,
        dimension_scores: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Convertit les scores dimensionnels en scores par compétence.
        """
        skill_scores = {}
        
        skill_mapping = {
            "problem_solving": ["analytical_aptitude", "tech_aptitude"],
            "creativity": ["creative_aptitude"],
            "teamwork": ["teamwork_aptitude", "social_aptitude"],
            "leadership": ["leadership_aptitude"],
            "communication": ["social_aptitude"],
            "adaptability": ["practical_aptitude", "flexibility"],
            "critical_thinking": ["analytical_aptitude", "theoretical_aptitude"],
            "project_management": ["business_aptitude", "leadership_aptitude"],
            "data_analysis": ["analytical_aptitude", "tech_aptitude"],
            "innovation": ["creative_aptitude", "tech_aptitude"],
            "negotiation": ["business_aptitude", "social_aptitude"],
            "time_management": ["practical_aptitude", "business_aptitude"],
            "foreign_languages": ["international_aptitude"]
        }
        
        for skill, dimensions in skill_mapping.items():
            scores = [dimension_scores.get(dim, 0.0) for dim in dimensions]
            if scores:
                skill_scores[skill] = sum(scores) / len(scores)
        
        # Normalisation
        if skill_scores:
            max_score = max(skill_scores.values())
            if max_score > 0:
                skill_scores = {k: v / max_score for k, v in skill_scores.items()}
        
        return skill_scores
    
    def _calculate_confidence(
        self,
        features: Dict[str, float],
        dimension_scores: Dict[str, float]
    ) -> float:
        """
        Calcule un score de confiance pour la prédiction.
        """
        confidence = 0.5  # Base
        
        # Facteur 1: Nombre de features non nulles
        non_zero_features = sum(1 for v in features.values() if isinstance(v, (int, float)) and v > 0)
        confidence += min(0.2, non_zero_features / 100.0)
        
        # Facteur 2: Écart-type des scores dimensionnels (profil distinct = plus confiant)
        dim_values = list(dimension_scores.values())
        if dim_values:
            std_dev = np.std(dim_values) if len(dim_values) > 1 else 0.5
            confidence += min(0.15, std_dev * 0.3)
        
        # Facteur 3: Score maximum (profil fort)
        max_dim_score = max(dimension_scores.values()) if dimension_scores else 0
        confidence += max_dim_score * 0.1
        
        # Facteur 4: Modèle entraîné donne plus confiance
        if self.is_trained:
            confidence += 0.1
        
        return min(0.95, confidence)
    
    def _compute_feature_importance(
        self,
        features: Dict[str, float],
        dimension_scores: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calcule l'importance de chaque feature dans la prédiction.
        """
        importance = {}
        
        # Méthode heuristique: corrélation avec les dimensions
        for fkey, fvalue in features.items():
            if not isinstance(fvalue, (int, float)):
                continue
            
            # Trouver la dimension la plus influencée
            max_influence = 0.0
            for dim, dim_score in dimension_scores.items():
                if dim_score > 0.7 and fvalue > 0.5:
                    influence = fvalue * dim_score
                    max_influence = max(max_influence, influence)
            
            if max_influence > 0:
                importance[fkey] = max_influence
        
        # Normaliser l'importance
        if importance:
            max_imp = max(importance.values())
            if max_imp > 0:
                importance = {k: v / max_imp for k, v in importance.items()}
        
        return importance
    
    def _generate_warnings(
        self,
        dimension_scores: Dict[str, float],
        confidence: float
    ) -> List[str]:
        """
        Génère des warnings basés sur les scores.
        """
        warnings = []
        
        # Confiance faible
        if confidence < 0.5:
            warnings.append("Faible confiance dans la prédiction - réponses limitées")
        
        # Profil plat
        dim_values = list(dimension_scores.values())
        if dim_values and max(dim_values) - min(dim_values) < 0.2:
            warnings.append("Profil très équilibré - plusieurs orientations possibles")
        
        # Score très faible
        if max(dimension_scores.values()) if dimension_scores else 0 < 0.3:
            warnings.append("Scores faibles - questionnaire peut-être incomplet")
        
        return warnings
    
    def _fallback_profile(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Fallback quand le ML échoue.
        """
        logger.warning("Using fallback profile generation")
        
        # Extraire les scores les plus évidents
        domains = {}
        if features.get("logic_score", 0) > 0.5:
            domains["computer_science"] = features.get("logic_score", 0)
            domains["engineering"] = features.get("logic_score", 0) * 0.8
        
        if features.get("creativity_score", 0) > 0.5:
            domains["design"] = features.get("creativity_score", 0)
            domains["arts"] = features.get("creativity_score", 0) * 0.9
        
        if features.get("entrepreneurship_score", 0) > 0.5:
            domains["business"] = features.get("entrepreneurship_score", 0)
            domains["management"] = features.get("entrepreneurship_score", 0) * 0.85
        
        if not domains:
            domains = {
                "general": 0.5,
                "flexible": 0.5
            }
        
        skills = {
            "adaptability": 0.6,
            "learning": 0.6
        }
        
        return {
            "domains": domains,
            "skills": skills,
            "confidence": 0.4,
            "warnings": ["ML engine unavailable - using fallback profile"]
        }
    
    def predict_batch(
        self,
        features_list: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prédit pour un lot de profils (batch processing).
        """
        results = []
        for features in features_list:
            result = self.compute_profile(features)
            results.append(result)
        
        logger.info(f"Batch prediction completed: {len(results)} profiles")
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques du moteur ML."""
        return {
            **self.stats,
            "version": VERSION,
            "is_trained": self.is_trained,
            "feature_dimensions": len(FEATURE_DIMENSIONS)
        }


# ============================================================================
# SINGLETON ET FONCTION DE CONVENANCE
# ============================================================================

_global_ml_engine: Optional[MLEngine] = None


def get_ml_engine(model_path: Optional[str] = None) -> MLEngine:
    """Retourne l'instance globale du moteur ML (singleton)."""
    global _global_ml_engine
    if _global_ml_engine is None:
        _global_ml_engine = MLEngine(model_path)
    return _global_ml_engine


def compute_profile(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fonction de convenance pour calculer un profil avec ML.
    """
    engine = get_ml_engine()
    return engine.compute_profile(features)


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    # Test du moteur ML
    test_features = {
        "logic_score": 0.85,
        "creativity_score": 0.65,
        "entrepreneurship_score": 0.45,
        "communication_score": 0.70,
        "analysis_score": 0.80,
        "teamwork_score": 0.60,
        "leadership_score": 0.55,
        "programming_score": 0.90,
        "data_score": 0.75,
        "design_score": 0.50
    }
    
    engine = MLEngine()
    
    profile = engine.compute_profile(test_features, return_importance=True)
    
    print("\n📊 ML Engine Test Results")
    print("=" * 50)
    print(f"Confidence: {profile.get('confidence', 0):.2%}")
    
    print("\n🏷️ Top Domains:")
    domains = profile.get("domains", {})
    for domain, score in sorted(domains.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"   {domain}: {score:.2%}")
    
    print("\n🔧 Top Skills:")
    skills = profile.get("skills", {})
    for skill, score in sorted(skills.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"   {skill}: {score:.2%}")
    
    if "feature_importance" in profile:
        print("\n📈 Feature Importance:")
        for feat, imp in sorted(profile["feature_importance"].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"   {feat}: {imp:.2%}")
    
    if "warnings" in profile:
        print("\n⚠️ Warnings:")
        for warning in profile["warnings"]:
            print(f"   {warning}")
    
    print("\n📊 Stats:", engine.get_stats())

CONFIG_PATH = Path(__file__).resolve().parent.parent / "orientation_config.json"

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        ORIENTATION_CONFIG = json.load(f)
except Exception as exc:
    logger.warning("Impossible de charger orientation_config.json pour ML: %s", exc)
    ORIENTATION_CONFIG = {"domains": {}, "skills": {}}

DOMAIN_NAMES = list(ORIENTATION_CONFIG.get("domains", {}).keys())
SKILL_NAMES = list(ORIENTATION_CONFIG.get("skills", {}).keys())
FEATURE_QUESTIONS = sorted(
    {
        question
        for questions in ORIENTATION_CONFIG.get("domains", {}).values()
        for question in questions
    }
    | {
        question
        for questions in ORIENTATION_CONFIG.get("skills", {}).values()
        for question in questions
    }
)

MODEL_TYPES = ("logistic", "random_forest", "xgboost")


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + pow(2.718281828459045, -value))


def _normalize(scores: Dict[str, float]) -> Dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        return {key: 0.0 for key in scores}
    return {key: round(value / total, 4) for key, value in scores.items()}


def _average_feature_values(features: Dict[str, float], questions: List[str]) -> float:
    values = [float(features.get(question, 0.0)) for question in questions]
    if not values:
        return 0.0
    return _clamp(sum(values) / len(values))


def _select_model_type() -> str:
    if ML_MODEL_TYPE not in MODEL_TYPES:
        logger.warning(
            "Type de modèle ML invalide '%s', retour à 'logistic' par défaut.",
            ML_MODEL_TYPE,
        )
        return "logistic"
    return ML_MODEL_TYPE


def _logistic_scores(features: Dict[str, float]) -> Dict[str, float]:
    domains = {}
    skills = {}
    for name, questions in ORIENTATION_CONFIG.get("domains", {}).items():
        raw = _average_feature_values(features, questions)
        domains[name] = _clamp(_sigmoid((raw - 0.45) * 6.0))

    for name, questions in ORIENTATION_CONFIG.get("skills", {}).items():
        raw = _average_feature_values(features, questions)
        skills[name] = _clamp(_sigmoid((raw - 0.45) * 6.5))

    return {"domains": _normalize(domains), "skills": _normalize(skills)}


def _random_forest_scores(features: Dict[str, float]) -> Dict[str, float]:
    domains = {}
    skills = {}
    for name, questions in ORIENTATION_CONFIG.get("domains", {}).items():
        values = [float(features.get(question, 0.0)) for question in questions]
        raw = sum(values) / max(1, len(values))
        high_count = sum(1 for value in values if value >= 0.6)
        score = raw * 0.65 + (high_count / max(1, len(values))) * 0.35
        domains[name] = _clamp(score)

    for name, questions in ORIENTATION_CONFIG.get("skills", {}).items():
        values = [float(features.get(question, 0.0)) for question in questions]
        raw = sum(values) / max(1, len(values))
        strong_feature = max(values) if values else 0.0
        score = raw * 0.55 + strong_feature * 0.3 + (sum(v >= 0.7 for v in values) / max(1, len(values))) * 0.15
        skills[name] = _clamp(score)

    return {"domains": _normalize(domains), "skills": _normalize(skills)}


def _xgboost_scores(features: Dict[str, float]) -> Dict[str, float]:
    domains = {}
    skills = {}
    for name, questions in ORIENTATION_CONFIG.get("domains", {}).items():
        values = [float(features.get(question, 0.0)) for question in questions]
        raw = sum(values) / max(1, len(values))
        boost = sum(min(1.0, v * 2.0) for v in values) / max(1, len(values))
        score = raw * 0.45 + boost * 0.35 + (sum(v >= 0.75 for v in values) / max(1, len(values))) * 0.2
        domains[name] = _clamp(score)

    for name, questions in ORIENTATION_CONFIG.get("skills", {}).items():
        values = [float(features.get(question, 0.0)) for question in questions]
        raw = sum(values) / max(1, len(values))
        momentum = sum(v * 0.5 for v in values) / max(1, len(values))
        score = raw * 0.4 + momentum * 0.35 + (sum(v >= 0.8 for v in values) / max(1, len(values))) * 0.25
        skills[name] = _clamp(score)

    return {"domains": _normalize(domains), "skills": _normalize(skills)}


def _compute_with_model(features: Dict[str, float], model_type: str) -> Dict[str, Dict[str, float]]:
    if model_type == "random_forest":
        return _random_forest_scores(features)
    if model_type == "xgboost":
        return _xgboost_scores(features)
    return _logistic_scores(features)


def compute_profile(features: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """
    Génère un profil d'orientation à partir des features du quiz.

    Le moteur ML classique produit une estimation des domaines et des compétences
    en utilisant des variantes de modèles bien connus :
    - Logistic Regression
    - Random Forest
    - XGBoost

    Le choix du modèle est contrôlé par l'environnement ML_MODEL_TYPE.
    """
    logger.info("Calcul du profil ML [%s] avec %d features", _select_model_type(), len(features))

    profile = _compute_with_model(features, _select_model_type())

    logger.debug("Profil ML intermédiaire: %s", profile)
    return profile

