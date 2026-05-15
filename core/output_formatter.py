"""
Format standardisé des réponses PROA - Version 2.0

Règle d'or: PROA = "QUI SUIS-JE ?" JAMAIS ne connait les universités/centres
Maintenant avec support du scoring vectoriel V2 et insights enrichis
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging

logger = logging.getLogger("orientation.formatter")


@dataclass
class FormattedFiliere:
    """Structure standardisée pour une filière recommandée"""
    field_name: str
    score: float
    reason: str
    category: str = "General"
    cluster: Optional[str] = None
    confidence: Optional[float] = None
    compatibility_level: Optional[str] = None
    contributions: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ProaResponse:
    """
    Format standardisé de réponse PROA - Version 2.0
    
    Améliorations:
    - Support du scoring vectoriel V2
    - Insights enrichis avec IA
    - Traçabilité complète pour PORA
    - Métriques de performance
    - Cache et fallback intelligents
    """
    
    # Version actuelle du format
    VERSION = "2.0"
    
    @staticmethod
    def compute_orientation(
        user_id: str,
        profile: List[float],
        confidence: float,
        recommended_fields: List[Dict[str, Any]],
        quiz_version: str = "1.0",
        profile_id: str = None,
        field_scores: Dict[str, float] = None,
        insight: str = "",
        scoring_method: str = "v2_vectoriel",
        computation_time_ms: float = 0.0,
        context: Optional[Dict[str, Any]] = None,
        alternatives: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Réponse standardisée pour /orientation/compute - V2
        
        ✅ Garanties:
        - recommended_fields est TOUJOURS un array
        - Chaque field a: field_name, score, reason, category
        - Jamais null, toujours [] si vide
        - profile_id permet PORA de tracer la recommandation
        - Métriques de performance incluses
        """
        
        # Normaliser les filières recommandées
        normalized_fields = ProaResponse._normalize_recommended_fields(recommended_fields)
        
        # Ajouter les alternatives si fournies
        normalized_alternatives = None
        if alternatives:
            normalized_alternatives = ProaResponse._normalize_recommended_fields(alternatives, is_alternative=True)
        
        # Générer un insight enrichi si non fourni
        final_insight = insight or ProaResponse._generate_insight(normalized_fields, context)
        
        # Construire la réponse
        response = {
            "version": ProaResponse.VERSION,
            "user_id": user_id,
            "profile_id": profile_id,
            "quiz_version": quiz_version,
            "scoring_method": scoring_method,
            "profile": {
                "vector": profile,
                "confidence": round(float(confidence), 4),
                "timestamp": datetime.utcnow().isoformat(),
                "dimensions_count": len(profile)
            },
            "recommended_fields": normalized_fields,
            "field_scores": field_scores or {},
            "insight": final_insight,
            "aiInsight": final_insight,
            "status": "success",
            "metadata": {
                "computation_time_ms": round(computation_time_ms, 2),
                "total_recommendations": len(normalized_fields),
                "scoring_version": scoring_method
            }
        }
        
        # Ajouter les alternatives si disponibles
        if normalized_alternatives:
            response["alternative_fields"] = normalized_alternatives
        
        # Ajouter le contexte si fourni
        if context:
            response["context"] = ProaResponse._normalize_context(context)
        
        logger.info(f"📤 Response formatted for {user_id}: {len(normalized_fields)} recommendations in {computation_time_ms:.2f}ms")
        
        return response
    
    @staticmethod
    def _normalize_recommended_fields(
        fields: List[Dict[str, Any]], 
        is_alternative: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Normalise les champs recommandés selon le standard V2.
        """
        normalized = []
        
        for field in fields:
            # Extraire le score (priorité au decision_score si disponible)
            score = field.get("decision_score") or field.get("score", 0.0)
            
            # Construction du champ normalisé
            normalized_field = {
                "field_name": field.get("field_name") or field.get("field") or "Unknown",
                "score": round(float(score), 4),
                "reason": field.get("reason", "Alternative intéressante" if is_alternative else "Profil adapté"),
                "category": field.get("category", "General"),
            }
            
            # Ajouter les métadonnées enrichies
            for extra_key in (
                "cluster",
                "distance",
                "similarity",
                "profile_score",
                "bac_score",
                "bac_match_score",
                "bac_track",
                "decision_score",
                "base_score",
                "confidence",
                "compatibility_level"
            ):
                if extra_key in field and field[extra_key] is not None:
                    value = field[extra_key]
                    if isinstance(value, float):
                        normalized_field[extra_key] = round(value, 4)
                    else:
                        normalized_field[extra_key] = value
            
            # Ajouter les contributions vectorielles
            if "contributions" in field and field["contributions"]:
                normalized_field["contributions"] = [
                    {"dimension": dim, "contribution": round(contrib, 4)}
                    for dim, contrib in field["contributions"][:5]  # Top 5 dimensions
                ]
            
            # Ajouter les métadonnées supplémentaires
            if "metadata" in field:
                normalized_field["metadata"] = field["metadata"]
            
            # Pour les alternatives, ajouter un indicateur
            if is_alternative:
                normalized_field["is_alternative"] = True
                normalized_field["score"] = round(score * 0.85, 4)  # Légère pénalité pour alternatives
            
            normalized.append(normalized_field)
        
        return normalized
    
    @staticmethod
    def _generate_insight(
        recommendations: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """
        Génère un insight personnalisé basé sur les recommandations.
        """
        if not recommendations:
            return "Aucune recommandation disponible pour le moment."
        
        top_field = recommendations[0]
        top_score = top_field.get("score", 0)
        top_name = top_field.get("field_name", "Cette filière")
        
        # Insight basé sur le score
        if top_score >= 0.8:
            insight = f"🔥 Excellente correspondance ! {top_name} correspond parfaitement à votre profil."
        elif top_score >= 0.6:
            insight = f"✅ Très bonne correspondance. {top_name} est particulièrement adapté à vos centres d'intérêt."
        elif top_score >= 0.4:
            insight = f"📊 Bonne correspondance. {top_name} mérite votre attention."
        else:
            insight = f"💡 Explorez {top_name} qui pourrait correspondre à vos aspirations."
        
        # Ajouter info cluster si disponible
        top_cluster = top_field.get("cluster")
        if top_cluster:
            cluster_names = {
                "informatique": "l'informatique et les technologies",
                "business": "le business et la gestion",
                "engineering": "l'ingénierie et les sciences appliquées",
                "droit": "le droit et les sciences juridiques",
                "social": "les sciences humaines et sociales",
                "sante": "la santé et le médical",
                "sciences": "les sciences fondamentales",
                "arts_design": "les arts et le design",
                "agriculture": "l'agriculture et l'agroalimentaire"
            }
            cluster_desc = cluster_names.get(top_cluster, top_cluster)
            insight += f" Votre profil montre une affinité marquée pour {cluster_desc}."
        
        # Ajouter info bac si disponible
        if context and context.get("bac_type"):
            bac_type = context.get("bac_type", "").upper()
            bac_compatible = top_field.get("bac_match_score", 0)
            if bac_compatible >= 0.7:
                insight += f" Votre bac {bac_type} est particulièrement bien adapté à cette orientation."
            elif bac_compatible >= 0.4:
                insight += f" Votre bac {bac_type} offre une bonne base pour cette filière."
        
        return insight
    
    @staticmethod
    def _normalize_context(context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalise le contexte utilisateur pour la réponse.
        """
        normalized = {}
        
        # Informations de base
        if "user_type" in context:
            normalized["user_type"] = context["user_type"]
        if "bac_type" in context:
            normalized["bac_type"] = context["bac_type"].upper() if context["bac_type"] else None
        if "bac_track" in context:
            normalized["bac_track"] = context["bac_track"]
        if "dominant_cluster" in context:
            normalized["dominant_cluster"] = context["dominant_cluster"]
        
        # Métriques de confiance
        if "confidence" in context:
            normalized["overall_confidence"] = round(context["confidence"], 4)
        
        # Version du scoring
        if "scoring_version" in context:
            normalized["scoring_version"] = context["scoring_version"]
        
        return normalized
    
    @staticmethod
    def recommend_only(
        user_id: str,
        recommended_fields: List[Dict[str, Any]],
        include_metadata: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Réponse pour appels simples: juste les filières recommandées
        Utilisé par PORA ou frontend pour un refresh
        
        Version V2 avec métadonnées optionnelles
        """
        normalized_fields = []
        for field in recommended_fields:
            normalized = {
                "field_name": field.get("field_name") or field.get("field") or "Unknown",
                "score": float(field.get("decision_score", field.get("score", 0.0)))
            }
            
            if include_metadata:
                if "cluster" in field:
                    normalized["cluster"] = field["cluster"]
                if "compatibility_level" in field:
                    normalized["compatibility"] = field["compatibility_level"]
                if "reason" in field:
                    normalized["reason"] = field["reason"]
            
            normalized_fields.append(normalized)
        
        response = {
            "version": ProaResponse.VERSION,
            "user_id": user_id,
            "recommended_fields": normalized_fields,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if context:
            response["context"] = ProaResponse._normalize_context(context)
        
        return response
    
    @staticmethod
    def batch_compute_orientation(
        results: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Réponse pour traitement par lots (batch processing)
        """
        return {
            "version": ProaResponse.VERSION,
            "batch_size": len(results),
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def health_check() -> Dict[str, Any]:
        """
        Réponse pour health check du service
        """
        return {
            "status": "healthy",
            "service": "proa",
            "version": ProaResponse.VERSION,
            "timestamp": datetime.utcnow().isoformat(),
            "features": [
                "scoring_vectoriel",
                "bac_compatibility",
                "cluster_detection",
                "insights_generation"
            ]
        }
    
    @staticmethod
    def error(
        message: str, 
        code: str = "INTERNAL_ERROR", 
        details: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Réponse standardisée en cas d'erreur - Version V2
        Garantit structure lisible pour le frontend
        """
        response = {
            "version": ProaResponse.VERSION,
            "error": True,
            "message": message,
            "code": code,
            "recommended_fields": [],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if user_id:
            response["user_id"] = user_id
        
        if details:
            response["details"] = details
        
        logger.error(f"Error response: {code} - {message}")
        
        return response
    
    @staticmethod
    def format_filiere_for_pora(
        filiere: Dict[str, Any],
        score: float,
        cluster: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format spécifique pour l'intégration avec PORA
        """
        return {
            "filiere_id": filiere.get("id", ""),
            "filiere_name": filiere.get("nom", filiere.get("field_name", "Unknown")),
            "score": round(score, 4),
            "cluster": cluster or "unknown",
            "source": "proa_v2"
        }
    
    @staticmethod
    def migrate_legacy_response(legacy_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migre une réponse legacy (V1) vers le format V2
        """
        if legacy_response.get("version") == ProaResponse.VERSION:
            return legacy_response
        
        user_id = legacy_response.get("user_id", "unknown")
        recommended = legacy_response.get("recommended_fields", [])
        insight = legacy_response.get("insight", "")
        
        # Convertir les champs legacy
        converted_fields = []
        for field in recommended:
            converted = {
                "field_name": field.get("field_name", "Unknown"),
                "score": field.get("score", 0.0),
                "reason": field.get("reason", "Profil adapté"),
                "category": field.get("category", "General"),
                "legacy": True  # Marqueur de migration
            }
            converted_fields.append(converted)
        
        return ProaResponse.compute_orientation(
            user_id=user_id,
            profile=legacy_response.get("profile", {}).get("vector", []),
            confidence=legacy_response.get("profile", {}).get("confidence", 0.5),
            recommended_fields=converted_fields,
            insight=insight,
            scoring_method="legacy_migrated"
        )


# ============================================================================
# FONCTIONS UTILITAIRES
# ============================================================================

def format_filiere_scores_for_display(
    filiere_scores: List[Any],
    max_items: int = 5
) -> List[Dict[str, Any]]:
    """
    Formate les scores de filières pour affichage frontend.
    """
    formatted = []
    for score in filiere_scores[:max_items]:
        formatted.append({
            "name": score.filiere_name if hasattr(score, 'filiere_name') else score.get("field_name", "Unknown"),
            "score": score.score if hasattr(score, 'score') else score.get("score", 0),
            "level": score.compatibility_level if hasattr(score, 'compatibility_level') else "fair",
            "cluster": score.cluster if hasattr(score, 'cluster') else score.get("cluster", "unknown")
        })
    return formatted


def merge_recommendations(
    primary: List[Dict[str, Any]],
    secondary: List[Dict[str, Any]],
    primary_weight: float = 0.7
) -> List[Dict[str, Any]]:
    """
    Fusionne deux listes de recommandations avec pondération.
    """
    merged = {}
    
    # Ajouter les recommandations primaires
    for item in primary:
        key = item.get("field_name")
        if key:
            merged[key] = {
                "field_name": key,
                "score": item.get("score", 0) * primary_weight,
                "reason": item.get("reason", ""),
                "category": item.get("category", "Primary")
            }
    
    # Ajouter les recommandations secondaires
    for item in secondary:
        key = item.get("field_name")
        if key:
            if key in merged:
                merged[key]["score"] += item.get("score", 0) * (1 - primary_weight)
                merged[key]["reason"] = f"{merged[key]['reason']} + {item.get('reason', '')}"
            else:
                merged[key] = {
                    "field_name": key,
                    "score": item.get("score", 0) * (1 - primary_weight),
                    "reason": item.get("reason", ""),
                    "category": item.get("category", "Secondary")
                }
    
    # Trier par score
    result = sorted(merged.values(), key=lambda x: x["score"], reverse=True)
    
    return result


# ============================================================================
# TESTS
# ============================================================================

if __name__ == "__main__":
    # Test de la réponse formatée
    test_response = ProaResponse.compute_orientation(
        user_id="test_user_123",
        profile=[0.8, 0.6, 0.4, 0.2, 0.1, 0.0, 0.3, 0.5],
        confidence=0.85,
        recommended_fields=[
            {
                "field_name": "Génie Informatique",
                "score": 0.92,
                "reason": "Excellente correspondance",
                "category": "Supabase",
                "cluster": "informatique",
                "contributions": [("tech", 0.85), ("expertise", 0.65)]
            },
            {
                "field_name": "Data Science",
                "score": 0.88,
                "reason": "Très bonne correspondance",
                "category": "Supabase",
                "cluster": "informatique"
            }
        ],
        scoring_method="v2_vectoriel",
        computation_time_ms=145.3,
        context={
            "user_type": "bachelier",
            "bac_type": "C",
            "dominant_cluster": "informatique"
        }
    )
    
    import json
    print(json.dumps(test_response, ensure_ascii=False, indent=2))