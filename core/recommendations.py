import json
import math
import os
import random
from collections import Counter
from typing import Dict, List, Any
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# ==================================================
# FIELD CLUSTERS FOR BUSINESS COHERENCE
# ==================================================
FIELD_CLUSTERS = {
    # 🖥️ INFORMATIQUE
    "informatique": [
        "génie logiciel", "développement informatique", "informatique", "informatique de gestion",
        "intelligence artificielle", "data science", "big data", "analyse de données",
        "cybersécurité", "sécurité informatique", "réseaux informatiques", "systèmes d'information",
        "développement web", "développement mobile", "programmation", "bases de données",
        "machine learning", "deep learning", "cloud computing", "devops"
    ],
    
    # 🌍 GÉOSCIENCES
    "géoscience": [
        "génie géologique", "géologie", "géophysique", "hydrogéologie", "génie civil géotechnique",
        "mines et géologie", "environnement", "gestion environnementale", "hydrologie",
        "océanographie", "météorologie", "cartographie", "topographie"
    ],
    
    # 💼 BUSINESS & MANAGEMENT
    "business": [
        "comptabilité", "finance", "gestion d'entreprise", "marketing", "commerce international",
        "management", "administration des affaires", "banque", "assurance", "audit",
        "ressources humaines", "gestion des ressources humaines", "entrepreneuriat",
        "commerce", "économie", "gestion financière"
    ],
    
    # ⚡ ÉLECTRONIQUE & ÉLECTROTECHNIQUE
    "électronique": [
        "génie électrique", "électronique", "électrotechnique", "automatique",
        "robotique", "systèmes embarqués", "télécommunications", "instrumentation"
    ],
    
    # 🏗️ GÉNIE CIVIL & CONSTRUCTION
    "génie_civil": [
        "génie civil", "construction", "architecture", "urbanisme", "bâtiment",
        "génie urbain", "aménagement du territoire"
    ],
    
    # 🔬 SCIENCES & RECHERCHE
    "sciences": [
        "mathématiques", "physique", "chimie", "biologie", "biochimie",
        "génie chimique", "génie biologique", "recherche scientifique"
    ],
    
    # 🎨 ARTS & DESIGN
    "arts_design": [
        "design graphique", "design industriel", "arts plastiques", "communication visuelle",
        "architecture d'intérieur", "mode", "photographie"
    ],
    
    # 🏥 SANTÉ & MÉDICAL
    "santé": [
        "médecine", "pharmacie", "dentaire", "sciences infirmières", "kinésithérapie",
        "sciences médicales", "biotechnologie médicale"
    ],
    
    # 🌾 AGRICULTURE & AGRO
    "agriculture": [
        "agronomie", "agriculture", "agroalimentaire", "génie agricole", "foresterie",
        "pêche", "aquaculture"
    ],
    
    # 🚀 AÉRONAUTIQUE & ESPACE
    "aéronautique": [
        "aéronautique", "aérospatiale", "génie aéronautique", "mécanique des fluides"
    ]
}
FIELD_CLUSTER_SYNONYMS = {
    "informatique": [
        "informatique", "programmation", "logiciel", "code", "developer", "développement",
        "data", "machine learning", "ia", "intelligence artificielle", "cybersécurité",
        "sécurité informatique", "réseaux", "base de données", "cloud"
    ],
    "business": [
        "comptabilité", "finance", "gestion", "marketing", "commerce international",
        "entrepreneuriat", "banque", "assurance", "audit", "ressources humaines",
        "management", "commerce", "économie"
    ],
    "électronique": [
        "électronique", "électrotechnique", "robotique", "automatique",
        "télécommunications", "systèmes embarqués", "instrumentation"
    ],
    "génie_civil": [
        "génie civil", "construction", "architecture", "urbanisme", "bâtiment",
        "infrastructure", "aménagement"
    ],
    "sciences": [
        "mathématiques", "physique", "chimie", "biologie", "biochimie",
        "génie chimique", "génie biologique", "recherche"
    ],
    "arts_design": [
        "design", "arts", "communication visuelle", "mode", "photographie",
        "graphique", "architecture d'intérieur"
    ],
    "santé": [
        "médecine", "pharmacie", "dentaire", "kinésithérapie", "sciences infirmières",
        "biotechnologie", "sciences médicales"
    ],
    "agriculture": [
        "agriculture", "agroalimentaire", "agronomie", "foresterie", "pêche", "aquaculture"
    ],
    "aéronautique": [
        "aéronautique", "aérospatiale", "génie aéronautique", "mécanique des fluides"
    ]
}

GENERIC_CLUSTER_TERMS = {
    "technical", "technique", "technology", "business", "gestion", "management",
    "science", "sciences", "analysis", "analytique", "data", "innovation",
    "creative", "communication", "entrepreneurship", "marketing"
}

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

