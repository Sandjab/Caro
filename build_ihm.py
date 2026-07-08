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
