"""
Utils - Fonctions utilitaires pour le scoring PROA
Version 2.0 - Support avancé pour validation, normalisation et gestion des réponses
"""

import logging
import re
import unicodedata
from typing import Dict, List, Optional, Tuple, Any
from functools import lru_cache

logger = logging.getLogger("orientation.utils")


# ============================================================================
# CONSTANTES
# ============================================================================

# Plages de valeurs valides pour les réponses
VALID_RESPONSE_RANGE = (1, 5)  # Maintenant supporte 1-5 (anciennement 1-4)
VALID_QUESTION_CODES = [f"q{i}" for i in range(1, 26)]  # q1 à q25

# Codes bac congolais valides
VALID_BAC_CODES = {
    "A", "A1", "A2", "A3",  # Lettres
    "B",  # Sciences économiques
    "C", "D",  # Mathématiques, Sciences
    "E", "F1", "F2", "F3", "F4",  # Techniques
    "G1", "G2", "G3",  # Commerciales
    "BG",  # Bac Général
    "H1", "H2", "H3", "H4", "H5",  # Pédagogie
    "R1", "R2", "R3", "R4", "R5", "R6",  # Pédagogie rurale
    "P2", "P3", "P4", "P5", "P6", "P7",  # Professionnel
}

# Mapping des séries bac vers tracks
BAC_TRACK_MAPPING = {
    "A": "humanities", "A1": "humanities", "A2": "humanities", "A3": "humanities",
    "B": "business",
    "C": "science", "D": "science",
    "E": "technical", "F1": "technical", "F2": "technical", "F3": "technical", "F4": "technical",
    "G1": "business", "G2": "business", "G3": "business",
    "BG": "general",
    "H1": "humanities", "H2": "humanities", "H3": "humanities", "H4": "humanities", "H5": "humanities",
    "R1": "humanities", "R2": "humanities", "R3": "humanities", "R4": "humanities", "R5": "humanities", "R6": "humanities",
    "P2": "vocational", "P3": "vocational", "P4": "vocational", "P5": "vocational", "P6": "vocational", "P7": "vocational",
}

# ============================================================================
# NORMALISATION DES RÉPONSES
# ============================================================================

def _strip_invisible_chars(value: str) -> str:
    """Remove zero-width and invisible unicode characters from a string."""
    if not value:
        return value
    return re.sub(r'[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]', '', value)


def normalize_response_code(code: Any) -> str:
    """Normalize question keys and semantic codes from user responses."""
    if code is None:
        return ""

    normalized = str(code)
    normalized = unicodedata.normalize("NFKC", normalized)
    normalized = _strip_invisible_chars(normalized)
    normalized = normalized.strip().lower()
    normalized = re.sub(r'^question_', '', normalized)
    normalized = re.sub(r'^qst_', '', normalized)

    return normalized


def normalize_responses(responses: Dict[str, int]) -> Dict[str, int]:
    """
    Normalise les codes de questions en minuscules.
    
    Transforme: {"Q1": 3, "Q2": 4} → {"q1": 3, "q2": 4}
    
    Args:
        responses: Réponses brutes utilisateur (n'importe quelle casse)
    
    Returns:
        Réponses normalisées (toutes les clés en minuscules)
    """
    if not responses:
        return {}
    
    normalized = {}
    for key, value in responses.items():
        normalized_key = normalize_response_code(key)
        normalized[normalized_key] = value
        
        if normalized_key != str(key):
            logger.debug(f"Normalized: {key} → {normalized_key}")
    
    logger.info(f"Responses normalized: {len(normalized)} entries")
    return normalized


def normalize_question_code(code: str) -> str:
    """
    Normalise un code de question individuel.
    
    Exemples:
    - "Q1" → "q1"
    - "question_2" → "q2"
    - "QST_03" → "q3"
    """
    normalized = normalize_response_code(code)
    
    match = re.search(r'(\d+)', normalized)
    if match:
        num = int(match.group(1))
        return f"q{num}"
    
    return normalized


def validate_response_values(responses: Dict[str, int]) -> bool:
    """
    Valide que toutes les valeurs de réponse sont dans la plage [1-5].
    
    Returns:
        True si valide, lève ValueError sinon
    """
    min_val, max_val = VALID_RESPONSE_RANGE
    
    for key, value in responses.items():
        if not isinstance(value, (int, float)):
            raise ValueError(f"Response {key} must be numeric, got {type(value)}")
        
        if not (min_val <= value <= max_val):
            raise ValueError(f"Response {key} must be {min_val}-{max_val}, got {value}")
        
        # Vérifier que c'est un entier
        if isinstance(value, float) and not value.is_integer():
            raise ValueError(f"Response {key} must be integer, got {value}")
    
    return True


