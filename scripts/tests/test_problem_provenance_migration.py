import unittest
from pathlib import Path


class ProblemProvenanceMigrationTest(unittest.TestCase):
    def test_migration_is_present_and_idempotent(self):
        migration = (
            Path(__file__).parents[2]
            / "sql"
            / "migrations"
            / "001_problem_provenance.sql"
        )

        self.assertTrue(migration.is_file())
        sql = migration.read_text(encoding="utf-8")
        self.assertIn("problem_source_system", sql)
        self.assertIn("problem_source_domain", sql)
        self.assertIn("problem_source_id", sql)
        self.assertIn("problem_content_sha256", sql)
        self.assertIn("problem_provenance", sql)
        self.assertIn("information_schema.COLUMNS", sql)
        self.assertIn("information_schema.STATISTICS", sql)
        self.assertNotIn("DROP TABLE", sql.upper())
    def test_identity_mapping_migration_is_guarded_and_preserves_foreign_keys(self):
        migration = (
            Path(__file__).parents[2]
            / "sql"
            / "migrations"
            / "002_problem_identity_mapping.sql"
        )

        self.assertTrue(migration.is_file())
        sql = migration.read_text(encoding="utf-8")
        for old_id, source_id, target_id in (
            (2024, "P00278", 278),
            (2025, "P00279", 279),
            (2026, "P00280", 280),
        ):
            self.assertIn(str(old_id), sql)
            self.assertIn(source_id, sql)
            self.assertIn(str(target_id), sql)
        self.assertIn("START TRANSACTION", sql)
        self.assertIn("FOR UPDATE", sql)
        self.assertIn("SIGNAL SQLSTATE", sql)
        self.assertNotIn("FOREIGN_KEY_CHECKS", sql.upper())
        self.assertNotIn("DROP TABLE", sql.upper())


if __name__ == "__main__":
    unittest.main()
