"""
=============================================================
🎯 CAREER RECOMMENDATIONS ENGINE - VERSION 2.0
=============================================================
Transforme les réponses du quiz en recommandations de carrière.
Partie intégrante du scoring PROA V2 avec support bac congolais.
"""

import json
import math
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import requests
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# =============================================================
# DIMENSION METADATA (ENRICHIE)
# =============================================================

DIMENSIONS_METADATA = {
    "logique": {"emoji": "🧠", "label": "Logique", "color": "#3B82F6", "category": "cognitive"},
    "tech": {"emoji": "💻", "label": "Technique", "color": "#10B981", "category": "technical"},
    "analyse": {"emoji": "📊", "label": "Analyse", "color": "#8B5CF6", "category": "cognitive"},
    "créativité": {"emoji": "🎨", "label": "Créativité", "color": "#EC4899", "category": "artistic"},
    "social": {"emoji": "🤝", "label": "Social", "color": "#F59E0B", "category": "interpersonal"},
    "leadership": {"emoji": "👑", "label": "Leadership", "color": "#EF4444", "category": "interpersonal"},
    "business": {"emoji": "💼", "label": "Business", "color": "#06B6D4", "category": "professional"},
    "initiative": {"emoji": "🚀", "label": "Initiative", "color": "#14B8A6", "category": "personality"},
    "empathie": {"emoji": "💝", "label": "Empathie", "color": "#F97316", "category": "interpersonal"},
    "attention-détail": {"emoji": "🔍", "label": "Attention au détail", "color": "#64748B", "category": "cognitive"},
    "flexibility": {"emoji": "🔄", "label": "Flexibilité", "color": "#A855F7", "category": "personality"},
    "international": {"emoji": "🌍", "label": "International", "color": "#3B82F6", "category": "professional"},
    "expertise": {"emoji": "🎓", "label": "Expertise", "color": "#8B5CF6", "category": "professional"},
}

# =============================================================
# USER TYPE CONTEXT & WEIGHTS (V2 ENRICHIE)
# =============================================================

USER_TYPE_CONTEXT = {
    "bachelier": {
        "focus_area": "filières",
        "recommendation_depth": "surface",
        "guidance_tone": "suggestive",
        "include_alternatives": True,
        "dimension_weights": {
            "filieres": 1.0,
            "metiers": 0.6,
            "specialisation": 0.2,
            "experience": 0.3,
            "stabilite": 0.4
        },
        "description": "Explore plusieurs domaines avant de choisir",
        "message_template": "exploratory"
    },
    "étudiant": {
        "focus_area": "métiers",
        "recommendation_depth": "moderate",
        "guidance_tone": "directive",
        "include_alternatives": True,
        "dimension_weights": {
            "metiers": 1.0,
            "specialisation": 0.9,
            "experience": 0.8,
            "stabilite": 0.6,
            "filieres": 0.5
        },
        "description": "Se spécialiser et préparer son insertion",
        "message_template": "professional"
    },
    "parent": {
        "focus_area": "guidance",
        "recommendation_depth": "deep",
        "guidance_tone": "educational",
        "include_alternatives": False,
        "dimension_weights": {
            "explication": 1.0,
            "stabilite": 0.9,
            "confiance": 0.8,
            "debouches": 0.8,
            "metiers": 0.7
        },
        "description": "Comprendre et guider le profil",
        "message_template": "supportive"
    },
    "reconversion": {
        "focus_area": "carrière",
        "recommendation_depth": "deep",
        "guidance_tone": "encouraging",
        "include_alternatives": True,
        "dimension_weights": {
            "metiers": 1.0,
            "experience": 0.9,
            "specialisation": 0.7,
            "stabilite": 0.8,
            "debouches": 0.8
        },
        "description": "Valoriser l'expérience et identifier les passerelles",
        "message_template": "encouraging"
    }
}

# =============================================================
# RESPONSE VALUE → SCORE MAPPING (ÉTENDU À 1-5)
# =============================================================