PROFILE_DIMENSION_SEEDS = {
    "tech": [
        "informatique", "programmat", "logiciel", "software", "développement",
        "ia", "intelligence artificielle", "machine learning", "data", "données",
        "cybersécurité", "cloud", "web", "mobile", "programmation",
        "algorithm", "devops", "réseaux", "systèmes d'information"
    ],
    "business": [
        "business", "marketing", "commerce", "finance", "gestion", "entrepreneuriat",
        "management", "banque", "assurance", "économie", "audit",
        "comptabilité", "vente", "commercial", "commerce international"
    ],
    "social": [
        "communication", "relation", "social", "collaboration", "équipe",
        "community", "relationnel", "dialogue", "oral", "échange",
        "humanitaire", "société", "psychologie", "service"
    ],
    "creativity": [
        "créativité", "créatif", "design", "artistique", "innovation",
        "architecture", "mode", "photographie", "graphique", "arts",
        "expression", "cinéma", "musique"
    ],
    "impact": [
        "impact", "durable", "environnement", "écologie", "santé",
        "communautaire", "solidarité", "bio", "biotechnologie", "médecine",
        "droit", "politique", "responsabilité"
    ],
    "flexibility": [
        "flexibilité", "polyvalent", "adaptabilité", "autonomie",
        "mobilité", "hybride", "polyvalence", "agile", "multi",
        "multidisciplinaire", "variété"
    ],
    "international": [
        "international", "global", "étranger", "langue", "anglais",
        "multiculturel", "diplomatie", "relations internationales",
        "tourisme", "aéronautique", "commerce international"
    ],
    "expertise": [
        "recherche", "scientifique", "spécialisation", "théorie",
        "mathématiques", "physique", "chimie", "ingénierie",
        "analyse", "expertise", "profondeur", "master", "doctorat"
    ],
}

FIELD_DIMENSION_SEEDS = {
    "tech": [
        "digital", "numérique", "informatique", "logiciel", "software", "ia",
        "intelligence artificielle", "machine learning", "data", "données",
        "cybersécurité", "cloud", "réseaux", "programmation", "web",
        "mobile", "systèmes d'information", "robotique", "automatisation"
    ],
    "business": [
        "business", "marketing", "commerce", "finance", "gestion",
        "entrepreneuriat", "management", "banque", "assurance", "économie",
        "audit", "comptabilité", "stratégie", "vente", "logistique",
        "gestion de projet", "commerce international", "e-commerce"
    ],
    "social": [
        "communication", "relation", "relationnel", "social", "collaboration",
        "équipe", "psychologie", "community", "service", "santé sociale",
        "droit", "éthique", "ressources humaines", "humanitaire"
    ],
    "creativity": [
        "créativité", "créatif", "design", "arts", "architecture", "mode",
        "photographie", "graphique", "innovation", "multimédia", "storytelling",
        "cinéma", "expression", "conceptuel"
    ],
    "impact": [
        "durable", "écologie", "environnement", "climat", "santé",
        "biotechnologie", "médecine", "solidarité", "responsabilité",
        "gouvernance", "développement durable", "société"
    ],
    "flexibility": [
        "flexibilité", "polyvalent", "adaptabilité", "autonomie",
        "mobilité", "hybride", "agile", "polyvalence", "multi",
        "variété", "projet", "freedom", "liberté"
    ],
    "international": [
        "international", "global", "étranger", "langue", "anglais",
        "multiculturel", "diplomatie", "géopolitique", "voyage",
        "commerce international", "relations internationales"
    ],
    "expertise": [
        "recherche", "scientifique", "spécialisation", "théorie",
        "méthodologie", "rigueur", "mathématiques", "physique",
        "chimie", "ingénierie", "analyse", "doctorat", "master",
        "certification"
    ],
}

FIELD_VECTOR_OVERRIDES = {
    "marketing digital": {"business": 0.75, "creativity": 0.55, "tech": 0.35, "international": 0.2},
    "marketing international": {"business": 0.75, "international": 0.6, "social": 0.3, "creativity": 0.2},
    "génie logiciel": {"tech": 0.85, "expertise": 0.65, "business": 0.15},
    "architecture d intérieur": {"creativity": 0.8, "impact": 0.35, "flexibility": 0.35},
    "droit": {"social": 0.55, "expertise": 0.55, "impact": 0.25},
    "cybersécurité": {"tech": 0.8, "expertise": 0.55, "impact": 0.2},
    "data science": {"tech": 0.65, "expertise": 0.55, "business": 0.2},
    "sciences infirmières": {"impact": 0.8, "social": 0.4, "expertise": 0.3},
    "commerce international": {"business": 0.7, "international": 0.65, "social": 0.25},
    "gestion des ressources humaines": {"business": 0.55, "social": 0.5, "expertise": 0.2},
    "énergies renouvelables": {"impact": 0.8, "expertise": 0.4, "tech": 0.25},
}

