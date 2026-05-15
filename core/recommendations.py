"""
Feature Engineering - Moteur de recommandations d'orientation
Version 2.0 - Améliorée avec scoring vectoriel dimensionnel et cache intelligent
"""

import json
import math
import os
import unicodedata
from collections import Counter
from typing import Dict, List, Any, Optional, Tuple
from functools import lru_cache
from datetime import datetime, timedelta
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY


# ============================================================================
# CONSTANTES ET CONFIGURATION
# ============================================================================

# Cache TTL en secondes
CACHE_TTL_SECONDS = 3600  # 1 heure
_FILIERES_CACHE: Optional[tuple] = None  # (timestamp, data)
_CACHE_TIMESTAMP: Optional[datetime] = None


# Dimensions du scoring vectoriel
DIMENSIONS = [
    "tech",
    "business",
    "social",
    "creativity",
    "impact",
    "flexibility",
    "international",
    "expertise",
]

# Poids pour le scoring hybride
PROFILE_SCORE_WEIGHT = 0.7
BAC_SCORE_WEIGHT = 0.3
MIN_SCORE_THRESHOLD = 0.12


# ============================================================================
# FONCTIONS DE NORMALISATION
# ============================================================================

def _normalize_match_text(value: str) -> str:
    """Normalize text for accent-insensitive matching across PROA/PORA."""
    if not value:
        return ""

    normalized = str(value).lower().strip()
    normalized = normalized.replace("&", " et ")
    normalized = normalized.replace("/", " ")
    normalized = normalized.replace("_", " ")
    normalized = normalized.replace("-", " ")
    normalized = unicodedata.normalize("NFKD", normalized)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split())


def _normalize_profile_keyword(key: str) -> str:
    """Normalise les keywords du profil."""
    normalized = str(key).lower().strip()
    if normalized.startswith("domain_"):
        normalized = normalized[len("domain_"):]
    elif normalized.startswith("skill_"):
        normalized = normalized[len("skill_"):]
    return _normalize_match_text(normalized)


def _normalize_vector(vector: Dict[str, float]) -> Dict[str, float]:
    """Normalise un vecteur dimensionnel pour que la somme = 1."""
    total = sum(vector.values())
    if total <= 0:
        if not vector:
            return {}
        return {dim: 1.0 / len(vector) for dim in vector}
    return {dim: value / total for dim, value in vector.items()}


# ============================================================================
# CLUSTERS ET MAPPINGS (optimisés)
# ============================================================================

FIELD_CLUSTERS = {
    "informatique": [
        "génie logiciel", "développement informatique", "informatique", "informatique de gestion",
        "intelligence artificielle", "data science", "big data", "analyse de données",
        "cybersécurité", "sécurité informatique", "réseaux informatiques", "systèmes d'information",
        "développement web", "développement mobile", "programmation", "bases de données",
        "machine learning", "deep learning", "cloud computing", "devops"
    ],
    "engineering": [
        "génie électrique", "électronique", "électrotechnique", "automatique",
        "robotique", "systèmes embarqués", "télécommunications", "instrumentation",
        "génie civil", "construction", "architecture", "urbanisme", "bâtiment",
        "génie mécanique", "mécatronique", "maintenance industrielle"
    ],
    "business": [
        "comptabilité", "finance", "gestion d'entreprise", "marketing", "commerce international",
        "management", "administration des affaires", "banque", "assurance", "audit",
        "ressources humaines", "gestion des ressources humaines", "entrepreneuriat",
        "commerce", "économie", "gestion financière", "logistique", "supply chain"
    ],
    "droit": [
        "droit", "juridique", "justice", "pénal", "public", "privé", "sciences politiques",
        "relations internationales", "diplomatie", "gouvernance", "affaires"
    ],
    "social": [
        "communication", "sociologie", "psychologie", "éducation", "enseignement",
        "sciences humaines", "anthropologie", "histoire", "géographie", "philosophie"
    ],
    "santé": [
        "médecine", "pharmacie", "dentaire", "sciences infirmières", "kinésithérapie",
        "sciences médicales", "biotechnologie médicale", "laboratoire", "imagerie médicale"
    ],
    "sciences": [
        "mathématiques", "physique", "chimie", "biologie", "biochimie",
        "génie chimique", "génie biologique", "recherche scientifique", "statistiques"
    ],
    "geoscience": [
        "géologie", "géophysique", "hydrogéologie", "mines", "environnement",
        "cartographie", "topographie", "géotechnique", "hydrologie", "océanographie"
    ],
    "arts_design": [
        "design graphique", "design industriel", "arts plastiques", "communication visuelle",
        "architecture d'intérieur", "mode", "photographie", "design numérique", "multimédia"
    ],
    "agriculture": [
        "agronomie", "agriculture", "agroalimentaire", "génie agricole", "foresterie",
        "pêche", "aquaculture", "viticulture", "œnologie"
    ],
}

