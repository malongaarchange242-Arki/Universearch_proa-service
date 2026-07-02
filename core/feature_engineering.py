"""
Feature Engineering Module - Version 3.0
Transforme les réponses du quiz en features pour le scoring PROA V2
Support des codes sémantiques, bac congolais, et scoring dimensionnel
"""

import logging
import os
import json
import statistics
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from supabase import Client

from core.utils import normalize_responses, normalize_response_code, get_bac_track

logger = logging.getLogger("orientation.feature_engineering")

# ==================================================
# GLOBAL CONFIG — Loaded at startup
# ==================================================
ORIENTATION_CONFIG: Dict[str, Any] = {}
SEMANTIC_MAPPING: Dict[str, Any] = {}
BAC_CONFIG: Dict[str, Any] = {}


def _normalize_response_score(response_value: Any, max_score: float, exponent: float = 1.0) -> float:
    """Safely normalize arbitrary numeric responses to [0, 1]."""
    try:
        numeric_value = float(response_value)
    except (TypeError, ValueError):
        return 0.0

    if max_score <= 0:
        return 0.0

    clipped_value = max(0.0, min(float(max_score), numeric_value))
    normalized = clipped_value / float(max_score)

    if exponent != 1.0 and normalized > 0.0:
        normalized = normalized ** exponent

    return max(0.0, min(1.0, normalized))


def _load_orientation_config() -> Dict[str, Any]:
    """Load configuration from orientation_config.json"""
    try:
        config_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "orientation_config.json",
        )
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info(f"✅ Loaded orientation_config.json: {len(config)} keys")
        return config
    except Exception as e:
        logger.error(f"❌ Failed to load orientation_config.json: {e}")
        return {"max_score": 5, "domains": {}, "skills": {}}  # Support 1-5 maintenant