FIELD_VECTOR_KEYWORD_OVERRIDES = {
    "digital": {"tech": 0.4, "creativity": 0.25},
    "numérique": {"tech": 0.4, "creativity": 0.25},
    "hospitalier": {"impact": 0.6, "social": 0.4},
    "droit": {"social": 0.4, "expertise": 0.4, "impact": 0.2},
    "cybersécurité": {"tech": 0.7, "expertise": 0.4},
    "marketing": {"business": 0.6, "creativity": 0.3},
    "communication": {"social": 0.6, "creativity": 0.3},
    "design": {"creativity": 0.7, "impact": 0.2},
    "entrepreneuriat": {"business": 0.6, "risk_tolerance": 0.3, "flexibility": 0.2},
    "finance": {"business": 0.7, "expertise": 0.3},
    "santé": {"impact": 0.7, "expertise": 0.3},
    "écologie": {"impact": 0.7, "international": 0.2},
    "architecture": {"creativity": 0.7, "impact": 0.3},
}

PROFILE_LATENT_TRAIT_SEEDS = {
    "risk_tolerance": [
        "risque", "audace", "startup", "entrepreneur", "venture",
        "challenge", "innovation", "créatif", "explorer", "aventure"
    ],
    "structure_positive": [
        "structure", "organisation", "rigueur", "cadre", "procédure",
        "méthode", "discipline", "gestion de projet"
    ],
    "freedom_positive": [
        "autonomie", "liberté", "flexibilité", "polyvalence", "indépendant",
        "créatif", "expérimental", "hybride"
    ],
    "people_positive": [
        "humain", "relationnel", "équipe", "client", "service", "communication",
        "community", "société", "psychologie"
    ],
    "systems_positive": [
        "système", "algorithm", "processus", "automatisation", "technologie",
        "analyse", "données", "mathématiques"
    ],
    "creation_positive": [
        "création", "créatif", "design", "innovation", "storytelling",
        "image", "artistique", "conceptuel"
    ],
    "analysis_positive": [
        "analyse", "analytique", "statistique", "mathématique", "recherche",
        "processus", "audit", "données"
    ],
}

FIELD_SYNONYMS = {
    "technical": ["informatique", "programmation", "logiciel", "code", "software"],
    "logic": ["logique", "algorithme", "algorithm", "mathématiques", "math", "algorithmique"],
    "creativity": ["créativité", "creative", "innovation", "design", "arts"],
    "teamwork": ["équipe", "team", "collaboration", "group", "travail"],
    "entrepreneurship": ["entrepreneuriat", "startup", "business", "commerce", "entreprise"],
    "communication": ["communication", "dialogue", "language", "rhetorique", "présentation"],
    "leadership": ["leadership", "direction", "management", "gestion", "pilotage"],
    "analysis": ["analyse", "analysis", "analytique", "statistique", "data"],
    "data": ["données", "data", "database", "analytics", "statistique"],
    "web": ["web", "internet", "frontend", "backend", "site", "page"],
    "mobile": ["mobile", "application", "app", "smartphone"],
    "software": ["logiciel", "software", "code", "programmation"],
    "finance": ["finance", "bancaire", "fintech", "économie", "comptabilité"],
    "marketing": ["marketing", "commerce", "vente", "commercial"],
}

# Cache pour les filières
_FILIERES_CACHE: List[Dict[str, Any]] | None = None

def _fetch_filieres_from_db() -> List[Dict[str, Any]]:
    """
    Récupère TOUTES les filières depuis Supabase.
    Cache le résultat pour éviter les requêtes répétées.
    """
    global _FILIERES_CACHE
    
    if _FILIERES_CACHE is not None:
        print(f"[PROA] Using cached filieres: {len(_FILIERES_CACHE)} items")
        return _FILIERES_CACHE
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/filieres"
        print(f"[PROA] Fetching from Supabase: {url}")
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        params = {
            "select": "id,nom,description",
            "limit": "9999"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"[PROA] Supabase response status: {response.status_code}")
        response.raise_for_status()
        
        _FILIERES_CACHE = response.json()
        print(f"[PROA] Cached {len(_FILIERES_CACHE)} filieres from Supabase")
        return _FILIERES_CACHE
        
    except Exception as e:
        print(f"[PROA] Error fetching filieres: {e}")
        return []


def _normalize_profile_keyword(key: str) -> str:
    normalized = key.lower().strip()
    if normalized.startswith("domain_"):
        normalized = normalized[len("domain_"):]
    elif normalized.startswith("skill_"):
        normalized = normalized[len("skill_"):]
    return normalized.replace("_", " ").strip()


