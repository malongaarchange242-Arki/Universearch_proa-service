"""
=============================================================
🎯 CAREER RECOMMENDATIONS ENGINE
=============================================================
Transforms quiz responses into career recommendations.
Part of PROA microservice.
"""

import json
import math
from typing import Dict, List, Tuple, Any
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# =============================================================
# DIMENSION METADATA
# =============================================================

DIMENSIONS_METADATA = {
    "logique": {"emoji": "🧠", "label": "Logique", "color": "#3B82F6"},
    "tech": {"emoji": "💻", "label": "Technique", "color": "#10B981"},
    "analyse": {"emoji": "📊", "label": "Analyse", "color": "#8B5CF6"},
    "créativité": {"emoji": "🎨", "label": "Créativité", "color": "#EC4899"},
    "social": {"emoji": "🤝", "label": "Social", "color": "#F59E0B"},
    "leadership": {"emoji": "👑", "label": "Leadership", "color": "#EF4444"},
    "business": {"emoji": "💼", "label": "Business", "color": "#06B6D4"},
    "initiative": {"emoji": "🚀", "label": "Initiative", "color": "#14B8A6"},
    "empathie": {"emoji": "💝", "label": "Empathie", "color": "#F97316"},
    "attention-détail": {"emoji": "🔍", "label": "Attention au détail", "color": "#64748B"},
}

# =============================================================
# USER TYPE CONTEXT & WEIGHTS
# =============================================================

USER_TYPE_CONTEXT = {
    "bachelier": {
        "focus_area": "filières",
        "recommendation_depth": "surface",
        "guidance_tone": "suggestive",
        "dimension_weights": {
            "filieres": 1.0,
            "metiers": 0.6,
            "specialisation": 0.2,
            "experience": 0.3,
            "stabilite": 0.4
        },
        "description": "Explore plusieurs domaines avant de choisir"
    },
    "étudiant": {
        "focus_area": "métiers",
        "recommendation_depth": "moderate",
        "guidance_tone": "directive",
        "dimension_weights": {
            "metiers": 1.0,
            "specialisation": 0.9,
            "experience": 0.8,
            "stabilite": 0.6,
            "filieres": 0.5
        },
        "description": "Se spécialiser et préparer son insertion"
    },
    "parent": {
        "focus_area": "guidance",
        "recommendation_depth": "deep",
        "guidance_tone": "educational",
        "dimension_weights": {
            "explication": 1.0,
            "stabilite": 0.9,
            "confiance": 0.8,
            "debouches": 0.8,
            "metiers": 0.7
        },
        "description": "Comprendre et guider le profil"
    }
}

# =============================================================
# RESPONSE VALUE → SCORE MAPPING
# =============================================================

def response_to_score(option_value: int) -> float:
    """
    Convert quiz option (1-4) to score (0.0-1.0).
    1 = ❌ Pas du tout    (0.0)
    2 = 😕 Un peu          (0.33)
    3 = 🙂 Beaucoup       (0.66)
    4 = 🔥 Absolument     (1.0)
    """
    mapping = {
        1: 0.0,
        2: 0.33,
        3: 0.66,
        4: 1.0
    }
    return mapping.get(int(option_value), 0.0)


# =============================================================
# FETCH CAREER DATA FROM SUPABASE
# =============================================================

_CAREERS_CACHE: Dict[str, Any] | None = None

def fetch_career_profiles() -> Dict[str, Any]:
    """
    Récupère tous les profils de carrière avec leurs poids de dimensions.
    Cache le résultat pour éviter les requêtes répétées.
    """
    global _CAREERS_CACHE
    
    if _CAREERS_CACHE is not None:
        print(f"[CAREER] Using cached career profiles: {len(_CAREERS_CACHE)} careers")
        return _CAREERS_CACHE
    
    try:
        # Utiliser la VIEW career_profiles_with_weights
        url = f"{SUPABASE_URL}/rest/v1/career_profiles_with_weights"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        careers = response.json()
        
        # Transformer en dict pour accès rapide
        _CAREERS_CACHE = {c["slug"]: c for c in careers}
        
        print(f"[CAREER] Cached {len(_CAREERS_CACHE)} career profiles from Supabase")
        return _CAREERS_CACHE
        
    except Exception as e:
        print(f"[CAREER] Error fetching career profiles: {e}")
        return {}