FIELD_CLUSTER_SYNONYMS = {
    "informatique": [
        "informatique", "programmation", "logiciel", "code", "developer", "développement",
        "data", "machine learning", "ia", "intelligence artificielle", "cybersécurité",
        "sécurité informatique", "réseaux", "base de données", "cloud", "devops"
    ],
    "engineering": [
        "génie", "ingénierie", "engineering", "électrique", "électronique", "électrotechnique",
        "robotique", "automatique", "mécanique", "civil", "construction", "industrie"
    ],
    "business": [
        "business", "marketing", "commerce", "finance", "gestion", "management",
        "entrepreneuriat", "banque", "assurance", "audit", "comptabilité", "logistique"
    ],
    "droit": [
        "droit", "juridique", "justice", "avocat", "notaire", "magistrat", "loi", "réglementation"
    ],
    "social": [
        "social", "communication", "relationnel", "éducation", "enseignement", "psychologie",
        "sociologie", "humanitaire", "service", "communauté"
    ],
    "santé": [
        "santé", "médical", "médecine", "pharmacie", "infirmier", "clinique", "hospitalier"
    ],
    "sciences": [
        "science", "recherche", "mathématique", "physique", "chimie", "biologie", "laboratoire"
    ],
    "geoscience": [
        "géologie", "géophysique", "mine", "environnement", "terre", "ressources naturelles"
    ],
    "arts_design": [
        "design", "art", "création", "graphisme", "architecture", "mode", "photographie"
    ],
    "agriculture": [
        "agriculture", "agronomie", "agroalimentaire", "forêt", "pêche", "viticulture"
    ],
}

CLUSTER_KEYWORDS = {
    "informatique": [
        "informatique", "logiciel", "développement", "programmation", "data", "ia",
        "cyber", "réseau", "telecom", "système", "numérique", "web", "mobile", "cloud"
    ],
    "engineering": [
        "génie", "électrique", "électronique", "mécanique", "civil", "btp", "construction",
        "robotique", "automatisme", "industrie", "production", "maintenance"
    ],
    "business": [
        "business", "gestion", "finance", "marketing", "commerce", "management",
        "comptabilité", "audit", "logistique", "rh", "ressources humaines", "économie"
    ],
    "droit": [
        "droit", "juridique", "justice", "pénal", "affaires", "international", "public"
    ],
    "social": [
        "social", "communication", "éducation", "enseignement", "psychologie", "sociologie"
    ],
    "santé": [
        "santé", "médecine", "pharmacie", "infirmier", "clinique", "hospitalier", "soin"
    ],
    "sciences": [
        "science", "mathématiques", "physique", "chimie", "biologie", "recherche"
    ],
    "geoscience": [
        "géologie", "mine", "environnement", "terre", "ressources", "cartographie"
    ],
    "arts_design": [
        "design", "art", "création", "graphisme", "architecture", "mode", "photographie"
    ],
    "agriculture": [
        "agriculture", "agronomie", "agro", "forêt", "pêche", "viticulture"
    ],
}

# ============================================================================
# DIMENSIONS ET VECTEURS
# ============================================================================

