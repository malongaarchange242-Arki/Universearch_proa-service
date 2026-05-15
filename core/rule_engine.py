# core/rule_engine.py

import json
import logging
import os

from typing import Dict, List, Optional, Tuple


from typing import Any, Dict, List

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

# Pondérations
DOMAIN_WEIGHT = ORIENTATION_CONFIG.get("domain_weight", 1.0)
SKILL_WEIGHT = ORIENTATION_CONFIG.get("skill_weight", 1.0)

# -------------------------------------------------
# Configuration Bac (nouveau)
# -------------------------------------------------
BAC_SERIES = ORIENTATION_CONFIG.get("bac_series", {})
BAC_SECTORS = ORIENTATION_CONFIG.get("bac_sectors", {})
BAC_RULES = ORIENTATION_CONFIG.get("bac_compatibility_rules", {})

# Extraction des règles avec valeurs par défaut
STRICT_FORBIDDEN = BAC_RULES.get("strict_forbidden", False)
APPLY_PENALTY = BAC_RULES.get("apply_penalty_instead_of_exclusion", True)
PENALTY_WEIGHT = BAC_RULES.get("penalty_weight", 0.30)
BONUS_WEIGHT = BAC_RULES.get("bonus_weight", 0.15)
MIN_SCORE_THRESHOLD = BAC_RULES.get("minimum_score_threshold", 0.10)


