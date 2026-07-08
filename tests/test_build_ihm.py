import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_ihm  # noqa: E402
import sqlite3
import unittest

# Seuil de paramètres pour détecter une clause IN variadique.
# Les requêtes légitimes lient 0 ou 1 paramètre ; 999 est la limite historique de SQLite.
# Un seuil de 50 permet de détecter un IN (?,?,…) sur des milliers de fiches.
SEUIL_PARAMETRES_MAX = 50


def conn_minimale():
    """Base en mémoire imitant rncp.sqlite3 : 4 fiches, 1 seule exploitable.

    RNCP0001 : VAE, 2 compétences, 2 blocs      -> retenue
    RNCP0002 : VAE, aucune compétence           -> exclue (comptée)
    RNCP0003 : apprentissage seulement          -> absente
    RNCP0004 : VAE, 1 compétence, sans niveau   -> retenue, niveau ""
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE voixdacces (numero_fiche TEXT, si_jury TEXT);
        CREATE TABLE standard (numero_fiche TEXT, intitule TEXT,
                               nomenclature_europe_niveau TEXT);
        CREATE TABLE nsf (numero_fiche TEXT, nsf_code TEXT, nsf_intitule TEXT);
        CREATE TABLE bloc_competences_xml (numero_fiche TEXT, bloc_code TEXT,
                               bloc_libelle TEXT, liste_competences TEXT);
        CREATE TABLE fiche_texte (numero_fiche TEXT, champ TEXT, contenu TEXT);
        CREATE TABLE domaine (domaine_id TEXT, libelle TEXT, ordre TEXT);
        CREATE TABLE competence_canonique (competence_id TEXT, domaine_id TEXT,
                               libelle TEXT, mots_cles TEXT);
        CREATE VIEW certification_competence AS
            SELECT 'RNCP0001' AS numero_fiche, 'site_web'  AS competence_id,
                   'numerique' AS domaine_id
            UNION ALL SELECT 'RNCP0001', 'oral',    'transversal'
            UNION ALL SELECT 'RNCP0004', 'site_web','numerique';
    """)
    conn.executemany("INSERT INTO voixdacces VALUES (?,?)", [
        ("RNCP0001", "Par expérience"),
        ("RNCP0001", "En contrat d’apprentissage"),
        ("RNCP0002", "Par expérience"),
        ("RNCP0003", "En contrat d’apprentissage"),
        ("RNCP0004", "Par expérience"),
    ])
    conn.executemany("INSERT INTO standard VALUES (?,?,?)", [
        ("RNCP0001", "Développeur web", "NIV6"),
        ("RNCP0002", "Fiche sans compétence", "NIV5"),
        ("RNCP0003", "Apprenti boulanger", "NIV3"),
        ("RNCP0004", "Fiche sans niveau", ""),
    ])
    conn.executemany("INSERT INTO nsf VALUES (?,?,?)", [
        ("RNCP0001", "326", "326 : Informatique"),
        ("RNCP0001", "326t", "326t : Programmation"),
        ("RNCP0002", "312", "312 : Commerce, vente"),
        ("RNCP0003", "221", "221 : Agro-alimentaire"),
        ("RNCP0004", "310", "310 : Spécialités plurivalentes"),
    ])
    conn.executemany("INSERT INTO bloc_competences_xml VALUES (?,?,?,?)", [
        ("RNCP0001", "RNCP0001BC01", "Créer un site", "coder html"),
        ("RNCP0001", "RNCP0001BC02", "Communiquer", "oral écrit"),
        ("RNCP0004", "RNCP0004BC01", "Faire un site", "html"),
    ])
    conn.executemany("INSERT INTO fiche_texte VALUES (?,?,?)", [
        ("RNCP0001", "objectifs_contexte", "Objectifs du dev web."),
        ("RNCP0001", "activites_visees", "Activités du dev web."),
        ("RNCP0001", "capacites_attestees", "NE DOIT PAS ÊTRE EMBARQUÉ"),
        ("RNCP0004", "objectifs_contexte", "Objectifs 4."),
    ])
    conn.executemany("INSERT INTO domaine VALUES (?,?,?)", [
        ("transversal", "Compétences transversales", "1"),
        ("numerique", "Numérique & informatique", "2"),
    ])
    conn.executemany("INSERT INTO competence_canonique VALUES (?,?,?,?)", [
        ("oral", "transversal", "S'exprimer à l'oral", "oral|écrit"),
        ("site_web", "numerique", "Créer un site web", "site|web|html"),
    ])
    conn.commit()
    return conn