def validate_question_codes(responses: Dict[str, int]) -> bool:
    """
    Valide que les codes de questions sont reconnus.
    """
    valid_codes = set(VALID_QUESTION_CODES)
    
    for key in responses.keys():
        normalized = normalize_question_code(key)
        if normalized not in valid_codes and not normalized.startswith("q"):
            logger.warning(f"Unknown question code: {key} (normalized: {normalized})")
            # On ne lève pas d'erreur, on log juste un warning
    
    return True


def normalize_and_validate(responses: Dict[str, int]) -> Dict[str, int]:
    """
    Combine: normalisation + validation
    
    Args:
        responses: Réponses brutes
    
    Returns:
        Réponses normalisées et validées
    
    Raises:
        ValueError: Si validation échoue
    """
    if not responses:
        raise ValueError("Responses cannot be empty")
    
    normalized = normalize_responses(responses)
    validate_response_values(normalized)
    validate_question_codes(normalized)
    
    return normalized


# ============================================================================
# NORMALISATION DES PROFILS
# ============================================================================

def normalize_domain_name(domain: str) -> str:
    """
    Normalise un nom de domaine pour le matching.
    """
    if not domain:
        return ""
    
    normalized = str(domain).lower().strip()
    normalized = normalized.replace("_", " ")
    normalized = normalized.replace("-", " ")
    normalized = re.sub(r'\s+', ' ', normalized)
    
    return normalized


def normalize_skill_name(skill: str) -> str:
    """
    Normalise un nom de compétence.
    """
    return normalize_domain_name(skill)


def normalize_bac_code(bac_code: Optional[str]) -> Optional[str]:
    """
    Normalise un code bac congolais.
    
    Exemples:
    - "c" → "C"
    - "C01" → "C"
    - "série C" → "C"
    """
    if not bac_code:
        return None
    
    # Nettoyer
    normalized = str(bac_code).upper().strip()
    
    # Extraire le code (premier caractère + optionnel chiffre)
    match = re.search(r'([A-Z])(\d+)?', normalized)
    if match:
        letter = match.group(1)
        number = match.group(2) if match.group(2) else ""
        
        # Codes spéciaux
        if normalized in ["BG"]:
            return "BG"
        
        # Format standard
        if number:
            return f"{letter}{number}"
        return letter
    
    # Vérifier si code valide
    if normalized in VALID_BAC_CODES:
        return normalized
    
    logger.warning(f"Unknown bac code: {bac_code}")
    return None


def get_bac_track(bac_code: Optional[str]) -> Optional[str]:
    """
    Retourne le track associé à un code bac.
    """
    normalized = normalize_bac_code(bac_code)
    if not normalized:
        return None
    
    return BAC_TRACK_MAPPING.get(normalized)


def is_valid_bac_code(bac_code: Optional[str]) -> bool:
    """
    Vérifie si un code bac est valide.
    """
    normalized = normalize_bac_code(bac_code)
    return normalized in VALID_BAC_CODES


# ============================================================================
# STATISTIQUES ET AGGREGATIONS
# ============================================================================

def compute_response_stats(responses: Dict[str, int]) -> Dict[str, Any]:
    """
    Calcule des statistiques sur les réponses utilisateur.
    """
    if not responses:
        return {
            "count": 0,
            "mean": 0,
            "std": 0,
            "min": 0,
            "max": 0,
            "distribution": {}
        }
    
    values = list(responses.values())
    
    # Distribution
    distribution = {}
    for v in range(VALID_RESPONSE_RANGE[0], VALID_RESPONSE_RANGE[1] + 1):
        distribution[str(v)] = values.count(v)
    
    # Moyenne et écart-type
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = variance ** 0.5
    
    return {
        "count": len(values),
        "mean": round(mean, 2),
        "std": round(std, 2),
        "min": min(values),
        "max": max(values),
        "distribution": distribution
    }


def get_question_categories(responses: Dict[str, int]) -> Dict[str, float]:
    """
    Regroupe les réponses par catégorie de question.
    """
    categories = {
        "technical": ["q1", "q2", "q3", "q4", "q5"],
        "business": ["q6", "q7", "q8", "q9", "q10"],
        "social": ["q11", "q12", "q13", "q14", "q15"],
        "creative": ["q16", "q17", "q18", "q19", "q20"],
        "scientific": ["q21", "q22", "q23", "q24", "q25"],
    }
    
    category_scores = {}
    
    for category, questions in categories.items():
        scores = [responses.get(q, 0) for q in questions if q in responses]
        if scores:
            category_scores[category] = sum(scores) / len(scores) / 5  # Normaliser 0-1
    
    return category_scores


# ============================================================================
# UTILITAIRES DE CACHE
# ============================================================================

