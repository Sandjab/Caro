import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import unittest
from tests.test_construire_taxonomie import conn_avec_blocs, taxo_test


class TestVue(unittest.TestCase):
    def setUp(self):
        self.conn = conn_avec_blocs()
        build_db.construire_taxonomie(self.conn, taxo_test())
        build_db.construire_fiche_competence(self.conn, taxo_test())
        build_db.creer_vue_certification_competence(self.conn)
        build_db.indexer_taxonomie(self.conn)

    def test_vue_certification_competence(self):
        rows = self.conn.execute(
            "SELECT numero_fiche, competence_id, domaine_id "
            "FROM certification_competence ORDER BY competence_id").fetchall()
        # BC01+BC02 -> site_web (distinct) ; BC03 non_classe exclu
        self.assertEqual(rows, [("RNCP0001", "site_web", "numerique")])

    def test_index_crees(self):
        idx = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("idx_bcc_numero", idx)
        self.assertIn("idx_bcc_competence", idx)


if __name__ == "__main__":
    unittest.main()