class TestGardeFous(unittest.TestCase):
    def test_verifier_base_ok(self):
        self.assertIsNone(build_ihm.verifier_base(conn_minimale()))

    def test_vue_absente(self):
        conn = conn_minimale()
        conn.execute("DROP VIEW certification_competence")
        with self.assertRaises(build_ihm.ErreurIHM) as ctx:
            build_ihm.verifier_base(conn)
        self.assertIn("--no-taxonomie", str(ctx.exception))

    def test_aucune_fiche_vae_liste_les_valeurs_presentes(self):
        conn = conn_minimale()
        conn.execute("UPDATE voixdacces SET si_jury='Par l’expérience'")
        with self.assertRaises(build_ihm.ErreurIHM) as ctx:
            build_ihm.numeros_vae(conn)
        msg = str(ctx.exception)
        self.assertIn("Par expérience", msg)      # la valeur attendue
        self.assertIn("Par l’expérience", msg)    # les valeurs présentes

    def test_numeros_vae_filtre_et_dedoublonne(self):
        # RNCP0001 a deux voies d'accès dont la VAE : une seule occurrence
        self.assertEqual(build_ihm.numeros_vae(conn_minimale()),
                         ["RNCP0001", "RNCP0002", "RNCP0004"])


class TestIndex(unittest.TestCase):
    def setUp(self):
        self.conn = conn_minimale()
        self.index, self.exclues = build_ihm.construire_index(
            self.conn, build_ihm.numeros_vae(self.conn))

    def test_fiche_sans_competence_exclue_et_comptee(self):
        numeros = [c[0] for c in self.index["certifs"]]
        self.assertEqual(numeros, ["RNCP0001", "RNCP0004"])
        self.assertEqual(self.exclues, 1)
        self.assertEqual(self.index["exclues"], 1)

    def test_fiche_hors_vae_absente(self):
        numeros = [c[0] for c in self.index["certifs"]]
        self.assertNotIn("RNCP0003", numeros)

    def test_niveau_vide_conserve(self):
        c4 = next(c for c in self.index["certifs"] if c[0] == "RNCP0004")
        self.assertEqual(c4[2], "")

    def test_transversalite_marquee(self):
        par_id = {c[0]: c for c in self.index["competences"]}
        self.assertEqual(par_id["oral"][3], 1)
        self.assertEqual(par_id["site_web"][3], 0)

    def test_mots_cles_embarques_pour_la_recherche(self):
        par_id = {c[0]: c for c in self.index["competences"]}
        self.assertEqual(par_id["site_web"][4], "site|web|html")

    def test_nsf_regroupe_sur_deux_chiffres_et_dedoublonne(self):
        # RNCP0001 porte 326 et 326t -> un seul groupe "32"
        codes = [n[0] for n in self.index["nsf"]]
        c1 = next(c for c in self.index["certifs"] if c[0] == "RNCP0001")
        self.assertEqual([codes[i] for i in c1[3]], ["32"])

    def test_groupe_nsf_inconnu_leve(self):
        self.conn.execute(
            "INSERT INTO nsf VALUES ('RNCP0001','990','990 : Groupe inventé')")
        with self.assertRaises(build_ihm.ErreurIHM) as ctx:
            build_ihm.construire_index(self.conn, build_ihm.numeros_vae(self.conn))
        self.assertIn("99", str(ctx.exception))

    def test_les_seize_groupes_nsf_ont_un_libelle(self):
        self.assertEqual(len(build_ihm.GROUPES_NSF), 16)
        for prefixe, libelle in build_ihm.GROUPES_NSF.items():
            self.assertEqual(len(prefixe), 2)
            self.assertTrue(libelle.strip())

    def test_competences_referencees_par_indice(self):
        ids = [c[0] for c in self.index["competences"]]
        c1 = next(c for c in self.index["certifs"] if c[0] == "RNCP0001")
        self.assertEqual(sorted(ids[i] for i in c1[4]), ["oral", "site_web"])

    def test_domaine_id_inconnu_leve(self):
        # competence_canonique référence un domaine_id absent de la table
        # domaine : repli silencieux interdit, symétrique au garde-fou NSF.
        self.conn.execute(
            "INSERT INTO competence_canonique VALUES "
            "('fantome', 'domaine_fantome', 'Compétence fantôme', '')")
        with self.assertRaises(build_ihm.ErreurIHM) as ctx:
            build_ihm.construire_index(self.conn, build_ihm.numeros_vae(self.conn))
        msg = str(ctx.exception)
        self.assertIn("domaine_fantome", msg)
        self.assertIn("fantome", msg)


