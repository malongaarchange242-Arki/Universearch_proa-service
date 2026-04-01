import json
import os
from typing import Dict, List, Any
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# ==================================================
# SYNONYMS FOR BETTER MATCHING
# ==================================================
FIELD_SYNONYMS = {
    "technical": ["informatique", "tech", "technologie", "programmation", "development", "système"],
    "logic": ["logique", "algorithme", "algorithm", "mathématiques", "math", "algorithmique"],
    "creativity": ["créativité", "creative", "innovation", "design", "arts"],
    "teamwork": ["équipe", "team", "collaboration", "group", "travail"],
    "entrepreneurship": ["entrepreneuriat", "startup", "business", "commerce", "entreprise"],
    "communication": ["communication", "dialogue", "language", "rhetorique", "présentation"],
    "leadership": ["leadership", "direction", "management", "gestion", "pilotage"],
    "analysis": ["analyse", "analysis", "analytique", "statistique", "data"],
    "data": ["données", "data", "database", "base", "analytics", "statistique"],
    "web": ["web", "internet", "frontend", "backend", "développement web"],
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
        print(f"✅ [PROA] Using cached filieres: {len(_FILIERES_CACHE)} items")
        return _FILIERES_CACHE
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/filieres"
        print(f"🔗 [PROA] Fetching from Supabase: {url}")
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        params = {
            "select": "id,nom,description",
            "limit": "9999"
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        print(f"📊 [PROA] Supabase response status: {response.status_code}")
        response.raise_for_status()
        
        _FILIERES_CACHE = response.json()
        print(f"✅ [PROA] Cached {len(_FILIERES_CACHE)} filieres from Supabase")
        return _FILIERES_CACHE
        
    except Exception as e:
        print(f"❌ [PROA] Error fetching filieres: {e}")
        return []


def _extract_keywords_from_profile(profile: Dict[str, Dict[str, float]]) -> List[tuple[str, float]]:
    """
    Extrait les keywords du profil avec leurs scores.
    Format: [("computer_science", 0.8), ("technical", 0.7), ...]
    
    ✅ FALLBACK: Si aucun keyword, retourne fallback keywords par défaut
    """
    keywords = []
    
    domains = profile.get("domains", {})
    print(f"🔍 [DEBUG] Profile domains: {domains if isinstance(domains, dict) else 'NOT A DICT'}")
    if isinstance(domains, dict):
        keywords.extend(domains.items())
    
    skills = profile.get("skills", {})
    print(f"🔍 [DEBUG] Profile skills: {skills if isinstance(skills, dict) else 'NOT A DICT'}")
    if isinstance(skills, dict):
        keywords.extend(skills.items())
    
    result = [(k.replace("_", " "), v) for k, v in keywords if v > 0.3]
    print(f"🔍 [DEBUG] Final keywords (score > 0.3): {result}")
    
    # ✅ FALLBACK CRITIQUE: Si aucun keyword extracté, utiliser defaults
    if not result:
        print("⚠️ [PROA] No keywords extracted! Using fallback keywords")
        FALLBACK_KEYWORDS = [
            ("informatique", 0.7),
            ("gestion", 0.6),
            ("marketing", 0.5),
            ("engineering", 0.7),
            ("technique", 0.6),
            ("business", 0.5)
        ]
        result = FALLBACK_KEYWORDS
        print(f"✅ [PROA] Fallback keywords applied: {result}")
    
    return result


def _compute_filiere_score(filiere: Dict[str, Any], keywords: List[tuple[str, float]]) -> float:
    """
    Calcule un score de match entre une filière et les keywords du profil.
    
    ✅ AMÉLIORATIONS:
    - Synonymes pour meilleur matching
    - Substring matching (pas juste exact),
    - Poids augmentés pour meilleur signal
    - Range 0.0-1.0
    """
    if not keywords:
        return 0.0
    
    filiere_text = (
        f"{filiere.get('nom', '')} {filiere.get('description', '')}".lower()
    )
    
    matches: List[float] = []
    
    for keyword, keyword_score in keywords:
        keyword_lower = keyword.lower()
        match_weight = 0.0
        
        # 🎯 STRATÉGIE 1: Exact match dans nom (meilleur signal)
        if keyword_lower in filiere.get('nom', '').lower():
            match_weight = keyword_score * 1.5  # 🔥 Augmenté à 1.5x
        
        # 🎯 STRATÉGIE 2: Substring match dans nom (bon signal)
        elif keyword_lower in filiere_text:
            match_weight = keyword_score * 1.0
        
        # 🎯 STRATÉGIE 3: Synonymes (expansion)
        else:
            for synonym_group, synonyms in FIELD_SYNONYMS.items():
                if keyword_lower in synonyms or keyword_lower == synonym_group:
                    # Chercher n'importe quel synonyme dans la filière
                    for syn in synonyms:
                        if syn in filiere_text:
                            match_weight = keyword_score * 1.2  # 🔥 Bonus synonyme
                            break
                    if match_weight > 0:
                        break
        
        if match_weight > 0:
            matches.append(match_weight)
    
    if not matches:
        return 0.0
    
    # ✅ Normaliser: divise par len(matches) pour éviter penaliser les non-matchs
    avg_score = sum(matches) / len(matches)
    return min(1.0, max(0.0, avg_score))


def compute_recommended_fields(profile: Dict[str, Any], top_n: int = 5) -> Dict[str, List[Dict[str, Any]]]:
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
    print(f"🔍 [PROA] Fetched {len(filieres) if filieres else 0} filieres from Supabase")
    if not filieres:
        print("❌ [PROA] No filieres returned from Supabase - using empty fallback")
        # Fallback: return empty list only if DB completely fails
        return {"recommended_fields": []}
    
    # Étape 2: Extraire les keywords du profil avec leurs scores
    print(f"🔍 [PROA] Profile input: {profile}")
    keywords = _extract_keywords_from_profile(profile)
    print(f"🔍 [PROA] Extracted {len(keywords)} keywords from profile: {keywords}")
    # NOTE: keywords is NEVER empty now due to fallback in _extract_keywords_from_profile
    
    # Étape 3: Scorer chaque filière
    results: List[Dict[str, Any]] = []
    all_scores: List[tuple[str, float]] = []  # Pour debug
    score_distribution = {"high": 0, "medium": 0, "low": 0}  # Stats
    
    for filiere in filieres:
        score = _compute_filiere_score(filiere, keywords)
        filiere_nom = filiere.get('nom', 'Unknown')
        all_scores.append((filiere_nom, score))
        
        # Track distribution
        if score >= 0.5:
            score_distribution["high"] += 1
        elif score >= 0.2:
            score_distribution["medium"] += 1
        else:
            score_distribution["low"] += 1
        
        # ✅ FIX: Seuil baissé de 0.4 à 0.2 (données réelles sont bruitées)
        if score >= 0.2:
            # Générer une raison lisible
            matched_keywords = [
                f"{kw.title()} ({s:.0%})"
                for kw, s in keywords 
                if kw.lower() in f"{filiere.get('nom', '')} {filiere.get('description', '')}".lower()
            ]
            reason = " + ".join(matched_keywords[:3]) if matched_keywords else "Profil adapté"
            
            results.append({
                "field_name": filiere_nom,
                "score": round(score, 4),
                "reason": reason,
                "category": "Supabase"
            })
    
    # 📊 COMPREHENSIVE DEBUG LOGS
    print(f"📊 [PROA] Score distribution - high(≥0.5): {score_distribution['high']}, medium(0.2-0.5): {score_distribution['medium']}, low(<0.2): {score_distribution['low']}")
    
    top_scores = sorted(all_scores, key=lambda x: x[1], reverse=True)[:5]
    print(f"🔥 [PROA] TOP 5 SCORES: {[(name, f'{score:.3f}') for name, score in top_scores]}")
    print(f"📈 [PROA] Total filières avec score ≥ 0.2: {len(results)}")
    
    # ✅ FALLBACK INTELLIGENT: Si aucun match du tout
    if not results:
        print("⚠️ [PROA] No filières matched! Using FALLBACK recommendations...")
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
        print(f"✅ [PROA] Fallback: returning {len(results)} random filieres")
    
    # Étape 4: Trier et retourner top_n
    results.sort(key=lambda r: r["score"], reverse=True)
    top = results[:top_n]
    
    # ✅ ULTIMATE GUARANTEE: Si moins de top_n résultats, padding avec fallback
    if len(top) < top_n:
        print(f"⚠️ [PROA] Only {len(top)} results, need {top_n}. Adding padding fallback...")
        # Récupérer les filières non encore utilisées
        used_field_names = {r["field_name"] for r in top}
        available_filieres = [f for f in filieres if f.get("nom", "") not in used_field_names]
        
        padding_needed = top_n - len(top)
        for filiere in available_filieres[:padding_needed]:
            top.append({
                "field_name": filiere.get("nom", ""),
                "score": 0.05,
                "reason": "Fallback padding",
                "category": "fallback"
            })
        print(f"✅ [PROA] Added {len(top) - len(results)} padding items")
    
    print(f"🎯 [PROA] FINAL RESULT: {len(top)} recommended fields (guaranteed ≥ {top_n})")
    print(f"📋 [PROA] Fields: {[f['field_name'] for f in top]}")
    
    # ✅ ABSOLUTE CONTRACT: Never return empty or less than required
    assert len(top) >= min(top_n, len(filieres)), f"Contract violated: {len(top)} < {top_n}"
    
    return {"recommended_fields": top}


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
