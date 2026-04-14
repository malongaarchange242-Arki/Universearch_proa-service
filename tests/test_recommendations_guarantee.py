"""
Test guarantee contract for PROA recommendations pipeline:
- compute_recommended_fields() MUST ALWAYS return ≥ 5 items
- Never return empty array
- Handle fallback gracefully
"""

import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from core.recommendations import compute_recommended_fields, _extract_keywords_from_profile
from core.feature_engineering import build_features as build_features_fe


class TestRecommendationsGuarantee:
    """Test that recommendations pipeline never fails or returns empty."""
    
    def test_empty_profile_guarantee(self):
        """Test: Even with empty profile, should return 5+ items."""
        empty_profile = {
            "domains": {},
            "skills": {}
        }
        result = compute_recommended_fields(empty_profile, top_n=5)
        
        assert result is not None, "Result is None!"
        assert "recommended_fields" in result, "Missing 'recommended_fields' key"
        
        fields = result["recommended_fields"]
        assert len(fields) >= 5, f"Expected ≥5 fields, got {len(fields)}"
        
        for field in fields:
            assert "field_name" in field, "Missing field_name"
            assert "score" in field, "Missing score"
            assert "reason" in field, "Missing reason"
            assert "category" in field, "Missing category"
            print(f"  ✓ {field['field_name']}: {field['score']:.3f} ({field['category']})")
    
    def test_minimal_profile_guarantee(self):
        """Test: Even with minimal scores, should return items."""
        minimal_profile = {
            "domains": {
                "technical": 0.1,
                "business": 0.05
            },
            "skills": {
                "analytical": 0.08
            }
        }
        result = compute_recommended_fields(minimal_profile, top_n=5)
        
        fields = result["recommended_fields"]
        assert len(fields) >= 5, f"Expected ≥5 fields with minimal profile, got {len(fields)}"
        print(f"✓ Minimal profile returned {len(fields)} recommendations")
    
    def test_zero_score_profile_guarantee(self):
        """Test: Even all zeros, should return fallback."""
        zero_profile = {
            "domains": {
                "a": 0.0,
                "b": 0.0
            },
            "skills": {
                "x": 0.0
            }
        }
        result = compute_recommended_fields(zero_profile, top_n=5)
        
        fields = result["recommended_fields"]
        assert len(fields) >= 5, f"Expected ≥5 fallback fields, got {len(fields)}"
        
        # Check for fallback category
        has_fallback = any(f["category"] == "fallback" for f in fields)
        assert has_fallback, "Expected fallback recommendations with zero scores"
        print(f"✓ Zero-score profile returned {len(fields)} fallback recommendations")
    
    def test_response_structure_invariant(self):
        """Test: Response structure is always correct."""
        profile = {
            "domains": {"technical": 0.7},
            "skills": {}
        }
        result = compute_recommended_fields(profile, top_n=5)
        
        assert isinstance(result, dict), "Response is not dict"
        assert "recommended_fields" in result, "Missing recommended_fields"
        assert "field_scores" in result, "Missing field_scores"
        assert "insight" in result, "Missing insight"
        
        fields = result["recommended_fields"]
        field_scores = result["field_scores"]
        assert isinstance(fields, list), "recommended_fields is not list"
        assert isinstance(field_scores, dict), "field_scores is not dict"
        assert isinstance(result["insight"], str), "insight is not string"
        
        for field in fields:
            assert isinstance(field["field_name"], str), f"field_name not string: {field}"
            assert isinstance(field["score"], (int, float)), f"score not numeric: {field}"
            assert 0.0 <= field["score"] <= 1.0, f"score out of range: {field['score']}"
            assert isinstance(field["reason"], str), f"reason not string: {field}"
            assert field["category"] in ["Supabase", "fallback"], f"invalid category: {field['category']}"
            assert field["field_name"] in field_scores, f"field_name {field['field_name']} missing from field_scores"
            assert field_scores[field["field_name"]] == field["score"], f"score mismatch for {field['field_name']}"

    def test_keyword_normalization_strips_prefixes(self):
        """Test: Profile keys with domain_/skill_ prefixes normalize correctly."""
        profile = {
            "domains": {
                "domain_technical": 0.8,
                "domain_logic": 0.6,
            },
            "skills": {
                "skill_communication": 0.7,
            }
        }
        keywords = _extract_keywords_from_profile(profile)
        assert ("technical", 0.8) in keywords
        assert ("logic", 0.6) in keywords
        assert ("communication", 0.7) in keywords
        assert all(not key.startswith("domain_") and not key.startswith("skill_") for key, _ in keywords)

    def test_feature_engineering_no_crash(self):
        """Test: Feature engineering never crashes even with bad input."""
        test_responses = {
            "Q19": 0,
            "Q20": 1,
            "Q21": 2,
            "Q22": 3,
            "Q23": 4,
            "Q24": 5
        }
        
        features = build_features_fe(test_responses, orientation_type="field")
        
        assert features is not None, "Features is None!"
        assert isinstance(features, dict), "Features is not dict"
        assert len(features) > 0, "Features is empty - fallback failed!"
        
        for key, value in features.items():
            assert isinstance(value, (int, float)), f"{key} is not numeric"
            assert 0.0 <= value <= 1.0, f"{key} out of range: {value}"
        
        print(f"✓ Feature engineering generated {len(features)} features")
        print(f"  Features: {features}")
    
    def test_top_n_parameter_respected(self):
        """Test: top_n parameter is respected."""
        profile = {
            "domains": {"technical": 0.8},
            "skills": {}
        }
        
        for top_n in [3, 5, 10]:
            result = compute_recommended_fields(profile, top_n=top_n)
            fields = result["recommended_fields"]
            
            # Should return max(top_n, available) but at least min(top_n, 5)
            expected = max(top_n, min(top_n, 5))
            assert len(fields) >= min(top_n, 5), \
                f"top_n={top_n}: expected ≥{min(top_n, 5)}, got {len(fields)}"
            
            print(f"✓ top_n={top_n}: returned {len(fields)} fields")


if __name__ == "__main__":
    print("=" * 60)
    print("PROA RECOMMENDATIONS GUARANTEE TEST SUITE")
    print("=" * 60)
    
    test = TestRecommendationsGuarantee()
    
    print("\n1. Testing empty profile guarantee...")
    test.test_empty_profile_guarantee()
    
    print("\n2. Testing minimal profile guarantee...")
    test.test_minimal_profile_guarantee()
    
    print("\n3. Testing zero-score profile guarantee...")
    test.test_zero_score_profile_guarantee()
    
    print("\n4. Testing response structure invariant...")
    test.test_response_structure_invariant()
    
    print("\n5. Testing feature engineering robustness...")
    test.test_feature_engineering_no_crash()
    
    print("\n6. Testing top_n parameter...")
    test.test_top_n_parameter_respected()
    
    print("\n" + "=" * 60)
    print("✅ ALL GUARANTEE TESTS PASSED")
    print("=" * 60)
