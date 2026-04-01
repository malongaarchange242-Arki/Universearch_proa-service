-- ============================================
-- MIGRATION 3b: Populate question_domain_mapping from orientation_config.json
-- ============================================

-- ⚠️ MANUEL: Adapter les domain_ids selon ta DB!

-- Exemple: Si vous avez ces domaines:
-- - 550e8400-e29b-41d4-a716-446655440000 → logic
-- - 550e8401-e29b-41d4-a716-446655440001 → technical
-- - 550e8402-e29b-41d4-a716-446655440002 → creativity
-- - etc.

-- SCRIPT À ADAPTER (remplacer les UUIDs):

-- Logic domain: q1, q3, q5
INSERT INTO question_domain_mapping (question_code, domain_id, weight)
VALUES 
    ('q1', '550e8400-e29b-41d4-a716-446655440000', 1.0),
    ('q3', '550e8400-e29b-41d4-a716-446655440000', 1.0),
    ('q5', '550e8400-e29b-41d4-a716-446655440000', 1.0)
ON CONFLICT (question_code, domain_id) DO NOTHING;

-- Technical domain: q2, q4, q6, q7, q8, q24
INSERT INTO question_domain_mapping (question_code, domain_id, weight)
VALUES 
    ('q2', '550e8401-e29b-41d4-a716-446655440001', 1.0),
    ('q4', '550e8401-e29b-41d4-a716-446655440001', 0.8),
    ('q6', '550e8401-e29b-41d4-a716-446655440001', 1.0),
    ('q7', '550e8401-e29b-41d4-a716-446655440001', 0.9),
    ('q8', '550e8401-e29b-41d4-a716-446655440001', 1.0),
    ('q24', '550e8401-e29b-41d4-a716-446655440001', 0.7)
ON CONFLICT (question_code, domain_id) DO NOTHING;

-- Creativity domain: q9, q10, q11
INSERT INTO question_domain_mapping (question_code, domain_id, weight)
VALUES 
    ('q9', '550e8402-e29b-41d4-a716-446655440002', 1.0),
    ('q10', '550e8402-e29b-41d4-a716-446655440002', 0.9),
    ('q11', '550e8402-e29b-41d4-a716-446655440002', 1.0)
ON CONFLICT (question_code, domain_id) DO NOTHING;

-- ... continuer avec tous les domaines ...

-- ✅ Vérifier:
SELECT 
    qm.question_code,
    d.name as domain_name,
    qm.weight
FROM question_domain_mapping qm
JOIN domaines d ON qm.domain_id = d.id
ORDER BY qm.question_code
LIMIT 25;
