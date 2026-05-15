"""
Tests pour le module ml_engine.py
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import ml_engine
from core.rule_engine import compute_profile as rule_compute_profile
from models.profile import OrientationProfile


class TestMlEngine:

    def test_compute_profile_returns_domain_and_skill_scores(self):
        features = {f"q{i}": (i % 4 + 1) / 4 for i in range(1, 25)}
        profile = ml_engine.compute_profile(features)

        assert isinstance(profile, dict)
        assert "domains" in profile and "skills" in profile
        assert isinstance(profile["domains"], dict)
        assert isinstance(profile["skills"], dict)
        assert all(0.0 <= score <= 1.0 for score in profile["domains"].values())
        assert all(0.0 <= score <= 1.0 for score in profile["skills"].values())

    def test_default_ml_model_type_is_logistic(self):
        assert ml_engine._select_model_type() == "logistic"


class TestRuleEngineProfileFromFeatures:

    def test_rule_engine_accepts_feature_dict(self):
        features = {"q1": 1.0, "q2": 0.0, "q3": 0.6, "q4": 0.4}
        profile = rule_compute_profile(features)

        assert isinstance(profile, dict)
        assert "domains" in profile and "skills" in profile
        assert all(0.0 <= score <= 1.0 for score in profile["domains"].values())
        assert all(0.0 <= score <= 1.0 for score in profile["skills"].values())

    def test_profile_values_are_consistent(self):
        features = {"q1": 0.3, "q5": 0.7, "q9": 0.5}
        profile = rule_compute_profile(features)

        assert profile["domains"]["logic"] == pytest.approx(0.3, rel=1e-2) or profile["domains"]["logic"] == pytest.approx(0.5, rel=1e-2)
        assert profile["skills"]["logic"] == pytest.approx(0.3, rel=1e-2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
