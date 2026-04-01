-- ============================================
-- MIGRATION 3: Create question_domain_mapping table
-- ============================================

-- ✅ ÉTAPE 1: Créer la table question_domain_mapping
CREATE TABLE IF NOT EXISTS question_domain_mapping (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_code TEXT NOT NULL,
    domain_id UUID NOT NULL REFERENCES domaines(id) ON DELETE CASCADE,
    weight FLOAT NOT NULL DEFAULT 1.0 CHECK (weight > 0 AND weight <= 1.0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ✅ ÉTAPE 2: Créer les indexes
CREATE INDEX IF NOT EXISTS idx_mapping_question_code 
ON question_domain_mapping(question_code);

CREATE INDEX IF NOT EXISTS idx_mapping_domain_id 
ON question_domain_mapping(domain_id);

CREATE INDEX IF NOT EXISTS idx_mapping_composite 
ON question_domain_mapping(question_code, domain_id);

-- ✅ ÉTAPE 3: Unique constraint pour éviter doublons
CREATE UNIQUE INDEX IF NOT EXISTS unique_question_domain 
ON question_domain_mapping(question_code, domain_id);

-- ✅ ÉTAPE 4: Trigger pour updated_at
CREATE OR REPLACE FUNCTION update_question_domain_mapping_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER question_domain_mapping_updated_at
BEFORE UPDATE ON question_domain_mapping
FOR EACH ROW
EXECUTE FUNCTION update_question_domain_mapping_timestamp();

-- ✅ ÉTAPE 5: Données initiales (mapper les questions q1-q24 aux domaines)
-- Cette étape dépend de ta config existante (orientation_config.json)
-- Exemple:

INSERT INTO question_domain_mapping (question_code, domain_id, weight)
SELECT 
    LOWER($1::text) as question_code,
    d.id as domain_id,
    COALESCE($2::float, 1.0) as weight
FROM domaines d
WHERE d.name = $3
ON CONFLICT (question_code, domain_id) DO UPDATE
SET weight = EXCLUDED.weight, updated_at = CURRENT_TIMESTAMP;

-- ✅ ÉTAPE 6: Vérifier les résultats
SELECT 
    qm.question_code,
    d.name as domain_name,
    qm.weight,
    qm.created_at
FROM question_domain_mapping qm
JOIN domaines d ON qm.domain_id = d.id
ORDER BY qm.question_code, d.name
LIMIT 50;

-- ✅ ÉTAPE 7: Compter les mappings
SELECT 
    COUNT(DISTINCT question_code) as total_questions,
    COUNT(DISTINCT domain_id) as total_domains,
    COUNT(*) as total_mappings
FROM question_domain_mapping;
