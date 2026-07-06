import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Force l'UTF-8 dans le process enfant : sous pipe redirigé, Windows utiliserait
# cp1252 et échouerait sur les caractères comme « … » des messages de log.
ENV_UTF8 = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def fabriquer_fixtures(base: Path):
    # Zip CSV : une fiche active (RNCP0001), une inactive (RNCP0002).
    csv_zip = base / "export-fiches-csv-2026-07-05.zip"
    with zipfile.ZipFile(csv_zip, "w") as z:
        z.writestr(
            "export_fiches_CSV_Standard_2026-07-05.csv",
            "Numero_Fiche;Intitule;Actif\n"
            "RNCP0001;Développeur web;ACTIVE\n"
            "RNCP0002;Ancien titre;INACTIVE\n")
    # Zip XML RNCP : blocs de RNCP0001 (BC01 mappé ia, BC02 lexical, BC03 non_classe).
    xml_zip = base / "export-fiches-rncp-v4-1-2026-07-05.zip"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><FICHES>'
        '<FICHE><NUMERO_FICHE>RNCP0001</NUMERO_FICHE><ACTIF>Oui</ACTIF>'
        '<BLOCS_COMPETENCES>'
        '<BLOC><CODE>RNCP0001BC01</CODE><LIBELLE>Bloc mappé</LIBELLE>'
        '<LISTE_COMPETENCES>peu importe</LISTE_COMPETENCES></BLOC>'
        '<BLOC><CODE>RNCP0001BC02</CODE><LIBELLE>Créer et gérer un site web</LIBELLE>'
        '<LISTE_COMPETENCES>coder html css serveur</LISTE_COMPETENCES></BLOC>'
        '<BLOC><CODE>RNCP0001BC03</CODE><LIBELLE>wobble frobnicate</LIBELLE>'
        '<LISTE_COMPETENCES>gizmo widget</LISTE_COMPETENCES></BLOC>'
        '</BLOCS_COMPETENCES></FICHE>'
        '<FICHE><NUMERO_FICHE>RNCP0002</NUMERO_FICHE><ACTIF>Non</ACTIF>'
        '</FICHE></FICHES>')
    with zipfile.ZipFile(xml_zip, "w") as z:
        z.writestr("export_fiches_RNCP_V4_1_2026-07-05.xml", xml)
    # Artefact taxonomie.
    taxo = base / "taxonomie"
    taxo.mkdir()
    (taxo / "domaines.csv").write_text(
        "domaine_id;libelle;description;ordre\nnumerique;Numérique;;1\n",
        encoding="utf-8")
    (taxo / "competences_canoniques.csv").write_text(
        "competence_id;domaine_id;libelle;description;mots_cles\n"
        "site_web;numerique;Créer un site web;;site|web|html|css|serveur\n",
        encoding="utf-8")
    (taxo / "mapping_blocs.csv").write_text(
        "bloc_code;competence_id;methode;score\nRNCP0001BC01;site_web;ia;0.9\n",
        encoding="utf-8")
    (taxo / "meta.json").write_text(
        json.dumps({"version": "1", "date": "2026-07-06", "modele": "test"}),
        encoding="utf-8")
    return csv_zip, xml_zip, taxo


class TestBoutEnBout(unittest.TestCase):
    def test_construction_avec_taxonomie(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            csv_zip, xml_zip, taxo = fabriquer_fixtures(base)
            db = base / "test.sqlite3"
            r = subprocess.run(
                [sys.executable, "build_db.py",
                 "--csv-zip", str(csv_zip), "--xml-zip", str(xml_zip),
                 "--taxonomie-dir", str(taxo), "--db", str(db)],
                cwd=RACINE, capture_output=True, text=True,
                encoding="utf-8", env=ENV_UTF8)
            self.assertEqual(r.returncode, 0, r.stderr)
            conn = sqlite3.connect(db)
            meta = dict(conn.execute("SELECT cle, valeur FROM meta"))
            self.assertEqual(meta["taxonomie"], "oui")
            self.assertEqual(meta["nb_competences_canoniques"], "1")
            self.assertEqual(meta["taxonomie_modele"], "test")
            methodes = dict(conn.execute(
                "SELECT bloc_code, methode FROM bloc_competence_canonique"))
            self.assertEqual(methodes,
                             {"RNCP0001BC01": "ia", "RNCP0001BC02": "lexical",
                              "RNCP0001BC03": "non_classe"})
            vue = conn.execute(
                "SELECT COUNT(*) FROM certification_competence").fetchone()[0]
            self.assertEqual(vue, 1)
            conn.close()

    def test_no_taxonomie(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            csv_zip, xml_zip, _ = fabriquer_fixtures(base)
            db = base / "test.sqlite3"
            r = subprocess.run(
                [sys.executable, "build_db.py",
                 "--csv-zip", str(csv_zip), "--xml-zip", str(xml_zip),
                 "--no-taxonomie", "--db", str(db)],
                cwd=RACINE, capture_output=True, text=True,
                encoding="utf-8", env=ENV_UTF8)
            self.assertEqual(r.returncode, 0, r.stderr)
            conn = sqlite3.connect(db)
            meta = dict(conn.execute("SELECT cle, valeur FROM meta"))
            self.assertEqual(meta["taxonomie"], "non")
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn("competence_canonique", tables)
            conn.close()


if __name__ == "__main__":
    unittest.main()
