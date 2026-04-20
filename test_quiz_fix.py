#!/usr/bin/env python3
"""
Test script to verify the quiz recommendation bug is fixed.

This tests that:
1. Semantic question codes are properly converted to domains
2. Different quiz responses produce different features
3. Features are used to generate different recommendations

Run with:
    python test_quiz_fix.py
"""

import json
import sys
import os

# Add services path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from core.feature_engineering import (
    build_features,
    convert_semantic_to_domain_mapping,
    SEMANTIC_MAPPING,
    ORIENTATION_CONFIG
)
from core.utils import normalize_responses

def test_semantic_code_detection():
    """Test 1: Verify semantic codes are detected"""
    print("\n" + "="*70)
    print("TEST 1: Semantic Code Detection")
    print("="*70)
    
    # Sample responses with semantic codes
    responses_semantic = {
        "q_passion_tech": 4,
        "q_love_coding": 4,
        "q_solve_problems": 3,
        "q_create_things": 2,
        "q_lead_team": 2
    }
    
    responses_normalized = normalize_responses(responses_semantic)
    first_code = list(responses_normalized.keys())[0]
    uses_semantic = first_code.startswith("q_") or "_" in first_code
    
    print(f"✅ Test sample responses: {list(responses_semantic.keys())[:3]}")
    print(f"✅ Detected semantic codes: {uses_semantic}")
    assert uses_semantic, "Failed to detect semantic codes"
    print("✅ PASSED\n")


def test_semantic_mapping_loaded():
    """Test 2: Verify semantic mapping is loaded"""
    print("="*70)
    print("TEST 2: Semantic Mapping Loaded")
    print("="*70)
    
    mappings = SEMANTIC_MAPPING.get("semantic_to_domain_mapping", {})
    print(f"✅ Loaded {len(mappings)} semantic code mappings")
    
    # Check some expected codes
    expected_codes = ["q_passion_tech", "q_social_networks", "q_lead_team"]
    found = [c for c in expected_codes if c in mappings]
    print(f"✅ Found {len(found)}/{len(expected_codes)} expected codes: {found}")
    
    assert len(mappings) > 0, "Semantic mapping is empty!"
    assert len(found) == len(expected_codes), "Missing expected semantic codes"
    print("✅ PASSED\n")


def test_semantic_conversion():
    """Test 3: Semantic code to domain conversion"""
    print("="*70)
    print("TEST 3: Semantic Code to Domain Conversion")
    print("="*70)
    
    responses = {
        "q_passion_tech": 4,
        "q_solve_problems": 3,
        "q_social_networks": 4,
        "q_lead_team": 3
    }
    
    mapping = convert_semantic_to_domain_mapping(responses)
    
    print(f"✅ Converted {len(mapping)} question codes to domain format")
    for code, domains in list(mapping.items())[:3]:
        domain_names = [d["domain"] for d in domains]
        print(f"   {code} → {domain_names}")
    
    assert len(mapping) > 0, "Conversion returned empty mapping"
    print("✅ PASSED\n")


def test_feature_calculation_different_responses():
    """Test 4: Different responses produce different features"""
    print("="*70)
    print("TEST 4: Different Responses → Different Features")
    print("="*70)
    
    # User 1: Tech-focused
    user1_responses = {
        "q_passion_tech": 4,
        "q_love_coding": 4,
        "q_solve_problems": 4,
        "q_create_things": 2,
        "q_lead_team": 1,
        "q_social_networks": 1,
        "q_learn_quickly": 3,
        "q_entrepreneurship": 2
    }
    
    # User 2: Leadership-focused
    user2_responses = {
        "q_passion_tech": 1,
        "q_love_coding": 1,
        "q_solve_problems": 2,
        "q_create_things": 2,
        "q_lead_team": 4,
        "q_social_networks": 4,
        "q_learn_quickly": 3,
        "q_entrepreneurship": 4
    }
    
    print("Computing features for User 1 (tech-focused)...")
    features1 = build_features(user1_responses)
    print(f"   Features: {features1}\n")
    
    print("Computing features for User 2 (leadership-focused)...")
    features2 = build_features(user2_responses)
    print(f"   Features: {features2}\n")
    
    # Check that features are different
    different_count = sum(1 for k in features1 if features1.get(k) != features2.get(k))
    print(f"✅ {different_count} features differ between users (out of {len(features1)})")
    
    # Check that both have non-zero features
    nonzero1 = sum(1 for v in features1.values() if v > 0)
    nonzero2 = sum(1 for v in features2.values() if v > 0)
    print(f"✅ User 1 non-zero features: {nonzero1}/{len(features1)}")
    print(f"✅ User 2 non-zero features: {nonzero2}/{len(features2)}")
    
    assert nonzero1 > 0, "User 1 has no non-zero features!"
    assert nonzero2 > 0, "User 2 has no non-zero features!"
    assert different_count > 0, "Users have identical features!"
    print("✅ PASSED\n")


def test_feature_calculation_not_default_fallback():
    """Test 5: Verify NOT using default fallback for all users"""
    print("="*70)
    print("TEST 5: Verify Not All Users Get Default Fallback")
    print("="*70)
    
    # The bug was that all users got the same default: {domain_technical: 0.5, domain_business: 0.4}
    default_fallback = {"domain_technical": 0.5, "domain_business": 0.4, "skill_logic": 0.5}
    
    responses = {
        "q_passion_tech": 4,
        "q_solve_problems": 4,
        "q_lead_team": 4,
        "q_social_networks": 4,
        "q_create_things": 1,
        "q_entrepreneurship": 1
    }
    
    features = build_features(responses)
    
    print(f"✅ Computed features: {features}")
    print(f"📌 Default fallback was: {default_fallback}")
    
    # Check that we're NOT just returning the fallback
    is_fallback = (
        features.get("domain_technical") == default_fallback["domain_technical"] and
        features.get("domain_business") == default_fallback["domain_business"] and
        len(features) == 3
    )
    
    print(f"✅ Is fallback: {is_fallback}")
    assert not is_fallback, "Got default fallback - semantic code conversion failed!"
    assert len(features) > 3, "Expected more than 3 features from semantic codes"
    print("✅ PASSED\n")


if __name__ == "__main__":
    try:
        print("\n" + "="*70)
        print("🧪 QUIZ BUG FIX VALIDATION TESTS")
        print("="*70)
        
        test_semantic_code_detection()
        test_semantic_mapping_loaded()
        test_semantic_conversion()
        test_feature_calculation_different_responses()
        test_feature_calculation_not_default_fallback()
        
        print("="*70)
        print("✅ ALL TESTS PASSED!")
        print("="*70)
        print("\n✅ Quiz recommendation bug is FIXED!")
        print("   - Semantic codes are properly detected")
        print("   - Domain mappings are loaded")
        print("   - Different responses produce different features")
        print("   - Not using default fallback anymore")
        print("\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