def _extract_keywords_from_profile(profile: Dict[str, Dict[str, float]]) -> List[tuple[str, float]]:
    """
    Extrait les keywords du profil avec leurs scores.
    Format: [("computer science", 0.8), ("technical", 0.7), ...]
    """
    keywords = []

    domains = profile.get("domains", {})
    print(f"[PROA DEBUG] Profile domains: {domains if isinstance(domains, dict) else 'NOT A DICT'}")
    if isinstance(domains, dict):
        for key, value in domains.items():
            normalized_key = _normalize_profile_keyword(key)
            keywords.append((normalized_key, value))

    skills = profile.get("skills", {})
    print(f"[PROA DEBUG] Profile skills: {skills if isinstance(skills, dict) else 'NOT A DICT'}")
    if isinstance(skills, dict):
        for key, value in skills.items():
            normalized_key = _normalize_profile_keyword(key)
            keywords.append((normalized_key, value))

    deduped_keywords: dict[str, float] = {}
    for k, v in keywords:
        if v > 0.0:
            deduped_keywords[k] = max(deduped_keywords.get(k, 0.0), v)
    result = list(deduped_keywords.items())
    print(f"[PROA DEBUG] Final keywords: {result}")
    return result


def _normalize_vector(vector: Dict[str, float]) -> Dict[str, float]:
    total = sum(vector.values())
    if total <= 0:
        if not vector:
            return {}
        return {dim: 1.0 / len(vector) for dim in vector}
    return {dim: value / total for dim, value in vector.items()}


def _vector_dot(a: Dict[str, float], b: Dict[str, float]) -> float:
    return sum(a.get(dim, 0.0) * b.get(dim, 0.0) for dim in a)


def _euclidean_distance(a: Dict[str, float], b: Dict[str, float]) -> float:
    return math.sqrt(sum((a.get(dim, 0.0) - b.get(dim, 0.0)) ** 2 for dim in DIMENSIONS))


def _build_latent_traits(profile: Dict[str, Any]) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    inputs: List[tuple[str, float]] = []

    for source in ["domains", "skills"]:
        values = profile.get(source, {}) or {}
        if isinstance(values, dict):
            for key, value in values.items():
                normalized = _normalize_profile_keyword(key)
                inputs.append((normalized, float(value)))

    for trait, seeds in PROFILE_LATENT_TRAIT_SEEDS.items():
        weights[trait] = 0.0
        for term, value in inputs:
            normalized_term = term.lower().strip()
            if any(seed in normalized_term for seed in seeds):
                weights[trait] += value

    structure = weights.get("structure_positive", 0.0)
    freedom = weights.get("freedom_positive", 0.0)
    people = weights.get("people_positive", 0.0)
    systems = weights.get("systems_positive", 0.0)
    creation = weights.get("creation_positive", 0.0)
    analysis = weights.get("analysis_positive", 0.0)
    risk = weights.get("risk_tolerance", 0.0)

    layout = {}
    layout["risk_tolerance"] = max(-1.0, min(1.0, risk / max(1.0, abs(risk))))
    if structure + freedom > 0:
        layout["structure_vs_freedom"] = (freedom - structure) / max(1.0, structure + freedom)
    else:
        layout["structure_vs_freedom"] = 0.0
    if people + systems > 0:
        layout["people_vs_systems"] = (people - systems) / max(1.0, people + systems)
    else:
        layout["people_vs_systems"] = 0.0
    if creation + analysis > 0:
        layout["creation_vs_analysis"] = (creation - analysis) / max(1.0, creation + analysis)
    else:
        layout["creation_vs_analysis"] = 0.0

    return layout


def _apply_latent_traits_to_vector(raw_vector: Dict[str, float], traits: Dict[str, float]) -> Dict[str, float]:
    raw_vector = raw_vector.copy()

    raw_vector["flexibility"] += max(0.0, traits.get("risk_tolerance", 0.0)) * 0.12
    raw_vector["business"] += max(0.0, traits.get("risk_tolerance", 0.0)) * 0.08

    trait_sf = traits.get("structure_vs_freedom", 0.0)
    raw_vector["creativity"] += max(0.0, trait_sf) * 0.2
    raw_vector["flexibility"] += max(0.0, trait_sf) * 0.1
    raw_vector["expertise"] += max(0.0, -trait_sf) * 0.15
    raw_vector["business"] += max(0.0, -trait_sf) * 0.05

    trait_ps = traits.get("people_vs_systems", 0.0)
    raw_vector["social"] += max(0.0, trait_ps) * 0.18
    raw_vector["impact"] += max(0.0, trait_ps) * 0.08
    raw_vector["tech"] += max(0.0, -trait_ps) * 0.15
    raw_vector["expertise"] += max(0.0, -trait_ps) * 0.08

    trait_ca = traits.get("creation_vs_analysis", 0.0)
    raw_vector["creativity"] += max(0.0, trait_ca) * 0.2
    raw_vector["social"] += max(0.0, trait_ca) * 0.08
    raw_vector["expertise"] += max(0.0, -trait_ca) * 0.15
    raw_vector["tech"] += max(0.0, -trait_ca) * 0.1

    return raw_vector


def _compute_dimension_contributions(profile_vector: Dict[str, float], field_vector: Dict[str, float]) -> Dict[str, float]:
    return {
        dim: profile_vector.get(dim, 0.0) * field_vector.get(dim, 0.0)
        for dim in DIMENSIONS
    }