class RuleEngine:
    """
    PROA – Profile Rule-Oriented Algorithm

    Génère un vecteur stable, interprétable,
    directement exploitable par PORA.

    Inclut la compatibilité Bac ↔ Filières
    basée sur le système éducatif congolais.
    """

    def __init__(self) -> None:
        # Maps pour le vecteur d'orientation
        self.domain_map = {name.lower(): idx for idx, name in enumerate(DOMAIN_NAMES)}
        self.skill_offset = len(DOMAIN_NAMES)
        self.skill_map = {
            name.lower(): idx + self.skill_offset
            for idx, name in enumerate(SKILL_NAMES)
        }
        self.vector_size = len(DOMAIN_NAMES) + len(SKILL_NAMES)

        # Cache de validation des codes bac
        self._valid_bac_codes: set = set(BAC_SERIES.keys())

        logger.info(
            "RuleEngine prêt | domains=%d | skills=%d | vector_size=%d | bacs=%d | secteurs=%d",
            len(DOMAIN_NAMES),
            len(SKILL_NAMES),
            self.vector_size,
            len(BAC_SERIES),
            len(BAC_SECTORS),
        )

    # =================================================
    # API PRINCIPALE
    # =================================================

    def build_orientation_vector(self, profile: OrientationProfile) -> List[float]:
        """Construit le vecteur d'orientation normalisé."""
        vector: List[float] = [0.0] * self.vector_size

        self._apply_domains(profile.domains, vector)
        self._apply_skills(profile.skills, vector)

        if NORMALIZE:
            self._normalize(vector)

        return vector

    # =================================================
    # COMPATIBILITÉ BAC (NOUVEAU)
    # =================================================

    def validate_bac_code(self, bac_code: str) -> bool:
        """
        Vérifie si un code bac est valide dans le système congolais.

        Args:
            bac_code: Le code du bac (ex: "C", "D", "H1", "R3")

        Returns:
            True si le code est reconnu
        """
        if not bac_code:
            return False
        return bac_code.upper().strip() in self._valid_bac_codes

    def get_bac_info(self, bac_code: str) -> Optional[dict]:
        """
        Récupère les informations d'une série de bac.

        Args:
            bac_code: Le code du bac

        Returns:
            Dict avec description, sector, icon, color ou None
        """
        if not bac_code:
            return None
        return BAC_SERIES.get(bac_code.upper().strip())

    def get_bac_sector(self, bac_code: str) -> Optional[str]:
        """
        Retourne le secteur d'un bac (science, business, technical, etc.).

        Args:
            bac_code: Le code du bac

        Returns:
            Le secteur ou None
        """
        info = self.get_bac_info(bac_code)
        return info.get("sector") if info else None

    def get_bac_sector_rules(self, bac_code: str) -> Optional[dict]:
        """
        Récupère les règles de compatibilité pour le secteur d'un bac.

        Args:
            bac_code: Le code du bac

        Returns:
            Dict avec allowed_clusters, forbidden_clusters, etc. ou None
        """
        sector = self.get_bac_sector(bac_code)
        if not sector:
            return None
        return BAC_SECTORS.get(sector)

    def is_cluster_allowed_for_bac(
        self,
        bac_code: str,
        cluster_name: str,
    ) -> Tuple[bool, float]:
        """
        Vérifie si un cluster métier est compatible avec un bac.

        Args:
            bac_code: Le code du bac (ex: "D")
            cluster_name: Le nom du cluster (ex: "business", "droit")

        Returns:
            Tuple (est_autorise, score_modificateur)
            - est_autorise: True si le cluster est autorisé
            - score_modificateur: bonus positif ou malus négatif à appliquer
        """
        # Sans bac, tout est autorisé (mode neutre)
        if not bac_code or not cluster_name:
            return True, 0.0

        rules = self.get_bac_sector_rules(bac_code)
        if not rules:
            logger.warning("Aucune règle trouvée pour le bac '%s'", bac_code)
            return True, 0.0

        cluster_lower = cluster_name.lower().strip()

        # Vérifier les clusters autorisés
        allowed = rules.get("allowed_clusters", [])
        forbidden = rules.get("forbidden_clusters", [])

        if cluster_lower in allowed:
            bonus = rules.get("cluster_bonus", BONUS_WEIGHT)
            logger.debug(
                "Bac %s → cluster '%s' : AUTORISÉ (bonus +%.2f)",
                bac_code, cluster_name, bonus,
            )
            return True, bonus

        if cluster_lower in forbidden:
            if STRICT_FORBIDDEN:
                logger.debug(
                    "Bac %s → cluster '%s' : INTERDIT (exclusion)",
                    bac_code, cluster_name,
                )
                return False, 0.0
            else:
                malus = rules.get("cluster_malus", -PENALTY_WEIGHT)
                logger.debug(
                    "Bac %s → cluster '%s' : PÉNALISÉ (malus %.2f)",
                    bac_code, cluster_name, malus,
                )
                return True, malus

        # Cluster non listé : neutre
        logger.debug(
            "Bac %s → cluster '%s' : NEUTRE (non listé)",
            bac_code, cluster_name,
        )
        return True, 0.0

    def is_domain_allowed_for_bac(
        self,
        bac_code: str,
        domain_name: str,
    ) -> Tuple[bool, float]:
        """
        Vérifie si un domaine de compétence est compatible avec un bac.

        Args:
            bac_code: Le code du bac
            domain_name: Le nom du domaine (ex: "computer_science", "communication")

        Returns:
            Tuple (est_autorise, score_modificateur)
        """
        if not bac_code or not domain_name:
            return True, 0.0

        rules = self.get_bac_sector_rules(bac_code)
        if not rules:
            return True, 0.0

        domain_lower = domain_name.lower().strip()
        allowed_domains = rules.get("allowed_domains", [])
        forbidden_domains = rules.get("forbidden_domains", [])

        if domain_lower in allowed_domains:
            return True, rules.get("cluster_bonus", BONUS_WEIGHT)

        if domain_lower in forbidden_domains:
            if STRICT_FORBIDDEN:
                return False, 0.0
            return True, rules.get("cluster_malus", -PENALTY_WEIGHT)

        return True, 0.0

    def compute_bac_compatibility_score(
        self,
        bac_code: str,
        field_cluster: str,
        field_domains: Optional[List[str]] = None,
    ) -> float:
        """
        Calcule un score de compatibilité entre un bac et une filière.

        Args:
            bac_code: Le code du bac
            field_cluster: Le cluster métier de la filière
            field_domains: Les domaines associés à la filière (optionnel)

        Returns:
            Score de compatibilité entre 0.0 et 1.0
            - 1.0 = parfaitement compatible
            - 0.5 = neutre
            - 0.0 = totalement incompatible
        """
        if not bac_code:
            return 0.5  # Neutre sans bac

        # Vérifier le cluster
        cluster_allowed, cluster_modifier = self.is_cluster_allowed_for_bac(
            bac_code, field_cluster
        )

        if not cluster_allowed:
            return 0.0

        # Base neutre
        score = 0.5

        # Appliquer le modificateur du cluster
        score += cluster_modifier

        # Vérifier les domaines si fournis
        if field_domains:
            domain_modifiers = []
            for domain in field_domains:
                _, mod = self.is_domain_allowed_for_bac(bac_code, domain)
                domain_modifiers.append(mod)

            if domain_modifiers:
                avg_domain_mod = sum(domain_modifiers) / len(domain_modifiers)
                score += avg_domain_mod * 0.5  # Poids des domaines à 50%

        # Clamper entre 0.0 et 1.0
        return max(0.0, min(1.0, score))

    def filter_fields_by_bac(
        self,
        bac_code: str,
        fields: List[dict],
    ) -> List[dict]:
        """
        Filtre et ajuste les scores des filières selon la compatibilité bac.

        Args:
            bac_code: Le code du bac
            fields: Liste des filières avec leurs scores

        Returns:
            Liste des filières avec scores ajustés
        """
        if not bac_code or not fields:
            return fields

        adjusted_fields = []

        for field in fields:
            field_cluster = field.get("cluster", "unknown")
            field_domains = field.get("domains", [])

            # Calculer la compatibilité
            compat_score = self.compute_bac_compatibility_score(
                bac_code, field_cluster, field_domains
            )

            # Appliquer le modificateur au score existant
            original_score = field.get("score", 0.5)

            if compat_score == 0.0:
                # Totalement incompatible
                if APPLY_PENALTY:
                    adjusted_score = original_score * MIN_SCORE_THRESHOLD
                else:
                    continue  # Exclure totalement
            else:
                # Ajuster le score selon la compatibilité
                adjustment = (compat_score - 0.5) * 2  # -1.0 à +1.0
                adjusted_score = original_score * (1.0 + adjustment * PENALTY_WEIGHT)
                adjusted_score = max(0.0, min(1.0, adjusted_score))

            adjusted_field = dict(field)
            adjusted_field["original_score"] = original_score
            adjusted_field["bac_compatibility"] = round(compat_score, 4)
            adjusted_field["bac_adjusted_score"] = round(adjusted_score, 4)
            adjusted_field["score"] = round(adjusted_score, 4)

            adjusted_fields.append(adjusted_field)

        # Re-trier par score ajusté
        adjusted_fields.sort(key=lambda f: f["score"], reverse=True)

        logger.info(
            "Filtrage bac '%s' : %d filières → %d retenues",
            bac_code, len(fields), len(adjusted_fields),
        )

        return adjusted_fields

    def get_recommended_bac_for_field(
        self,
        field_cluster: str,
    ) -> List[str]:
        """
        Suggère les bacs les plus adaptés pour une filière donnée.

        Utile pour l'orientation inversée.

        Args:
            field_cluster: Le cluster métier de la filière

        Returns:
            Liste des codes bac recommandés
        """
        recommended = []

        for bac_code, bac_info in BAC_SERIES.items():
            sector = bac_info.get("sector")
            if not sector:
                continue

            rules = BAC_SECTORS.get(sector, {})
            allowed = rules.get("allowed_clusters", [])

            if field_cluster.lower() in allowed:
                recommended.append(bac_code)

        return recommended

    # =================================================
    # MÉTHODES INTERNES (ORIGINALES + OPTIMISÉES)
    # =================================================

    def _apply_domains(self, domains: Dict[str, float], vector: List[float]) -> None:
        for domain, value in domains.items():
            if value == 0.0:
                continue
            idx = self.domain_map.get(domain.lower())
            if idx is not None:
                v = value * DOMAIN_WEIGHT
                vector[idx] += v if 0.0 <= v <= 1.0 else max(0.0, min(1.0, v))

    def _apply_skills(self, skills: Dict[str, float], vector: List[float]) -> None:
        for skill, value in skills.items():
            if value == 0.0:
                continue
            idx = self.skill_map.get(skill.lower())
            if idx is not None:
                v = value * SKILL_WEIGHT
                vector[idx] += v if 0.0 <= v <= 1.0 else max(0.0, min(1.0, v))

    def _normalize(self, vector: List[float]) -> None:
        total = sum(vector)
        if total == 0:
            return
        inv_total = 1.0 / total
        for i in range(len(vector)):
            vector[i] = round(vector[i] * inv_total, 4)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))


