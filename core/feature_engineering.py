# core/feature_engineering.py

import logging
import os
import json
from typing import Dict

logger = logging.getLogger("orientation.feature_engineering")

# Charger la configuration
CONFIG_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "orientation_config.json",
)

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        ORIENTATION_CONFIG = json.load(f)
except Exception:
    logger.exception("Impossible de charger orientation_config.json")
    ORIENTATION_CONFIG = {}


def build_features(responses: Dict[str, float]) -> Dict[str, float]:
    """
    Transforme les réponses brutes du quiz en features normalisées [0, 1].
    
    Logique:
    - Chaque domaine/skill est calculé comme la MOYENNE des réponses
    - Les réponses sont normalisées par max_score (défaut: 5)
    - Applique un seuil minimum (défaut: 2) pour activer un domaine
    
    Args:
        responses (Dict[str, float]): réponses brutes du quiz {question_id: score}
        
    Returns:
        Dict[str, float]: features normalisées {feature_name: normalized_score}
    """
    if not responses:
        logger.warning("Aucune réponse fournie")
        return {}
    
    try:
        max_score = ORIENTATION_CONFIG.get("max_score", 5)
        domain_threshold = ORIENTATION_CONFIG.get("domain_threshold", 2)
        
        features = {}
        
        # --- SKILLS (moyenne simple) ---
        skills_config = ORIENTATION_CONFIG.get("skills", {})
        for skill_name, question_ids in skills_config.items():
            values = [responses.get(q_id, 0.0) for q_id in question_ids if q_id in responses]
            if values:
                avg_value = sum(values) / len(values)
                # Normaliser [0, max_score] → [0, 1]
                normalized = max(0.0, min(1.0, avg_value / max_score))
                features[f"skill_{skill_name}"] = round(normalized, 4)
            else:
                features[f"skill_{skill_name}"] = 0.0
        
        # --- DOMAINS (moyenne avec seuil) ---
        domains_config = ORIENTATION_CONFIG.get("domains", {})
        for domain_name, question_ids in domains_config.items():
            values = [responses.get(q_id, 0.0) for q_id in question_ids if q_id in responses]
            if values:
                avg_value = sum(values) / len(values)
                # Appliquer le seuil minimum
                if avg_value >= domain_threshold:
                    normalized = max(0.0, min(1.0, avg_value / max_score))
                    features[f"domain_{domain_name}"] = round(normalized, 4)
                else:
                    features[f"domain_{domain_name}"] = 0.0
            else:
                features[f"domain_{domain_name}"] = 0.0
        
        logger.info(f"Features générées: {len(features)} (skills + domains)")
        return features
        
    except Exception as exc:
        logger.error(f"Erreur lors de la génération des features: {str(exc)}")
        raise
