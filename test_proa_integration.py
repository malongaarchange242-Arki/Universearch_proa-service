#!/usr/bin/env python3
"""
Integration test: Simulate a real quiz submission through the PROA pipeline

This tests the complete flow:
1. Load quiz questions
2. Simulate user responses
3. Submit to PROA compute endpoint model
4. Verify recommendations are different between users

Run with:
    python test_proa_integration.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from core.feature_engineering import build_features
from core.rule_engine import compute_profile
from models.profile import OrientationProfile


def test_complete_pipeline():
    """Test: Complete PROA pipeline simulation"""
    print("\n" + "="*70)
    print("🧪 INTEGRATION TEST: Complete PROA Pipeline")
    print("="*70)
    
    # Simulate two different students
    print("\n📝 STUDENT 1: Tech + Analysis Profile")
    print("-" * 70)
    
    student1_responses = {
        "q_passion_tech": 4,
        "q_love_coding": 4,
        "q_solve_problems": 4,
        "q_create_things": 3,
        "q_lead_team": 2,
        "q_social_networks": 2,
        "q_learn_quickly": 4,
        "q_entrepreneurship": 2,
        "q_communicate_well": 2,
        "q_handle_pressure": 3
    }
    
    # Step 1: Build features
    features1 = build_features(student1_responses, "field")
    print(f"\n✅ Features extracted: {len(features1)} domains")
    for domain, score in sorted(features1.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"   {domain}: {score:.2f}⭐")
    
    # Step 2: Create orientation profile
    domains1 = {k.replace("domain_", ""): v for k, v in features1.items() if k.startswith("domain_")}
    skills1 = {k.replace("skill_", ""): v for k, v in features1.items() if k.startswith("skill_")}
    profile1 = OrientationProfile(domains=domains1, skills=skills1)
    print(f"\n✅ Profile created: {len(domains1)} domains, {len(skills1)} skills")
    
    # Step 3: Compute profile vector
    vector1 = compute_profile(profile1)
    print(f"✅ Profile vector computed: {len(vector1)} components")
    top_components = sorted(enumerate(vector1), key=lambda x: x[1], reverse=True)[:3]
    for idx, val in top_components:
        print(f"   Component {idx}: {val:.3f}")
    
    print("\n" + "="*70)
    print("📝 STUDENT 2: Leadership + Communication Profile")
    print("-" * 70)
    
    student2_responses = {
        "q_passion_tech": 1,
        "q_love_coding": 1,
        "q_solve_problems": 2,
        "q_create_things": 2,
        "q_lead_team": 4,
        "q_social_networks": 4,
        "q_learn_quickly": 3,
        "q_entrepreneurship": 4,
        "q_communicate_well": 4,
        "q_handle_pressure": 4
    }
    
    # Step 1: Build features
    features2 = build_features(student2_responses, "field")
    print(f"\n✅ Features extracted: {len(features2)} domains")
    for domain, score in sorted(features2.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"   {domain}: {score:.2f}⭐")
    
    # Step 2: Create orientation profile
    domains2 = {k.replace("domain_", ""): v for k, v in features2.items() if k.startswith("domain_")}
    skills2 = {k.replace("skill_", ""): v for k, v in features2.items() if k.startswith("skill_")}
    profile2 = OrientationProfile(domains=domains2, skills=skills2)
    print(f"\n✅ Profile created: {len(domains2)} domains, {len(skills2)} skills")
    
    # Step 3: Compute profile vector
    vector2 = compute_profile(profile2)
    print(f"✅ Profile vector computed: {len(vector2)} components")
    top_components = sorted(enumerate(vector2), key=lambda x: x[1], reverse=True)[:3]
    for idx, val in top_components:
        print(f"   Component {idx}: {val:.3f}")
    
    print("\n" + "="*70)
    print("📊 COMPARISON")
    print("="*70)
    
    # Compare vectors
    differences = sum(1 for v1, v2 in zip(vector1, vector2) if abs(v1 - v2) > 0.01)
    print(f"\n✅ Vector differences: {differences}/{len(vector1)} components differ significantly")
    
    # Check they're different
    vectors_identical = all(abs(v1 - v2) < 0.001 for v1, v2 in zip(vector1, vector2))
    print(f"✅ Vectors are identical: {vectors_identical}")
    
    if vectors_identical:
        print("❌ ERROR: Both students got identical profiles (bug not fixed!)")
        return False
    else:
        print("\n✅ SUCCESS! Different students get different profiles!")
        print("   Student 1 optimized for: Tech + Analysis")
        print("   Student 2 optimized for: Leadership + Communication")
        return True


if __name__ == "__main__":
    try:
        success = test_complete_pipeline()
        
        print("\n" + "="*70)
        if success:
            print("✅ INTEGRATION TEST PASSED!")
            print("   The quiz recommendation system is working correctly!")
        else:
            print("❌ INTEGRATION TEST FAILED!")
            sys.exit(1)
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
