#!/usr/bin/env python3
"""Génère une page HTML autonome de recherche de certifications par VAE.

Lit la base construite par build_db.py, extrait les certifications accessibles
par validation des acquis de l'expérience, et injecte index et détail
(compressés, encodés en base64) dans ihm/template.html.

Aucune dépendance externe : Python 3.9+ et sa bibliothèque standard.

Exemple :
    python3 build_ihm.py                       # rncp.sqlite3 -> ihm/index.html
"""

from __future__ import annotations

import base64
import gzip
import json
import sqlite3

VOIE_VAE = "Par expérience"


class ErreurIHM(Exception):
    """Erreur bloquante : mieux vaut ne rien produire qu'une page vide plausible."""


def log(msg: str) -> None:
    print(msg, flush=True)


def _objet_existe(conn: sqlite3.Connection, nom: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name = ? LIMIT 1", (nom,)).fetchone()
    return row is not None


def verifier_base(conn: sqlite3.Connection) -> None:
    """Vérifie que la base contient ce dont l'IHM a besoin."""
    if not _objet_existe(conn, "certification_competence"):
        raise ErreurIHM(
            "la vue certification_competence est absente : la base a été "
            "construite avec --no-taxonomie, l'IHM n'a pas d'objet.")
    for table in ("voixdacces", "standard", "nsf", "bloc_competences_xml",
                  "fiche_texte", "domaine", "competence_canonique"):
        if not _objet_existe(conn, table):
            raise ErreurIHM(f"table {table} absente de la base.")


def numeros_vae(conn: sqlite3.Connection) -> list[str]:
    """Numéros de fiche accessibles par VAE, triés et dédoublonnés."""
    rows = conn.execute(
        "SELECT DISTINCT numero_fiche FROM voixdacces WHERE si_jury = ? "
        "ORDER BY numero_fiche", (VOIE_VAE,)).fetchall()
    if not rows:
        presentes = [r[0] for r in conn.execute(
            "SELECT DISTINCT si_jury FROM voixdacces ORDER BY 1")]
        raise ErreurIHM(
            f"aucune fiche avec si_jury = {VOIE_VAE!r}. La valeur a peut-être "
            f"changé dans l'export. Valeurs présentes : {presentes!r}")
    return [r[0] for r in rows]


# Groupes NSF (2 chiffres). La base ne contient que les codes fins ; ces
# libellés viennent de la nomenclature officielle. Un groupe absent de cette
# table fait échouer le build : mieux vaut un arrêt qu'un filtre muet.
GROUPES_NSF = {
    "10": "Formations générales",
    "11": "Mathématiques et sciences",
    "12": "Sciences humaines et droit",
    "13": "Lettres et arts",
    "20": "Spécialités pluritechnologiques de production",
    "21": "Agriculture, pêche, forêt et espaces verts",
    "22": "Transformations",
    "23": "Génie civil, construction et bois",
    "24": "Matériaux souples",
    "25": "Mécanique, électricité, électronique",
    "30": "Spécialités plurivalentes des services",
    "31": "Échanges et gestion",
    "32": "Communication et information",
    "33": "Services aux personnes",
    "34": "Services à la collectivité",
    "41": "Développement personnel et professionnel",
}

DOMAINES_TRANSVERSAUX = {"transversal", "enseignement_general"}


def _table_temp_numeros(conn: sqlite3.Connection, numeros: list[str]) -> str:
    """Crée une table temporaire des numéros de fiche à traiter et renvoie son nom.

    Évite un IN (?,?,…) de plusieurs milliers de variables : SQLite en limite
    le nombre (999 sur les builds anciens, 5 582 fiches VAE en production).
    Même motif que build_db.py (filter_tables_to_active) : une table
    temporaire plutôt qu'une clause IN variadique.

    Réutilisable plusieurs fois sur la même connexion : la table est
    recréée (DROP TABLE IF EXISTS) à chaque appel, donc pas de conflit si
    la fonction appelante est invoquée plus d'une fois sur le même `conn`.
    """
    conn.execute("DROP TABLE IF EXISTS numeros_a_traiter")
    conn.execute("CREATE TEMP TABLE numeros_a_traiter (numero_fiche TEXT PRIMARY KEY)")
    conn.executemany(
        "INSERT OR IGNORE INTO numeros_a_traiter VALUES (?)",
        ((n,) for n in numeros))
    return "numeros_a_traiter"


def construire_index(conn: sqlite3.Connection,
                     numeros: list[str]) -> "tuple[dict, int]":
    """Construit l'index compact. Renvoie (index, nombre de fiches exclues).

    Une fiche VAE sans aucune compétence rattachée est exclue : on ne peut pas
    classer par couverture ce dont on ignore les exigences.
    """
    table = _table_temp_numeros(conn, numeros)

    # domaines, dans l'ordre de la taxonomie
    dom_rows = conn.execute(
        "SELECT domaine_id, libelle FROM domaine "
        "ORDER BY CAST(ordre AS INTEGER), domaine_id").fetchall()
    dom_idx = {d: i for i, (d, _) in enumerate(dom_rows)}
    domaines = [lib for _, lib in dom_rows]

    # compétences, internées par indice
    comp_rows = conn.execute(
        "SELECT competence_id, libelle, domaine_id, COALESCE(mots_cles, '') "
        "FROM competence_canonique ORDER BY domaine_id, competence_id").fetchall()
    competences, comp_idx = [], {}
    for cid, libelle, did, mots in comp_rows:
        if did not in dom_idx:
            raise ErreurIHM(
                f"domaine_id {did!r} inconnu (compétence {cid!r} : {libelle!r}) "
                "absent de la table domaine. Mapping incohérent entre "
                "competence_canonique et domaine : mieux vaut échouer que "
                "ranger silencieusement la compétence sous le premier domaine venu.")
        comp_idx[cid] = len(competences)
        competences.append([cid, libelle, dom_idx[did],
                            1 if did in DOMAINES_TRANSVERSAUX else 0, mots])

    # groupes NSF réellement présents
    presents = sorted({r[0][:2] for r in conn.execute(
        f"SELECT nsf_code FROM nsf JOIN {table} USING (numero_fiche)")})
    inconnus = [g for g in presents if g not in GROUPES_NSF]
    if inconnus:
        raise ErreurIHM(
            f"groupes NSF inconnus dans l'export : {inconnus!r}. Compléter "
            "GROUPES_NSF avec leur libellé officiel.")
    nsf = [[g, GROUPES_NSF[g]] for g in presents]
    nsf_idx = {g: i for i, g in enumerate(presents)}

    # exigences : numero -> indices de compétences
    exig: dict[str, set[int]] = {}
    for num, cid in conn.execute(
            f"SELECT numero_fiche, competence_id FROM certification_competence "
            f"JOIN {table} USING (numero_fiche)"):
        if cid in comp_idx:
            exig.setdefault(num, set()).add(comp_idx[cid])

    # groupes NSF par fiche
    groupes: dict[str, set[int]] = {}
    for num, code in conn.execute(
            f"SELECT numero_fiche, nsf_code FROM nsf JOIN {table} USING (numero_fiche)"):
        groupes.setdefault(num, set()).add(nsf_idx[code[:2]])

    # intitulés et niveaux
    infos = {num: (intitule, niveau or "") for num, intitule, niveau in conn.execute(
        f"SELECT numero_fiche, intitule, COALESCE(nomenclature_europe_niveau, '') "
        f"FROM standard JOIN {table} USING (numero_fiche)")}

    conn.execute(f"DROP TABLE {table}")

    certifs, exclues = [], 0
    for num in numeros:
        comps = exig.get(num)
        if not comps:
            exclues += 1
            continue
        intitule, niveau = infos.get(num, (num, ""))
        certifs.append([num, intitule, niveau,
                        sorted(groupes.get(num, set())), sorted(comps)])

    index = {"domaines": domaines, "competences": competences,
             "nsf": nsf, "certifs": certifs, "exclues": exclues}
    return index, exclues


CHAMPS_DETAIL = {"objectifs_contexte": "o", "activites_visees": "a"}


def construire_detail(conn: sqlite3.Connection, numeros: list[str]) -> dict:
    """Texte de présentation et blocs de compétences, par numéro de fiche.

    capacites_attestees n'est pas embarqué : ce champ redit, réagencé, le
    contenu des liste_competences des blocs (27 Mo bruts pour rien).
    """
    table = _table_temp_numeros(conn, numeros)
    detail: dict[str, dict] = {n: {"o": "", "a": "", "b": []} for n in numeros}

    champs_ph = ",".join("?" * len(CHAMPS_DETAIL))
    for num, champ, contenu in conn.execute(
            f"SELECT numero_fiche, champ, contenu FROM fiche_texte "
            f"JOIN {table} USING (numero_fiche) "
            f"WHERE champ IN ({champs_ph})",
            list(CHAMPS_DETAIL)):
        detail[num][CHAMPS_DETAIL[champ]] = contenu or ""

    for num, code, libelle, comps in conn.execute(
            f"SELECT numero_fiche, bloc_code, bloc_libelle, "
            f"COALESCE(liste_competences, '') FROM bloc_competences_xml "
            f"JOIN {table} USING (numero_fiche) "
            f"ORDER BY numero_fiche, bloc_code"):
        detail[num]["b"].append([code, libelle, comps])

    conn.execute(f"DROP TABLE {table}")
    return detail


MARQUEURS = ("/*__INDEX_B64__*/", "/*__DETAIL_B64__*/", "/*__MATCHER_JS__*/")


def compresser(obj) -> str:
    """JSON compact -> gzip -> base64 ASCII, prêt à être collé dans du JS."""
    brut = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(gzip.compress(brut, 9)).decode("ascii")


def decompresser(b64: str):
    """Inverse de compresser(). Utilisée par les tests d'aller-retour."""
    return json.loads(gzip.decompress(base64.b64decode(b64)).decode("utf-8"))


def injecter(template: str, index_b64: str, detail_b64: str,
             matcher_js: str) -> str:
    """Remplace les trois marqueurs du gabarit. Lève si l'un manque."""
    manquants = [m for m in MARQUEURS if m not in template]
    if manquants:
        raise ErreurIHM(
            f"gabarit corrompu : marqueurs absents {manquants!r}")
    html = template.replace(MARQUEURS[0], index_b64)
    html = html.replace(MARQUEURS[1], detail_b64)
    return html.replace(MARQUEURS[2], matcher_js)