def _conn_grande_echelle(n_fiches: int) -> sqlite3.Connection:
    """Base en mémoire avec `n_fiches` fiches VAE, pour tester le passage à
    l'échelle sans clause IN variadique (5 582 fiches en production)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE voixdacces (numero_fiche TEXT, si_jury TEXT);
        CREATE TABLE standard (numero_fiche TEXT, intitule TEXT,
                               nomenclature_europe_niveau TEXT);
        CREATE TABLE nsf (numero_fiche TEXT, nsf_code TEXT, nsf_intitule TEXT);
        CREATE TABLE domaine (domaine_id TEXT, libelle TEXT, ordre TEXT);
        CREATE TABLE competence_canonique (competence_id TEXT, domaine_id TEXT,
                               libelle TEXT, mots_cles TEXT);
        CREATE TABLE certification_competence (numero_fiche TEXT,
                               competence_id TEXT, domaine_id TEXT);
    """)
    conn.execute(
        "INSERT INTO domaine VALUES ('numerique', 'Numérique', '1')")
    conn.execute(
        "INSERT INTO competence_canonique VALUES "
        "('site_web', 'numerique', 'Créer un site web', 'site|web')")
    numeros = [f"RNCP{90000 + i:05d}" for i in range(n_fiches)]
    conn.executemany(
        "INSERT INTO voixdacces VALUES (?, 'Par expérience')",
        [(n,) for n in numeros])
    conn.executemany(
        "INSERT INTO standard VALUES (?, ?, 'NIV5')",
        [(n, f"Titre {n}") for n in numeros])
    conn.executemany(
        "INSERT INTO nsf VALUES (?, '310', '310 : x')",
        [(n,) for n in numeros])
    conn.executemany(
        "INSERT INTO certification_competence VALUES (?, 'site_web', 'numerique')",
        [(n,) for n in numeros])
    conn.commit()
    return conn


