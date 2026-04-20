# core/feature_engineering.py

import logging
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from supabase import Client

from core.utils import normalize_responses

logger = logging.getLogger("orientation.feature_engineering")

# ==================================================
# GLOBAL CONFIG — Loaded at startup
# ==================================================
ORIENTATION_CONFIG: Dict[str, Any] = {}
SEMANTIC_MAPPING: Dict[str, Any] = {}


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
        return {"max_score": 4, "domains": {}, "skills": {}}

def _load_semantic_mapping() -> Dict[str, Any]:
    """Load semantic question code to domain mapping"""
    try:
        mapping_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "semantic_question_mapping.json",
        )
        with open(mapping_path, "r", encoding="utf-8") as f:
            mapping = json.load(f)
        logger.info(f"✅ Loaded semantic_question_mapping.json: {len(mapping.get('semantic_to_domain_mapping', {}))} mappings")
        return mapping
    except Exception as e:
        logger.warning(f"⚠️ Failed to load semantic_question_mapping.json: {e}")
        logger.warning(f"   Will fall back to q1-q24 numeric format only")
        return {"semantic_to_domain_mapping": {}}

# Load config at module startup
ORIENTATION_CONFIG = _load_orientation_config()
SEMANTIC_MAPPING = _load_semantic_mapping()

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
    
    Args:
        responses: {"q_passion_tech": 3, "q_social_networks": 4, ...}
    
    Returns:
        Mapping: question_code -> semantic definition from config.
        Definitions may be legacy lists or richer per-answer objects.
    """
    semantic_to_domain = SEMANTIC_MAPPING.get("semantic_to_domain_mapping", {})
    
    if not semantic_to_domain:
        logger.warning("❌ Semantic mapping is empty - questions may not be properly mapped to domains")
        return {}
    
    # Build mapping from semantic definitions
    mapping = {}
    matched_questions = []
    unmatched_questions = []
    
    for question_code in responses.keys():
        if question_code in semantic_to_domain:
            mapping[question_code] = semantic_to_domain[question_code]
            matched_questions.append(question_code)
        else:
            unmatched_questions.append(question_code)
    
    match_rate = len(matched_questions) / len(responses) * 100 if responses else 0
    logger.info(f"🔄 Semantic code conversion:")
    logger.info(f"   Matched: {len(matched_questions)}/{len(responses)} ({match_rate:.0f}%)")
    if matched_questions:
        logger.info(f"   Examples: {matched_questions[:3]}")
    if unmatched_questions:
        logger.warning(f"   Unmatched codes: {unmatched_questions[:5]}")
    
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

    numeric_value = max(1.0, min(float(max_score), numeric_value))
    if reverse_scale:
        numeric_value = (float(max_score) + 1.0) - numeric_value

    return max(0.0, min(1.0, numeric_value / float(max_score)))


def _resolve_semantic_entries_for_response(
    question_code: str,
    response_value: Any,
    semantic_definition: Any,
    response_metadata: Optional[Dict[str, Any]],
    max_score: float,
) -> List[Dict[str, Any]]:
    """
    Resolve the domain contributions for one semantic question.

    Supported shapes:
    - legacy list: ["technical", "innovation"]
    - rich object with answer_mappings / score_mappings / default_domains
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
        logger.warning(f"⚠️ Unsupported semantic definition for {question_code}: {semantic_definition}")
        return []

    metadata = response_metadata or {}
    raw_answer = _normalize_semantic_answer(metadata.get("raw_value"))
    selected_text = _normalize_semantic_answer(metadata.get("selected_text"))

    answer_mappings = semantic_definition.get("answer_mappings", {}) or {}
    normalized_answer_mappings = {
        _normalize_semantic_answer(key): value
        for key, value in answer_mappings.items()
    }

    selected_entries: List[Dict[str, Any]] = []
    intensity = _normalize_semantic_intensity(
        response_value,
        max_score,
        reverse_scale=bool(semantic_definition.get("reverse_scale", False)),
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
        try:
            score_key = str(int(float(response_value)))
        except (TypeError, ValueError):
            score_key = ""

        if score_key and score_key in score_mappings:
            selected_entries = _normalize_semantic_entry_list(score_mappings[score_key])
            if not semantic_definition.get("use_numeric_intensity", False):
                intensity = 1.0
        else:
            default_entries = semantic_definition.get("default_domains", semantic_definition.get("domains", []))
            selected_entries = _normalize_semantic_entry_list(default_entries)

    resolved_entries: List[Dict[str, Any]] = []
    for entry in selected_entries:
        resolved_entries.append({
            "domain": entry["domain"],
            "score": round(intensity * float(entry.get("weight", 1.0)), 4),
        })

    return resolved_entries


def _compute_features_from_semantic_mapping(
    responses: Dict[str, float],
    semantic_mapping: Dict[str, Any],
    max_score: float,
    orientation_type: str = "field",
    response_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, float]:
    """
    Compute features from semantic question definitions.

    This supports both legacy semantic mappings and richer answer-aware mappings
    used by the dynamic quiz flow.
    """
    domain_scores: Dict[str, List[float]] = {}
    match_stats = {"matched": 0, "total": len(semantic_mapping), "missing": 0, "resolved": 0}

    for question_code, semantic_definition in semantic_mapping.items():
        response_value = responses.get(question_code)

        if response_value is None:
            match_stats["missing"] += 1
            logger.debug(f"   ⚠️ {question_code}: pas de réponse")
            continue

        match_stats["matched"] += 1

        question_metadata = (response_metadata or {}).get(question_code, {})
        resolved_entries = _resolve_semantic_entries_for_response(
            question_code=question_code,
            response_value=response_value,
            semantic_definition=semantic_definition,
            response_metadata=question_metadata,
            max_score=max_score,
        )

        if not resolved_entries:
            logger.debug(f"   ⚠️ {question_code}: aucune entrée sémantique résolue")
            continue

        match_stats["resolved"] += 1
        for entry in resolved_entries:
            domain_name = entry["domain"]
            domain_score = float(entry["score"])

            if domain_name not in domain_scores:
                domain_scores[domain_name] = []

            domain_scores[domain_name].append(domain_score)
            logger.debug(
                f"   {question_code} -> {domain_name}: "
                f"{domain_score:.3f} (meta={question_metadata})"
            )

    features: Dict[str, float] = {}
    for domain_name, scores in domain_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            feature_key = f"domain_{domain_name}"
            features[feature_key] = round(avg, 4)
            logger.info(f"✅ {domain_name:20s}: {avg:.4f} (n={len(scores)})")

    logger.info(f"\n{'='*70}")
    logger.info(f"📊 FEATURE ENGINEERING STATS:")
    logger.info(f"   Questions mappées: {match_stats['total']}")
    logger.info(f"   Réponses matched: {match_stats['matched']}")
    logger.info(f"   Réponses résolues: {match_stats['resolved']}")
    logger.info(f"   Réponses manquantes: {match_stats['missing']}")
    if match_stats["total"] > 0:
        logger.info(f"   Couverture: {(match_stats['matched']/match_stats['total']*100):.0f}%")
    logger.info(f"   Features calculées: {len(features)}")

    non_zero = {k: v for k, v in features.items() if v > 0}
    if non_zero:
        logger.info(f"   Features non-zéro: {len(non_zero)}")
    else:
        logger.error(f"   ❌ ALERTE: Aucune feature > 0!")

    logger.info(f"{'='*70}\n")

    if not features:
        logger.error("❌ Aucune feature calculée - returning empty")
        return {}

    return features


# ==================================================
# FONCTION: Récupérer les mappings question-domaine
# ==================================================

def get_question_domain_mapping(supabase: Client) -> Dict[str, List[Dict[str, Any]]]:
    """
    Récupère les mappings question → domaine depuis la base de données.
    
    Utilise un nested select Supabase pour éviter N+1:
    
    Structure attendue:
    {
        "q1": [
            {"domain": "logic", "weight": 1.0},
            {"domain": "technical", "weight": 0.5}  # Une question peut mapper à plusieurs domaines
        ],
        "q2": [{"domain": "technical", "weight": 1.0}]
    }
    
    Cache: 1 heure pour éviter saturations DB
    
    Fallback: JSON statique si table vide
    """
    try:
        # ✅ ÉTAPE 1: Vérifier le cache d'abord
        cached_mapping = _mapping_cache.get()
        if cached_mapping:
            logger.info(f"Cache HIT: {len(cached_mapping)} questions en mémoire")
            return cached_mapping
        
        logger.info("Cache MISS: Récupération depuis Supabase...")
        
        # ✅ ÉTAPE 2: Requête Supabase avec nested select (1 query!)
        # SELECT question_code, weight, domaines(name, id)
        result = supabase.table("question_domain_mapping").select(
            """
            question_code,
            weight,
            domaines:domain_id (
                id,
                name
            )
            """
        ).execute()
        
        # ✅ ÉTAPE 3: Parser la réponse
        rows = result.data if hasattr(result, 'data') else result.get('data', [])
        
        if not rows:
            logger.warning("❌ Aucun mapping trouvé dans question_domain_mapping")
            logger.warning("   → Utilisation du fallback JSON statique")
            return _load_json_fallback()
        
        # ✅ ÉTAPE 4: Construire la structure
        mapping: Dict[str, List[Dict[str, Any]]] = {}
        
        for row in rows:
            question_code = row.get('question_code', '').toLowerCase()
            weight = row.get('weight', 1.0)
            domain_obj = row.get('domaines')  # Nested object from Supabase
            
            if not question_code:
                logger.warning(f"Question code manquant dans row: {row}")
                continue
            
            if not domain_obj:
                logger.warning(f"Domaine manquant pour question {question_code}")
                continue
            
            # Extraire nom du domaine (peut être objet ou string selon config Supabase)
            domain_name = domain_obj.get('name', domain_obj) if isinstance(domain_obj, dict) else domain_obj
            domain_name = domain_name.lower()
            
            # Initialiser la liste pour cette question si pas existe
            if question_code not in mapping:
                mapping[question_code] = []
            
            # Ajouter le domaine avec son poids
            mapping[question_code].append({
                "domain": domain_name,
                "weight": float(weight)
            })
        
        logger.info(f"✅ Chargé {len(mapping)} questions depuis DB")
        logger.info(f"   Domains trouvés: {set(d['domain'] for q in mapping.values() for d in q)}")
        
        # ✅ ÉTAPE 5: Cacher le résultat
        if mapping:
            _mapping_cache.set(mapping)
        
        return mapping
    
    except Exception as e:
        logger.error(f"❌ Erreur lors du chargement question_domain_mapping: {e}")
        logger.error("   → Fallback au JSON statique")
        return _load_json_fallback()


# ==================================================
# FALLBACK: Charger depuis JSON statique
# ==================================================

def _load_json_fallback() -> Dict[str, List[Dict[str, Any]]]:
    """
    Fallback au JSON statique si table DB vide.
    
    Format:
    {
        "q1": [{"domain": "logic", "weight": 1.0}]
    }
    """
    try:
        config_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "orientation_config.json",
        )
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Convertir le format old (domains/skills) au new (question_code → domains)
        mapping: Dict[str, List[Dict[str, Any]]] = {}
        
        domains_config = config.get("domains", {})
        for domain_name, question_codes in domains_config.items():
            for q_code in question_codes:
                q_code_normalized = q_code.lower()
                
                if q_code_normalized not in mapping:
                    mapping[q_code_normalized] = []
                
                mapping[q_code_normalized].append({
                    "domain": domain_name.lower(),
                    "weight": 1.0
                })
        
        logger.warning(f"⚠️ FALLBACK JSON: {len(mapping)} questions depuis orientation_config.json")
        return mapping
    
    except Exception as e:
        logger.error(f"❌ Erreur lors du chargement du fallback JSON: {e}")
        return {}