def _build_profile_vector(profile: Dict[str, Any]) -> Dict[str, float]:
    raw_vector = {dim: 0.0 for dim in DIMENSIONS}
    inputs: List[tuple[str, float]] = []

    for source in ["domains", "skills"]:
        values = profile.get(source, {}) or {}
        if isinstance(values, dict):
            for key, value in values.items():
                normalized = _normalize_profile_keyword(key)
                inputs.append((normalized, float(value)))

    for term, value in inputs:
        normalized_term = term.lower().strip()
        for dim, seeds in PROFILE_DIMENSION_SEEDS.items():
            if any(seed in normalized_term for seed in seeds):
                raw_vector[dim] += value

    latent_traits = _build_latent_traits(profile)
    raw_vector = _apply_latent_traits_to_vector(raw_vector, latent_traits)

    return _normalize_vector(raw_vector)


def _build_field_vector(filiere: Dict[str, Any]) -> Dict[str, float]:
    raw_vector = {dim: 0.0 for dim in DIMENSIONS}
    normalized_name = _normalize_profile_keyword(filiere.get('nom', ''))
    text = f"{filiere.get('nom', '')} {filiere.get('description', '')}".lower()

    if normalized_name in FIELD_VECTOR_OVERRIDES:
        raw_vector.update(FIELD_VECTOR_OVERRIDES[normalized_name])
    else:
        for keyword, boost in FIELD_VECTOR_KEYWORD_OVERRIDES.items():
            if keyword in normalized_name or keyword in text:
                for dim, value in boost.items():
                    if dim in raw_vector:
                        raw_vector[dim] += value

        for dim, seeds in FIELD_DIMENSION_SEEDS.items():
            for seed in seeds:
                if seed in text:
                    raw_vector[dim] += 1.0

    if sum(raw_vector.values()) <= 0:
        cluster = _get_filiere_cluster(filiere.get('nom', ''))
        if cluster == 'informatique':
            raw_vector['tech'] += 1.0
            raw_vector['expertise'] += 0.4
        elif cluster == 'business':
            raw_vector['business'] += 1.0
            raw_vector['international'] += 0.3
        elif cluster == 'social':
            raw_vector['social'] += 1.0
            raw_vector['impact'] += 0.3
        elif cluster == 'arts_design' or cluster == 'génie_civil' or cluster == 'électronique':
            raw_vector['creativity'] += 0.8
            raw_vector['flexibility'] += 0.25
        elif cluster == 'santé':
            raw_vector['impact'] += 1.0
            raw_vector['expertise'] += 0.3
        else:
            raw_vector['flexibility'] += 0.6
            raw_vector['expertise'] += 0.4

    return _normalize_vector(raw_vector)


def _build_cluster_frequency_weights(cluster_counts: Dict[str, int], total: int) -> Dict[str, float]:
    if total <= 0:
        return {}
    mean_share = 1.0 / max(1, len(cluster_counts))
    weights: Dict[str, float] = {}
    for cluster, count in cluster_counts.items():
        share = count / total
        penalty = max(0.75, 1.0 - 0.3 * max(0.0, share - mean_share) / (1.0 - mean_share))
        weights[cluster] = penalty
    return weights


def _describe_contributions(profile_vector: Dict[str, float], field_vector: Dict[str, float]) -> List[tuple[str, float]]:
    contributions = {
        dim: profile_vector.get(dim, 0.0) * field_vector.get(dim, 0.0)
        for dim in DIMENSIONS
    }
    return sorted(contributions.items(), key=lambda item: item[1], reverse=True)


# ==================================================
# CLUSTER BUSINESS LOGIC FUNCTIONS
# ==================================================

def _get_filiere_cluster(filiere_name: str) -> str:
    """
    Détermine le cluster métier d'une filière.
    Retourne le nom du cluster ou "unknown" si non trouvé.
    """
    filiere_lower = filiere_name.lower().strip()
    
    for cluster_name, filieres in FIELD_CLUSTERS.items():
        for cluster_filiere in filieres:
            if cluster_filiere.lower() in filiere_lower or filiere_lower in cluster_filiere.lower():
                return cluster_name
    
    print(f"[PROA] Unknown cluster for filiere: {filiere_name}")
    return "unknown"


