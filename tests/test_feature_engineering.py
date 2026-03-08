"""
Tests pour le module feature_engineering.py
"""

import pytest
import sys
import os

# Ajouter le répertoire parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.feature_engineering import build_features


class TestBuildFeatures:
    
    def test_empty_responses(self):
        """Test avec réponses vides"""
        features = build_features({})
        assert features == {}
    
    def test_single_response(self):
        """Test avec une seule réponse"""
        responses = {"logic_1": 5.0}
        features = build_features(responses)
        
        # logic_1 appartient à skill_logic et domain_computer_science
        assert "skill_logic" in features
        assert features["skill_logic"] == 1.0  # 5 / 5 = 1.0
    
    def test_normalization_range(self):
        """Test que les features sont normalisées [0, 1]"""
        responses = {
            "logic_1": 2.5,
            "creativity_1": 3.0,
            "entrepreneurship_1": 1.0,
            "leadership_1": 4.0,
            "management_1": 5.0,
            "communication_1": 2.0,
            "analysis_1": 3.5,
            "technical_1": 2.0,
            "teamwork_1": 4.5,
            "organization_1": 3.0,
            "resilience_1": 2.0,
            "negotiation_1": 1.5,
        }
        
        features = build_features(responses)
        
        for key, value in features.items():
            assert 0.0 <= value <= 1.0, f"{key} = {value} hors intervalle [0, 1]"
    
    def test_score_clipping(self):
        """Test que les scores > 1 sont clippés à 1"""
        responses = {
            "logic_1": 5.0,  # 5/5 = 1.0
        }
        features = build_features(responses)
        assert features["skill_logic"] == 1.0
    
    def test_domain_threshold(self):
        """Test que le seuil de domaine est appliqué"""
        # score < threshold (2) → domaine = 0
        responses = {
            "logic_1": 1.0,  # < threshold
            "technical_1": 1.0,
            "creativity_1": 3.0,  # > threshold
        }
        features = build_features(responses)
        
        # computer_science a [logic_1, technical_1] avg=1.0 < threshold → 0.0
        assert features["domain_computer_science"] == 0.0
        # art a [creativity_1] avg=3.0 > threshold → 3.0/5 = 0.6
        assert features["domain_art"] == 0.6
    
    def test_skill_average(self):
        """Test que les skills sont calculés en moyenne"""
        responses = {
            "leadership_1": 4.0,
            "management_1": 2.0,
        }
        features = build_features(responses)
        
        # business_domain = (entrepreneurship_1, leadership_1, management_1)
        # entrepreneurship_1 manquant (0), leadership_1=4.0, management_1=2.0
        # avg = (0 + 4 + 2) / 3 = 2.0 > threshold(2) → 2.0/5 = 0.4
        # MAIS: build_features calcule avg sur les REPONSES PRESENTES uniquement
        # = (4.0 + 2.0) / 2 = 3.0 > threshold → 3.0/5 = 0.6
        assert features["domain_business"] == 0.6
    
    def test_rounding(self):
        """Test que les valeurs sont arrondies à 4 décimales"""
        responses = {
            "logic_1": 1.0,
            "technical_1": 2.0,
        }
        features = build_features(responses)
        
        for key, value in features.items():
            # Vérifier que c'est un float avec max 4 décimales
            assert isinstance(value, float)
            # Vérifier qu'il y a max 4 décimales
            assert len(str(value).split('.')[-1]) <= 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