PROFILE_DIMENSION_SEEDS = {
    "tech": [
        "informatique", "programmation", "logiciel", "software", "développement",
        "ia", "intelligence artificielle", "machine learning", "data", "données",
        "cybersécurité", "cloud", "web", "mobile", "algorithmique", "devops", "réseaux"
    ],
    "business": [
        "business", "marketing", "commerce", "finance", "gestion", "entrepreneuriat",
        "management", "banque", "assurance", "économie", "audit", "comptabilité", "vente"
    ],
    "social": [
        "communication", "relation", "social", "collaboration", "équipe", "communauté",
        "relationnel", "dialogue", "échange", "humanitaire", "psychologie", "service"
    ],
    "creativity": [
        "créativité", "créatif", "design", "artistique", "innovation", "architecture",
        "mode", "photographie", "graphique", "arts", "expression", "multimédia"
    ],
    "impact": [
        "impact", "durable", "environnement", "écologie", "santé", "communautaire",
        "solidarité", "biotechnologie", "médecine", "droit", "politique", "responsabilité"
    ],
    "flexibility": [
        "flexibilité", "polyvalent", "adaptabilité", "autonomie", "mobilité",
        "hybride", "polyvalence", "agile", "multidisciplinaire", "variété"
    ],
    "international": [
        "international", "global", "étranger", "langue", "anglais", "multiculturel",
        "diplomatie", "relations internationales", "tourisme", "aéronautique"
    ],
    "expertise": [
        "recherche", "scientifique", "spécialisation", "théorie", "méthodologie",
        "rigueur", "mathématiques", "physique", "chimie", "analyse", "doctorat", "master"
    ],
}

FIELD_DIMENSION_SEEDS = {
    "tech": [
        "digital", "numérique", "informatique", "logiciel", "software", "ia", "ia",
        "intelligence artificielle", "machine learning", "data", "cybersécurité",
        "cloud", "réseaux", "programmation", "web", "mobile", "robotique", "automatisation"
    ],
    "business": [
        "business", "marketing", "commerce", "finance", "gestion", "entrepreneuriat",
        "management", "banque", "assurance", "économie", "audit", "comptabilité",
        "stratégie", "vente", "logistique", "e-commerce"
    ],
    "social": [
        "communication", "relation", "relationnel", "social", "collaboration", "équipe",
        "psychologie", "service", "droit", "éthique", "ressources humaines", "humanitaire"
    ],
    "creativity": [
        "créativité", "créatif", "design", "arts", "architecture", "mode", "photographie",
        "graphique", "innovation", "multimédia", "storytelling", "expression"
    ],
    "impact": [
        "durable", "écologie", "environnement", "climat", "santé", "biotechnologie",
        "médecine", "solidarité", "responsabilité", "développement durable"
    ],
    "flexibility": [
        "flexibilité", "polyvalent", "adaptabilité", "autonomie", "mobilité", "hybride",
        "agile", "polyvalence", "variété", "liberté"
    ],
    "international": [
        "international", "global", "étranger", "langue", "anglais", "multiculturel",
        "diplomatie", "géopolitique", "voyage", "relations internationales"
    ],
    "expertise": [
        "recherche", "scientifique", "spécialisation", "théorie", "méthodologie", "rigueur",
        "mathématiques", "physique", "chimie", "analyse", "doctorat", "master", "certification"
    ],
}

PROFILE_EXACT_DIMENSION_WEIGHTS = {
    "computer science": {"tech": 1.0, "expertise": 0.25},
    "computer_science": {"tech": 1.0, "expertise": 0.25},
    "engineering": {"tech": 0.55, "expertise": 0.35, "impact": 0.1},
    "business": {"business": 1.0},
    "finance": {"business": 0.75, "expertise": 0.25},
    "management": {"business": 0.7, "social": 0.15},
    "marketing": {"business": 0.6, "creativity": 0.3},
    "communication": {"social": 0.7, "creativity": 0.15},
    "design": {"creativity": 0.8, "impact": 0.15},
    "data science": {"tech": 0.65, "expertise": 0.55, "business": 0.2},
    "cybersécurité": {"tech": 0.8, "expertise": 0.55},
    "droit": {"social": 0.55, "expertise": 0.55, "impact": 0.25},
}

# ============================================================================
# BAC CONGOLAIS - COMPATIBILITÉ
# ============================================================================