def _detect_dominant_cluster(keywords: List[tuple[str, float]]) -> str | None:
    """
    Détecte le cluster métier dominant basé sur les keywords du profil.
    Retourne le cluster avec le score le plus élevé, ou None si le profil est ambigu.
    """
    cluster_scores = {}
    
    for keyword, score in keywords:
        keyword_lower = keyword.lower().strip()
        
        # Chercher dans tous les clusters
        for cluster_name, filieres in FIELD_CLUSTERS.items():
            matched = False
            for cluster_filiere in filieres:
                if cluster_filiere.lower() in keyword_lower or keyword_lower in cluster_filiere.lower():
                    cluster_scores[cluster_name] = cluster_scores.get(cluster_name, 0) + score
                    matched = True
                    break
            if matched:
                continue

            # Vérifier les synonymes spécifiques par cluster
            synonyms = FIELD_CLUSTER_SYNONYMS.get(cluster_name, [])
            if any(syn in keyword_lower for syn in synonyms):
                weight = 0.9
                if keyword_lower in GENERIC_CLUSTER_TERMS:
                    weight = 0.35
                cluster_scores[cluster_name] = cluster_scores.get(cluster_name, 0) + score * weight
                continue

    if not cluster_scores:
        print("[PROA] No cluster detected, using neutral cluster None")
        return None

    sorted_scores = sorted(cluster_scores.items(), key=lambda x: x[1], reverse=True)
    top_cluster, top_score = sorted_scores[0]
    second_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0
    ratio = top_score / max(second_score, 0.0001)
    
    # Seuil minimal pour éviter une décision de cluster trop faible ou trop proche
    if top_score < 0.5 or (len(sorted_scores) > 1 and ratio < 1.3):
        print(f"[PROA] Cluster ambiguous (top={top_score:.3f}, second={second_score:.3f}, ratio={ratio:.3f}), using neutral None")
        print(f"[PROA] All cluster scores: {cluster_scores}")
        return None

    print(f"[PROA] Dominant cluster: {top_cluster} (score: {top_score:.3f})")
    print(f"[PROA] All cluster scores: {cluster_scores}")
    return top_cluster


def _filter_filieres_by_cluster(filieres: List[Dict[str, Any]], dominant_cluster: str) -> List[Dict[str, Any]]:
    """
    Filtre les filières pour garder seulement celles du cluster dominant.
    Applique une pénalité aux filières hors cluster.
    """
    filtered = []
    
    for filiere in filieres:
        filiere_name = filiere.get("nom", "").lower().strip()
        filiere_cluster = _get_filiere_cluster(filiere_name)
        
        if dominant_cluster is None:
            # Aucun cluster dominant clair : ne pas favoriser une filière spécifique
            filiere["cluster_bonus"] = 1.0
            filtered.append(filiere)
            continue
        
        if filiere_cluster == dominant_cluster:
            # Bonus pour les filières du cluster dominant
            filiere["cluster_bonus"] = 1.0
            filtered.append(filiere)
        elif filiere_cluster == "unknown":
            # Garder les filières inconnues avec une pénalité très légère
            filiere["cluster_bonus"] = 0.9
            filtered.append(filiere)
        else:
            # Ne pas écarter complètement les filières hors cluster
            filiere["cluster_bonus"] = 0.85
            filtered.append(filiere)
    
    print(f"[PROA] Filtered {len(filtered)}/{len(filieres)} filieres for cluster '{dominant_cluster}'")
    return filtered


def _compute_filiere_score(
    filiere: Dict[str, Any],
    profile_vector: Dict[str, float],
    field_vector: Dict[str, float],
    cluster_weights: Dict[str, float],
    dominant_cluster: str | None,
) -> tuple[float, List[tuple[str, float]], float, float]:
    """
    Calcule un score de filière normalisé par vecteur avec distance métier.
    """
    raw_similarity = _vector_dot(profile_vector, field_vector)
    distance = _euclidean_distance(profile_vector, field_vector)
    distance_factor = 1.0 / (1.0 + distance)

    cluster = _get_filiere_cluster(filiere.get('nom', ''))
    cluster_weight = cluster_weights.get(cluster, 1.0)
    soft_cluster_boost = 1.05 if dominant_cluster and cluster == dominant_cluster else 1.0

    score = raw_similarity * distance_factor * cluster_weight * soft_cluster_boost
    score = min(1.0, max(0.0, score))

    contributions = _compute_dimension_contributions(profile_vector, field_vector)
    return score, contributions, raw_similarity, distance


