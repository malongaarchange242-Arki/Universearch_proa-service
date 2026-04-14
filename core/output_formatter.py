"""
Format standardisé des réponses PROA.

Règle d'or: PROA = "QUI SUIS-JE ?" JAMAIS ne connait les universités/centres
"""

from datetime import datetime
from typing import Dict, Any, List
import logging

logger = logging.getLogger("orientation.formatter")


class ProaResponse:
    """
    Format standardisé de réponse PROA.
    
    Garantit:
    - Cohérence totale entre les endpoints
    - Format parsable par PORA et frontend
    - Aucune donnée null (toujours [] ou {})
    """
    
    @staticmethod
    def compute_orientation(
        user_id: str,
        profile: List[float],
        confidence: float,
        recommended_fields: List[Dict[str, Any]],
        quiz_version: str = "1.0",
        profile_id: str = None,  # 🔗 Ajouter profile_id pour traçabilité
        field_scores: Dict[str, float] = None,
        insight: str = ""
    ) -> Dict[str, Any]:
        """
        Réponse standardisée pour /orientation/compute
        
        ✅ Garanties:
        - recommended_fields est TOUJOURS un array
        - Chaque field a: field_name, score, reason, category
        - Jamais null, toujours [] si vide
        - profile_id permet PORA de tracer la recommandation
        """
        
        # Normaliser les filières recommandées
        normalized_fields = []
        if recommended_fields:
            for field in recommended_fields:
                normalized_fields.append({
                    "field_name": field.get("field_name") or field.get("field") or "Unknown",
                    "score": float(field.get("score", 0.0)),
                    "reason": field.get("reason", "Profil adapté"),
                    "category": field.get("category", "General"),
                })
        
        return {
            "user_id": user_id,
            "profile_id": profile_id,  # 🔗 Traçabilité pour PORA
            "quiz_version": quiz_version,
            "profile": {
                "vector": profile,
                "confidence": round(float(confidence), 4),
                "timestamp": datetime.utcnow().isoformat()
            },
            "recommended_fields": normalized_fields,  # ✅ JAMAIS null
            "field_scores": field_scores or {},
            "insight": insight or "",
            "aiInsight": insight or "",
            "status": "success"
        }
    
    @staticmethod
    def recommend_only(
        user_id: str,
        recommended_fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Réponse pour appels simples: juste les filières recommandées
        Utilisé par PORA ou frontend pour un refresh
        """
        normalized_fields = []
        if recommended_fields:
            for field in recommended_fields:
                normalized_fields.append({
                    "field_name": field.get("field_name") or field.get("field") or "Unknown",
                    "score": float(field.get("score", 0.0)),
                })
        
        return {
            "user_id": user_id,
            "recommended_fields": normalized_fields,  # ✅ JAMAIS null
        }
    
    @staticmethod
    def error(message: str, code: str = "INTERNAL_ERROR") -> Dict[str, Any]:
        """
        Réponse standardisée en cas d'erreur
        Garantit structure lisible pour le frontend
        """
        return {
            "error": True,
            "message": message,
            "code": code,
            "recommended_fields": [],  # ✅ Toujours [] même en erreur
        }


# Utilisation dans routes.py:
# 
# from core.output_formatter import ProaResponse
# 
# return ProaResponse.compute_orientation(
#     user_id=payload.user_id,
#     profile=vector,
#     confidence=confidence,
#     recommended_fields=recommended.get("recommended_fields", []),
#     quiz_version=payload.quiz_version
# )
