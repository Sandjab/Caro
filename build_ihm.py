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


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def construire_index(conn: sqlite3.Connection,
                     numeros: list[str]) -> "tuple[dict, int]":
    """Construit l'index compact. Renvoie (index, nombre de fiches exclues).

    Une fiche VAE sans aucune compétence rattachée est exclue : on ne peut pas
    classer par couverture ce dont on ignore les exigences.
    """
    ph = _placeholders(len(numeros))

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
        comp_idx[cid] = len(competences)
        competences.append([cid, libelle, dom_idx.get(did, 0),
                            1 if did in DOMAINES_TRANSVERSAUX else 0, mots])

    # groupes NSF réellement présents
    presents = sorted({r[0][:2] for r in conn.execute(
        f"SELECT nsf_code FROM nsf WHERE numero_fiche IN ({ph})", numeros)})
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
            f"WHERE numero_fiche IN ({ph})", numeros):
        if cid in comp_idx:
            exig.setdefault(num, set()).add(comp_idx[cid])

    # groupes NSF par fiche
    groupes: dict[str, set[int]] = {}
    for num, code in conn.execute(
            f"SELECT numero_fiche, nsf_code FROM nsf WHERE numero_fiche IN ({ph})",
            numeros):
        groupes.setdefault(num, set()).add(nsf_idx[code[:2]])

    # intitulés et niveaux
    infos = {num: (intitule, niveau or "") for num, intitule, niveau in conn.execute(
        f"SELECT numero_fiche, intitule, COALESCE(nomenclature_europe_niveau, '') "
        f"FROM standard WHERE numero_fiche IN ({ph})", numeros)}

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
