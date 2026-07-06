import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import unittest


class TestScoreLexical(unittest.TestCase):
    def test_jaccard(self):
        # inter = {b, c} (2) ; union = {a, b, c, d} (4) -> 0.5
        self.assertAlmostEqual(
            build_db.score_lexical({"a", "b", "c"}, {"b", "c", "d"}), 0.5)

    def test_ensemble_vide(self):
        self.assertEqual(build_db.score_lexical(set(), {"a"}), 0.0)


class TestMeilleurMatch(unittest.TestCase):
    def setUp(self):
        self.competences = {
            "site_web": build_db.tokeniser("site web html css serveur"),
            "gestion": build_db.tokeniser("gestion comptabilite budget"),
        }

    def test_match_au_dessus_du_seuil(self):
        cid, score = build_db.meilleur_match_lexical(
            "Créer et gérer un site web avec HTML et CSS", self.competences, 0.12)
        self.assertEqual(cid, "site_web")
        self.assertGreaterEqual(score, 0.12)

    def test_sous_le_seuil_renvoie_none(self):
        cid, score = build_db.meilleur_match_lexical(
            "wobble frobnicate gizmo", self.competences, 0.12)
        self.assertIsNone(cid)
        self.assertLess(score, 0.12)


if __name__ == "__main__":
    unittest.main()
