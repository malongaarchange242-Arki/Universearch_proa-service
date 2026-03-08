# core/ml_engine.py

import logging
from models.profile import OrientationProfile

logger = logging.getLogger("orientation.ml_engine")

def compute_profile(features: dict) -> dict:
    """
    Placeholder pour un moteur ML.
    Transforme les features en un profil d'orientation.
    
    Args:
        features (dict): dictionnaire des features extraites du quiz

    Returns:
        dict: dict compatible avec OrientationProfile
              {
                  "domains": {"domain1": float, ...},
                  "skills": {"skill1": float, ...}
              }
    """
    try:
        logger.info("Calcul du profil ML avec features: %s", features)

        # Exemple simple basé sur les features existantes
        profile_dict = {
            "domains": {
                "logic": features.get("logic_score", 0.0),
                "creativity": features.get("creativity_score", 0.0),
                "entrepreneurship": features.get("entrepreneurship_score", 0.0),
                "theory_practice_ratio": features.get("theory_practice_ratio", 0.0),
            },
            "skills": {
                "problem_solving": features.get("logic_score", 0.0),
                "innovation": features.get("creativity_score", 0.0),
                "business": features.get("entrepreneurship_score", 0.0),
            }
        }

        logger.info("Profil ML calculé: %s", profile_dict)
        return profile_dict

    except Exception as exc:
        logger.error("Erreur dans ML engine compute_profile: %s", str(exc))
        raise
