# core/scorer.py

import logging
from config import ENGINE_MODE
from core import rule_engine, ml_engine
from models.profile import OrientationProfile

logger = logging.getLogger("orientation.scorer")

def compute_orientation(features: dict) -> tuple[OrientationProfile, float]:
    """
    Calcule le profil d'orientation de l'utilisateur à partir des features
    générées par le quiz. Choisit automatiquement le moteur rule-based
    ou ML selon la configuration.

    Args:
        features (dict): dictionnaire des features normalisées

    Returns:
        tuple[OrientationProfile, float]: profil d'orientation et confiance (0.0-1.0)
    """
    try:
        if ENGINE_MODE == "ml":
            logger.info("Utilisation du moteur ML pour le scoring")
            profile_dict = ml_engine.compute_profile(features)
        else:
            logger.info("Utilisation du moteur rule-based pour le scoring")
            profile_dict = rule_engine.compute_profile(features)

        profile = OrientationProfile(**profile_dict)

        # TODO: Calculer une vraie confiance basée sur le moteur ou les features
        confidence = 0.85

        logger.info(
            "Profil calculé: %s | Confiance: %.2f", profile_dict, confidence
        )
        return profile, confidence

    except Exception as exc:
        logger.error("Erreur lors du calcul de l'orientation: %s", str(exc))
        raise
