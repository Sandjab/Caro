import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import sqlite3
import unittest


def conn_avec_blocs():
    """Base en mémoire avec un bloc_competences_xml minimal (3 blocs)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE bloc_competences_xml ("
        "numero_fiche TEXT, repertoire TEXT, bloc_code TEXT, bloc_libelle TEXT, "
        "liste_competences TEXT, modalites_evaluation TEXT)")
    conn.executemany(
        "INSERT INTO bloc_competences_xml VALUES (?,?,?,?,?,?)",
        [
            ("RNCP0001", "RNCP", "RNCP0001BC01", "Bloc mappé", "peu importe", ""),
            ("RNCP0001", "RNCP", "RNCP0001BC02",
             "Créer et gérer un site web", "coder html css serveur", ""),
            ("RNCP0001", "RNCP", "RNCP0001BC03",
             "wobble frobnicate", "gizmo widget", ""),
        ])
    conn.commit()
    return conn


def taxo_test():
    domaines = [{"domaine_id": "numerique", "libelle": "Numérique",
                 "description": "", "ordre": "1"}]
    competences = [
        {"competence_id": "site_web", "domaine_id": "numerique",
         "libelle": "Créer un site web", "description": "",
         "mots_cles": "site|web|html|css|serveur"},
        {"competence_id": "gestion", "domaine_id": "numerique",
         "libelle": "Gérer", "description": "", "mots_cles": "gestion|budget"},
    ]
    mapping = {"RNCP0001BC01": ("site_web", "ia", 0.9)}
    return build_db.Taxonomie(domaines, competences, mapping, {})


class TestConstruireTaxonomie(unittest.TestCase):
    def setUp(self):
        self.conn = conn_avec_blocs()
        self.stats = build_db.construire_taxonomie(self.conn, taxo_test())

    def test_tables_creees(self):
        noms = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertLessEqual(
            {"domaine", "competence_canonique", "bloc_competence_canonique"}, noms)

    def test_trois_methodes(self):
        m = dict(self.conn.execute(
            "SELECT bloc_code, methode FROM bloc_competence_canonique"))
        self.assertEqual(m["RNCP0001BC01"], "ia")
        self.assertEqual(m["RNCP0001BC02"], "lexical")
        self.assertEqual(m["RNCP0001BC03"], "non_classe")

    def test_non_classe_competence_nulle(self):
        cid = self.conn.execute(
            "SELECT competence_id FROM bloc_competence_canonique "
            "WHERE bloc_code='RNCP0001BC03'").fetchone()[0]
        self.assertIsNone(cid)

    def test_nb_blocs(self):
        nb = dict(self.conn.execute(
            "SELECT competence_id, nb_blocs FROM competence_canonique"))
        self.assertEqual(nb["site_web"], 2)  # BC01 (ia) + BC02 (lexical)
        self.assertEqual(nb["gestion"], 0)

    def test_stats(self):
        self.assertEqual(self.stats["nb_blocs"], 3)
        self.assertEqual(self.stats["blocs_ia"], 1)
        self.assertEqual(self.stats["blocs_lexical"], 1)
        self.assertEqual(self.stats["blocs_non_classe"], 1)

    def test_mapping_methode_malformee_comptee_ia(self):
        conn = conn_avec_blocs()
        taxo = taxo_test()
        taxo.mapping = {"RNCP0001BC01": ("site_web", "MANUEL", 0.9)}
        stats = build_db.construire_taxonomie(conn, taxo)
        methode = conn.execute(
            "SELECT methode FROM bloc_competence_canonique "
            "WHERE bloc_code='RNCP0001BC01'").fetchone()[0]
        self.assertEqual(methode, "ia")
        self.assertEqual(stats["blocs_ia"], 1)


if __name__ == "__main__":
    unittest.main()