def response_to_score(option_value: int) -> float:
    """
    Convertit la réponse du quiz (1-5) en score (0.0-1.0).
    1 = ❌ Pas du tout    (0.0)
    2 = 😕 Un peu          (0.25)
    3 = 🙂 Moyennement     (0.5)
    4 = 😊 Beaucoup       (0.75)
    5 = 🔥 Absolument     (1.0)
    """
    mapping = {
        1: 0.0,
        2: 0.25,
        3: 0.5,
        4: 0.75,
        5: 1.0
    }
    return mapping.get(int(option_value), 0.0)


# =============================================================
# MODÈLES DE DONNÉES
# =============================================================

@dataclass
class CareerScore:
    """Score pour une carrière"""
    id: str
    name: str
    slug: str
    score: float
    icon: str = ""
    category: str = ""
    description: str = ""
    related_filieres: List[str] = field(default_factory=list)
    dimensions: List[Dict[str, Any]] = field(default_factory=list)
    match_quality: str = "Fair"
    
    def __post_init__(self):
        if self.score >= 0.7:
            self.match_quality = "Excellent"
        elif self.score >= 0.5:
            self.match_quality = "Good"
        elif self.score >= 0.3:
            self.match_quality = "Fair"
        else:
            self.match_quality = "Low"


@dataclass
class Strength:
    """Force/dimension forte du profil"""
    dimension: str
    score: float
    emoji: str = ""
    label: str = ""
    color: str = ""
    category: str = ""
    
    def __post_init__(self):
        meta = DIMENSIONS_METADATA.get(self.dimension, {})
        self.emoji = meta.get("emoji", "")
        self.label = meta.get("label", self.dimension)
        self.color = meta.get("color", "")
        self.category = meta.get("category", "")


# =============================================================
# FETCH CAREER DATA FROM SUPABASE (AVEC CACHE V2)
# =============================================================

_CAREERS_CACHE: Optional[Dict[str, Any]] = None
_CAREERS_CACHE_TIMESTAMP: Optional[datetime] = None
_CACHE_TTL_SECONDS = 3600  # 1 heure


