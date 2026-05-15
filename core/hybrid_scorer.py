"""
Hybrid Scorer for intelligent filière matching
Combine semantic, rule-based, and interest-based scoring
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ProaScore:
    """Score PROA complet pour une filière"""
    filiere_id: str
    filiere_name: str
    total_score: float
    confidence: float
    matched_domains: List[str]
    recommendations: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class HybridScorer:
    """
    Scorer hybride qui combine plusieurs méthodes
    """
    
    def __init__(self):
        logger.info("HybridScorer initialisé")
    
    def compute_proa_score(self, filiere_info: Dict, user_domains: List[Dict],
                          quiz_responses: Optional[Dict] = None,
                          user_profile: Optional[Dict] = None) -> ProaScore:
        """
        Calcule le score PROA hybride
        
        Version simplifiée pour commencer
        """
        # Score basé sur les domaines (simple matching d'abord)
        filiere_domains = filiere_info.get('proa_domains', [])
        user_domain_names = [d.get('domain_name') for d in user_domains]
        
        matched = [d for d in filiere_domains if d in user_domain_names]
        
        if filiere_domains:
            base_score = len(matched) / len(filiere_domains)
        else:
            base_score = 0.5  # Score neutre si pas de domaines
        
        # Bonus pour la confiance
        confidence = 0.7 if matched else 0.3
        
        # Générer des recommandations
        recommendations = []
        if base_score >= 0.7:
            recommendations.append("Excellente correspondance avec vos centres d'intérêt")
        elif base_score >= 0.4:
            recommendations.append("Bonne correspondance, explorez davantage")
        else:
            recommendations.append("Correspondance à améliorer")
        
        return ProaScore(
            filiere_id=filiere_info.get('filiere_id', ''),
            filiere_name=filiere_info.get('filiere_name', ''),
            total_score=base_score,
            confidence=confidence,
            matched_domains=matched,
            recommendations=recommendations,
            metadata={
                "total_domains": len(filiere_domains),
                "matched_count": len(matched)
            }
        )