class _ConnexionTracante:
    """Enveloppe une connexion SQLite et enregistre le nombre de paramètres
    liés de chaque requête. Utilisée pour vérifier qu'aucune requête ne
    construit une clause IN variadique."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.requetes_param_count: list[int] = []

    def execute(self, sql: str, params=()):
        """Exécute une requête et enregistre le nombre de paramètres."""
        param_count = len(params) if params else 0
        self.requetes_param_count.append(param_count)
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, seq_params):
        """Exécute une requête sur plusieurs paramètres et enregistre le max."""
        seq_params_list = list(seq_params)
        if seq_params_list:
            param_count = len(seq_params_list[0]) if seq_params_list[0] else 0
            self.requetes_param_count.append(param_count)
        return self._conn.executemany(sql, seq_params_list)

    def __getattr__(self, name):
        """Délègue les autres attributs à la connexion encapsulée."""
        return getattr(self._conn, name)


class TestDetail(unittest.TestCase):
    def setUp(self):
        conn = conn_minimale()
        index, _ = build_ihm.construire_index(conn, build_ihm.numeros_vae(conn))
        self.numeros = [c[0] for c in index["certifs"]]
        self.detail = build_ihm.construire_detail(conn, self.numeros)

    def test_ne_contient_que_les_fiches_retenues(self):
        self.assertEqual(sorted(self.detail), ["RNCP0001", "RNCP0004"])

    def test_objectifs_et_activites(self):
        self.assertEqual(self.detail["RNCP0001"]["o"], "Objectifs du dev web.")
        self.assertEqual(self.detail["RNCP0001"]["a"], "Activités du dev web.")

    def test_champ_absent_devient_chaine_vide(self):
        # RNCP0004 n'a pas d'activites_visees
        self.assertEqual(self.detail["RNCP0004"]["a"], "")

    def test_capacites_attestees_exclu(self):
        aplati = repr(self.detail)
        self.assertNotIn("NE DOIT PAS ÊTRE EMBARQUÉ", aplati)

    def test_blocs_tries_par_code(self):
        blocs = self.detail["RNCP0001"]["b"]
        self.assertEqual([b[0] for b in blocs],
                         ["RNCP0001BC01", "RNCP0001BC02"])
        self.assertEqual(blocs[0][1], "Créer un site")
        self.assertEqual(blocs[0][2], "coder html")


def _conn_grande_echelle_detail(n_fiches: int) -> sqlite3.Connection:
    """Base en mémoire avec `n_fiches` fiches, texte de présentation et un
    bloc de compétences chacune, pour tester construire_detail() à l'échelle
    sans clause IN variadique."""
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE fiche_texte (numero_fiche TEXT, champ TEXT, contenu TEXT);
        CREATE TABLE bloc_competences_xml (numero_fiche TEXT, bloc_code TEXT,
                               bloc_libelle TEXT, liste_competences TEXT);
    """)
    numeros = [f"RNCP{90000 + i:05d}" for i in range(n_fiches)]
    conn.executemany(
        "INSERT INTO fiche_texte VALUES (?, 'objectifs_contexte', ?)",
        [(n, f"Objectifs {n}") for n in numeros])
    conn.executemany(
        "INSERT INTO fiche_texte VALUES (?, 'capacites_attestees', 'NE DOIT PAS ÊTRE EMBARQUÉ')",
        [(n,) for n in numeros])
    conn.executemany(
        "INSERT INTO bloc_competences_xml VALUES (?, ?, 'Bloc', 'comp')",
        [(n, n + "BC01") for n in numeros])
    conn.commit()
    return conn


class TestDetailEchelle(unittest.TestCase):
    def test_pas_de_clause_in_variadique_sans_setlimit(self):
        """Porte la garantie que construire_detail() n'utilise jamais IN (?,?,…),
        symétrique à TestIndexEchelle.test_pas_de_clause_in_variadique_sans_setlimit."""
        conn = _conn_grande_echelle_detail(1200)
        numeros = [f"RNCP{90000 + i:05d}" for i in range(1200)]
        conn_tracante = _ConnexionTracante(conn)

        detail = build_ihm.construire_detail(conn_tracante, numeros)
        self.assertEqual(len(detail), 1200)

        max_params = max(conn_tracante.requetes_param_count) \
            if conn_tracante.requetes_param_count else 0
        self.assertLessEqual(
            max_params, SEUIL_PARAMETRES_MAX,
            f"Une requête a {max_params} paramètres : suspicion de clause "
            f"IN variadique. Requêtes enregistrées : {conn_tracante.requetes_param_count}")
        self.assertTrue(
            conn_tracante.requetes_param_count,
            "Aucune requête n'a été enregistrée (enveloppe infonctionnelle)")


