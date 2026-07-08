import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_ihm  # noqa: E402
import sqlite3
import unittest


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


if __name__ == "__main__":
    unittest.main()
