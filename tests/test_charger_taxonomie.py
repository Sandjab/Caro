import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import json
import tempfile
import unittest
from pathlib import Path


def ecrire_artefact(dossier, mapping_lignes):
    d = Path(dossier)
    (d / "domaines.csv").write_text(
        "domaine_id;libelle;description;ordre\n"
        "numerique;Numérique & data;Le numérique;1\n",
        encoding="utf-8")
    (d / "competences_canoniques.csv").write_text(
        "competence_id;domaine_id;libelle;description;mots_cles\n"
        "site_web;numerique;Créer un site web;;site|web|html\n",
        encoding="utf-8")
    (d / "mapping_blocs.csv").write_text(
        "bloc_code;competence_id;methode;score\n" + mapping_lignes,
        encoding="utf-8")
    (d / "meta.json").write_text(
        json.dumps({"version": "1", "date": "2026-07-06", "modele": "test"}),
        encoding="utf-8")


class TestChargerTaxonomie(unittest.TestCase):
    def test_repertoire_absent(self):
        self.assertIsNone(build_db.charger_taxonomie(Path("n_existe_pas_xyz")))

    def test_chargement_nominal(self):
        with tempfile.TemporaryDirectory() as d:
            ecrire_artefact(d, "RNCP0001BC01;site_web;ia;0.9\n")
            taxo = build_db.charger_taxonomie(Path(d))
            self.assertIsNotNone(taxo)
            self.assertEqual(len(taxo.domaines), 1)
            self.assertEqual(len(taxo.competences), 1)
            self.assertEqual(taxo.mapping["RNCP0001BC01"], ("site_web", "ia", 0.9))
            self.assertEqual(taxo.meta["modele"], "test")

    def test_mapping_orphelin_ecarte(self):
        with tempfile.TemporaryDirectory() as d:
            ecrire_artefact(d, "RNCP0001BC01;inconnu;ia;0.9\n")
            taxo = build_db.charger_taxonomie(Path(d))
            self.assertNotIn("RNCP0001BC01", taxo.mapping)

    def test_csv_requis_manquant(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "domaines.csv").write_text("domaine_id;libelle\n", encoding="utf-8")
            self.assertIsNone(build_db.charger_taxonomie(Path(d)))

    def test_score_non_numerique_tolere(self):
        with tempfile.TemporaryDirectory() as d:
            ecrire_artefact(d, "RNCP0001BC01;site_web;ia;abc\n")
            taxo = build_db.charger_taxonomie(Path(d))
            self.assertIsNotNone(taxo)
            self.assertEqual(taxo.mapping["RNCP0001BC01"], ("site_web", "ia", None))

    def test_competence_sans_id_ignoree(self):
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d)
            (dossier / "domaines.csv").write_text(
                "domaine_id;libelle;description;ordre\n"
                "numerique;Numérique & data;Le numérique;1\n",
                encoding="utf-8")
            (dossier / "competences_canoniques.csv").write_text(
                "competence_id;domaine_id;libelle;description;mots_cles\n"
                "site_web;numerique;Créer un site web;;site|web|html\n"
                ";numerique;Compétence sans id;;\n",
                encoding="utf-8")
            (dossier / "mapping_blocs.csv").write_text(
                "bloc_code;competence_id;methode;score\n"
                "RNCP0001BC01;site_web;ia;0.9\n",
                encoding="utf-8")
            (dossier / "meta.json").write_text(
                json.dumps({"version": "1", "date": "2026-07-06", "modele": "test"}),
                encoding="utf-8")
            taxo = build_db.charger_taxonomie(dossier)
            self.assertIsNotNone(taxo)
            self.assertEqual(len(taxo.competences), 1)
            self.assertEqual(taxo.competences[0]["competence_id"], "site_web")


if __name__ == "__main__":
    unittest.main()