@lru_cache(maxsize=1000)
def hash_responses(responses_tuple: Tuple[Tuple[str, int], ...]) -> str:
    """
    Crée un hash unique pour un ensemble de réponses.
    Utile pour le caching.
    """
    import hashlib
    import json
    
    responses_dict = dict(responses_tuple)
    sorted_responses = json.dumps(responses_dict, sort_keys=True)
    return hashlib.md5(sorted_responses.encode()).hexdigest()


def responses_to_tuple(responses: Dict[str, int]) -> Tuple[Tuple[str, int], ...]:
    """
    Convertit un dict de réponses en tuple pour le caching.
    """
    return tuple(sorted((k, v) for k, v in responses.items()))


# ============================================================================
# VALIDATION DE PROFIL
# ============================================================================

def validate_profile(profile: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Valide la structure d'un profil utilisateur.
    
    Returns:
        Tuple[is_valid, list_of_errors]
    """
    errors = []
    
    # Vérifier les domaines
    domains = profile.get("domains", {})
    if not isinstance(domains, dict):
        errors.append("domains must be a dictionary")
    else:
        for domain, score in domains.items():
            if not isinstance(score, (int, float)) or not (0 <= score <= 1):
                errors.append(f"Domain {domain} score must be 0-1, got {score}")
    
    # Vérifier les compétences
    skills = profile.get("skills", {})
    if not isinstance(skills, dict):
        errors.append("skills must be a dictionary")
    
    # Vérifier le contexte
    context = profile.get("context", {})
    if context and not isinstance(context, dict):
        errors.append("context must be a dictionary")
    elif context:
        bac_code = context.get("bac_code")
        if bac_code and not is_valid_bac_code(bac_code):
            errors.append(f"Invalid bac_code: {bac_code}")
    
    return len(errors) == 0, errors


def sanitize_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nettoie un profil utilisateur (supprime les valeurs invalides).
    """
    sanitized = {}
    
    # Domains
    domains = profile.get("domains", {})
    if isinstance(domains, dict):
        sanitized["domains"] = {
            k: min(1.0, max(0.0, float(v)))
            for k, v in domains.items()
            if isinstance(v, (int, float)) and v > 0
        }
    else:
        sanitized["domains"] = {}
    
    # Skills
    skills = profile.get("skills", {})
    if isinstance(skills, dict):
        sanitized["skills"] = {
            k: min(1.0, max(0.0, float(v)))
            for k, v in skills.items()
            if isinstance(v, (int, float)) and v > 0
        }
    else:
        sanitized["skills"] = {}
    
    # Context
    context = profile.get("context", {})
    if isinstance(context, dict):
        sanitized_context = {}
        if "bac_code" in context:
            normalized = normalize_bac_code(context.get("bac_code"))
            if normalized:
                sanitized_context["bac_code"] = normalized
                sanitized_context["bac_track"] = get_bac_track(normalized)
        if "user_type" in context:
            sanitized_context["user_type"] = context["user_type"]
        sanitized["context"] = sanitized_context
    else:
        sanitized["context"] = {}
    
    return sanitized


# ============================================================================
# FONCTIONS DE CONVENANCE
# ============================================================================

def safe_get(responses: Dict[str, int], key: str, default: int = 3) -> int:
    """
    Récupère une valeur de réponse de manière sécurisée.
    """
    normalized_key = normalize_question_code(key)
    return responses.get(normalized_key, default)


def get_response_scale(responses: Dict[str, int]) -> Tuple[int, int]:
    """
    Détermine l'échelle des réponses (min, max).
    """
    if not responses:
        return VALID_RESPONSE_RANGE
    
    values = list(responses.values())
    return min(values), max(values)


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    # Test de normalisation
    test_responses = {"Q1": 5, "Q2": 4, "QUESTION_3": 3, "qst_04": 2}
    normalized = normalize_responses(test_responses)
    print(f"Normalized: {normalized}")
    
    # Test validation
    try:
        validate_response_values({"q1": 5, "q2": 4})
        print("Validation OK")
    except ValueError as e:
        print(f"Validation error: {e}")
    
    # Test bac codes
    for code in ["C", "c", "C01", "série C", "A2", "G3"]:
        normalized = normalize_bac_code(code)
        track = get_bac_track(code)
        print(f"Bac {code} → {normalized} ({track})")
    
    # Test statistiques
    stats = compute_response_stats(normalized)
    print(f"Stats: {stats}")
    
    # Test profil validation
    profile = {
        "domains": {"tech": 0.8, "business": 0.6},
        "skills": {"python": 0.9},
        "context": {"bac_code": "C", "user_type": "bachelier"}
    }
    is_valid, errors = validate_profile(profile)
    print(f"Profile valid: {is_valid}, errors: {errors}")