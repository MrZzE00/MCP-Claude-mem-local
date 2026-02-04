-- Migration des catégories MCP-Claude-mem-local
-- Ajoute la catégorie 'preference' à la contrainte CHECK
-- Exécuter avec: psql -U claude -d claude_memory -f scripts/migrate-categories.sql

BEGIN;

-- Supprimer l'ancienne contrainte
ALTER TABLE memories DROP CONSTRAINT IF EXISTS valid_category;

-- Ajouter la nouvelle contrainte avec toutes les 10 catégories
ALTER TABLE memories ADD CONSTRAINT valid_category CHECK (category IN (
    'bugfix', 'decision', 'feature', 'discovery',
    'refactor', 'change', 'learning', 'pattern',
    'error_solution', 'preference'
));

-- Vérification
SELECT 'Migration réussie! Catégories disponibles:' AS status;
SELECT DISTINCT category, COUNT(*) as count
FROM memories
GROUP BY category
ORDER BY count DESC;

COMMIT;
