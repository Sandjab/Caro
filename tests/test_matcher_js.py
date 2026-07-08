import os
import re
import shutil
import subprocess
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _nb_tests_executes(sortie: str) -> int | None:
    """Extrait le nombre de tests exécutés du récapitulatif de Node.

    Node imprime le récapitulatif en début de ligne, précédé d'un marqueur
    non-alphanumérique (« ℹ » pour reporter par défaut, « # » pour TAP).
    Ancre la regex sur le début de ligne pour éviter de capturer les nombres
    provenant des lignes de résultats individuels (par ex. « ✔ mes tests 0 »).

    Args:
        sortie: Sortie combinée (stdout + stderr) de Node.

    Returns:
        Nombre de tests exécutés, ou None si le récapitulatif est introuvable.
    """
    # Ancre sur le début de ligne (re.MULTILINE) en tolérant un préfixe
    # de marqueur non-alphanumérique ([^a-zA-Z0-9]*), suivi du mot "tests",
    # espaces, et le nombre jusqu'à la fin de ligne ($).
    # Évite de dépendre du caractère non-ASCII ℹ.
    match = re.search(r'^[^a-zA-Z0-9]*tests\s+(\d+)\s*\r?$', sortie, re.MULTILINE)
    if match:
        return int(match.group(1))
    return None


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
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        # Vérifier que le script a exécuté sans erreur.
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

        # Vérifier qu'au moins un test a été exécuté : analyser le récapitulatif
        # de Node pour extraire le nombre de tests.
        sortie = r.stdout + r.stderr
        nombre_tests = _nb_tests_executes(sortie)

        self.assertIsNotNone(
            nombre_tests,
            f"Aucun récapitulatif de test trouvé dans la sortie Node. "
            f"Le motif « {motif} » n'a probablement rien trouvé. "
            f"Sortie :\n{sortie}"
        )

        self.assertGreater(
            nombre_tests, 0,
            f"Aucun test n'a été exécuté (tests trouvés : {nombre_tests}). "
            f"Le motif « {motif} » n'a probablement rien trouvé. "
            f"Sortie :\n{sortie}"
        )

    def test_nb_tests_executes_regression(self):
        """Teste l'extraction du nombre de tests contre les faux positifs.

        Régression : ligne de résultat individuel « ✔ mes tests 0 » ne doit
        pas être confondue avec le récapitulatif « ℹ tests 1 ».
        """
        # Cas 1 : résultat individuel suivi du récapitulatif (faux positif
        # potentiel de l'ancienne regex).
        sortie_avec_faux_positif = (
            "✔ mes tests 0 passent toujours (0.4779ms)\n"
            "ℹ tests 1"
        )
        self.assertEqual(
            _nb_tests_executes(sortie_avec_faux_positif), 1,
            "Doit ignorer la ligne de résultat « mes tests 0 » "
            "et extraire le récapitulatif « tests 1 »"
        )

        # Cas 2 : récapitulatif seul avec zéro test.
        sortie_zero = "ℹ tests 0"
        self.assertEqual(
            _nb_tests_executes(sortie_zero), 0,
            "Doit extraire 0 du récapitulatif « tests 0 »"
        )

        # Cas 3 : récapitulatif avec marqueur TAP « # ».
        sortie_tap = "# tests 2"
        self.assertEqual(
            _nb_tests_executes(sortie_tap), 2,
            "Doit extraire le nombre du récapitulatif avec marqueur TAP"
        )

        # Cas 4 : sans préfixe marqueur (edge case edge valide).
        sortie_pas_marqueur = "tests 5"
        self.assertEqual(
            _nb_tests_executes(sortie_pas_marqueur), 5,
            "Doit extraire le nombre même sans marqueur de début"
        )

        # Cas 5 : pas de récapitulatif.
        sortie_vide = "✔ un test (1.2ms)"
        self.assertIsNone(
            _nb_tests_executes(sortie_vide),
            "Doit retourner None si le récapitulatif est absent"
        )

        # Cas 6 : récapitulatif avec fins de ligne Windows (CRLF).
        sortie_crlf = "ℹ tests 11\r\nℹ pass 11\r\n"
        self.assertEqual(
            _nb_tests_executes(sortie_crlf), 11,
            "Doit extraire le nombre même avec des fins de ligne CRLF"
        )

        # Cas 7 : faux positif potentiel avec CRLF (régression).
        sortie_crlf_avec_faux_positif = (
            "✔ mes tests 0 passent (0.4ms)\r\n"
            "ℹ tests 1\r\n"
        )
        self.assertEqual(
            _nb_tests_executes(sortie_crlf_avec_faux_positif), 1,
            "Doit ignorer la ligne de résultat et extraire le récapitulatif "
            "même avec des fins de ligne CRLF"
        )

        # Cas 8 : mot « suites » ne doit pas être confondu avec « tests ».
        sortie_avec_suites = "ℹ suites 3\nℹ tests 5"
        self.assertEqual(
            _nb_tests_executes(sortie_avec_suites), 5,
            "Doit extraire « tests 5 » et ignorer « suites 3 »"
        )


if __name__ == "__main__":
    unittest.main()
