# core/rule_engine.py

import json
import logging
import os
from typing import Dict, List
from models.profile import OrientationProfile

logger = logging.getLogger("orientation.rule_engine")

# -------------------------------------------------
# Chargement config (robuste)
# -------------------------------------------------
CONFIG_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "orientation_config.json",
)

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    ORIENTATION_CONFIG = json.load(f)

DOMAIN_NAMES = list(ORIENTATION_CONFIG.get("domains", {}).keys())
SKILL_NAMES = list(ORIENTATION_CONFIG.get("skills", {}).keys())

NORMALIZE = ORIENTATION_CONFIG.get("normalize_vector", True)

# Pondérations futures (safe defaults)
DOMAIN_WEIGHT = ORIENTATION_CONFIG.get("domain_weight", 1.0)
SKILL_WEIGHT = ORIENTATION_CONFIG.get("skill_weight", 1.0)


class RuleEngine:
    """
    PROA – Profile Rule-Oriented Algorithm

    Génère un vecteur stable, interprétable,
    directement exploitable par PORA.
    """

    def __init__(self) -> None:
        self.domain_map = {name.lower(): idx for idx, name in enumerate(DOMAIN_NAMES)}
        self.skill_offset = len(DOMAIN_NAMES)
        self.skill_map = {
            name.lower(): idx + self.skill_offset
            for idx, name in enumerate(SKILL_NAMES)
        }

        self.vector_size = len(DOMAIN_NAMES) + len(SKILL_NAMES)

        logger.info(
            "RuleEngine prêt | domains=%d | skills=%d | vector_size=%d",
            len(DOMAIN_NAMES),
            len(SKILL_NAMES),
            self.vector_size,
        )

    # -------------------------------------------------
    # API principale
    # -------------------------------------------------
    def build_orientation_vector(self, profile: OrientationProfile) -> List[float]:
        vector: List[float] = [0.0] * self.vector_size

        self._apply_domains(profile.domains, vector)
        self._apply_skills(profile.skills, vector)

        if NORMALIZE:
            self._normalize(vector)

        return vector

    # -------------------------------------------------
    # Domaines (déjà normalisés en amont)
    # -------------------------------------------------
    def _apply_domains(self, domains: Dict[str, float], vector: List[float]) -> None:
        for domain, value in domains.items():
            idx = self.domain_map.get(domain.lower())
            if idx is not None:
                vector[idx] += self._clamp(value * DOMAIN_WEIGHT)

    # -------------------------------------------------
    # Skills (déjà normalisés en amont)
    # -------------------------------------------------
    def _apply_skills(self, skills: Dict[str, float], vector: List[float]) -> None:
        for skill, value in skills.items():
            idx = self.skill_map.get(skill.lower())
            if idx is not None:
                vector[idx] += self._clamp(value * SKILL_WEIGHT)

    # -------------------------------------------------
    # Normalisation globale (stable)
    # -------------------------------------------------
    def _normalize(self, vector: List[float]) -> None:
        total = sum(vector)
        if total == 0:
            return
        for i in range(len(vector)):
            vector[i] = round(vector[i] / total, 4)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))


# -------------------------------------------------
# Singleton moteur
# -------------------------------------------------
_ENGINE = RuleEngine()


def compute_profile(profile: OrientationProfile) -> List[float]:
    """
    Point d’entrée unique appelé par l’API
    """
    return _ENGINE.build_orientation_vector(profile)