def _normalize_semantic_mapping_keys(mapping: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize JSON semantic mapping keys so comparisons are stable."""
    if not isinstance(mapping, dict):
        return {}

    normalized_mapping = {}
    for raw_key, value in mapping.items():
        normalized_key = normalize_response_code(raw_key)
        normalized_mapping[normalized_key] = value
        if normalized_key != raw_key:
            logger.debug(f"Normalized mapping key: {repr(raw_key)} -> {repr(normalized_key)}")

    return normalized_mapping


def _load_semantic_mapping() -> Dict[str, Any]:
    """Load semantic question code to domain mapping"""
    try:
        mapping_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "semantic_question_mapping.json",
        )
        mapping_path = os.path.abspath(mapping_path)
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)

        semantic_to_domain = mapping.get("semantic_to_domain_mapping", {})
        normalized_mapping = _normalize_semantic_mapping_keys(semantic_to_domain)
        mapping["semantic_to_domain_mapping"] = normalized_mapping

        logger.info(
            f"✅ Loaded semantic_question_mapping.json from {mapping_path}: "
            f"{len(normalized_mapping)} mappings"
        )
        logger.debug("=== MAPPING KEYS ===")
        for key in normalized_mapping.keys():
            logger.debug(repr(key))
        return mapping
    except Exception as e:
        logger.warning(f"⚠️ Failed to load semantic_question_mapping.json: {e}")
        return {"semantic_to_domain_mapping": {}}


def _load_bac_config() -> Dict[str, Any]:
    """Load bac compatibility configuration"""
    try:
        config_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "bac_config.json",
        )
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logger.info(f"✅ Loaded bac_config.json: {len(config)} keys")
        return config
    except Exception as e:
        logger.warning(f"⚠️ Failed to load bac_config.json: {e}")
        return {}


# Load config at module startup
ORIENTATION_CONFIG = _load_orientation_config()
SEMANTIC_MAPPING = _load_semantic_mapping()
BAC_CONFIG = _load_bac_config()


# ==================================================
# IN-MEMORY CACHE pour éviter N+1 queries
# ==================================================
class MappingCache:
    """Cache simple in-memory avec expiration"""
    
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.timestamp: Optional[datetime] = None
    
    def get(self) -> Optional[Dict[str, List[Dict]]]:
        """Récupère le cache s'il est encore valide"""
        if not self.cache or not self.timestamp:
            return None
        
        elapsed = (datetime.utcnow() - self.timestamp).total_seconds()
        if elapsed > self.ttl_seconds:
            logger.info(f"Cache expiré (TTL: {self.ttl_seconds}s, elapsed: {elapsed:.0f}s)")
            self.cache.clear()
            self.timestamp = None
            return None
        
        return self.cache
    
    def set(self, mapping: Dict[str, List[Dict]]) -> None:
        """Stocke le mapping dans le cache"""
        self.cache = mapping
        self.timestamp = datetime.utcnow()
        logger.info(f"Cache mis à jour {len(mapping)} mappings")
    
    def clear(self) -> None:
        """Vide le cache"""
        self.cache.clear()
        self.timestamp = None
        logger.info("Cache vidé")


# Cache global (singleton)
_mapping_cache = MappingCache(ttl_seconds=3600)  # 1 heure


# ==================================================
# FONCTION: Convertir codes sémantiques en domaines
# ==================================================

def convert_semantic_to_domain_mapping(
    responses: Dict[str, float],
    response_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Convert semantic question codes (e.g., q_passion_tech) to domain mapping format.
    
    This handles the new dynamic questions system which uses semantic codes instead of q1-q24.
    """
    semantic_to_domain = SEMANTIC_MAPPING.get("semantic_to_domain_mapping", {})
    
    if not semantic_to_domain:
        logger.warning("❌ Semantic mapping is empty - questions may not be properly mapped to domains")
        return {}
    
    mapping = {}
    matched_questions = []
    unmatched_questions = []
    
    logger.info("=== RESPONSE KEYS ===")
    for key in responses.keys():
        logger.info(repr(key))

    logger.info("=== MAPPING KEYS ===")
    for key in semantic_to_domain.keys():
        logger.info(repr(key))

    for question_code in responses.keys():
        if question_code in semantic_to_domain:
            mapping[question_code] = semantic_to_domain[question_code]
            matched_questions.append(question_code)
        else:
            unmatched_questions.append(question_code)
    
    match_rate = len(matched_questions) / len(responses) * 100 if responses else 0
    logger.info(f"🔄 Semantic code conversion:")
    logger.info(f"   Matched: {len(matched_questions)}/{len(responses)} ({match_rate:.0f}%)")
    if unmatched_questions:
        logger.warning(f"   Unmatched codes: {unmatched_questions}")
    
    return mapping


def _normalize_semantic_answer(value: Any) -> str:
    """Normalize raw answer values from the frontend metadata."""
    if value is None:
        return ""
    return str(value).strip().lower()


def _normalize_semantic_entry_list(entries: Any) -> List[Dict[str, Any]]:
    """Coerce semantic mapping entries to a consistent [{domain, weight}] format."""
    normalized_entries: List[Dict[str, Any]] = []

    if isinstance(entries, str):
        normalized_entries.append({"domain": entries, "weight": 1.0})
        return normalized_entries

    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, str):
                normalized_entries.append({"domain": entry, "weight": 1.0})
            elif isinstance(entry, dict) and entry.get("domain"):
                normalized_entries.append({
                    "domain": str(entry["domain"]),
                    "weight": float(entry.get("weight", 1.0)),
                })

    return normalized_entries


def _compute_dimension_vector(
    domain_scores: Dict[str, float]
) -> Dict[str, float]:
    """
    Convertit les scores de domaines en vecteur dimensionnel (8 dimensions)
    pour le scoring V2.
    """
    # Mapping des domaines vers les dimensions
    domain_to_dimension = {
        # Tech
        "computer_science": "tech",
        "engineering": "tech",
        "technology": "tech",
        "programming": "tech",
        "software": "tech",
        # Business
        "business": "business",
        "finance": "business",
        "management": "business",
        "marketing": "business",
        "commerce": "business",
        # Social
        "social": "social",
        "communication": "social",
        "psychology": "social",
        "education": "social",
        # Creativity
        "design": "creativity",
        "arts": "creativity",
        "creative": "creativity",
        "innovation": "creativity",
        # Impact
        "environment": "impact",
        "health": "impact",
        "medicine": "impact",
        "sustainable": "impact",
        # Flexibility
        "adaptability": "flexibility",
        "multidisciplinary": "flexibility",
        # International
        "international": "international",
        "languages": "international",
        # Expertise
        "research": "expertise",
        "analysis": "expertise",
        "mathematics": "expertise",
        "science": "expertise",
    }
    
    dimension_scores = {
        "tech": 0.0,
        "business": 0.0,
        "social": 0.0,
        "creativity": 0.0,
        "impact": 0.0,
        "flexibility": 0.0,
        "international": 0.0,
        "expertise": 0.0
    }
    
    dimension_counts = {dim: 0 for dim in dimension_scores}
    
    for domain, score in domain_scores.items():
        dimension = domain_to_dimension.get(domain.lower())
        if dimension and dimension in dimension_scores:
            dimension_scores[dimension] += score
            dimension_counts[dimension] += 1
    
    # Moyenne par dimension
    for dim in dimension_scores:
        if dimension_counts[dim] > 0:
            dimension_scores[dim] /= dimension_counts[dim]
    
    # Normalisation
    max_score = max(dimension_scores.values()) if dimension_scores else 1.0
    if max_score > 0:
        dimension_scores = {k: v / max_score for k, v in dimension_scores.items()}
    
    return dimension_scores


# ==================================================
# FONCTION PRINCIPALE: Calculer les features (V3)
# ==================================================

def build_features(
    responses: Dict[str, float],
    orientation_type: str = "field",
    response_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    bac_code: Optional[str] = None,
    return_dimensions: bool = False
) -> Dict[str, Any]:
    """
    Version V3 - Construit les features avec support bac et dimensions.
    
    Args:
        responses: Réponses utilisateur
        orientation_type: Type d'orientation
        response_metadata: Métadonnées des réponses
        bac_code: Code bac congolais
        return_dimensions: Retourner aussi le vecteur dimensionnel
    
    Returns:
        Features dict + optionnellement dimension_vector
    """
    # Backward compatibility
    if not isinstance(orientation_type, str):
        logger.info("ℹ️ Legacy build_features signature detected")
        orientation_type = "field"
        response_metadata = None

    if not responses:
        logger.warning("❌ No responses provided - returning emergency default")
        default_features = {"domain_technical": 0.5, "domain_business": 0.4, "skill_logic": 0.5}
        if return_dimensions:
            return {"features": default_features, "dimension_vector": {}}
        return default_features
    
    # Normalize responses
    responses = normalize_responses(responses)
    logger.info(f"✅ Responses normalized: {len(responses)} entries")
    
    try:
        max_score = ORIENTATION_CONFIG.get("max_score", 5)  # Support 1-5
        domains_config = ORIENTATION_CONFIG.get("domains", {})
        skills_config = ORIENTATION_CONFIG.get("skills", {})
        
        features = {}
        
        # Détecter si codes sémantiques
        first_code = list(responses.keys())[0] if responses else ""
        expected_numeric_codes = {f"q{i}" for i in range(1, 25)}
        uses_semantic_codes = first_code.startswith("q") and first_code not in expected_numeric_codes
        
        if uses_semantic_codes:
            logger.info(f"🔄 Semantic codes detected: {first_code}")
            semantic_mapping = convert_semantic_to_domain_mapping(responses, response_metadata)
            if semantic_mapping:
                result = _compute_features_from_semantic_mapping_v2(
                    responses, semantic_mapping, max_score, orientation_type,
                    response_metadata, bac_code
                )
                if return_dimensions:
                    return result
                return result.get("features", {})
        
        # Mode numérique standard
        result = _compute_features_from_numeric_mapping_v2(
            responses, domains_config, skills_config, max_score,
            orientation_type, bac_code
        )
        
        if return_dimensions:
            return result
        
        return result.get("features", {})
        
    except Exception as exc:
        logger.error(f"❌ Exception in build_features: {str(exc)}")
        import traceback
        logger.error(traceback.format_exc())
        default = {"domain_technical": 0.5, "domain_business": 0.4, "skill_logic": 0.5}
        if return_dimensions:
            return {"features": default, "dimension_vector": {}}
        return default


def _compute_features_from_numeric_mapping_v2(
    responses: Dict[str, float],
    domains_config: Dict[str, List[str]],
    skills_config: Dict[str, List[str]],
    max_score: float,
    orientation_type: str,
    bac_code: Optional[str]
) -> Dict[str, Any]:
    """
    Version V2 du calcul depuis mapping numérique.
    """
    features = {}
    domain_scores_raw = {}
    
    # Calcul des domaines
    logger.info(f"\n🔍 COMPUTING DOMAINS V2:")
    for domain_name, question_ids in domains_config.items():
        matched_scores = []
        for q_id in question_ids:
            if q_id in responses:
                raw_score = responses[q_id]
                normalized = _normalize_response_score(raw_score, max_score, exponent=1.2)
                matched_scores.append(normalized)
        
        if matched_scores:
            avg = sum(matched_scores) / len(matched_scores)
            feature_key = f"domain_{domain_name}"
            features[feature_key] = round(avg, 4)
            domain_scores_raw[domain_name] = avg
            logger.info(f"   ✅ {domain_name:20s}: {avg:.4f} (n={len(matched_scores)})")
        else:
            features[f"domain_{domain_name}"] = 0.0
            domain_scores_raw[domain_name] = 0.0
    
    # Application du bonus bac
    if bac_code:
        bac_track = get_bac_track(bac_code)
        if bac_track:
            bac_bonus = BAC_CONFIG.get("domain_bonus", {}).get(bac_track, {})
            for domain_name in domain_scores_raw:
                bonus = bac_bonus.get(domain_name, 1.0)
                if bonus != 1.0:
                    old_score = domain_scores_raw[domain_name]
                    domain_scores_raw[domain_name] = min(1.0, old_score * bonus)
                    features[f"domain_{domain_name}"] = round(domain_scores_raw[domain_name], 4)
                    logger.info(f"   🎓 Bac {bac_code} bonus: {domain_name} {old_score:.3f} → {domain_scores_raw[domain_name]:.3f} (x{bonus})")
    
    # Calcul des compétences
    if orientation_type == "field" and skills_config:
        logger.info(f"\n🔍 COMPUTING SKILLS V2:")
        for skill_name, question_ids in skills_config.items():
            matched_scores = []
            for q_id in question_ids:
                if q_id in responses:
                    raw_score = responses[q_id]
                    normalized = _normalize_response_score(raw_score, max_score, exponent=1.2)
                    matched_scores.append(normalized)
            
            if matched_scores:
                avg = sum(matched_scores) / len(matched_scores)
                features[f"skill_{skill_name}"] = round(avg, 4)
                logger.info(f"   ✅ {skill_name:20s}: {avg:.4f}")
            else:
                features[f"skill_{skill_name}"] = 0.0
    
    # Calcul du vecteur dimensionnel
    dimension_vector = _compute_dimension_vector(domain_scores_raw)
    
    # Vérification des features nulles
    non_zero = {k: v for k, v in features.items() if v > 0}
    if not non_zero:
        logger.error(f"🔥 CRITICAL: ALL FEATURES ARE 0.0!")
        # Fallback
        if responses:
            max_resp = max(responses.values()) if responses else 2
            baseline = max_resp / max_score
            features = {
                "domain_technical": baseline,
                "domain_business": baseline * 0.8,
                "skill_logic": baseline,
            }
            dimension_vector = {"tech": baseline, "business": baseline * 0.7, "expertise": baseline}
    
    return {
        "features": features,
        "domain_scores": domain_scores_raw,
        "dimension_vector": dimension_vector
    }


def _compute_features_from_semantic_mapping_v2(
    responses: Dict[str, float],
    semantic_mapping: Dict[str, Any],
    max_score: float,
    orientation_type: str,
    response_metadata: Optional[Dict[str, Any]],
    bac_code: Optional[str]
) -> Dict[str, Any]:
    """
    Version V2 du calcul depuis mapping sémantique.
    """
    domain_scores: Dict[str, List[float]] = {}
    
    for question_code, semantic_definition in semantic_mapping.items():
        response_value = responses.get(question_code)
        if response_value is None:
            continue
        
        question_metadata = (response_metadata or {}).get(question_code, {})
        resolved_entries = _resolve_semantic_entries_for_response(
            question_code, response_value, semantic_definition,
            question_metadata, max_score
        )
        
        for entry in resolved_entries:
            domain_name = entry["domain"]
            domain_score = float(entry["score"])
            if domain_name not in domain_scores:
                domain_scores[domain_name] = []
            domain_scores[domain_name].append(domain_score)
    
    # Agréger
    features = {}
    domain_scores_raw = {}
    for domain_name, scores in domain_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            feature_key = f"domain_{domain_name}"
            features[feature_key] = round(avg, 4)
            domain_scores_raw[domain_name] = avg
            logger.info(f"✅ {domain_name:20s}: {avg:.4f} (n={len(scores)})")
    
    # Bonus bac
    if bac_code:
        bac_track = get_bac_track(bac_code)
        if bac_track:
            bac_bonus = BAC_CONFIG.get("domain_bonus", {}).get(bac_track, {})
            for domain_name in domain_scores_raw:
                bonus = bac_bonus.get(domain_name, 1.0)
                if bonus != 1.0:
                    old_score = domain_scores_raw[domain_name]
                    domain_scores_raw[domain_name] = min(1.0, old_score * bonus)
                    features[f"domain_{domain_name}"] = round(domain_scores_raw[domain_name], 4)
    
    # Vecteur dimensionnel
    dimension_vector = _compute_dimension_vector(domain_scores_raw)
    
    return {
        "features": features,
        "domain_scores": domain_scores_raw,
        "dimension_vector": dimension_vector
    }


def _resolve_semantic_entries_for_response(
    question_code: str,
    response_value: Any,
    semantic_definition: Any,
    response_metadata: Dict[str, Any],
    max_score: float,
) -> List[Dict[str, Any]]:
    """
    Resolve the domain contributions for one semantic question.
    """
    if semantic_definition is None:
        return []

    if isinstance(semantic_definition, list):
        intensity = _normalize_semantic_intensity(response_value, max_score)
        return [
            {
                "domain": entry["domain"],
                "score": round(intensity * float(entry.get("weight", 1.0)), 4),
            }
            for entry in _normalize_semantic_entry_list(semantic_definition)
        ]

    if not isinstance(semantic_definition, dict):
        return []

    raw_answer = _normalize_semantic_answer(response_metadata.get("raw_value"))
    selected_text = _normalize_semantic_answer(response_metadata.get("selected_text"))

    answer_mappings = semantic_definition.get("answer_mappings", {}) or {}
    normalized_answer_mappings = {
        _normalize_semantic_answer(key): value
        for key, value in answer_mappings.items()
    }

    intensity = _normalize_semantic_intensity(
        response_value, max_score,
        reverse_scale=bool(semantic_definition.get("reverse_scale", False))
    )

    if raw_answer and raw_answer in normalized_answer_mappings:
        selected_entries = _normalize_semantic_entry_list(normalized_answer_mappings[raw_answer])
        if not semantic_definition.get("use_numeric_intensity", False):
            intensity = 1.0
    elif selected_text and selected_text in normalized_answer_mappings:
        selected_entries = _normalize_semantic_entry_list(normalized_answer_mappings[selected_text])
        if not semantic_definition.get("use_numeric_intensity", False):
            intensity = 1.0
    else:
        score_mappings = semantic_definition.get("score_mappings", {}) or {}
        score_key = str(int(float(response_value))) if response_value else ""
        if score_key and score_key in score_mappings:
            selected_entries = _normalize_semantic_entry_list(score_mappings[score_key])
            if not semantic_definition.get("use_numeric_intensity", False):
                intensity = 1.0
        else:
            default_entries = semantic_definition.get("default_domains", semantic_definition.get("domains", []))
            selected_entries = _normalize_semantic_entry_list(default_entries)

    return [
        {
            "domain": entry["domain"],
            "score": round(intensity * float(entry.get("weight", 1.0)), 4),
        }
        for entry in selected_entries
    ]


def _normalize_semantic_intensity(
    response_value: Any,
    max_score: float,
    reverse_scale: bool = False,
) -> float:
    """Convert a numeric response to [0, 1] intensity, optionally reversed."""
    try:
        numeric_value = float(response_value)
    except (TypeError, ValueError):
        return 0.0

    if max_score <= 0:
        return 0.0

    numeric_value = max(1.0, min(max_score, numeric_value))
    if reverse_scale:
        numeric_value = (max_score + 1.0) - numeric_value

    return max(0.0, min(1.0, numeric_value / max_score))


# ==================================================
# FONCTIONS DE COMPATIBILITÉ (LEGACY)
# ==================================================

def build_features_db_driven(
    responses: Dict[str, float],
    supabase: Client,
    orientation_type: str = "field"
) -> Dict[str, float]:
    """
    Legacy function - use build_features() instead.
    """
    result = build_features(responses, orientation_type)
    if isinstance(result, dict) and "features" in result:
        return result["features"]
    return result


def get_question_domain_mapping(supabase: Client) -> Dict[str, List[Dict[str, Any]]]:
    """
    Legacy function - kept for backward compatibility.
    """
    return {}


def compute_recommended_fields(profile: Dict[str, Any], top_n: int = 5) -> Dict[str, Any]:
    """
    Compatibility wrapper to expose compute_recommended_fields from core.recommendations.

    This is kept here so that modules still importing the function from
    core.feature_engineering continue to work.
    """
    from core.recommendations import compute_recommended_fields as _compute_recommended_fields_impl
    return _compute_recommended_fields_impl(profile, top_n)


# ==================================================
# TESTS
# ==================================================

if __name__ == "__main__":
    # Test avec réponses simulées
    test_responses = {
        "q1": 5, "q2": 4, "q3": 5, "q4": 3, "q5": 4,
        "q6": 2, "q7": 3, "q8": 4, "q9": 5, "q10": 4,
        "q11": 3, "q12": 4, "q13": 5, "q14": 2, "q15": 3,
    }
    
    # Simuler config
    ORIENTATION_CONFIG = {
        "max_score": 5,
        "domains": {
            "computer_science": ["q1", "q2", "q3"],
            "business": ["q6", "q7", "q8"],
            "social": ["q11", "q12", "q13"]
        },
        "skills": {
            "problem_solving": ["q1", "q4"],
            "teamwork": ["q5", "q11"]
        }
    }
    
    print("\n" + "="*60)
    print("🧪 FEATURE ENGINEERING V3 TEST")
    print("="*60)
    
    result = build_features(
        test_responses,
        orientation_type="field",
        bac_code="C",
        return_dimensions=True
    )
    
    print(f"\n📊 Features: {result.get('features', {})}")
    print(f"\n🎯 Dimension vector: {result.get('dimension_vector', {})}")