import os
import shutil
import subprocess
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestMatcherJS(unittest.TestCase):
    """Délègue à `node --test`. Node n'est pas une dépendance dure du dépôt :
    absent, la suite est ignorée — comme pour FTS5 dans build_db.py.

    Le motif ihm/*.test.js (plutôt que le seul dossier ihm) contourne un
    comportement observé de node --test sur cette machine (Node 24.13.0,
    Windows) : un chemin de dossier nu passé en argument positionnel est
    résolu comme point d'entrée du script principal (Module._load) au lieu
    de déclencher le balayage récursif de fichiers de test, et échoue avec
    « Cannot find module '<dossier>' » que le dossier soit vide, absent ou
    correctement peuplé — reproduit aussi avec un dossier de test sans
    rapport avec ihm/. `node --test` sans argument (auto-découverte) et
    `node --test <motif ou fichier>` fonctionnent correctement dans ce même
    environnement ; le motif explicite est préféré ici pour rester limité
    aux tests de ihm/ plutôt que balayer tout le dépôt.
    """

    def test_suite_node(self):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node absent du PATH : moteur JS non testé")
        motif = os.path.join(RACINE, "ihm", "*.test.js")
        r = subprocess.run([node, "--test", motif],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
