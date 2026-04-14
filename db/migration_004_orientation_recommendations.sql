-- ============================================
-- MIGRATION 4: Create orientation_recommendations table
-- ============================================
-- 📊 Enregistrement des recommandations générées par PORA
-- Permet de tracer, analyser et améliorer les recommandations

-- ✅ ÉTAPE 1: Créer la table orientation_recommendations
CREATE TABLE IF NOT EXISTS orientation_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- 🔗 Contexte utilisateur
    user_id UUID NOT NULL REFERENCES profiles(user_id) ON DELETE CASCADE,
    profile_id UUID NOT NULL REFERENCES orientation_profiles(id) ON DELETE CASCADE,
    session_id UUID NOT NULL,  -- Regrouper une session complète de recommandations
    
    -- 🎯 Détail de la recommandation
    target_type VARCHAR(50) NOT NULL CHECK (target_type IN ('filiere', 'universite', 'centre')),
    target_id VARCHAR(255) NOT NULL,  -- ID de la filière/université
    target_name VARCHAR(255) NOT NULL,  -- Nom lisible
    
    -- 📈 Scores et ranking
    score FLOAT NOT NULL CHECK (score >= 0 AND score <= 1),
    rank INT NOT NULL CHECK (rank > 0),
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    
    -- 🧠 Raison de la recommandation
    reason TEXT,  -- Détail: "77% match orientation + 23% popularité"
    recommendation_engine VARCHAR(100),  -- "pora_v1", "pora_v2", etc.
    
    -- 📊 Métadata
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ✅ ÉTAPE 2: Créer les indexes
CREATE INDEX IF NOT EXISTS idx_recommendations_user_id 
ON orientation_recommendations(user_id);

CREATE INDEX IF NOT EXISTS idx_recommendations_profile_id 
ON orientation_recommendations(profile_id);

CREATE INDEX IF NOT EXISTS idx_recommendations_session_id 
ON orientation_recommendations(session_id);

CREATE INDEX IF NOT EXISTS idx_recommendations_target 
ON orientation_recommendations(target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_recommendations_created_at 
ON orientation_recommendations(created_at DESC);

-- Index composite pour analyser les patterns
CREATE INDEX IF NOT EXISTS idx_recommendations_user_target 
ON orientation_recommendations(user_id, target_type, target_id);

-- ✅ ÉTAPE 3: Trigger pour updated_at
CREATE OR REPLACE FUNCTION update_orientation_recommendations_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER orientation_recommendations_updated_at
BEFORE UPDATE ON orientation_recommendations
FOR EACH ROW
EXECUTE FUNCTION update_orientation_recommendations_timestamp();

-- ✅ ÉTAPE 4: Vue analytique - Top recommandations par type
CREATE OR REPLACE VIEW v_top_recommendations_by_type AS
SELECT 
    target_type,
    target_name,
    COUNT(*) as recommendation_count,
    ROUND(AVG(score)::numeric, 2) as avg_score,
    ROUND(AVG(confidence)::numeric, 2) as avg_confidence,
    MAX(created_at) as last_recommended
FROM orientation_recommendations
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY target_type, target_name
ORDER BY recommendation_count DESC;

-- ✅ ÉTAPE 5: Vue analytique - Recommandations par profil
CREATE OR REPLACE VIEW v_recommendations_by_profile AS
SELECT 
    p.id as profile_id,
    COUNT(DISTINCT r.user_id) as unique_users,
    COUNT(*) as total_recommendations,
    ROUND(AVG(r.score)::numeric, 2) as avg_recommendation_score,
    STRING_AGG(DISTINCT r.target_name, ', ' ORDER BY r.target_name) as top_targets
FROM orientation_recommendations r
JOIN orientation_profiles p ON r.profile_id = p.id
GROUP BY p.id
ORDER BY total_recommendations DESC;

-- ✅ ÉTAPE 6: Vue pour détecter les biais
CREATE OR REPLACE VIEW v_recommendation_bias_detection AS
SELECT 
    target_type,
    target_name,
    COUNT(*) as total_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY target_type)::numeric, 2) as percentage,
    ROUND(AVG(score)::numeric, 3) as avg_score,
    COUNT(CASE WHEN score >= 0.8 THEN 1 END) as high_confidence_count,
    MIN(created_at) as first_recommended,
    MAX(created_at) as last_recommended
FROM orientation_recommendations
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY target_type, target_name
HAVING COUNT(*) >= 5  -- Au moins 5 recommandations pour être significatif
ORDER BY total_count DESC;