# -------------------------------------------------
# Singleton moteur
# -------------------------------------------------
_ENGINE = RuleEngine()


def compute_profile(profile: OrientationProfile) -> List[float]:
    """Point d'entrée unique appelé par l'API."""
    return _ENGINE.build_orientation_vector(profile)


# Fonctions exposées pour la compatibilité bac
def validate_bac_code(bac_code: str) -> bool:
    """Valide un code bac congolais."""
    return _ENGINE.validate_bac_code(bac_code)


def get_bac_info(bac_code: str) -> Optional[dict]:
    """Récupère les infos d'une série de bac."""
    return _ENGINE.get_bac_info(bac_code)


def get_bac_sector(bac_code: str) -> Optional[str]:
    """Retourne le secteur d'un bac."""
    return _ENGINE.get_bac_sector(bac_code)


def check_bac_field_compatibility(
    bac_code: str,
    field_cluster: str,
    field_domains: Optional[List[str]] = None,
) -> float:
    """Calcule la compatibilité entre un bac et une filière."""
    return _ENGINE.compute_bac_compatibility_score(
        bac_code, field_cluster, field_domains
    )


def filter_fields_by_bac(
    bac_code: str,
    fields: List[dict],
) -> List[dict]:
    """Filtre les filières selon la compatibilité bac."""
    return _ENGINE.filter_fields_by_bac(bac_code, fields)


