"""
Tests pour le module rule_engine.py
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rule_engine import compute_profile, _ENGINE
from models.profile import OrientationProfile


class TestRuleEngine:
    
    def test_empty_profile(self):
        """Test avec profil vide"""
        profile = OrientationProfile(domains={}, skills={})
        vector = compute_profile(profile)
        
        assert isinstance(vector, list)
        assert len(vector) == _ENGINE.vector_size
        assert all(v == 0.0 for v in vector)  # Tout est zéro
    
    def test_vector_normalization(self):
        """Test que le vecteur est normalisé"""
        profile = OrientationProfile(
            domains={"computer_science": 0.5, "art": 0.8},
            skills={"logic": 0.6, "creativity": 0.9}
        )
        vector = compute_profile(profile)
        
        # La normalisation fait que la somme = 1.0
        total = sum(vector)
        assert abs(total - 1.0) < 0.01, f"Somme={total}, attendu ~1.0"
    
    def test_vector_size(self):
        """Test que la taille du vecteur est correcte"""
        profile = OrientationProfile(
            domains={"computer_science": 0.5},
            skills={"logic": 0.6}
        )
        vector = compute_profile(profile)
        
        # Domaines + skills
        expected_size = len(_ENGINE.domain_map) + len(_ENGINE.skill_map)
        assert len(vector) == expected_size
    
    def test_clamping(self):
        """Test que les valeurs sont clippées [0, 1] dans _apply_domains"""
        # OrientationProfile valide seulement [0, 1], donc on passe des valeurs valides
        # et on vérifie que le moteur les gère bien
        profile = OrientationProfile(
            domains={"computer_science": 0.9},
            skills={"logic": 0.1}
        )
        vector = compute_profile(profile)
        
        # Après normalisation, toutes les valeurs devraient être [0, 1]
        assert all(0.0 <= v <= 1.0 for v in vector)
    
    def test_positive_values_only(self):
        """Test que les domaines/skills actifs produisent des valeurs positives"""
        profile = OrientationProfile(
            domains={"computer_science": 0.7},
            skills={"logic": 0.8}
        )
        vector = compute_profile(profile)
        
        positive_count = sum(1 for v in vector if v > 0)
        assert positive_count >= 2  # Au moins les éléments actifs
    
    def test_domain_skill_separation(self):
        """Test que domaines et skills sont à des positions différentes"""
        # Les domaines sont avant les skills dans le vecteur
        profile = OrientationProfile(
            domains={"computer_science": 0.5},
            skills={"logic": 0.0}  # Skill à zéro
        )
        vector = compute_profile(profile)
        
        # Le domaine devrait avoir un impact au début du vecteur
        # Le skill au milieu/fin
        domain_position = _ENGINE.domain_map.get("computer_science", -1)
        skill_position = _ENGINE.skill_map.get("logic", -1)
        
        assert domain_position < skill_position


class TestProfileValidation:
    
    def test_invalid_domain_values(self):
        """Test que les valeurs hors intervalle sont rejetées"""
        with pytest.raises(ValueError):
            OrientationProfile(
                domains={"computer_science": 1.5},  # > 1.0
                skills={}
            )
    
    def test_invalid_skill_values(self):
        """Test que les compétences invalides sont rejetées"""
        with pytest.raises(ValueError):
            OrientationProfile(
                domains={},
                skills={"logic": -0.1}  # < 0.0
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