class TestIndexEchelle(unittest.TestCase):
    def test_limite_forcee_moteur_reel(self):
        """Exerce le moteur SQLite réel avec la limite de variables forcée à 999.

        Complément optionnel (Python 3.11+ uniquement) : prouve que
        construire_index() traite correctement 1 200 fiches malgré un moteur SQLite
        contraint. La garantie portable sur toutes les versions Python est assurée
        par test_pas_de_clause_in_variadique_sans_setlimit.

        Skipped si sqlite3.Connection.setlimit indisponible (Python < 3.11).
        """
        conn = _conn_grande_echelle(1200)
        if not hasattr(conn, "setlimit"):
            self.skipTest(
                "sqlite3.Connection.setlimit indisponible (Python < 3.11)")
        conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 999)

        numeros = build_ihm.numeros_vae(conn)
        self.assertEqual(len(numeros), 1200)
        index, exclues = build_ihm.construire_index(conn, numeros)
        self.assertEqual(len(index["certifs"]), 1200)
        self.assertEqual(exclues, 0)

    def test_pas_de_clause_in_variadique_sans_setlimit(self):
        """Porte la garantie que construire_index() n'utilise jamais IN (?,?,…).

        Valide sur toutes les versions de Python (contrairement à
        test_limite_forcee_moteur_reel). Traite 1 200 fiches en production
        (bien au-delà du seuil historique de 999 variables SQLite).

        Enveloppe la connexion pour observer le nombre de paramètres de chaque
        requête. Assert qu'aucune requête n'a plus de SEUIL_PARAMETRES_MAX
        paramètres — un seuil suffisant pour les requêtes légitimes, mais trop bas
        pour un IN variadique sur des milliers de fiches.
        """
        conn = _conn_grande_echelle(1200)
        conn_tracante = _ConnexionTracante(conn)

        numeros = build_ihm.numeros_vae(conn)
        self.assertEqual(len(numeros), 1200)
        index, exclues = build_ihm.construire_index(conn_tracante, numeros)
        self.assertEqual(len(index["certifs"]), 1200)
        self.assertEqual(exclues, 0)

        # Aucune requête n'a plus de SEUIL_PARAMETRES_MAX paramètres : repli efficace sur table temp.
        max_params = max(conn_tracante.requetes_param_count) \
            if conn_tracante.requetes_param_count else 0
        self.assertLessEqual(
            max_params, SEUIL_PARAMETRES_MAX,
            f"Une requête a {max_params} paramètres : suspicion de clause "
            f"IN variadique. Requêtes enregistrées : {conn_tracante.requetes_param_count}")
        self.assertTrue(
            conn_tracante.requetes_param_count,
            "Aucune requête n'a été enregistrée (enveloppe infonctionnelle)")


class TestCompressionInjection(unittest.TestCase):
    def test_aller_retour_gzip_base64(self):
        obj = {"certifs": [["RNCP0001", "Développeur web", "NIV6", [0], [1, 2]]],
               "accents": "éèêç — «»"}
        self.assertEqual(build_ihm.decompresser(build_ihm.compresser(obj)), obj)

    def test_base64_est_ascii_pur(self):
        b64 = build_ihm.compresser({"x": "éàü"})
        self.assertTrue(b64.isascii())

    def test_injection_remplace_les_trois_marqueurs(self):
        gabarit = ('const IDX="/*__INDEX_B64__*/";'
                   'const DET="/*__DETAIL_B64__*/";'
                   '/*__MATCHER_JS__*/')
        html = build_ihm.injecter(gabarit, "AAA", "BBB", "function matcher(){}")
        self.assertIn('const IDX="AAA";', html)
        self.assertIn('const DET="BBB";', html)
        self.assertIn("function matcher(){}", html)
        for marqueur in build_ihm.MARQUEURS:
            self.assertNotIn(marqueur, html)

    def test_marqueur_manquant_leve(self):
        with self.assertRaises(build_ihm.ErreurIHM) as ctx:
            build_ihm.injecter("gabarit sans marqueur", "A", "B", "C")
        self.assertIn("__INDEX_B64__", str(ctx.exception))

    def test_sequence_fermeture_script_minuscule_leve(self):
        """Détecte </script> dans le JavaScript injecté, casse minuscule."""
        gabarit = ('const IDX="/*__INDEX_B64__*/";'
                   'const DET="/*__DETAIL_B64__*/";'
                   '<script>/*__MATCHER_JS__*/</script>')
        matcher_dangereux = 'console.log("</script>"); // oups'
        with self.assertRaises(build_ihm.ErreurIHM) as ctx:
            build_ihm.injecter(gabarit, "AAA", "BBB", matcher_dangereux)
        msg = str(ctx.exception)
        self.assertIn("</script>", msg)

    def test_sequence_fermeture_script_casse_mixte_leve(self):
        """Détecte </Script> et autres variantes de casse."""
        gabarit = ('const IDX="/*__INDEX_B64__*/";'
                   'const DET="/*__DETAIL_B64__*/";'
                   '<script>/*__MATCHER_JS__*/</script>')
        matcher_dangereux = 'console.log("</Script>"); // casse mixte'
        with self.assertRaises(build_ihm.ErreurIHM) as ctx:
            build_ihm.injecter(gabarit, "AAA", "BBB", matcher_dangereux)
        msg = str(ctx.exception)
        self.assertIn("</script>", msg.lower())


if __name__ == "__main__":
    unittest.main()