def fetch_question_dimensions() -> Dict[str, List[str]]:
    """
    Récupère le mapping question_id → dimensions depuis Supabase.
    Table: orientation_quiz_question_dimensions
    """
    try:
        url = f"{SUPABASE_URL}/rest/v1/orientation_quiz_question_dimensions"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        mappings = response.json()
        # Transformer: [{question_id: "Q1", dimensions: ["logique"]}, ...]
        result = {}
        for row in mappings:
            q_id = row.get("question_id")
            dims = row.get("dimensions", [])
            if q_id:
                result[q_id] = dims
        
        print(f"[CAREER] Loaded {len(result)} question-dimension mappings")
        return result
        
    except Exception as e:
        print(f"[CAREER] Error fetching question dimensions: {e}")
        # Fallback: mappings par défaut
        return {}


def fetch_user_type_weights(user_type: str = "all") -> Dict[str, float]:
    """
    Récupère les poids contextuels pour un user_type spécifique.
    Fallback aux poids par défaut si user_type non trouvé.
    
    Args:
        user_type: 'all', 'bachelier', 'étudiant', 'parent'
    
    Returns:
        Dict[dimension: weight]
    """
    
    # Fallback aux contextes locaux
    if user_type in USER_TYPE_CONTEXT:
        weights = USER_TYPE_CONTEXT[user_type].get("dimension_weights", {})
        print(f"[CAREER] Using context weights for user_type='{user_type}':")
        for dim, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            print(f"  {dim}: {w}")
        return weights
    
    # Si user_type inconnu, utiliser contexte par défaut
    print(f"[CAREER] Unknown user_type '{user_type}', using default weights")
    return {}



# =============================================================
# CALCULATE DIMENSION SCORES
# =============================================================

def calculate_dimension_scores(
    quiz_responses: Dict[str, float],
    question_dimensions: Dict[str, List[str]]
) -> Dict[str, float]:
    """
    Calcule le score pour chaque dimension basé sur les réponses du quiz.
    
    Args:
        quiz_responses: {question_id: option_value}
        question_dimensions: {question_id: [dimension1, dimension2]}
    
    Returns:
        {dimension: score (0.0-1.0)}
    """
    
    dimension_scores = {}
    dimension_counts = {}
    
    print("[CAREER] Computing dimension scores...")
    
    for question_id, option_value in quiz_responses.items():
        # Convertir réponse en score
        response_score = response_to_score(option_value)
        
        # Récupérer les dimensions liées
        dimensions = question_dimensions.get(question_id, [])
        
        if not dimensions:
            print(f"  ⚠️ Question {question_id} has no dimensions")
            continue
        
        # Ajouter le score à chaque dimension
        for dimension in dimensions:
            if dimension not in dimension_scores:
                dimension_scores[dimension] = 0.0
                dimension_counts[dimension] = 0
            
            dimension_scores[dimension] += response_score
            dimension_counts[dimension] += 1
    
    # Normaliser (moyenne)
    for dimension in dimension_scores:
        count = dimension_counts.get(dimension, 1)
        if count > 0:
            dimension_scores[dimension] = dimension_scores[dimension] / count
    
    print("[CAREER] Dimension scores computed:")
    for dim, score in sorted(dimension_scores.items(), key=lambda x: x[1], reverse=True):
        emoji = DIMENSIONS_METADATA.get(dim, {}).get("emoji", "")
        print(f"  {emoji} {dim}: {score:.2f}")
    
    return dimension_scores


# =============================================================
# SCORE INDIVIDUAL CAREER
# =============================================================

def score_career(
    career: Dict[str, Any],
    dimension_scores: Dict[str, float]
) -> float:
    """
    Calcule le score d'une carrière pour l'utilisateur.
    Score = somme(user_dimension_score × career_dimension_weight) / total_weights
    
    Args:
        career: {id, name, dimensions: [{dimension, weight}, ...]}
        dimension_scores: {dimension: score}
    
    Returns:
        float: Score de 0.0 à 1.0
    """
    
    dimensions = career.get("dimensions", [])
    if not dimensions:
        return 0.0
    
    total_score = 0.0
    total_weight = 0.0
    
    for dim_obj in dimensions:
        dimension = dim_obj.get("dimension")
        weight = dim_obj.get("weight", 0.5)
        
        # Score utilisateur pour cette dimension
        user_score = dimension_scores.get(dimension, 0.0)
        
        # Contribution = score × poids
        contribution = user_score * weight
        total_score += contribution
        total_weight += weight
    
    # Normaliser
    if total_weight > 0:
        normalized_score = total_score / total_weight
    else:
        normalized_score = 0.0
    
    return min(1.0, max(0.0, normalized_score))


# =============================================================
# COMPUTE ALL CAREER SCORES
# =============================================================

