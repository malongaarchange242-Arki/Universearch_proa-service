"""
Feature Engineering - Moteur de recommandations d'orientation
Version 2.0 - Améliorée avec scoring vectoriel dimensionnel et cache intelligent
"""
"""
Feature Engineering - Moteur de recommandations d'orientation
Version 3.0 - Corrigée avec compatibilité BAC renforcée et clusters alignés
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
_FILIERES_CACHE: Optional[list] = None
_CACHE_TIMESTAMP: Optional[datetime] = None
_BAC_SPECIFIC_RULES_CACHE: Optional[Dict] = None

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

# Poids pour le scoring hybride (CORRIGÉS)
PROFILE_SCORE_WEIGHT = 0.5      # ↓ baissé de 0.7
BAC_SCORE_WEIGHT = 0.5          # ↑ augmenté de 0.3
MIN_SCORE_THRESHOLD = 0.25      # ↑ augmenté de 0.12

# Pénalités et bonus pour règles spécifiques
PREFERRED_BONUS = 0.35          # Bonus pour preferred_fields
FORBIDDEN_PENALTY = -0.50       # Pénalité pour forbidden_fields


# ============================================================================
# FONCTIONS DE CHARGEMENT DES RÈGLES BAC SPÉCIFIQUES
# ============================================================================

def _load_bac_specific_rules() -> Dict:
    """Charge les règles spécifiques par série de bac depuis bac_specific_rules.json."""
    global _BAC_SPECIFIC_RULES_CACHE
    
    if _BAC_SPECIFIC_RULES_CACHE is not None:
        return _BAC_SPECIFIC_RULES_CACHE
    
    rules_path = os.path.join(os.path.dirname(__file__), "..", "bac_specific_rules.json")
    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            _BAC_SPECIFIC_RULES_CACHE = config.get("bac_rules", {})
            print(f"[PROA] Chargé {len(_BAC_SPECIFIC_RULES_CACHE)} règles BAC spécifiques")
            return _BAC_SPECIFIC_RULES_CACHE
    except Exception as e:
        print(f"[PROA] Erreur chargement bac_specific_rules.json: {e}")
        _BAC_SPECIFIC_RULES_CACHE = {}
        return _BAC_SPECIFIC_RULES_CACHE


def _get_bac_specific_rules(bac_code: str) -> Optional[Dict]:
    """Récupère les règles spécifiques pour une série de bac."""
    if not bac_code:
        return None
    rules = _load_bac_specific_rules()
    return rules.get(bac_code.upper().strip())


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
# CLUSTERS ET MAPPINGS (ALIGNÉS AVEC academic_clusters.json)
# ============================================================================

FIELD_CLUSTERS = {
    "informatique_numerique": [
        "génie logiciel", "développement informatique", "informatique", "informatique de gestion",
        "intelligence artificielle", "data science", "big data", "analyse de données",
        "cybersécurité", "sécurité informatique", "réseaux informatiques", "systèmes d'information",
        "développement web", "développement mobile", "programmation", "bases de données",
        "machine learning", "deep learning", "cloud computing", "devops", "ia"
    ],
    "genie_electrique_energie": [
        "génie électrique", "électronique", "électrotechnique", "automatique",
        "robotique", "systèmes embarqués", "télécommunications", "instrumentation",
        "automatisme", "maintenance industrielle", "installation panneaux solaires",
        "photo-voltaïque", "énergie renouvelable"
    ],
    "genie_mecanique_industriel": [
        "génie mécanique", "mécatronique", "conception mécanique", "construction mécanique",
        "productique", "fabrication mécanique", "electromecanique"
    ],
    "genie_civil_btp": [
        "génie civil", "construction", "architecture", "urbanisme", "bâtiment",
        "travaux publics", "géomètre", "topographe", "matériaux de construction"
    ],
    "gestion_finance_comptabilite": [
        "comptabilité", "finance", "gestion d'entreprise", "audit", "contrôle de gestion",
        "banque", "assurance", "actuariat", "gestion financière", "comptabilité de gestion"
    ],
    "commerce_marketing_vente": [
        "marketing", "commerce international", "vente", "action commerciale",
        "business trade", "e-commerce", "digital marketing", "relation client"
    ],
    "management_rh_administration": [
        "management", "ressources humaines", "administration", "gestion des ressources humaines",
        "entrepreneuriat", "management des projets", "organisation", "gestion publique"
    ],
    "sciences_sante_medicale": [
        "médecine", "pharmacie", "soins infirmiers", "biologie médicale", "santé publique",
        "odontostomatologie", "assistant médical"
    ],
    "sciences_naturelles_environnement": [
        "biologie", "chimie", "géologie", "environnement", "biochimie", "géophysique",
        "géosciences", "hydrogéologie", "écologie"
    ],
    "agriculture_elevage_agro": [
        "agronomie", "agriculture", "production végétale", "production animale", 
        "santé animale", "génie rural", "agroalimentaire", "machinisme agricole"
    ],
    "droit_sciences_juridiques": [
        "droit", "sciences politiques", "relations internationales", "diplomatie",
        "droit des affaires", "droit pénal", "droit privé", "droit public"
    ],
    "lettres_langues_communication": [
        "lettres", "langues", "philosophie", "sociologie", "psychologie", "histoire",
        "géographie", "anthropologie", "journalisme", "communication", "traduction"
    ],
    "arts_design_creatif": [
        "design", "art", "créativité", "infographie", "mode", "photographie",
        "architecture intérieur", "arts plastiques"
    ],
    "tourisme_hotellerie_restauration": [
        "hôtellerie", "tourisme", "restauration", "événementiel", "cuisine"
    ],
    "logistique_transport_douane": [
        "logistique", "transport", "supply chain", "douane", "transit", "commerce international",
        "gestion des stocks", "shipping", "freight"
    ],
    "genie_petrolier_chimie": [
        "génie pétrolier", "raffinage", "pétrochimie", "forage", "production pétrolière",
        "économie pétrolière"
    ],
    "formation_professionnelle_metiers": [
        "menuisier", "plombier", "électricien bâtiment", "soudure", "chaudronnerie",
        "peintre industriel", "coiffure", "esthétique", "pâtisserie"
    ],
}

FIELD_CLUSTER_SYNONYMS = {
    "informatique_numerique": [
        "informatique", "programmation", "logiciel", "data", "ia", "cyber", "réseau"
    ],
    "genie_electrique_energie": [
        "électrique", "électronique", "électrotechnique", "automatique", "robotique"
    ],
    "genie_mecanique_industriel": [
        "mécanique", "mécatronique", "construction mécanique", "maintenance"
    ],
    "genie_civil_btp": [
        "civil", "btp", "construction", "architecture", "bâtiment"
    ],
    "gestion_finance_comptabilite": [
        "comptabilité", "finance", "gestion", "audit", "banque", "assurance"
    ],
    "commerce_marketing_vente": [
        "marketing", "commerce", "vente", "business"
    ],
    "management_rh_administration": [
        "management", "rh", "ressources humaines", "administration"
    ],
    "sciences_sante_medicale": [
        "médecine", "santé", "pharmacie", "infirmier", "clinique"
    ],
    "droit_sciences_juridiques": [
        "droit", "juridique", "justice", "avocat"
    ],
}

CLUSTER_KEYWORDS = {
    "informatique_numerique": ["informatique", "logiciel", "data", "ia", "cyber", "réseau"],
    "genie_electrique_energie": ["électrique", "électronique", "automatique", "robotique"],
    "genie_mecanique_industriel": ["mécanique", "mécatronique", "maintenance"],
    "genie_civil_btp": ["civil", "btp", "construction", "architecture"],
    "gestion_finance_comptabilite": ["compta", "finance", "gestion", "audit"],
    "commerce_marketing_vente": ["marketing", "commerce", "vente"],
    "management_rh_administration": ["management", "rh", "ressources humaines"],
    "sciences_sante_medicale": ["médecine", "santé", "pharmacie"],
    "droit_sciences_juridiques": ["droit", "juridique", "justice"],
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
        "digital", "numérique", "informatique", "logiciel", "software", "ia",
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
# BAC CONGOLAIS - COMPATIBILITÉ (RENFORCÉE)
# ============================================================================

# Matrice de compatibilité avec les nouveaux clusters
BAC_TRACK_COMPATIBILITY = {
    "technical": {
        "clusters": {
            "genie_electrique_energie": 1.0,
            "genie_mecanique_industriel": 0.85,
            "genie_civil_btp": 0.60,
            "genie_petrolier_chimie": 0.70,
            "informatique_numerique": 0.35,      # ↓ baissé de 0.72
            "formation_professionnelle_metiers": 0.80,
            "sciences_naturelles_environnement": 0.40,
            "agriculture_elevage_agro": 0.45,
            "logistique_transport_douane": 0.30,
            "gestion_finance_comptabilite": 0.15,
            "commerce_marketing_vente": 0.12,
            "management_rh_administration": 0.10,
            "sciences_sante_medicale": 0.05,
            "droit_sciences_juridiques": 0.05,
            "lettres_langues_communication": 0.05,
            "arts_design_creatif": 0.05,
            "tourisme_hotellerie_restauration": 0.05,
        },
    },
    "science": {
        "clusters": {
            "informatique_numerique": 0.85,
            "genie_civil_btp": 0.80,
            "genie_petrolier_chimie": 0.85,
            "sciences_sante_medicale": 0.95,
            "sciences_naturelles_environnement": 0.95,
            "agriculture_elevage_agro": 0.70,
            "genie_electrique_energie": 0.60,
            "genie_mecanique_industriel": 0.65,
            "gestion_finance_comptabilite": 0.20,
            "business": 0.15,
        },
    },
    "informatics": {
        "clusters": {
            "informatique_numerique": 1.0,
            "genie_electrique_energie": 0.50,
            "genie_mecanique_industriel": 0.40,
            "gestion_finance_comptabilite": 0.25,
            "commerce_marketing_vente": 0.20,
            "sciences_sante_medicale": 0.10,
            "droit_sciences_juridiques": 0.08,
        },
    },
    "business": {
        "clusters": {
            "gestion_finance_comptabilite": 1.0,
            "commerce_marketing_vente": 0.95,
            "management_rh_administration": 0.90,
            "logistique_transport_douane": 0.70,
            "droit_sciences_juridiques": 0.60,
            "informatique_numerique": 0.30,
            "tourisme_hotellerie_restauration": 0.50,
            "genie_civil_btp": 0.10,
            "genie_electrique_energie": 0.05,
        },
    },
    "humanities": {
        "clusters": {
            "lettres_langues_communication": 1.0,
            "droit_sciences_juridiques": 0.90,
            "arts_design_creatif": 0.70,
            "tourisme_hotellerie_restauration": 0.60,
            "management_rh_administration": 0.55,
            "commerce_marketing_vente": 0.45,
            "gestion_finance_comptabilite": 0.35,
            "informatique_numerique": 0.10,
            "sciences_sante_medicale": 0.08,
        },
    },
    "vocational": {
        "clusters": {
            "formation_professionnelle_metiers": 1.0,
            "genie_civil_btp": 0.85,
            "genie_mecanique_industriel": 0.80,
            "genie_electrique_energie": 0.75,
            "agriculture_elevage_agro": 0.60,
            "tourisme_hotellerie_restauration": 0.55,
            "arts_design_creatif": 0.50,
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
    """Récupère les filières depuis Supabase avec cache intelligent."""
    global _FILIERES_CACHE, _CACHE_TIMESTAMP
    
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

        exact_weights = PROFILE_EXACT_DIMENSION_WEIGHTS.get(normalized_term)
        if exact_weights:
            _apply_dimension_weights(raw_vector, exact_weights, value)

        for dim, seeds in PROFILE_DIMENSION_SEEDS.items():
            if any(_normalize_match_text(seed) in normalized_term for seed in seeds):
                raw_vector[dim] += value

    return _normalize_vector(raw_vector)


def _build_field_vector(filiere: Dict[str, Any]) -> Dict[str, float]:
    """Construit le vecteur dimensionnel d'une filière."""
    raw_vector = {dim: 0.0 for dim in DIMENSIONS}
    filiere_name = filiere.get("nom", "")
    text = _normalize_match_text(f"{filiere_name} {filiere.get('description', '')}")

    for dim, seeds in FIELD_DIMENSION_SEEDS.items():
        for seed in seeds:
            if _normalize_match_text(seed) in text:
                raw_vector[dim] += 1.0

    if sum(raw_vector.values()) <= 0:
        cluster = _get_filiere_cluster(filiere_name)
        cluster_fallback = {
            "informatique_numerique": {"tech": 1.0, "expertise": 0.4},
            "genie_electrique_energie": {"tech": 0.8, "expertise": 0.3, "impact": 0.1},
            "genie_mecanique_industriel": {"tech": 0.75, "expertise": 0.35},
            "genie_civil_btp": {"tech": 0.7, "expertise": 0.3, "impact": 0.15},
            "gestion_finance_comptabilite": {"business": 1.0, "expertise": 0.3},
            "commerce_marketing_vente": {"business": 0.9, "social": 0.2},
            "management_rh_administration": {"business": 0.7, "social": 0.3},
            "sciences_sante_medicale": {"impact": 1.0, "expertise": 0.4},
            "droit_sciences_juridiques": {"social": 0.6, "expertise": 0.5, "impact": 0.2},
            "lettres_langues_communication": {"social": 0.8, "creativity": 0.3},
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
    
    for cluster_name, filieres in FIELD_CLUSTERS.items():
        for cluster_filiere in filieres:
            if cluster_filiere in filiere_lower or filiere_lower in cluster_filiere:
                return cluster_name
    
    for cluster_name, synonyms in FIELD_CLUSTER_SYNONYMS.items():
        if any(syn in filiere_lower for syn in synonyms):
            return cluster_name
    
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
# FONCTIONS BAC CONGOLAIS (AMÉLIORÉES)
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
    """
    Calcule le score de compatibilité bac/filière.
    Version améliorée avec règles spécifiques prioritaires.
    """
    if not bac_type:
        return None
    
    # PRIORITÉ 1: Règles spécifiques par série
    specific_rules = _get_bac_specific_rules(bac_type)
    if specific_rules:
        field_name = filiere.get("nom", "")
        preferred_fields = specific_rules.get("preferred_fields", [])
        allowed_fields = specific_rules.get("allowed_fields", [])
        forbidden_fields = specific_rules.get("forbidden_fields", [])
        
        if field_name in forbidden_fields:
            return 0.0  # Totalement incompatible
        if field_name in preferred_fields:
            return 1.0  # Parfaitement compatible
        if field_name in allowed_fields:
            return 0.7  # Acceptable
    
    # PRIORITÉ 2: Règles par track (fallback)
    track = _classify_bac_track(bac_type)
    if not track:
        return None

    rules = BAC_TRACK_COMPATIBILITY.get(track, {})
    cluster = _get_filiere_cluster(filiere.get("nom", ""))
    
    # Score par cluster
    cluster_score = rules.get("clusters", {}).get(cluster, 0.0)
    if cluster_score > 0:
        return cluster_score
    
    return 0.3  # Score neutre par défaut


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
    
    if decision_cluster:
        primary = [r for r in results if r.get("cluster") == decision_cluster]
        for item in primary[:top_n]:
            if len(selected) < top_n and item not in selected:
                selected.append(item)
    
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
    
    profile_keywords = _extract_keywords_from_profile(profile)
    profile_vector = _build_profile_vector(profile)
    bac_type = _extract_bac_type(profile)
    bac_track = _classify_bac_track(bac_type)
    dominant_cluster = _detect_dominant_cluster(profile_keywords)
    
    candidates = []
    for filiere in filieres:
        field_vector = _build_field_vector(filiere)
        cluster = _get_filiere_cluster(filiere.get("nom", ""))
        candidates.append({
            "filiere": filiere,
            "field_vector": field_vector,
            "cluster": cluster,
        })
    
    cluster_counts = Counter(c["cluster"] for c in candidates)
    cluster_weights = _build_cluster_frequency_weights(cluster_counts, len(candidates))
    
    results = []
    for candidate in candidates:
        filiere = candidate["filiere"]
        field_vector = candidate["field_vector"]
        
        score, contributions, raw_similarity, distance = _compute_filiere_score(
            filiere, profile_vector, field_vector, cluster_weights, dominant_cluster
        )
        
        # Intégration du score bac (NOUVEAU: priorité aux règles spécifiques)
        bac_score = _compute_bac_compatibility_score(bac_type, filiere)
        if bac_score is not None:
            # Pénaliser plus fortement les scores bas
            if bac_score < 0.3:
                final_score = score * bac_score  # Pénalisation forte
            else:
                final_score = score * PROFILE_SCORE_WEIGHT + bac_score * BAC_SCORE_WEIGHT
            final_score = min(1.0, max(0.0, final_score))
        else:
            final_score = score
        
        reason_parts = [f"{dim} ({contrib:.0%})" for dim, contrib in contributions[:3] if contrib > 0]
        reason = " + ".join(reason_parts) if reason_parts else "Profil adapté"
        if bac_score is not None and bac_type:
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
    
    filtered = [r for r in results if r["score"] >= MIN_SCORE_THRESHOLD]
    filtered.sort(key=lambda x: x["score"], reverse=True)
    
    if not filtered and results:
        filtered = results
        filtered.sort(key=lambda x: x["score"], reverse=True)
    
    final = _select_coherent_recommendations(filtered, top_n, dominant_cluster)
    
    if len(final) < top_n:
        used_names = {f["field_name"] for f in final}
        available = [r for r in results if r["field_name"] not in used_names]
        for item in available[:top_n - len(final)]:
            final.append(item)
    
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
    """DEPRECATED: Les institutions sont recommandées par PORA."""
    return {"recommended_institutions": []}


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    # Test avec bac F3
    sample_profile_f3 = {
        "domains": {"technical": 0.8, "logic": 0.7},
        "skills": {"electricite": 0.9, "maintenance": 0.8},
        "context": {"bac_type": "F3"}
    }
    
    print("=== TEST BAC F3 ===")
    result_f3 = compute_recommended_fields(sample_profile_f3, top_n=5)
    for field in result_f3["recommended_fields"]:
        print(f"  - {field['field_name']}: {field['score']} | {field['reason']}")
    
    # Test avec bac C
    sample_profile_c = {
        "domains": {"computer_science": 0.8, "technical": 0.7},
        "skills": {"python": 0.9, "math": 0.85},
        "context": {"bac_type": "C"}
    }
    
    print("\n=== TEST BAC C ===")
    result_c = compute_recommended_fields(sample_profile_c, top_n=5)
    for field in result_c["recommended_fields"]:
        print(f"  - {field['field_name']}: {field['score']} | {field['reason']}")