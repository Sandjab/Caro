import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import tempfile
import shutil
import unittest
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