# ==================================================
# FONCTION PRINCIPALE: Calculer les features
# ==================================================

def build_features_db_driven(
    responses: Dict[str, float],
    supabase: Client,
    orientation_type: str = "field"
) -> Dict[str, float]:
    """
    Construit les features (profil d'orientation) à partir des réponses au quiz.
    
    ✨ NOUVELLE VERSION: Piloté par la base de données!
    
    PROCESSUS:
    1. Récupère le mapping question → domaine depuis DB (ou cache)
    2. Normalise les réponses (Q1 → q1)
    3. Calcule un score pondéré par domaine
    4. Agrège en moyenne finale
    
    FORMULE DE CALCUL:
    - Pour chaque (question, domaine, weight):
        - score = (response_value / 4) * weight
    - Agrégation par domaine:
        - total = somme(scores_pondérés)
        - count = nombre de questions pour ce domaine
        - feature = total / count
    
    Args:
        responses: Réponses utilisateur {"q1": 3, "q2": 4, ...}
        supabase: Client Supabase pour requêtes DB
        orientation_type: Type d'orientation (field/institution) - pour compatibilité
    
    Returns:
        Features normalisées: {"domain_logic": 0.75, "domain_technical": 0.62, ...}
    """
    if not responses:
        logger.warning("❌ No responses provided - returning empty features")
        return {}
    
    try:
        # ✅ ÉTAPE 1: Normaliser les réponses (Q1 → q1)
        responses_normalized = normalize_responses(responses)
        logger.info(f"📥 Réponses reçues: {len(responses_normalized)}")
        logger.debug(f"   Keys (sample): {list(responses_normalized.keys())[:5]}")
        
        # ✅ ÉTAPE 2: Récupérer le mapping depuis DB (avec cache)
        mapping = get_question_domain_mapping(supabase)
        
        if not mapping:
            logger.error("❌ Aucun mapping question-domaine trouvé!")
            return {}
        
        logger.info(f"📋 Mapping chargé: {len(mapping)} questions")
        
        # ✅ ÉTAPE 3: Accumulateurs pour calcul pondéré
        domain_scores: Dict[str, List[float]] = {}  # domain → [scores]
        match_stats = {"matched": 0, "total_mapped": 0, "missing": 0}
        
        # ✅ ÉTAPE 4: Itérer sur le mapping et scorer
        for question_code, domain_list in mapping.items():
            match_stats["total_mapped"] += 1
            
            # Récupérer la réponse pour cette question
            response_value = responses_normalized.get(question_code)
            
            if response_value is None:
                match_stats["missing"] += 1
                logger.debug(f"   ⚠️ {question_code}: pas de réponse")
                continue
            
            match_stats["matched"] += 1
            
            # Scorer pour chaque domaine lié à cette question
            for domain_info in domain_list:
                domain_name = domain_info["domain"]
                weight = domain_info["weight"]
                
                # Formule: (value / 4) * weight
                # value ∈ [1, 4], donc (value / 4) ∈ [0.25, 1]
                weighted_score = _normalize_response_score(response_value, 4.0) * weight
                
                if domain_name not in domain_scores:
                    domain_scores[domain_name] = []
                
                domain_scores[domain_name].append(weighted_score)
                
                logger.debug(
                    f"   {question_code} → {domain_name}: "
                    f"{response_value}/4 × {weight} = {weighted_score:.3f}"
                )
        
        # ✅ ÉTAPE 5: Agréger par domaine (moyenne)
        features: Dict[str, float] = {}
        
        for domain_name, scores in domain_scores.items():
            if scores:
                avg = sum(scores) / len(scores)
                feature_key = f"domain_{domain_name}"
                features[feature_key] = round(avg, 4)
                logger.info(f"✅ {domain_name:20s}: {avg:.4f} (n={len(scores)})")
        
        # ✅ ÉTAPE 6: Logging statistiques
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 FEATURE ENGINEERING STATS:")
        logger.info(f"   Questions mappées: {match_stats['total_mapped']}")
        logger.info(f"   Réponses matched: {match_stats['matched']}")
        logger.info(f"   Réponses manquantes: {match_stats['missing']}")
        logger.info(f"   Couverture: {(match_stats['matched']/match_stats['total_mapped']*100):.0f}%")
        logger.info(f"   Features calculées: {len(features)}")
        
        non_zero = {k: v for k, v in features.items() if v > 0}
        if non_zero:
            logger.info(f"   Features non-zéro: {len(non_zero)}")
        else:
            logger.error(f"   ❌ ALERTE: Aucune feature > 0!")
        
        logger.info(f"{'='*70}\n")
        
        # ✅ ÉTAPE 7: Fallback si aucune feature
        if not features:
            logger.error("❌ Aucune feature calculée - returning empty")
            return {}
        
        return features
    
    except Exception as e:
        logger.error(f"❌ Exception dans build_features: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {}



def _compute_features_from_domain_list(
    responses: Dict[str, float],
    domain_mapping: Dict[str, List[Dict[str, Any]]],
    max_score: float,
    orientation_type: str = "field"
) -> Dict[str, float]:
    """
    Helper function to compute features from a domain list mapping.
    
    Used for both semantic code conversion and DB-driven mappings.
    
    Args:
        responses: Question responses
        domain_mapping: {question_code: [{domain: ..., weight: ...}]}
        max_score: Maximum question score (typically 4)
        orientation_type: "field" or "institution"
    
    Returns:
        Features dict: {domain_logic: 0.62, ...}
    """
    domain_scores: Dict[str, List[float]] = {}
    match_stats = {"matched": 0, "total": len(domain_mapping), "missing": 0}
    
    for question_code, domain_list in domain_mapping.items():
        response_value = responses.get(question_code)
        
        if response_value is None:
            match_stats["missing"] += 1
            logger.debug(f"   ⚠️ {question_code}: pas de réponse")
            continue
        
        match_stats["matched"] += 1
        
        # Score chaque domaine lié à cette question
        for domain_info in domain_list:
            domain_name = domain_info.get("domain", "unknown")
            weight = domain_info.get("weight", 1.0)
            
            weighted_score = _normalize_response_score(response_value, max_score) * weight
            
            if domain_name not in domain_scores:
                domain_scores[domain_name] = []
            
            domain_scores[domain_name].append(weighted_score)
            logger.debug(f"   {question_code} → {domain_name}: {response_value}/{max_score} × {weight} = {weighted_score:.3f}")
    
    # Agréger par domaine (moyenne)
    features: Dict[str, float] = {}
    
    for domain_name, scores in domain_scores.items():
        if scores:
            avg = sum(scores) / len(scores)
            feature_key = f"domain_{domain_name}"
            features[feature_key] = round(avg, 4)
            logger.info(f"✅ {domain_name:20s}: {avg:.4f} (n={len(scores)})")
    
    logger.info(f"\n{'='*70}")
    logger.info(f"📊 FEATURE ENGINEERING STATS:")
    logger.info(f"   Questions mappées: {match_stats['total']}")
    logger.info(f"   Réponses matched: {match_stats['matched']}")
    logger.info(f"   Réponses manquantes: {match_stats['missing']}")
    if match_stats['total'] > 0:
        logger.info(f"   Couverture: {(match_stats['matched']/match_stats['total']*100):.0f}%")
    logger.info(f"   Features calculées: {len(features)}")
    
    non_zero = {k: v for k, v in features.items() if v > 0}
    if non_zero:
        logger.info(f"   Features non-zéro: {len(non_zero)}")
    else:
        logger.error(f"   ❌ ALERTE: Aucune feature > 0!")
    
    logger.info(f"{'='*70}\n")
    
    if not features:
        logger.error("❌ Aucune feature calculée - returning empty")
        return {}
    
    return features


def build_features(
    responses: Dict[str, float],
    orientation_type: str = "field",
    response_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, float]:
    """
    🔥 ULTRA-SMART version: Adaptive mapping with fallback
    
    The brain of the system. Handles 3 scenarios:
    1. NEW: Semantic codes (q_passion_tech, q_social_networks, etc.) → maps using semantic mapping
    2. Perfect match: Config keys match response keys exactly (q1-q24)
    3. Partial match: Some config keys exist in responses  
    4. No match: Create smart fallback based on responses
    
    Maps quiz responses (1-4 scale) to domain/skill features (0-1)
    
    ✨ NOW WITH SEMANTIC CODE SUPPORT: Handles both q1-q24 and q_semantic_codes
    """
    # Backward compatibility: older callers still pass (responses, supabase, orientation_type)
    if not isinstance(orientation_type, str):
        logger.info("ℹ️ Legacy build_features signature detected; ignoring positional supabase argument")
        if isinstance(response_metadata, str):
            orientation_type = response_metadata
        else:
            orientation_type = "field"
        response_metadata = None

    if not responses:
        logger.warning("❌ No responses provided - returning emergency default")
        return {"domain_technical": 0.5, "domain_business": 0.4, "skill_logic": 0.5}
    
    # ✅ CRITICAL FIX: Normalize question codes (Q1 → q1)
    responses = normalize_responses(responses)
    logger.info(f"✅ Responses normalized: {len(responses)} entries")
    
    try:
        max_score = ORIENTATION_CONFIG.get("max_score", 4)
        domains_config = ORIENTATION_CONFIG.get("domains", {})
        skills_config = ORIENTATION_CONFIG.get("skills", {})
        
        features = {}
        
        # 🔄 STEP 0: Check if responses use semantic codes (new system) or numeric codes (old system)
        first_code = list(responses.keys())[0] if responses else ""
        # Updated detection: semantic codes are any 'q' codes that are not simple q1-q24
        expected_numeric_codes = {f"q{i}" for i in range(1, 25)}  # q1 to q24
        uses_semantic_codes = first_code.startswith("q") and first_code not in expected_numeric_codes
        
        if uses_semantic_codes:
            logger.info(f"🔄 SEMANTIC QUESTION CODES DETECTED: {first_code}")
            logger.info(f"   Using semantic_question_mapping.json for domain mapping")
            
            # Convert semantic codes to domain mapping format
            semantic_mapping = convert_semantic_to_domain_mapping(
                responses,
                response_metadata=response_metadata,
            )
            
            if semantic_mapping:
                logger.info(f"✅ Successfully converted {len(semantic_mapping)} semantic codes to domains")
                # Use semantic mapping instead of config
                return _compute_features_from_semantic_mapping(
                    responses,
                    semantic_mapping,
                    max_score,
                    orientation_type,
                    response_metadata=response_metadata,
                )
            else:
                logger.warning(f"⚠️ Semantic code conversion failed or empty - will try numeric format as fallback")
        
        # 📊 DETAILED DIAGNOSTIC (for numeric codes)
        logger.info(f"\n{'='*70}")
        logger.info(f"🔍 BUILD_FEATURES DIAGNOSTIC")
        logger.info(f"{'='*70}")
        logger.info(f"📥 RECEIVED ({len(responses)} responses):")
        logger.info(f"   Keys: {sorted(responses.keys())}")
        logger.info(f"   Sample: {dict(list(responses.items())[:5])}")
        logger.info(f"📋 CONFIG EXPECTS:")
        logger.info(f"   Domains: {list(domains_config.keys()) if domains_config else '❌ EMPTY'}")
        if domains_config:
            expected_qs = []
            for qs in domains_config.values():
                expected_qs.extend(qs)
            logger.info(f"   Question codes: {sorted(set(expected_qs))}")
        
        # ✅ STEP 1: Validate match quality
        response_keys_set = set(responses.keys())
        expected_qs_set = set()
        for qs in (domains_config.values() if domains_config else []):
            expected_qs_set.update(qs)
        
        matching_keys = response_keys_set & expected_qs_set
        match_quality = len(matching_keys) / len(expected_qs_set) if expected_qs_set else 0
        
        logger.info(f"\n📊 MATCH ANALYSIS:")
        logger.info(f"   Expected questions: {sorted(expected_qs_set)}")
        logger.info(f"   Received questions: {sorted(response_keys_set)}")
        logger.info(f"   Matching: {sorted(matching_keys)} ({len(matching_keys)}/{len(expected_qs_set)})")
        logger.info(f"   Match quality: {match_quality*100:.0f}%")
        
        # ✅ STEP 2: Compute domains (with detailed logging)
        logger.info(f"\n🔍 COMPUTING DOMAINS:")
        for domain_name, question_ids in domains_config.items():
            matched_scores = []
            matched_ids = []
            missing_ids = []
            
            for q_id in question_ids:
                if q_id in responses:
                    raw_score = responses[q_id]
                    normalized = _normalize_response_score(raw_score, max_score, exponent=1.5)
                    matched_scores.append(normalized)
                    matched_ids.append((q_id, normalized))
                else:
                    missing_ids.append(q_id)
            
            if matched_scores:
                avg = sum(matched_scores) / len(matched_scores)
                features[f"domain_{domain_name}"] = round(avg, 4)
                detail = f"{matched_ids}"
                if missing_ids:
                    detail += f" (missing: {missing_ids})"
                logger.info(f"   ✅ {domain_name:20s}: {avg:.2f} {detail}")
            else:
                features[f"domain_{domain_name}"] = 0.0
                logger.error(f"   ❌ {domain_name:20s}: 0.0 (NO MATCH for {question_ids})")
        
        # ✅ STEP 3: Compute skills (if field mode)
        if orientation_type == "field" and skills_config:
            logger.info(f"\n🔍 COMPUTING SKILLS:")
            for skill_name, question_ids in skills_config.items():
                matched_scores = []
                matched_ids = []
                
                for q_id in question_ids:
                    if q_id in responses:
                        raw_score = responses[q_id]
                        normalized = _normalize_response_score(raw_score, max_score, exponent=1.5)
                        matched_scores.append(normalized)
                        matched_ids.append((q_id, normalized))
                
                if matched_scores:
                    avg = sum(matched_scores) / len(matched_scores)
                    features[f"skill_{skill_name}"] = round(avg, 4)
                    logger.info(f"   ✅ {skill_name:20s}: {avg:.2f}")
                else:
                    features[f"skill_{skill_name}"] = 0.0
                    logger.error(f"   ❌ {skill_name:20s}: 0.0 (NO MATCH)")
        
        # 📊 FINAL RESULT
        non_zero = {k: v for k, v in features.items() if v > 0}
        zero_features = {k: v for k, v in features.items() if v == 0.0}
        
        logger.info(f"\n{'='*70}")
        logger.info(f"📊 RESULT:")
        logger.info(f"   Total features: {len(features)}")
        logger.info(f"   Non-zero: {len(non_zero)} → {non_zero}")
        logger.info(f"   Zero features: {list(zero_features.keys())}")
        
        # 🚨 CRITICAL: If all features are 0, we have a fundamental problem
        if not non_zero:
            logger.error(f"\n🔥 CRITICAL: ALL FEATURES ARE 0.0!")
            logger.error(f"   This means responses keys don't match config at all")
            logger.error(f"   Config expects: {sorted(expected_qs_set)}")
            logger.error(f"   But got: {sorted(response_keys_set)}")
            logger.error(f"   Root cause options:")
            logger.error(f"     1. Supabase question_codes are wrong (e.g., Q19-Q24 instead of q1-q24)")
            logger.error(f"     2. Quiz selected is not the student quiz (wrong quiz_id)")
            logger.error(f"     3. orientation_config.json is not synced with actual Supabase data")
            logger.error(f"\n   → Fix: Verify Supabase data matches orientation_config.json")
            
            # Emergency fallback using actual response data
            if responses:
                max_resp_value = max(responses.values()) if responses else 2
                baseline = max_resp_value / max_score
                logger.warning(f"   📌 Emergency fallback: using max response {max_resp_value}/{max_score} = {baseline:.2f}")
                features = {
                    "domain_technical": baseline,
                    "domain_business": baseline * 0.8,
                    "skill_logic": baseline,
                    "skill_creativity": baseline * 0.8,
                }
        
        logger.info(f"{'='*70}\n")
        return features
        
    except Exception as exc:
        logger.error(f"❌ EXCEPTION in build_features: {str(exc)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"domain_technical": 0.5, "domain_business": 0.4, "skill_logic": 0.5}