def fetch_career_profiles(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Récupère tous les profils de carrière avec leurs poids de dimensions.
    Version V2 avec cache intelligent et fallback.
    """
    global _CAREERS_CACHE, _CAREERS_CACHE_TIMESTAMP
    
    # Vérifier le cache
    if not force_refresh and _CAREERS_CACHE is not None and _CAREERS_CACHE_TIMESTAMP is not None:
        cache_age = (datetime.utcnow() - _CAREERS_CACHE_TIMESTAMP).total_seconds()
        if cache_age < _CACHE_TTL_SECONDS:
            print(f"[CAREER] Using cached career profiles: {len(_CAREERS_CACHE)} careers")
            return _CAREERS_CACHE
    
    try:
        # Utiliser la VIEW career_profiles_with_weights
        url = f"{SUPABASE_URL}/rest/v1/career_profiles_with_weights"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }
        params = {"select": "*", "limit": "500"}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        careers = response.json()
        
        # Transformer en dict pour accès rapide
        _CAREERS_CACHE = {c["slug"]: c for c in careers}
        _CAREERS_CACHE_TIMESTAMP = datetime.utcnow()
        
        print(f"[CAREER] Cached {len(_CAREERS_CACHE)} career profiles from Supabase")
        return _CAREERS_CACHE
        
    except Exception as e:
        print(f"[CAREER] Error fetching career profiles: {e}")
        # Fallback: retourner cache existant ou vide
        return _CAREERS_CACHE or {}


def fetch_question_dimensions() -> Dict[str, List[str]]:
    """
    Récupère le mapping question_id → dimensions depuis Supabase.
    Version améliorée avec fallback local.
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
        result = {}
        for row in mappings:
            q_id = row.get("question_id")
            dims = row.get("dimensions", [])
            if q_id:
                # Si dimensions est une chaîne JSON, la parser
                if isinstance(dims, str):
                    try:
                        dims = json.loads(dims)
                    except:
                        dims = []
                result[q_id] = dims
        
        print(f"[CAREER] Loaded {len(result)} question-dimension mappings")
        return result
        
    except Exception as e:
        print(f"[CAREER] Error fetching question dimensions: {e}")
        # Fallback: mappings par défaut pour les questions standard
        return _get_default_question_dimensions()


def _get_default_question_dimensions() -> Dict[str, List[str]]:
    """Fallback mappings par défaut."""
    return {
        "q1": ["logique", "analyse"],
        "q2": ["tech", "logique"],
        "q3": ["analyse", "attention-détail"],
        "q4": ["créativité", "initiative"],
        "q5": ["social", "empathie"],
        "q6": ["business", "leadership"],
        "q7": ["leadership", "initiative"],
        "q8": ["flexibility", "adaptability"],
        "q9": ["international", "business"],
        "q10": ["expertise", "analyse"],
    }


def fetch_user_type_weights(user_type: str = "all") -> Dict[str, float]:
    """
    Récupère les poids contextuels pour un user_type spécifique.
    Version V2 avec validation.
    """
    # Normaliser user_type
    user_type_normalized = user_type.lower().strip()
    
    # Fallback aux contextes locaux
    if user_type_normalized in USER_TYPE_CONTEXT:
        weights = USER_TYPE_CONTEXT[user_type_normalized].get("dimension_weights", {})
        print(f"[CAREER] Using context weights for user_type='{user_type_normalized}':")
        for dim, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            print(f"  {dim}: {w}")
        return weights
    
    # Si user_type inconnu, utiliser contexte par défaut
    print(f"[CAREER] Unknown user_type '{user_type}', using default weights")
    return {}


# =============================================================
# CALCULATE DIMENSION SCORES (V2)
# =============================================================

def calculate_dimension_scores(
    quiz_responses: Dict[str, float],
    question_dimensions: Dict[str, List[str]],
    dimension_weights: Optional[Dict[str, float]] = None
) -> Dict[str, float]:
    """
    Calcule le score pour chaque dimension basé sur les réponses du quiz.
    Version V2 avec pondération optionnelle.
    
    Args:
        quiz_responses: {question_id: option_value}
        question_dimensions: {question_id: [dimension1, dimension2]}
        dimension_weights: Poids supplémentaires par dimension
    
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
    
    # Appliquer les poids contextuels si fournis
    if dimension_weights:
        for dimension in dimension_scores:
            weight = dimension_weights.get(dimension, 1.0)
            dimension_scores[dimension] = min(1.0, dimension_scores[dimension] * weight)
    
    print("[CAREER] Dimension scores computed:")
    for dim, score in sorted(dimension_scores.items(), key=lambda x: x[1], reverse=True)[:10]:
        emoji = DIMENSIONS_METADATA.get(dim, {}).get("emoji", "")
        print(f"  {emoji} {dim}: {score:.2f}")
    
    return dimension_scores


# =============================================================
# SCORE INDIVIDUAL CAREER (V2)
# =============================================================

def score_career(
    career: Dict[str, Any],
    dimension_scores: Dict[str, float],
    confidence_adjustment: float = 1.0
) -> float:
    """
    Calcule le score d'une carrière pour l'utilisateur.
    Version V2 avec ajustement de confiance.
    
    Score = somme(user_dimension_score × career_dimension_weight) / total_weights
    
    Args:
        career: {id, name, dimensions: [{dimension, weight}, ...]}
        dimension_scores: {dimension: score}
        confidence_adjustment: Facteur d'ajustement (0.5-1.5)
    
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
    
    # Appliquer l'ajustement de confiance
    final_score = min(1.0, max(0.0, normalized_score * confidence_adjustment))
    
    return final_score


# =============================================================
# COMPUTE ALL CAREER SCORES (V2)
# =============================================================

def compute_career_scores(
    dimension_scores: Dict[str, float],
    careers: Dict[str, Any],
    confidence: float = 0.85,
    top_n: int = 10
) -> List[CareerScore]:
    """
    Score tous les profils de carrière et les trier par score.
    Version V2 avec objets structurés.
    """
    
    career_scores = []
    
    for slug, career in careers.items():
        score = score_career(career, dimension_scores, confidence_adjustment=confidence)
        
        career_scores.append(CareerScore(
            id=career.get("id", ""),
            name=career.get("name", slug),
            slug=slug,
            score=score,
            icon=career.get("icon", ""),
            category=career.get("category", ""),
            description=career.get("description", ""),
            related_filieres=career.get("related_filieres", []),
            dimensions=career.get("dimensions", [])
        ))
    
    # Trier par score DESC
    career_scores.sort(key=lambda x: x.score, reverse=True)
    
    print("[CAREER] Career rankings:")
    for i, c in enumerate(career_scores[:5], 1):
        print(f"  {i}. {c.name}: {c.score:.2f} ({c.match_quality})")
    
    return career_scores[:top_n]


# =============================================================
# FIND STRENGTHS (V2)
# =============================================================

def find_strengths(
    dimension_scores: Dict[str, float], 
    top_n: int = 5,
    threshold: float = 0.4
) -> List[Strength]:
    """
    Identifie les forces du profil (dimensions > threshold).
    Version V2 avec objets structurés.
    """
    
    strengths = []
    
    for dimension, score in dimension_scores.items():
        if score >= threshold:
            strengths.append(Strength(
                dimension=dimension,
                score=score
            ))
    
    # Trier par score DESC
    strengths.sort(key=lambda x: x.score, reverse=True)
    
    # Retourner top N
    return strengths[:top_n]


# =============================================================
# FIND WEAKNESSES (NOUVEAU)
# =============================================================

def find_weaknesses(
    dimension_scores: Dict[str, float],
    threshold: float = 0.3,
    top_n: int = 3
) -> List[Strength]:
    """
    Identifie les axes d'amélioration (dimensions < threshold).
    Nouveau dans V2.
    """
    
    weaknesses = []
    
    for dimension, score in dimension_scores.items():
        if score < threshold:
            weaknesses.append(Strength(
                dimension=dimension,
                score=score
            ))
    
    weaknesses.sort(key=lambda x: x.score)
    
    return weaknesses[:top_n]


# =============================================================
# GENERATE PERSONALIZED MESSAGE (V2)
# =============================================================

def generate_message(
    top_career: CareerScore,
    strengths: List[Strength],
    weaknesses: List[Strength],
    user_type: str = "all",
    bac_info: Optional[Dict] = None
) -> str:
    """
    Génère un message personnalisé basé sur le profil et le user_type.
    Version V2 avec support bac congolais.
    """
    
    career_name = top_career.name
    score = top_career.score
    strength_names = " et ".join([s.label for s in strengths[:2]])
    
    # Ajouter information bac si disponible
    bac_section = ""
    if bac_info and bac_info.get("code"):
        bac_track = bac_info.get("track", "")
        track_labels = {
            "science": "scientifique",
            "technical": "technique",
            "business": "commerciale",
            "humanities": "littéraire",
            "informatics": "informatique",
            "vocational": "professionnelle"
        }
        track_label = track_labels.get(bac_track, bac_track)
        bac_section = f"\nAvec votre bac {bac_info['code']} ({track_label}), vous avez déjà une excellente base. "
    
    # Messages selon user_type
    if user_type == "bachelier":
        if score >= 0.7:
            prefix = "🎯 Perspective extraordinaire!"
            confidence = "vous avez absolument le profil idéal"
        elif score >= 0.5:
            prefix = "📚 Excellente découverte!"
            confidence = "vous avez un profil solide"
        else:
            prefix = "🌳 À explorer!"
            confidence = "vous pourriez découvrir ce domaine"
        
        message = f"""{prefix} {career_name} pourrait vous captiver!
{bac_section}
Votre profil montre une excellente préparation en {strength_names}.
Explorez les formations dans ce domaine et voyez si c'est votre chemin.
"""
    
    elif user_type == "étudiant":
        if score >= 0.7:
            prefix = "🔥 Profil extraordinaire!"
            confidence = "vous avez absolument le profil"
        elif score >= 0.5:
            prefix = "✨ Excellent match!"
            confidence = "vous avez un profil solide"
        else:
            prefix = "🎯 Bon potentiel"
            confidence = "vous avez du potentiel"
        
        message = f"""{prefix} {career_name} vous correspond très bien!
{bac_section}
Vous devriez vous spécialiser en {strength_names}.
Vos forces vous y prédisposent naturellement. Préparez-vous dès maintenant.
"""
    
    elif user_type == "parent":
        if score >= 0.7:
            prefix = "✅ Profil Excellent"
            stability = "très prometteur"
        elif score >= 0.5:
            prefix = "✅ Profil Solide"
            stability = "prometteur"
        else:
            prefix = "✅ Profil Viable"
            stability = "intéressant"
        
        message = f"""{prefix}
Votre enfant a un profil {stability} pour {career_name}.
{bac_section}
Ses forces principales: {strength_names}.
Encouragez-le à explorer les formations dans ce domaine et les stages.
"""
    
    elif user_type == "reconversion":
        if score >= 0.7:
            confidence = "une excellente adéquation"
        elif score >= 0.5:
            confidence = "une bonne adéquation"
        else:
            confidence = "un potentiel à explorer"
        
        message = f"""💼 Reconversion professionnelle
Votre expérience montre {confidence} avec {career_name}.
{bac_section}
Vos forces en {strength_names} sont très valorisables dans ce domaine.
Des formations courtes peuvent faciliter votre transition.
"""
    
    else:  # default
        if score >= 0.7:
            prefix = "🔥 Profil extraordinaire!"
            confidence = "vous avez absolument le profil"
        elif score >= 0.5:
            prefix = "✨ Excellent match!"
            confidence = "vous avez un profil solide"
        else:
            prefix = "👍 Possible"
            confidence = "vous pourriez explorer"
        
        message = f"""{prefix} {career_name} vous correspond bien!
{bac_section}
Votre profil montre une force en {strength_names}, ce qui est essentiel pour cette carrière.
"""
    
    # Ajouter suggestion d'amélioration si nécessaire
    if weaknesses and score < 0.5:
        weak_names = " et ".join([w.label for w in weaknesses[:2]])
        message += f"\n💡 Pour augmenter votre compatibilité, vous pourriez développer {weak_names}."
    
    return message.strip()


# =============================================================
# MAIN PIPELINE (V2)
# =============================================================

def compute_career_recommendations(
    quiz_responses: Dict[str, float],
    user_type: str = "all",
    bac_code: Optional[str] = None,
    confidence: float = 0.85
) -> Dict[str, Any]:
    """
    Pipeline complet: réponses quiz → recommandations de carrière.
    Version V2 avec support bac congolais.
    
    Args:
        quiz_responses: {question_id: option_value}
        user_type: 'all', 'bachelier', 'étudiant', 'parent', 'reconversion'
        bac_code: Code bac congolais (optionnel)
        confidence: Score de confiance global (0-1)
    
    Returns:
        Recommandations complètes avec métadonnées
    """
    
    print("\n" + "="*60)
    print("🎯 CAREER RECOMMENDATIONS ENGINE V2")
    print(f"📍 User Type: {user_type}")
    if bac_code:
        print(f"🎓 Bac Code: {bac_code}")
    print(f"📊 Confidence: {confidence:.2%}")
    print("="*60)
    
    # Étape 0: Valider user_type
    if user_type not in USER_TYPE_CONTEXT and user_type != "all":
        print(f"[WARNING] Unknown user_type '{user_type}', using 'all'")
        user_type = "all"
    
    # Étape 1: Récupérer les mappings question → dimensions
    question_dimensions = fetch_question_dimensions()
    
    # Étape 2: Récupérer les poids contextuels du user_type
    user_type_weights = fetch_user_type_weights(user_type)
    
    # Étape 3: Calculer scores par dimension
    dimension_scores = calculate_dimension_scores(
        quiz_responses, 
        question_dimensions,
        user_type_weights
    )
    
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
    career_scores = compute_career_scores(dimension_scores, careers, confidence)
    
    # Étape 6: Identifier les forces et faiblesses
    strengths = find_strengths(dimension_scores)
    weaknesses = find_weaknesses(dimension_scores)
    
    # Étape 7: Préparer informations bac
    bac_info = None
    if bac_code:
        from core.utils import get_bac_track
        bac_track = get_bac_track(bac_code)
        if bac_track:
            bac_info = {"code": bac_code.upper(), "track": bac_track}
    
    # Étape 8: Générer message contextuel
    top_career = career_scores[0] if career_scores else None
    message = generate_message(top_career, strengths, weaknesses, user_type, bac_info) if top_career else ""
    
    # Étape 9: Récupérer contexte métadonnées
    context = USER_TYPE_CONTEXT.get(user_type, {}) if user_type != "all" else {}
    
    # Étape 10: Préparer réponse
    result = {
        "status": "success",
        "version": "2.0",
        "user_type": user_type,
        "bac_info": bac_info,
        "confidence": confidence,
        "context_metadata": {
            "focus_area": context.get("focus_area", "general"),
            "recommendation_depth": context.get("recommendation_depth", "surface"),
            "guidance_tone": context.get("guidance_tone", "suggestive"),
            "description": context.get("description", "")
        },
        "dimension_scores": {k: round(v, 3) for k, v in dimension_scores.items()},
        "strengths": [
            {"dimension": s.dimension, "score": round(s.score, 3), "label": s.label, "emoji": s.emoji}
            for s in strengths
        ],
        "weaknesses": [
            {"dimension": w.dimension, "score": round(w.score, 3), "label": w.label, "emoji": w.emoji}
            for w in weaknesses
        ] if weaknesses else [],
        "recommended_career": {
            "name": top_career.name,
            "slug": top_career.slug,
            "icon": top_career.icon,
            "category": top_career.category,
            "score": round(top_career.score, 3),
            "match_quality": top_career.match_quality,
            "related_filieres": top_career.related_filieres[:5] if top_career.related_filieres else []
        } if top_career else None,
        "top_3_careers": [
            {
                "name": c.name,
                "slug": c.slug,
                "score": round(c.score, 3),
                "icon": c.icon,
                "match_quality": c.match_quality
            }
            for c in career_scores[:3]
        ] if career_scores else [],
        "alternative_careers": [
            {
                "name": c.name,
                "slug": c.slug,
                "score": round(c.score, 3),
                "icon": c.icon
            }
            for c in career_scores[3:8]
        ] if len(career_scores) > 3 else [],
        "message": message,
        "all_careers_count": len(career_scores)
    }
    
    print("\n" + "="*60)
    print("✅ Career recommendations V2 computed successfully")
    if top_career:
        print(f"🎯 Top career: {top_career.name} ({top_career.match_quality})")
    print("="*60 + "\n")
    
    return result


# =============================================================
# FONCTION DE COMPATIBILITÉ (LEGACY)
# =============================================================

def compute_career_recommendations_legacy(
    quiz_responses: Dict[str, float],
    user_type: str = "all"
) -> Dict[str, Any]:
    """
    Version legacy pour compatibilité ascendante.
    """
    return compute_career_recommendations(
        quiz_responses=quiz_responses,
        user_type=user_type,
        bac_code=None,
        confidence=0.85
    )


# =============================================================
# TESTS
# =============================================================

if __name__ == "__main__":
    # Test avec réponses simulées
    test_responses = {
        "q1": 5, "q2": 4, "q3": 5, "q4": 3, "q5": 4,
        "q6": 2, "q7": 3, "q8": 4, "q9": 5, "q10": 4
    }
    
    # Test pour bachelier
    result = compute_career_recommendations(
        quiz_responses=test_responses,
        user_type="bachelier",
        bac_code="C",
        confidence=0.85
    )
    
    print("\n📊 Résultat du test:")
    print(f"  Status: {result['status']}")
    print(f"  Version: {result['version']}")
    if result.get('recommended_career'):
        print(f"  Top career: {result['recommended_career']['name']} ({result['recommended_career']['match_quality']})")
    print(f"  Strengths: {[s['label'] for s in result['strengths']]}")
    print(f"\n💬 Message:\n{result['message']}")