BAC_TRACK_COMPATIBILITY = {
    "technical": {
        "clusters": {
            "engineering": 1.0, "informatique": 0.72, "sciences": 0.62,
            "geoscience": 0.78, "agriculture": 0.52, "sante": 0.28,
            "business": 0.18, "droit": 0.05, "social": 0.12, "arts_design": 0.1
        },
    },
    "science": {
        "clusters": {
            "informatique": 0.88, "engineering": 0.9, "sciences": 1.0,
            "geoscience": 0.86, "agriculture": 0.6, "sante": 0.92,
            "business": 0.18, "droit": 0.12, "social": 0.18, "arts_design": 0.12
        },
    },
    "informatics": {
        "clusters": {
            "informatique": 1.0, "engineering": 0.56, "sciences": 0.48,
            "geoscience": 0.22, "agriculture": 0.18, "sante": 0.18,
            "business": 0.16, "droit": 0.08, "social": 0.1, "arts_design": 0.12
        },
    },
    "business": {
        "clusters": {
            "business": 1.0, "droit": 0.4, "social": 0.58, "informatique": 0.22,
            "engineering": 0.12, "sciences": 0.14, "geoscience": 0.08,
            "agriculture": 0.14, "sante": 0.1, "arts_design": 0.26
        },
    },
    "humanities": {
        "clusters": {
            "droit": 1.0, "social": 0.94, "arts_design": 0.42, "business": 0.34,
            "informatique": 0.12, "engineering": 0.08, "sciences": 0.12
        },
    },
    "vocational": {
        "clusters": {
            "engineering": 0.96, "geoscience": 0.62, "agriculture": 0.46,
            "informatique": 0.34, "sciences": 0.18, "sante": 0.14, "business": 0.08
        },
    },
}

BAC_TRACK_KEYWORD_HINTS = {
    "humanities": {"droit": 1.0, "communication": 0.94, "sciences humaines": 0.96},
    "science": {"math": 1.0, "informatique": 0.86, "data": 0.84, "medecine": 0.94},
    "technical": {"genie electrique": 1.0, "mecanique": 0.95, "maintenance": 0.9},
    "informatics": {"informatique": 1.0, "reseau": 0.98, "data": 0.92, "cyber": 0.92},
    "business": {"comptabilite": 1.0, "gestion": 0.96, "management": 0.92, "finance": 0.88},
    "vocational": {"maintenance": 1.0, "btp": 1.0, "construction": 0.96},
}

# ============================================================================
# FONCTIONS DE CHARGEMENT DES DONNÉES AVEC CACHE
# ============================================================================

