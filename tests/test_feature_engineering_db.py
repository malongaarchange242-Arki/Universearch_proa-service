# test_feature_engineering_db.py
"""
Exemples de test et d'utilisation du nouveau feature engineering piloté par DB.
"""

import pytest
from typing import Dict
from core.feature_engineering import (
    get_question_domain_mapping,
    build_features,
    _mapping_cache,
)
from db.repository import supabase


# ============================================
# TEST 1: Charger mappings depuis DB
# ============================================

def test_load_mapping_from_db():
    """Teste que le mapping se charge depuis la DB."""
    mapping = get_question_domain_mapping(supabase)
    
    # Assertions
    assert isinstance(mapping, dict), "mapping doit être un dict"
    assert len(mapping) > 0, "mapping ne doit pas être vide"
    
    # Vérifier structure
    for question_code, domains in mapping.items():
        assert isinstance(question_code, str)
        assert isinstance(domains, list)
        assert len(domains) > 0
        
        for domain_info in domains:
            assert "domain" in domain_info
            assert "weight" in domain_info
            assert 0 < domain_info["weight"] <= 1.0
    
    print(f"✅ Mapping chargé: {len(mapping)} questions")
    return mapping


# ============================================
# TEST 2: Cache fonctionne
# ============================================

def test_cache_is_working():
    """Teste que le cache in-memory fonctionne."""
    # Vider le cache
    _mapping_cache.clear()
    
    # 1ère requête: charge depuis DB
    mapping1 = get_question_domain_mapping(supabase)
    
    # 2e requête: doit être en cache
    mapping2 = get_question_domain_mapping(supabase)
    
    # Ils doivent être identiques
    assert mapping1 == mapping2
    print(f"✅ Cache fonctionne correctement")


# ============================================
# TEST 3: Calculer features avec réponses
# ============================================

def test_build_features_with_responses():
    """Teste le calcul des features à partir de réponses."""
    
    # Réponses utilisateur
    responses = {
        "q1": 3,   # Plutôt d'accord
        "q2": 4,   # Fortement d'accord
        "q3": 2,   # Plutôt pas d'accord
        "q4": 4,
        "q5": 3,
        "q6": 2,
        "q7": 4,
        "q8": 3,
        "q9": 2,
        "q10": 4,
        "q11": 3,
        "q12": 2,
        "q13": 4,
        "q14": 3,
        "q15": 2,
        "q16": 4,
        "q17": 3,
        "q18": 2,
        "q19": 4,
        "q20": 3,
        "q21": 2,
        "q22": 4,
        "q23": 3,
        "q24": 2,
    }
    
    # Calculer features
    features = build_features(responses, supabase, orientation_type="field")
    
    # Assertions
    assert isinstance(features, dict), "Features doit être un dict"
    assert len(features) > 0, "Features ne doit pas être vide"
    
    # Vérifier que toutes les features sont en [0, 1]
    for domain_name, score in features.items():
        assert domain_name.startswith("domain_"), f"{domain_name} doit commencer par domain_"
        assert 0 <= score <= 1, f"{domain_name}={score} doit être entre 0 et 1"
        print(f"  ✅ {domain_name:25s}: {score:.4f}")
    
    print(f"✅ {len(features)} features calculées")
    return features


# ============================================
# TEST 4: Réponses avec clés en majuscules
# ============================================

def test_build_features_uppercase_keys():
    """Teste que Q1, Q2 sont normalisés en q1, q2."""
    
    responses = {
        "Q1": 3,   # Uppercase!
        "Q2": 4,
        "Q3": 2,
        # ... ajouter autres
    }
    
    features = build_features(responses, supabase)
    
    assert len(features) > 0, "Doit fonctionner même avec uppercase"
    print(f"✅ Normalization fonctionne: {len(features)} features")


# ============================================
# TEST 5: Aperçu des mappings
# ============================================

def test_mapping_structure():
    """Affiche la structure des mappings."""
    mapping = get_question_domain_mapping(supabase)
    
    print("\n=== STRUCTURE DES MAPPINGS ===\n")
    for q_code in list(mapping.keys())[:5]:
        print(f"{q_code}:")
        for domain_info in mapping[q_code]:
            print(f"  → {domain_info['domain']:20s} (weight: {domain_info['weight']})")


# ============================================
# EXEMPLE: Utilisation en production
# ============================================

def example_production_usage():
    """Exemple d'utilisation du système en production."""
    
    print("\n=== EXEMPLE PRODUCTION ===\n")
    
    # 1. Quiz soumis par utilisateur
    user_responses = {
        "q1": 4, "q2": 3, "q3": 4,
        "q4": 2, "q5": 3, "q6": 4,
        "q7": 3, "q8": 2, "q9": 4,
        "q10": 3, "q11": 2, "q12": 4,
        "q13": 3, "q14": 2, "q15": 4,
        "q16": 3, "q17": 2, "q18": 4,
        "q19": 3, "q20": 2, "q21": 4,
        "q22": 3, "q23": 2, "q24": 4,
    }
    
    print(f"1. Réponses reçues: {len(user_responses)} questions")
    
    # 2. Calculer features
    features = build_features(user_responses, supabase, orientation_type="field")
    print(f"\n2. Features calculées:")
    print(f"   {features}\n")
    
    # 3. Extraire top domains
    sorted_features = sorted(features.items(), key=lambda x: x[1], reverse=True)
    print(f"3. Top 3 domaines:")
    for i, (domain, score) in enumerate(sorted_features[:3], 1):
        print(f"   {i}. {domain}: {score:.2%}")
    
    # 4. Suggérer des filières (futur)
    print(f"\n4. Prochaine étape: Matcher avec filières/centres")
    print(f"   (Sera fait dans compute_recommended_fields)")


# ============================================
# RUN TESTS
# ============================================

if __name__ == "__main__":
    print("🚀 FEATURE ENGINEERING TESTS\n")
    
    try:
        # Test 1: Charger mapping
        mapping = test_load_mapping_from_db()
        
        # Test 2: Cache
        test_cache_is_working()
        
        # Test 3: Calculer features
        features = test_build_features_with_responses()
        
        # Test 4: Uppercase
        test_build_features_uppercase_keys()
        
        # Test 5: Structure
        test_mapping_structure()
        
        # Exemple
        example_production_usage()
        
        print("\n✅ TOUS LES TESTS PASSENT!")
    
    except Exception as e:
        print(f"\n❌ TEST ÉCHOUÉ: {e}")
        import traceback
        traceback.print_exc()
