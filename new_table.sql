-- Table principale des scores
CREATE TABLE IF NOT EXISTS matcheur_filiere_scores (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,           -- ID de l'utilisateur
    session_id VARCHAR(255),                 -- ID de session (optionnel)
    filiere_id VARCHAR(255) NOT NULL,        -- ID de la filière
    filiere_name VARCHAR(500),               -- Nom de la filière (dénormalisé)
    cluster VARCHAR(100),                    -- Cluster PROA détecté
    score DECIMAL(5,4),                      -- Score de compatibilité (0-1)
    compatibility_level VARCHAR(20),         -- 'high', 'medium', 'low'
    duration_years DECIMAL(4,2),             -- Durée en années
    user_domains JSON,                       -- Domaines de l'utilisateur
    matched_domains JSON,                    -- Domaines matchés avec poids
    top_domains JSON,                        -- Top 3 domaines matchés
    all_domains JSON,                        -- Tous les domaines de la filière
    score_details JSON,                      -- Détails (rang, percentile, etc.)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Index pour performance
    INDEX idx_user_filiere (user_id, filiere_id),
    INDEX idx_session (session_id),
    INDEX idx_score (score DESC),
    INDEX idx_created (created_at DESC)
);

-- Table des historiques (optionnel - garder trace des évolutions)
CREATE TABLE IF NOT EXISTS matcheur_filiere_scores_history (
    id SERIAL PRIMARY KEY,
    original_id INTEGER,
    user_id VARCHAR(255) NOT NULL,
    filiere_id VARCHAR(255) NOT NULL,
    score DECIMAL(5,4),
    compatibility_level VARCHAR(20),
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);