def _load_fields_metadata() -> Dict[str, Dict[str, Any]]:
    """Charge les métadonnées des filières depuis le fichier JSON."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "fields_mapping.json")
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}

    metadata: Dict[str, Dict[str, Any]] = {}
    for row in payload.get("fields", []):
        field_name = row.get("field", "")
        normalized_name = _normalize_match_text(field_name)
        if not normalized_name:
            continue

        domains = []
        for domain in row.get("domains", []):
            if isinstance(domain, dict):
                domains.append(_normalize_match_text(domain.get("name", "")))
            else:
                domains.append(_normalize_match_text(domain))

        metadata[normalized_name] = {
            "field_name": field_name,
            "category": _normalize_match_text(row.get("category", "")),
            "domains": [domain for domain in domains if domain],
        }

    return metadata


FIELDS_METADATA = _load_fields_metadata()


def _build_local_filiere_fallback() -> List[Dict[str, Any]]:
    """Fallback catalog built from local fields_mapping metadata."""
    fallback: List[Dict[str, Any]] = []
    for normalized_name, metadata in FIELDS_METADATA.items():
        field_name = metadata.get("field_name")
        if not field_name:
            continue
        fallback.append({
            "id": f"local::{normalized_name}",
            "nom": field_name,
            "description": f"category: {metadata.get('category', '')}" if metadata.get('category') else "",
            "source": "fallback",
        })
    return fallback


def _fetch_filieres_from_db() -> List[Dict[str, Any]]:
    """
    Récupère les filières depuis Supabase avec cache intelligent.
    """
    global _FILIERES_CACHE, _CACHE_TIMESTAMP
    
    # Vérifier le cache
    if _FILIERES_CACHE is not None and _CACHE_TIMESTAMP is not None:
        cache_age = (datetime.utcnow() - _CACHE_TIMESTAMP).total_seconds()
        if cache_age < CACHE_TTL_SECONDS:
            print(f"[PROA] Using cached filieres: {len(_FILIERES_CACHE)} items")
            return _FILIERES_CACHE
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/filieres"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        params = {"select": "id,nom,description", "limit": "9999"}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        _FILIERES_CACHE = response.json()
        _CACHE_TIMESTAMP = datetime.utcnow()
        print(f"[PROA] Cached {len(_FILIERES_CACHE)} filieres from Supabase")
        return _FILIERES_CACHE
        
    except Exception as e:
        print(f"[PROA] Error fetching filieres: {e}")
        fallback = _build_local_filiere_fallback()
        if fallback:
            print(f"[PROA] Using local filiere fallback: {len(fallback)} items")
        return fallback


# ============================================================================
# FONCTIONS DE VECTEURS ET SCORING
# ============================================================================

def _apply_dimension_weights(raw_vector: Dict[str, float], weights: Dict[str, float], scale: float = 1.0) -> None:
    """Applique des poids aux dimensions du vecteur."""
    for dim, weight in weights.items():
        if dim in raw_vector:
            raw_vector[dim] += weight * scale


def _extract_keywords_from_profile(profile: Dict[str, Any]) -> List[tuple[str, float]]:
    """Extrait les keywords du profil avec leurs scores."""
    keywords = []

    domains = profile.get("domains", {})
    if isinstance(domains, dict):
        for key, value in domains.items():
            normalized_key = _normalize_profile_keyword(key)
            if value > 0:
                keywords.append((normalized_key, float(value)))

    skills = profile.get("skills", {})
    if isinstance(skills, dict):
        for key, value in skills.items():
            normalized_key = _normalize_profile_keyword(key)
            if value > 0:
                keywords.append((normalized_key, float(value)))

    # Déduplication
    deduped: dict[str, float] = {}
    for k, v in keywords:
        if v > 0.0:
            deduped[k] = max(deduped.get(k, 0.0), v)
    
    return list(deduped.items())


def _build_profile_vector(profile: Dict[str, Any]) -> Dict[str, float]:
    """Construit le vecteur dimensionnel du profil."""
    raw_vector = {dim: 0.0 for dim in DIMENSIONS}
    inputs: List[tuple[str, float]] = []

    for source in ["domains", "skills"]:
        values = profile.get(source, {}) or {}
        if isinstance(values, dict):
            for key, value in values.items():
                normalized = _normalize_profile_keyword(key)
                if value > 0:
                    inputs.append((normalized, float(value)))

    for term, value in inputs:
        normalized_term = _normalize_match_text(term)

        # Poids exacts
        exact_weights = PROFILE_EXACT_DIMENSION_WEIGHTS.get(normalized_term)
        if exact_weights:
            _apply_dimension_weights(raw_vector, exact_weights, value)

        # Poids par dimension
        for dim, seeds in PROFILE_DIMENSION_SEEDS.items():
            if any(_normalize_match_text(seed) in normalized_term for seed in seeds):
                raw_vector[dim] += value

    return _normalize_vector(raw_vector)


def _build_field_vector(filiere: Dict[str, Any]) -> Dict[str, float]:
    """Construit le vecteur dimensionnel d'une filière."""
    raw_vector = {dim: 0.0 for dim in DIMENSIONS}
    filiere_name = filiere.get("nom", "")
    text = _normalize_match_text(f"{filiere_name} {filiere.get('description', '')}")

    # Poids par dimension
    for dim, seeds in FIELD_DIMENSION_SEEDS.items():
        for seed in seeds:
            if _normalize_match_text(seed) in text:
                raw_vector[dim] += 1.0

    # Fallback basé sur le cluster
    if sum(raw_vector.values()) <= 0:
        cluster = _get_filiere_cluster(filiere_name)
        cluster_fallback = {
            "informatique": {"tech": 1.0, "expertise": 0.4},
            "engineering": {"tech": 0.7, "expertise": 0.35, "impact": 0.1},
            "business": {"business": 1.0, "international": 0.3},
            "droit": {"social": 0.7, "expertise": 0.5, "impact": 0.2},
            "social": {"social": 1.0, "impact": 0.3},
            "arts_design": {"creativity": 0.8, "flexibility": 0.25},
            "sciences": {"expertise": 0.8, "tech": 0.2},
            "geoscience": {"impact": 0.55, "expertise": 0.35},
            "agriculture": {"impact": 0.55, "expertise": 0.35},
            "sante": {"impact": 1.0, "expertise": 0.3},
        }
        fallback = cluster_fallback.get(cluster, {"flexibility": 0.6, "expertise": 0.4})
        for dim, value in fallback.items():
            raw_vector[dim] += value

    return _normalize_vector(raw_vector)