def get_recommended_bac_for_field(field_cluster: str) -> List[str]:
    """Suggère les bacs adaptés à une filière."""
    return _ENGINE.get_recommended_bac_for_field(field_cluster)

def _average_feature_values(features: Dict[str, float], questions: List[str]) -> float:
    values = [float(features.get(question, 0.0)) for question in questions]
    if not values:
        return 0.0
    average = sum(values) / len(values)
    return max(0.0, min(1.0, average))


def build_profile_from_features(features: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    """
    Construit un profil d'orientation formaté à partir des features brutes.
    """
    domains = {
        name: _average_feature_values(features, questions)
        for name, questions in ORIENTATION_CONFIG.get("domains", {}).items()
    }
    skills = {
        name: _average_feature_values(features, questions)
        for name, questions in ORIENTATION_CONFIG.get("skills", {}).items()
    }
    return {
        "domains": domains,
        "skills": skills,
    }


def compute_profile(profile_or_features) -> Any:
    """
    Point d’entrée unique pour le moteur d'orientation.

    Accepte soit un OrientationProfile (pour la génération du vecteur),
    soit un dictionnaire de features (pour la génération de domaines/skills).
    """
    if isinstance(profile_or_features, OrientationProfile):
        return _ENGINE.build_orientation_vector(profile_or_features)

    if isinstance(profile_or_features, dict):
        return build_profile_from_features(profile_or_features)

    raise TypeError(
        "compute_profile attend un OrientationProfile ou un dictionnaire de features."
    )

