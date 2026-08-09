SET @schema_name = DATABASE();

SET @statement = IF(
  EXISTS(
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'voj_problems'
      AND COLUMN_NAME = 'problem_source_system'
  ),
  'SELECT 1',
  'ALTER TABLE voj_problems ADD COLUMN problem_source_system varchar(32) COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER problem_hint'
);
PREPARE migration_statement FROM @statement;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @statement = IF(
  EXISTS(
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'voj_problems'
      AND COLUMN_NAME = 'problem_source_domain'
  ),
  'SELECT 1',
  'ALTER TABLE voj_problems ADD COLUMN problem_source_domain varchar(64) COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER problem_source_system'
);
PREPARE migration_statement FROM @statement;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @statement = IF(
  EXISTS(
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'voj_problems'
      AND COLUMN_NAME = 'problem_source_id'
  ),
  'SELECT 1',
  'ALTER TABLE voj_problems ADD COLUMN problem_source_id varchar(128) COLLATE utf8mb4_unicode_ci DEFAULT NULL AFTER problem_source_domain'
);
PREPARE migration_statement FROM @statement;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @statement = IF(
  EXISTS(
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'voj_problems'
      AND COLUMN_NAME = 'problem_content_sha256'
  ),
  'SELECT 1',
  'ALTER TABLE voj_problems ADD COLUMN problem_content_sha256 char(64) COLLATE ascii_bin DEFAULT NULL AFTER problem_source_id'
);
PREPARE migration_statement FROM @statement;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;

SET @statement = IF(
  EXISTS(
    SELECT 1 FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = @schema_name
      AND TABLE_NAME = 'voj_problems'
      AND INDEX_NAME = 'problem_provenance'
  ),
  'SELECT 1',
  'ALTER TABLE voj_problems ADD UNIQUE KEY problem_provenance (problem_source_system, problem_source_domain, problem_source_id)'
);
PREPARE migration_statement FROM @statement;
EXECUTE migration_statement;
DEALLOCATE PREPARE migration_statement;