def _select_diverse_recommendations(results: List[Dict[str, Any]], top_n: int = 5) -> List[Dict[str, Any]]:
    """Sélectionne un top N équilibré en respectant la diversité de cluster."""
    if not results:
        return []

    results = sorted(results, key=lambda r: r["score"], reverse=True)
    selected: List[Dict[str, Any]] = []
    cluster_counts: Dict[str, int] = {}
    max_per_cluster = max(1, math.floor(top_n * 0.5))
    min_clusters = min(2, len({r["cluster"] for r in results}), top_n)

    cluster_candidates: Dict[str, List[Dict[str, Any]]] = {}
    for item in results:
        cluster_candidates.setdefault(item["cluster"], []).append(item)

    # Assurer une représentation minimale par cluster
    cluster_order = sorted(
        cluster_candidates.items(),
        key=lambda entry: entry[1][0]["score"],
        reverse=True,
    )
    for cluster, items in cluster_order[:min_clusters]:
        if len(selected) >= top_n:
            break
        selected.append(items[0])
        cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1

    # Remplir le top N avec les meilleurs restants en respectant le plafond de cluster
    for item in results:
        if len(selected) >= top_n:
            break
        cluster = item["cluster"]
        if cluster_counts.get(cluster, 0) >= max_per_cluster:
            continue
        if item in selected:
            continue
        selected.append(item)
        cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1

    # Si le top final est trop homogène, forcer une deuxième cluster
    selected_clusters = {item["cluster"] for item in selected}
    if len(selected_clusters) < 2:
        alternate = next((item for item in results if item["cluster"] not in selected_clusters), None)
        if alternate and len(selected) >= 1:
            for i in range(len(selected) - 1, -1, -1):
                if cluster_counts.get(selected[i]["cluster"], 0) > 1:
                    old_cluster = selected[i]["cluster"]
                    selected[i] = alternate
                    cluster_counts[old_cluster] -= 1
                    cluster_counts[alternate["cluster"]] = cluster_counts.get(alternate["cluster"], 0) + 1
                    break

    # Ajouter une exploration contrôlée depuis un cluster non encore présent
    for item in results:
        if len(selected) >= top_n:
            break
        if item in selected:
            continue
        if item["cluster"] not in selected_clusters:
            selected.append(item)
            break

    return selected[:top_n]


def _build_profile_insight(profile: Dict[str, Any]) -> str:
    domains = profile.get("domains", {}) or {}
    skills = profile.get("skills", {}) or {}

    top_domain = None
    if domains:
        top_domain = max(domains.items(), key=lambda p: p[1])[0]
        top_domain = _normalize_profile_keyword(top_domain)

    top_skills = [k for k, v in sorted(skills.items(), key=lambda p: p[1], reverse=True) if v > 0.3]
    top_skills = [_normalize_profile_keyword(k) for k in top_skills[:2]]

    if top_domain and top_skills:
        return (
            f"Tu montres une forte affinité avec {top_domain}, "
            f"notamment grâce à tes compétences en {', '.join(top_skills)}."
        )
    if top_domain:
        return f"Tu montres une forte affinité avec {top_domain}."
    if top_skills:
        return f"Tes compétences en {', '.join(top_skills)} ressortent clairement."
    return "Ton profil montre une orientation équilibrée vers plusieurs domaines."


