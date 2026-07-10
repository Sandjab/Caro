import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import tempfile
import shutil
import unittest
import sqlite3
from pathlib import Path


def ecrire_taxo(base: Path, avec_fiches: bool):
    """Écrit un artefact taxonomie minimal ; ajoute mapping_fiches.csv si demandé."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "domaines.csv").write_text(
        "domaine_id;libelle;description;ordre\nnumerique;Numérique;;1\n",
        encoding="utf-8")
    (base / "competences_canoniques.csv").write_text(
        "competence_id;domaine_id;libelle;description;mots_cles\n"
        "site_web;numerique;Créer un site web;;site|web\n",
        encoding="utf-8")
    (base / "mapping_blocs.csv").write_text(
        "bloc_code;competence_id;methode;score\nRNCP0001BC01;site_web;ia;0.9\n",
        encoding="utf-8")
    if avec_fiches:
        (base / "mapping_fiches.csv").write_text(
            "numero_fiche;competence_id;methode\n"
            "RS0009;site_web;ia\n"            # valide
            "RS0009;inconnue;ia\n"            # competence inconnue -> ignorée
            "RNCP0003;site_web;humain\n",     # valide, methode humain
            encoding="utf-8")


class TestChargerMappingFiches(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_fiche_mapping_absent_vide(self):
        ecrire_taxo(self.d, avec_fiches=False)
        taxo = build_db.charger_taxonomie(self.d)
        self.assertEqual(taxo.fiche_mapping, [])

    def test_fiche_mapping_charge_et_filtre_orphelins(self):
        ecrire_taxo(self.d, avec_fiches=True)
        taxo = build_db.charger_taxonomie(self.d)
        self.assertEqual(
            sorted(taxo.fiche_mapping),
            [("RNCP0003", "site_web", "humain"), ("RS0009", "site_web", "ia")])


def taxo_avec_fiches():
    domaines = [{"domaine_id": "numerique", "libelle": "Numérique",
                 "description": "", "ordre": "1"}]
    competences = [{"competence_id": "site_web", "domaine_id": "numerique",
                    "libelle": "Créer un site web", "description": "",
                    "mots_cles": "site|web"}]
    t = build_db.Taxonomie(domaines, competences, {}, {},
                           fiche_mapping=[("RS0009", "site_web", "ia"),
                                          ("RS0009", "site_web", "ia"),   # doublon
                                          ("RNCP0003", "site_web", "humain")])
    return t


class TestConstruireFicheCompetence(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        # competence_canonique doit préexister (créée par construire_taxonomie)
        self.conn.execute(
            "CREATE TABLE competence_canonique (competence_id TEXT PRIMARY KEY, "
            "domaine_id TEXT, libelle TEXT, description TEXT, mots_cles TEXT, "
            "nb_blocs INTEGER DEFAULT 0)")
        self.conn.execute(
            "INSERT INTO competence_canonique (competence_id, domaine_id) "
            "VALUES ('site_web', 'numerique')")
        self.stats = build_db.construire_fiche_competence(self.conn, taxo_avec_fiches())

    def test_table_creee_et_dedupe(self):
        rows = self.conn.execute(
            "SELECT numero_fiche, competence_id, methode "
            "FROM fiche_competence_canonique ORDER BY numero_fiche").fetchall()
        self.assertEqual(
            rows, [("RNCP0003", "site_web", "humain"),
                   ("RS0009", "site_web", "ia")])  # doublon RS0009 fusionné

    def test_stats(self):
        self.assertEqual(self.stats["nb_rattachements_fiche"], 2)
        self.assertEqual(self.stats["nb_fiches_rattachees"], 2)

    def test_table_vide_si_mapping_vide(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE competence_canonique (competence_id TEXT)")
        t = build_db.Taxonomie([], [], {}, {}, fiche_mapping=[])
        stats = build_db.construire_fiche_competence(conn, t)
        n = conn.execute("SELECT COUNT(*) FROM fiche_competence_canonique").fetchone()[0]
        self.assertEqual(n, 0)
        self.assertEqual(stats["nb_fiches_rattachees"], 0)