def _vector_dot(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Produit scalaire entre deux vecteurs."""
    return sum(a.get(dim, 0.0) * b.get(dim, 0.0) for dim in a)


def _euclidean_distance(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Distance euclidienne entre deux vecteurs."""
    return math.sqrt(sum((a.get(dim, 0.0) - b.get(dim, 0.0)) ** 2 for dim in DIMENSIONS))


def _compute_dimension_contributions(profile_vector: Dict[str, float], field_vector: Dict[str, float]) -> Dict[str, float]:
    """Calcule les contributions de chaque dimension."""
    return {
        dim: profile_vector.get(dim, 0.0) * field_vector.get(dim, 0.0)
        for dim in DIMENSIONS
    }


# ============================================================================
# FONCTIONS DE CLUSTER
# ============================================================================

@lru_cache(maxsize=1000)
def _get_filiere_cluster(filiere_name: str) -> str:
    """Détermine le cluster d'une filière avec cache."""
    filiere_lower = _normalize_match_text(filiere_name)
    
    # Recherche dans les clusters
    for cluster_name, filieres in FIELD_CLUSTERS.items():
        for cluster_filiere in filieres:
            if cluster_filiere in filiere_lower or filiere_lower in cluster_filiere:
                return cluster_name
    
    # Recherche par synonymes
    for cluster_name, synonyms in FIELD_CLUSTER_SYNONYMS.items():
        if any(syn in filiere_lower for syn in synonyms):
            return cluster_name
    
    # Recherche par mots-clés
    for cluster_name, keywords in CLUSTER_KEYWORDS.items():
        if any(keyword in filiere_lower for keyword in keywords):
            return cluster_name
    
    return "unknown"


def _detect_dominant_cluster(keywords: List[tuple[str, float]]) -> Optional[str]:
    """Détecte le cluster dominant du profil."""
    cluster_scores: Dict[str, float] = {}

    for keyword, score in keywords:
        keyword_lower = _normalize_match_text(keyword)
        
        for cluster_name, filieres in FIELD_CLUSTERS.items():
            for cluster_filiere in filieres:
                if cluster_filiere in keyword_lower or keyword_lower in cluster_filiere:
                    cluster_scores[cluster_name] = cluster_scores.get(cluster_name, 0) + score
                    break
            
            synonyms = FIELD_CLUSTER_SYNONYMS.get(cluster_name, [])
            if any(syn in keyword_lower for syn in synonyms):
                weight = 0.9
                cluster_scores[cluster_name] = cluster_scores.get(cluster_name, 0) + score * weight

    if not cluster_scores:
        return None

    sorted_scores = sorted(cluster_scores.items(), key=lambda x: x[1], reverse=True)
    top_cluster, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    ratio = top_score / max(second_score, 0.0001)

    if top_score < 0.5 or (len(sorted_scores) > 1 and ratio < 1.3):
        return None

    return top_cluster


# ============================================================================
# FONCTIONS BAC CONGOLAIS
# ============================================================================

def _extract_bac_type(profile: Dict[str, Any]) -> Optional[str]:
    """Extrait le type de bac du profil."""
    if not isinstance(profile, dict):
        return None

    context = profile.get("context") or {}
    if isinstance(context, dict):
        for key in ("bac_type", "bac", "serie_bac", "series_bac"):
            value = context.get(key)
            if value:
                return str(value)

    for key in ("bac_type", "bac", "serie_bac", "series_bac"):
        value = profile.get(key)
        if value:
            return str(value)

    return None


def _classify_bac_track(bac_type: Optional[str]) -> Optional[str]:
    """Classifie le bac en track."""
    if not bac_type:
        return None
    
    code = _normalize_match_text(bac_type)
    
    tracks = {
        "humanities": {"a", "a1", "a2", "a3", "l", "lettres", "litteraire", "humanites"},
        "science": {"b", "c", "d", "s", "scientifique", "science", "svt"},
        "technical": {"e", "f", "ti", "technique", "industrie"},
        "informatics": {"h", "informatique", "reseaux", "telecom"},
        "business": {"g", "bg", "stg", "stmg", "economie", "commercial", "gestion"},
        "vocational": {"p", "pro", "professionnel"},
    }
    
    for track, aliases in tracks.items():
        if code in aliases or any(code.startswith(a) for a in aliases if len(a) <= 2):
            return track
    
    return None


def _compute_bac_compatibility_score(bac_type: Optional[str], filiere: Dict[str, Any]) -> Optional[float]:
    """Calcule le score de compatibilité bac/filière."""
    track = _classify_bac_track(bac_type)
    if not track:
        return None

    rules = BAC_TRACK_COMPATIBILITY.get(track, {})
    cluster = _get_filiere_cluster(filiere.get("nom", ""))
    filiere_text = _normalize_match_text(f"{filiere.get('nom', '')} {filiere.get('description', '')}")
    
    signals: List[float] = []
    
    # Score par cluster
    cluster_score = rules.get("clusters", {}).get(cluster, 0.0)
    if cluster_score > 0:
        signals.append(cluster_score)
    
    # Score par mots-clés
    keyword_hints = BAC_TRACK_KEYWORD_HINTS.get(track, {})
    for keyword, weight in keyword_hints.items():
        if keyword in filiere_text:
            signals.append(weight)
    
    if not signals:
        return None
    
    return min(1.0, max(0.0, sum(signals) / len(signals)))


# ============================================================================
# FONCTIONS DE RANKING ET SÉLECTION
# ============================================================================

def _build_cluster_frequency_weights(cluster_counts: Dict[str, int], total: int) -> Dict[str, float]:
    """Calcule les poids pour équilibrer les clusters."""
    if total <= 0:
        return {}
    mean_share = 1.0 / max(1, len(cluster_counts))
    weights: Dict[str, float] = {}
    for cluster, count in cluster_counts.items():
        share = count / total
        penalty = max(0.75, 1.0 - 0.3 * max(0.0, share - mean_share) / max(1.0 - mean_share, 0.01))
        weights[cluster] = penalty
    return weights


def _compute_filiere_score(
    filiere: Dict[str, Any],
    profile_vector: Dict[str, float],
    field_vector: Dict[str, float],
    cluster_weights: Dict[str, float],
    dominant_cluster: Optional[str],
) -> Tuple[float, List[tuple[str, float]], float, float]:
    """Calcule le score complet d'une filière."""
    raw_similarity = _vector_dot(profile_vector, field_vector)
    distance = _euclidean_distance(profile_vector, field_vector)
    distance_factor = 1.0 / (1.0 + distance)

    cluster = _get_filiere_cluster(filiere.get("nom", ""))
    cluster_weight = cluster_weights.get(cluster, 1.0)
    cluster_boost = 1.05 if dominant_cluster and cluster == dominant_cluster else 1.0

    score = raw_similarity * distance_factor * cluster_weight * cluster_boost
    score = min(1.0, max(0.0, score))

    contributions = _compute_dimension_contributions(profile_vector, field_vector)
    contribution_list = sorted(contributions.items(), key=lambda x: x[1], reverse=True)
    
    return score, contribution_list, raw_similarity, distance


def _select_coherent_recommendations(
    results: List[Dict[str, Any]],
    top_n: int,
    decision_cluster: Optional[str],
) -> List[Dict[str, Any]]:
    """Sélectionne les recommandations cohérentes."""
    if not results:
        return []
    
    results = sorted(results, key=lambda x: x.get("score", 0), reverse=True)
    selected = []
    
    # Priorité au cluster décidé
    if decision_cluster:
        primary = [r for r in results if r.get("cluster") == decision_cluster]
        for item in primary[:top_n]:
            if len(selected) < top_n and item not in selected:
                selected.append(item)
    
    # Compléter avec d'autres clusters
    for item in results:
        if len(selected) >= top_n:
            break
        if item not in selected:
            selected.append(item)
    
    return selected[:top_n]


def _build_profile_insight(profile: Dict[str, Any]) -> str:
    """Génère un insight textuel sur le profil."""
    domains = profile.get("domains", {}) or {}
    skills = profile.get("skills", {}) or {}

    top_domain = None
    if domains:
        top_domain = max(domains.items(), key=lambda x: x[1])[0]
        top_domain = _normalize_profile_keyword(top_domain)

    top_skills = [k for k, v in sorted(skills.items(), key=lambda x: x[1], reverse=True) if v > 0.3][:2]
    top_skills = [_normalize_profile_keyword(k) for k in top_skills]

    if top_domain and top_skills:
        return f"Tu montres une forte affinité avec {top_domain}, notamment grâce à tes compétences en {', '.join(top_skills)}."
    if top_domain:
        return f"Tu montres une forte affinité avec {top_domain}."
    if top_skills:
        return f"Tes compétences en {', '.join(top_skills)} ressortent clairement."
    return "Ton profil montre une orientation équilibrée vers plusieurs domaines."


# ============================================================================
# FONCTION PRINCIPALE
# ============================================================================

def compute_recommended_fields(profile: Dict[str, Any], top_n: int = 5) -> Dict[str, Any]:
    """
    Calcule les filières recommandées pour un profil utilisateur.
    
    Args:
        profile: Dictionnaire avec clés `domains` et `skills`
        top_n: Nombre maximum de recommandations
    
    Returns:
        Dictionnaire avec recommended_fields, field_scores, insight, etc.
    """
    # Étape 1: Récupérer les filières
    filieres = _fetch_filieres_from_db()
    if not filieres:
        return {
            "recommended_fields": [],
            "field_scores": {},
            "insight": "Aucune filière disponible pour le moment.",
            "dominant_cluster": None,
            "bac_type": None,
            "bac_track": None
        }
    
    # Étape 2: Extraire les informations du profil
    profile_keywords = _extract_keywords_from_profile(profile)
    profile_vector = _build_profile_vector(profile)
    bac_type = _extract_bac_type(profile)
    bac_track = _classify_bac_track(bac_type)
    dominant_cluster = _detect_dominant_cluster(profile_keywords)
    
    # Étape 3: Préparer les candidats
    candidates = []
    for filiere in filieres:
        field_vector = _build_field_vector(filiere)
        cluster = _get_filiere_cluster(filiere.get("nom", ""))
        candidates.append({
            "filiere": filiere,
            "field_vector": field_vector,
            "cluster": cluster,
        })
    
    # Étape 4: Calculer les poids des clusters
    cluster_counts = Counter(c["cluster"] for c in candidates)
    cluster_weights = _build_cluster_frequency_weights(cluster_counts, len(candidates))
    
    # Étape 5: Calculer les scores
    results = []
    for candidate in candidates:
        filiere = candidate["filiere"]
        field_vector = candidate["field_vector"]
        
        score, contributions, raw_similarity, distance = _compute_filiere_score(
            filiere, profile_vector, field_vector, cluster_weights, dominant_cluster
        )
        
        # Intégration du score bac
        bac_score = _compute_bac_compatibility_score(bac_type, filiere)
        if bac_score is not None:
            final_score = min(1.0, max(0.0, score * PROFILE_SCORE_WEIGHT + bac_score * BAC_SCORE_WEIGHT))
        else:
            final_score = score
        
        # Générer la raison
        reason_parts = [f"{dim} ({contrib:.0%})" for dim, contrib in contributions[:3] if contrib > 0]
        reason = " + ".join(reason_parts) if reason_parts else "Profil adapté"
        if bac_score and bac_type:
            reason += f" | Bac {bac_type.upper()}: {bac_score:.0%}"
        
        results.append({
            "field_name": filiere.get("nom", "Unknown"),
            "score": round(final_score, 4),
            "reason": reason,
            "category": "Supabase",
            "cluster": candidate["cluster"],
            "similarity": round(raw_similarity, 4),
            "distance": round(distance, 4),
        })
    
    # Étape 6: Filtrer et trier
    filtered = [r for r in results if r["score"] >= MIN_SCORE_THRESHOLD]
    filtered.sort(key=lambda x: x["score"], reverse=True)
    
    if not filtered and results:
        filtered = results
        filtered.sort(key=lambda x: x["score"], reverse=True)
    
    # Étape 7: Sélection finale
    final = _select_coherent_recommendations(filtered, top_n, dominant_cluster)
    
    # Étape 8: Garantir le nombre de résultats
    if len(final) < top_n:
        used_names = {f["field_name"] for f in final}
        available = [r for r in results if r["field_name"] not in used_names]
        for item in available[:top_n - len(final)]:
            final.append(item)
    
    # Étape 9: Construire la réponse
    return {
        "recommended_fields": final,
        "field_scores": {f["field_name"]: f["score"] for f in final},
        "insight": _build_profile_insight(profile),
        "dominant_cluster": dominant_cluster,
        "bac_type": bac_type,
        "bac_track": bac_track,
    }


# ============================================================================
# FONCTION DE COMPATIBILITÉ
# ============================================================================

def compute_recommended_institutions(profile: Dict[str, Any], top_n: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """
    DEPRECATED: Les institutions sont recommandées par PORA.
    Cette fonction est conservée pour compatibilité.
    """
    return {"recommended_institutions": []}


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    sample_profile = {
        "domains": {"computer_science": 0.8, "technical": 0.7, "logic": 0.75},
        "skills": {"python": 0.9, "data_analysis": 0.8},
        "context": {"bac_type": "C"}
    }
    
    result = compute_recommended_fields(sample_profile, top_n=5)
    print(json.dumps(result, ensure_ascii=False, indent=2))