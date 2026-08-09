DELIMITER //

DROP PROCEDURE IF EXISTS migrate_problem_identity_mapping//
CREATE PROCEDURE migrate_problem_identity_mapping()
BEGIN
  DECLARE unmigrated_count INT DEFAULT 0;
  DECLARE migrated_count INT DEFAULT 0;
  DECLARE occupied_count INT DEFAULT 0;

  START TRANSACTION;

  SELECT COUNT(*) INTO unmigrated_count
  FROM voj_problems
  WHERE (problem_id = 2024 AND problem_source_system = 'manual' AND problem_source_domain = 'user-provided' AND problem_source_id = 'P00278')
     OR (problem_id = 2025 AND problem_source_system = 'manual' AND problem_source_domain = 'user-provided' AND problem_source_id = 'P00279')
     OR (problem_id = 2026 AND problem_source_system = 'manual' AND problem_source_domain = 'user-provided' AND problem_source_id = 'P00280')
  FOR UPDATE;

  SELECT COUNT(*) INTO migrated_count
  FROM voj_problems
  WHERE (problem_id = 278 AND problem_source_system = 'manual' AND problem_source_domain = 'user-provided' AND problem_source_id = 'P00278')
     OR (problem_id = 279 AND problem_source_system = 'manual' AND problem_source_domain = 'user-provided' AND problem_source_id = 'P00279')
     OR (problem_id = 280 AND problem_source_system = 'manual' AND problem_source_domain = 'user-provided' AND problem_source_id = 'P00280')
  FOR UPDATE;

  SELECT COUNT(*) INTO occupied_count
  FROM voj_problems
  WHERE problem_id IN (278, 279, 280, 2024, 2025, 2026)
  FOR UPDATE;

  IF migrated_count = 3 AND unmigrated_count = 0 AND occupied_count = 3 THEN
    COMMIT;
  ELSEIF unmigrated_count = 3 AND migrated_count = 0 AND occupied_count = 3 THEN
    UPDATE voj_problems
    SET problem_id = CASE problem_id
      WHEN 2024 THEN 278
      WHEN 2025 THEN 279
      WHEN 2026 THEN 280
    END
    WHERE problem_id IN (2024, 2025, 2026);

    IF ROW_COUNT() <> 3 THEN
      SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'problem identity migration did not update exactly three rows';
    END IF;
    COMMIT;
  ELSE
    ROLLBACK;
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'problem identity migration requires a complete unmigrated or migrated state';
  END IF;
END//

CALL migrate_problem_identity_mapping()//
DROP PROCEDURE migrate_problem_identity_mapping//

DELIMITER ;
