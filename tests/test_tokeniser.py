import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import unittest


class TestTokeniser(unittest.TestCase):
    def test_minuscule_sans_accent(self):
        self.assertEqual(build_db.tokeniser("Créer"), {"creer"})

    def test_split_et_longueur_min(self):
        # "de" (2 car.) écarté ; "web" gardé
        self.assertEqual(build_db.tokeniser("Développeur de web"), {"developpeur", "web"})

    def test_mots_vides_ecartes(self):
        # "les", "des" sont des mots vides
        self.assertEqual(build_db.tokeniser("les blocs des competences"),
                         {"blocs", "competences"})

    def test_chaine_vide(self):
        self.assertEqual(build_db.tokeniser(""), set())


if __name__ == "__main__":
    unittest.main()