def compute_career_scores(
    dimension_scores: Dict[str, float],
    careers: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Score tous les profils de carrière et les trier par score.
    """
    
    career_scores = []
    
    for slug, career in careers.items():
        score = score_career(career, dimension_scores)
        
        career_scores.append({
            "id": career.get("id"),
            "name": career.get("name"),
            "slug": slug,
            "score": score,
            "icon": career.get("icon", ""),
            "category": career.get("category", ""),
            "description": career.get("description", ""),
            "related_filieres": career.get("related_filieres", []),
            "dimensions": career.get("dimensions", [])
        })
    
    # Trier par score DESC
    career_scores.sort(key=lambda x: x["score"], reverse=True)
    
    print("[CAREER] Career rankings:")
    for i, c in enumerate(career_scores[:5], 1):
        print(f"  {i}. {c['name']}: {c['score']:.2f}")
    
    return career_scores


# =============================================================
# FIND STRENGTHS (TOP DIMENSIONS)
# =============================================================

def find_strengths(dimension_scores: Dict[str, float], top_n: int = 4) -> List[Dict[str, Any]]:
    """
    Identifie les forces (dimensions > 0.50 au lieu de 0.70).
    Seuil ajusté pour plus de réalisme.
    """
    
    strengths = []
    
    for dimension, score in dimension_scores.items():
        if score >= 0.50:  # 🔧 FIX: Seuil réduit de 0.70 à 0.50
            meta = DIMENSIONS_METADATA.get(dimension, {})
            strengths.append({
                "dimension": dimension,
                "score": score,
                "emoji": meta.get("emoji", ""),
                "label": meta.get("label", dimension),
                "color": meta.get("color", "")
            })
    
    # Trier par score DESC
    strengths.sort(key=lambda x: x["score"], reverse=True)
    
    # Retourner top N
    return strengths[:top_n]


# =============================================================
# GENERATE PERSONALIZED MESSAGE
# =============================================================

def generate_message(top_career: Dict[str, Any], strengths: List[Dict[str, Any]], user_type: str = "all") -> str:
    """
    Génère un message personnalisé basé sur le profil découvert et le user_type.
    
    Args:
        top_career: Meilleure carrière recommandée
        strengths: Liste des dimensions fortes
        user_type: 'all', 'bachelier', 'étudiant', 'parent'
    
    Returns:
        Message personnalisé
    """
    
    career_name = top_career.get("name", "Unknown")
    score = top_career.get("score", 0.0)
    strength_names = " et ".join([s["label"] for s in strengths[:2]])
    
    if user_type == "bachelier":
        # Message pour bacheliers: exploratoire, léger
        if score >= 0.75:  # 🔧 FIX: Seuil réduit de 0.85 à 0.75
            prefix = "🎯 Perspective extraordinaire!"
            confidence = "tu as absolument le profil idéal"
        elif score >= 0.60:  # 🔧 FIX: Seuil réduit de 0.75 à 0.60
            prefix = "📚 Excellent découverte!"
            confidence = "tu as un profil solide"
        else:
            prefix = "🌳 À explorer!"
            confidence = "tu devrais découvrir brièvement"
        
        message = f"""{prefix} {career_name} pourrait te captiver!
Ton profil montre une excellente préparation en {strength_names}.
Explore les formations dans ce domaine et vois si c'est ton chemin.
"""
    
    elif user_type == "étudiant":
        # Message pour étudiants: orienté métier et spécialisation
        if score >= 0.75:  # 🔧 FIX: Seuil réduit de 0.85 à 0.75
            prefix = "🔥 Profil extraordinaire!"
            confidence = "tu as absolument le profil"
        elif score >= 0.60:  # 🔧 FIX: Seuil réduit de 0.75 à 0.60
            prefix = "✨ Excellent match!"
            confidence = "tu as un profil solide"
        else:
            prefix = "🎯 Bon potentiel"
            confidence = "tu as du potentiel"
        
        message = f"""{prefix} {career_name} te correspond très bien!
Tu devrais te spécialiser en {strength_names}.
Tes forces t'y prédisposent naturellement. Prépare-toi dès maintenant.
"""
    
    elif user_type == "parent":
        # Message pour parents: rassurant, explicatif
        if score >= 0.75:  # 🔧 FIX: Seuil réduit de 0.85 à 0.75
            prefix = "✅ Profil Excellent"
            stability = "très prometteur"
        elif score >= 0.60:  # 🔧 FIX: Seuil réduit de 0.75 à 0.60
            prefix = "✅ Profil Solide"
            stability = "prometteur"
        else:
            prefix = "✅ Profil Viable"
            stability = "possible"
        
        message = f"""{prefix}
Votre enfant a un profil {stability} pour {career_name}.
Ses forces principales: {strength_names}.
Encouragez-le à explorer les formations dans ce domaine et les stages.
"""
    
    else:  # user_type == "all" ou défaut
        if score >= 0.75:  # 🔧 FIX: Seuil réduit de 0.85 à 0.75
            prefix = "🔥 Profil extraordinaire!"
            confidence = "tu as absolument le profil"
        elif score >= 0.60:  # 🔧 FIX: Seuil réduit de 0.75 à 0.60
            prefix = "✨ Excellent match!"
            confidence = "tu has un profil solide"
        else:
            prefix = "👍 Possible"
            confidence = "tu pourrais explorer"
        
        message = f"""{prefix} {career_name} te correspond très bien!
Ton profil montre une force en {strength_names}, ce qui est essentiel pour cette carrière.
"""
    
    return message.strip()



# =============================================================
# MAIN PIPELINE
# =============================================================

def compute_career_recommendations(quiz_responses: Dict[str, float], user_type: str = "all") -> Dict[str, Any]:
    """
    Pipeline complet: réponses quiz → recommandations de carrière.
    Adapte les poids et les messages selon le user_type.
    
    Args:
        quiz_responses: {question_id: option_value}
        user_type: 'all', 'bachelier', 'étudiant', 'parent'
    
    Returns:
        {
            "recommended_career": {...},
            "top_3_careers": [...],
            "strengths": [...],
            "dimension_scores": {...},
            "message": "...",
            "user_type": "...",
            "context_metadata": {...}
        }
    """
    
    print("\n" + "="*60)
    print("🎯 CAREER RECOMMENDATIONS ENGINE")
    print(f"📍 User Type: {user_type}")
    print("="*60)
    
    # Étape 0: Valider user_type
    if user_type not in USER_TYPE_CONTEXT and user_type != "all":
        print(f"[WARNING] Unknown user_type '{user_type}', using 'all'")
        user_type = "all"
    
    # Étape 1: Récupérer les mappings question → dimensions
    question_dimensions = fetch_question_dimensions()
    
    # Étape 2: Calculer scores par dimension
    dimension_scores = calculate_dimension_scores(quiz_responses, question_dimensions)
    
    # Étape 3: Récupérer les poids contextuels du user_type
    user_type_weights = fetch_user_type_weights(user_type)
    
    # Étape 4: Récupérer tous les profils de carrière
    careers = fetch_career_profiles()
    
    if not careers:
        print("[CAREER] ⚠️ No careers found!")
        return {
            "status": "error",
            "message": "Aucune carrière disponible",
            "user_type": user_type
        }
    
    # Étape 5: Scorer toutes les carrières
    career_scores = compute_career_scores(dimension_scores, careers)
    
    # Étape 6: Identifier les forces
    strengths = find_strengths(dimension_scores)
    
    # Étape 7: Générer message contextuel
    top_career = career_scores[0] if career_scores else {}
    message = generate_message(top_career, strengths, user_type)
    
    # Étape 8: Récupérer contexte métadonnées
    context = USER_TYPE_CONTEXT.get(user_type, {}) if user_type != "all" else {}
    
    # Étape 9: Préparer réponse
    result = {
        "status": "success",
        "user_type": user_type,
        "context_metadata": {
            "focus_area": context.get("focus_area", "general"),
            "recommendation_depth": context.get("recommendation_depth", "surface"),
            "guidance_tone": context.get("guidance_tone", "suggestive"),
            "description": context.get("description", "")
        },
        "recommended_career": {
            "name": top_career.get("name"),
            "slug": top_career.get("slug"),
            "icon": top_career.get("icon"),
            "category": top_career.get("category"),
            "score": round(top_career.get("score", 0.0), 3),
            "match_quality": "Excellent" if top_career.get("score", 0) >= 0.65 else "Good" if top_career.get("score", 0) >= 0.45 else "Fair",  # 🔧 FIX: Seuils réduits
            "related_filieres": top_career.get("related_filieres", [])
        },
        "top_3_careers": [
            {
                "name": c.get("name"),
                "score": round(c.get("score", 0.0), 3),
                "icon": c.get("icon")
            }
            for c in career_scores[:3]
        ],
        "strengths": strengths,
        "dimension_scores": {k: round(v, 3) for k, v in dimension_scores.items()},
        "message": message,
        "all_careers_ranked": [
            {
                "name": c.get("name"),
                "slug": c.get("slug"),
                "score": round(c.get("score", 0.0), 3),
                "icon": c.get("icon"),
                "category": c.get("category")
            }
            for c in career_scores
        ]
    }
    
    print("\n" + "="*60)
    print("✅ Career recommendations computed successfully")
    print(f"📍 User Type: {user_type}")
    print("="*60 + "\n")
    
    return result