def compute_recommended_fields(profile: Dict[str, Any], top_n: int = 5) -> Dict[str, Any]:
    """
    Calcule les filières recommandées en fetchant depuis SUPABASE (pas JSON statique).
    
    ✅ ARCHITECTURE DYNAMIQUE:
    - Récupère les ~200 filières réelles de Supabase
    - Score chacune basée sur le profil utilisateur
    - Retourne les top 5 avec scores + raisons

    ✅ FORMAT STANDARDISÉ POUR PORA:
    - field_name: Nom lisible (ex: "Génie Informatique")
    - score: Score de recommandation (0.0-1.0)
    - reason: Explication du matching
    - category: "Supabase" (pour différencier du JSON legacy)

    Args:
        profile: dict avec clés `domains` et `skills`, chacune mappée key->score (0..1).
        top_n: nombre max de filières retournées.

    Returns:
        {"recommended_fields": [
            {
                "field_name": "Génie Informatique",
                "score": 0.92,
                "reason": "Match: computer_science (0.8) + technical (0.7)",
                "category": "Supabase"
            }
        ]}
    """
    # Étape 1: Récupérer toutes les filières réelles de Supabase
    filieres = _fetch_filieres_from_db()
    print(f"[PROA] Fetched {len(filieres) if filieres else 0} filieres from Supabase")
    if not filieres:
        print("[PROA] No filieres returned from Supabase - using empty fallback")
        # Fallback: return empty list only if DB completely fails
        return {
            "recommended_fields": [],
            "field_scores": {},
            "insight": "Aucune filière disponible pour le moment."
        }
    
    # Étape 2: Construire le vecteur profile normalisé
    print(f"[PROA] Profile input: {profile}")
    profile_keywords = _extract_keywords_from_profile(profile)
    profile_vector = _build_profile_vector(profile)
    print(f"[PROA] Profile vector: {profile_vector}")
    dominant_cluster = _detect_dominant_cluster(profile_keywords)
    print(f"[PROA] Dominant cluster: {dominant_cluster}")

    # Étape 3: Construire les vecteurs de filières et calculer le score
    results: List[Dict[str, Any]] = []
    all_scores: List[tuple[str, float]] = []
    raw_scores: List[tuple[str, float]] = []

    candidate_fields: List[Dict[str, Any]] = []
    for filiere in filieres:
        field_vector = _build_field_vector(filiere)
        field_cluster = _get_filiere_cluster(filiere.get('nom', 'Unknown'))
        candidate_fields.append({
            "filiere": filiere,
            "field_vector": field_vector,
            "cluster": field_cluster,
        })

    cluster_counts = Counter(candidate["cluster"] for candidate in candidate_fields)
    cluster_weights = _build_cluster_frequency_weights(cluster_counts, len(candidate_fields))
    print(f"[PROA] Cluster counts: {cluster_counts}")
    print(f"[PROA] Cluster weights: {cluster_weights}")

    MIN_SCORE = 0.25
    for candidate in candidate_fields:
        filiere = candidate["filiere"]
        field_vector = candidate["field_vector"]
        cluster = candidate["cluster"]
        score, contributions, raw_similarity, distance = _compute_filiere_score(
            filiere,
            profile_vector,
            field_vector,
            cluster_weights,
            dominant_cluster,
        )

        filiere_nom = filiere.get('nom', 'Unknown')
        all_scores.append((filiere_nom, score))
        raw_scores.append((filiere_nom, raw_similarity))

        contribution_list = sorted(contributions.items(), key=lambda item: item[1], reverse=True)
        reasons = [
            f"{dim} ({value:.0%})"
            for dim, value in contribution_list
            if value > 0
        ][:3]
        reason = " + ".join(reasons) if reasons else "Profil adapté"
        reason = f"{reason} | distance métier {distance:.2f}" if reason else f"Distance métier {distance:.2f}"

        results.append({
            "field_name": filiere_nom,
            "score": round(score, 4),
            "reason": reason,
            "category": "Supabase",
            "cluster": cluster,
            "distance": round(distance, 4),
            "similarity": round(raw_similarity, 4),
            "contributions": contribution_list,
        })

    # 📊 DEBUG OBLIGATOIRE
    print("=== PROA DEBUG ===")
    print("Profile keywords:", profile_keywords)
    print("Profile vector:", profile_vector)
    print("Cluster counts:", cluster_counts)
    print("Raw scores:")
    for name, score in sorted(raw_scores, key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {name} -> {score:.3f}")
    print("Final scores:")
    for name, score in sorted(all_scores, key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {name} -> {score:.3f}")

    filtered = [r for r in results if r["score"] >= MIN_SCORE]
    filtered = sorted(filtered, key=lambda r: r["score"], reverse=True)
    print(f"[PROA] Filieres retenues après seuil {MIN_SCORE}: {len(filtered)}")

    # ✅ Profil narratif
    insight = _build_profile_insight(profile)

    # ✅ FALLBACK INTELLIGENT: Si aucun match du tout
    if not results:
        print("[PROA] No filières matched! Using FALLBACK recommendations...")
        fallback_filieres = filieres[:top_n]
        results = [
            {
                "field_name": f.get("nom", "Unknown"),
                "score": 0.1,
                "reason": "Fallback recommendation (no keyword matches)",
                "category": "fallback"
            }
            for f in fallback_filieres
        ]
        print(f"[PROA] Fallback: returning {len(results)} random filieres")
    
    # Étape 4: Construire un top diversifié avec la fonction dédiée
    final: List[Dict[str, Any]] = _select_diverse_recommendations(filtered, top_n)

    # Compléter si nécessaire avec les meilleurs restants
    for item in filtered:
        if len(final) >= top_n:
            break
        if item not in final:
            final.append(item)

    # ✅ ULTIMATE GUARANTEE: Si moins de top_n résultats, padding avec fallback
    if len(final) < top_n:
        print(f"[PROA] Only {len(final)} results after diversity selection, need {top_n}. Adding padding fallback...")
        used_field_names = {r["field_name"] for r in final}
        available_filieres = [f for f in filieres if f.get("nom", "") not in used_field_names]
        padding_needed = top_n - len(final)
        for filiere in available_filieres[:padding_needed]:
            final.append({
                "field_name": filiere.get("nom", ""),
                "score": 0.05,
                "reason": "Fallback padding",
                "category": "fallback"
            })
        print(f"[PROA] Added {padding_needed} padding items")

    field_scores = {item["field_name"]: item["score"] for item in final}

    print(f"[PROA] FINAL RESULT: {len(final)} recommended fields (guaranteed >= {top_n})")
    print(f"[PROA] Fields: {[f['field_name'] for f in final]}")
    return {
        "recommended_fields": final,
        "field_scores": field_scores,
        "insight": insight,
    }


def compute_recommended_institutions(profile: Dict[str, Any], top_n: int = 5) -> Dict[str, List[Dict[str, Any]]]:
    """
    DEPRECATED: Les institutions sont recommandées par PORA, pas PROA.
    Cette fonction est conservée pour compatibilité backwards.
    """
    return {"recommended_institutions": []}


if __name__ == "__main__":
    # petit test local rapide
    sample_profile = {
        "domains": {"computer_science": 0.8, "technical": 0.7, "logic": 0.75, "marketing": 0.2},
        "skills": {}
    }
    print(json.dumps(compute_recommended_fields(sample_profile, top_n=5), ensure_ascii=False, indent=2))
