#!/usr/bin/env python3
"""Construit une base SQLite à partir des exports open data de France compétences.

Jeu de données source (data.gouv.fr) :
    https://www.data.gouv.fr/datasets/repertoire-national-des-certifications-professionnelles-et-repertoire-specifique

Le script télécharge (via l'API data.gouv.fr) les derniers exports publiés :
  - export-fiches-csv-AAAA-MM-JJ.zip        -> tables relationnelles (une par CSV)
  - export-fiches-rncp-v4-1-AAAA-MM-JJ.zip  -> texte intégral des fiches RNCP (XML V4.1)
  - export-fiches-rs-v4-1-AAAA-MM-JJ.zip    -> texte intégral des fiches RS (XML V4.1)

puis charge le tout dans une base SQLite requêtable (par défaut : fiches actives
uniquement). Aucune dépendance externe : Python 3.9+ et sa bibliothèque standard.

Exemples :
    python3 build_db.py                          # télécharge puis construit rncp.sqlite3
    python3 build_db.py --all                    # inclut aussi les fiches inactives
    python3 build_db.py --csv-zip data/export-fiches-csv-2026-07-04.zip \
                        --xml-zip data/export-fiches-rncp-v4-1-2026-07-04.zip \
                        --xml-zip data/export-fiches-rs-v4-1-2026-07-04.zip
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

DATASET_API = (
    "https://www.data.gouv.fr/api/1/datasets/"
    "repertoire-national-des-certifications-professionnelles-et-repertoire-specifique/"
)
USER_AGENT = "Caro-rncp-loader/1.0"

# Motifs de repérage des ressources dans la réponse de l'API data.gouv.fr.
RESOURCE_KINDS = {
    "csv": re.compile(r"export[-_]fiches[-_]csv", re.I),
    "xml_rncp": re.compile(r"export[-_]fiches[-_]rncp", re.I),
    "xml_rs": re.compile(r"export[-_]fiches[-_]rs[-_]", re.I),
}
DATE_IN_NAME = re.compile(r"(\d{4}[-_]\d{2}[-_]\d{2})")

# Valeurs signalant une fiche active (CSV : "ACTIVE", XML : "Oui").
ACTIVE_VALUES = {"oui", "active", "actif", "true", "1"}

# Champs texte de premier niveau des fiches XML V4.1 à conserver tels quels.
XML_TEXT_TAGS = {
    "ACTIVITES_VISEES",
    "CAPACITES_ATTESTEES",
    "SECTEURS_ACTIVITE",
    "TYPE_EMPLOI_ACCESSIBLES",
    "OBJECTIFS_CONTEXTE",
    "REGLEMENTATIONS_ACTIVITES",
    "PREREQUIS_ENTREE_FORMATION",
    "PREREQUIS_VALIDATION_CERTIFICATION",
}
# Champs structurés de premier niveau qu'il ne faut jamais verser dans fiche_texte
# (ils sont déjà couverts par les tables CSV ou par bloc_competences_xml).
XML_STRUCTURED_TAGS = {
    "BLOCS_COMPETENCES",
    "CERTIFICATEURS",
    "PARTENAIRES",
    "CODES_NSF",
    "CODES_ROME",
    "FORMACODES",
    "VOIES_D_ACCES",
    "ANCIENNE_CERTIFICATION",
    "NOUVELLE_CERTIFICATION",
    "NOMENCLATURE_EUROPE",
    "ABREGE",
    "STATISTIQUES_PROMOTIONS",
    "JURY",
    "SI_JURY",
    "CCN",
    "IDCC",
}
# Au-delà de cette longueur, un champ texte inconnu est conservé quand même :
# le format V4.x évolue et on préfère capturer trop que pas assez.
XML_TEXT_FALLBACK_LEN = 300

# Seuil de similarité lexicale en deçà duquel un bloc reste non classé.
SEUIL_LEXICAL = 0.12


def log(msg: str) -> None:
    print(msg, flush=True)


def slugify(name: str) -> str:
    """Normalise un nom de table/colonne : minuscules, sans accents, [a-z0-9_]."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").lower()
    if not text:
        text = "col"
    if text[0].isdigit():
        text = "c_" + text
    return text


# Mots vides français fréquents (≥ 3 caractères) écartés de la tokenisation.
MOTS_VIDES = {
    "les", "des", "une", "aux", "dans", "pour", "par", "sur", "avec", "ses",
    "son", "sa", "leur", "leurs", "que", "qui", "aux", "ces", "cette", "est",
    "ou", "et", "en", "un", "au", "de", "du", "la", "le",
}


def tokeniser(texte: str) -> set[str]:
    """Découpe un texte en jetons normalisés (minuscule, sans accent, ≥ 3 car.)."""
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower()
    bruts = re.split(r"[^a-z0-9]+", texte)
    return {t for t in bruts if len(t) >= 3 and t not in MOTS_VIDES}


def score_lexical(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Similarité de Jaccard entre deux ensembles de jetons (0.0 à 1.0)."""
    if not tokens_a or not tokens_b:
        return 0.0
    union = len(tokens_a | tokens_b)
    return len(tokens_a & tokens_b) / union if union else 0.0


def meilleur_match_lexical(
    texte_bloc: str,
    competences_tokens: "dict[str, set[str]]",
    seuil: float,
) -> "tuple[str | None, float]":
    """Compétence canonique la plus proche du texte d'un bloc, ou (None, meilleur_score)."""
    jetons = tokeniser(texte_bloc)
    meilleur_id, meilleur_score = None, 0.0
    for cid, ctokens in competences_tokens.items():
        s = score_lexical(jetons, ctokens)
        if s > meilleur_score:
            meilleur_id, meilleur_score = cid, s
    if meilleur_id is not None and meilleur_score >= seuil:
        return meilleur_id, meilleur_score
    return None, meilleur_score


class Taxonomie:
    """Artefact de taxonomie chargé depuis taxonomie/*.csv."""

    def __init__(self, domaines, competences, mapping, meta, fiche_mapping=None):
        self.domaines = domaines        # list[dict]
        self.competences = competences  # list[dict]
        self.mapping = mapping          # dict[str, tuple[str, str, float | None]]
        self.meta = meta                # dict[str, str]
        self.fiche_mapping = fiche_mapping or []  # list[tuple[str, str, str]]


def _lire_csv_point_virgule(chemin: Path) -> "list[dict]":
    with open(chemin, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh, delimiter=";"))


def charger_taxonomie(taxo_dir: Path) -> "Taxonomie | None":
    """Charge l'artefact de taxonomie. Renvoie None si absent/incomplet."""
    requis = ["domaines.csv", "competences_canoniques.csv", "mapping_blocs.csv"]
    if not taxo_dir.is_dir() or any(not (taxo_dir / f).exists() for f in requis):
        return None

    domaines = _lire_csv_point_virgule(taxo_dir / "domaines.csv")
    competences = _lire_csv_point_virgule(taxo_dir / "competences_canoniques.csv")
    competences_valides = []
    for c in competences:
        if c.get("competence_id"):
            competences_valides.append(c)
        else:
            log("  taxonomie : compétence sans competence_id ignorée")
    competences = competences_valides
    ids_connus = {c["competence_id"] for c in competences}

    mapping: "dict[str, tuple[str, str, float | None]]" = {}
    for row in _lire_csv_point_virgule(taxo_dir / "mapping_blocs.csv"):
        cid = row.get("competence_id", "")
        code = row.get("bloc_code", "")
        if not code:
            continue
        if cid not in ids_connus:
            log(f"  taxonomie : mapping ignoré (competence inconnue) : {code} -> {cid}")
            continue
        brut = row.get("score", "")
        try:
            score = float(brut) if brut not in (None, "") else None
        except ValueError:
            log(f"  taxonomie : score non numérique ignoré pour {code} : {brut!r}")
            score = None
        mapping[code] = (cid, row.get("methode", "ia") or "ia", score)

    # Rattachement par fiche (optionnel) : pour les certifications sans bloc
    # dans la source, qui ne peuvent pas passer par mapping_blocs.
    fiche_mapping: "list[tuple[str, str, str]]" = []
    chemin_fiches = taxo_dir / "mapping_fiches.csv"
    if chemin_fiches.exists():
        for row in _lire_csv_point_virgule(chemin_fiches):
            num = (row.get("numero_fiche") or "").strip()
            cid = (row.get("competence_id") or "").strip()
            if not num or not cid:
                continue
            if cid not in ids_connus:
                log(f"  taxonomie : rattachement fiche ignoré "
                    f"(competence inconnue) : {num} -> {cid}")
                continue
            fiche_mapping.append((num, cid, (row.get("methode") or "ia") or "ia"))

    meta = {}
    meta_path = taxo_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            log(f"  taxonomie : meta.json illisible ({exc})")

    return Taxonomie(domaines, competences, mapping, meta, fiche_mapping)


def construire_taxonomie(conn: sqlite3.Connection, taxo: "Taxonomie",
                         seuil: float = SEUIL_LEXICAL) -> dict:
    """Crée les tables de taxonomie et rattache chaque bloc réel. Renvoie des stats."""
    conn.execute("DROP TABLE IF EXISTS domaine")
    conn.execute(
        "CREATE TABLE domaine ("
        "domaine_id TEXT PRIMARY KEY, libelle TEXT, description TEXT, ordre INTEGER)")
    conn.executemany(
        "INSERT OR REPLACE INTO domaine (domaine_id, libelle, description, ordre) "
        "VALUES (?, ?, ?, ?)",
        [(d.get("domaine_id"), d.get("libelle"), d.get("description"),
          d.get("ordre")) for d in taxo.domaines])

    conn.execute("DROP TABLE IF EXISTS competence_canonique")
    conn.execute(
        "CREATE TABLE competence_canonique ("
        "competence_id TEXT PRIMARY KEY, domaine_id TEXT, libelle TEXT, "
        "description TEXT, mots_cles TEXT, nb_blocs INTEGER DEFAULT 0)")
    conn.executemany(
        "INSERT OR REPLACE INTO competence_canonique "
        "(competence_id, domaine_id, libelle, description, mots_cles) "
        "VALUES (?, ?, ?, ?, ?)",
        [(c.get("competence_id"), c.get("domaine_id"), c.get("libelle"),
          c.get("description"), c.get("mots_cles")) for c in taxo.competences])

    conn.execute("DROP TABLE IF EXISTS bloc_competence_canonique")
    conn.execute(
        "CREATE TABLE bloc_competence_canonique ("
        "bloc_code TEXT PRIMARY KEY, numero_fiche TEXT, competence_id TEXT, "
        "methode TEXT, score REAL)")

    # Jetons précalculés par compétence canonique (pour le repli lexical).
    comp_tokens = {
        c.get("competence_id"): tokeniser((c.get("mots_cles") or "").replace("|", " "))
        for c in taxo.competences
    }

    stats = {"nb_blocs": 0, "blocs_ia": 0, "blocs_lexical": 0, "blocs_non_classe": 0}
    lignes = conn.execute(
        "SELECT bloc_code, numero_fiche, bloc_libelle, liste_competences "
        "FROM bloc_competences_xml WHERE TRIM(bloc_code) != ''"
    ).fetchall()
    a_inserer = []
    for bloc_code, numero, libelle, comps in lignes:
        if bloc_code in taxo.mapping:
            cid, _methode_source, score = taxo.mapping[bloc_code]
            methode = "ia"  # une entrée de mapping vaut toujours provenance IA
        else:
            texte = f"{libelle or ''} {comps or ''}"
            cid, score = meilleur_match_lexical(texte, comp_tokens, seuil)
            methode = "lexical" if cid else "non_classe"
        a_inserer.append((bloc_code, numero, cid, methode, score))
        stats["nb_blocs"] += 1
        stats["blocs_" + methode] += 1
    conn.executemany(
        "INSERT OR IGNORE INTO bloc_competence_canonique "
        "(bloc_code, numero_fiche, competence_id, methode, score) VALUES (?, ?, ?, ?, ?)",
        a_inserer)

    conn.execute(
        "UPDATE competence_canonique SET nb_blocs = ("
        "SELECT COUNT(*) FROM bloc_competence_canonique m "
        "WHERE m.competence_id = competence_canonique.competence_id)")

    total = stats["nb_blocs"] or 1
    for cle in ("ia", "lexical", "non_classe"):
        stats[f"blocs_{cle}_pct"] = round(100 * stats[f"blocs_{cle}"] / total, 1)
    conn.commit()
    return stats


def construire_fiche_competence(conn: sqlite3.Connection, taxo: "Taxonomie") -> dict:
    """Crée fiche_competence_canonique et rattache chaque fiche listée.

    Chemin « par fiche » : pour les certifications sans bloc dans la source,
    on rattache la fiche entière à des compétences canoniques (issues du texte
    libre, décidées hors ligne par la passe de curation). La table est TOUJOURS
    créée, même vide, pour que la vue certification_competence puisse l'unir
    sans condition. Renvoie des stats.
    """
    conn.execute("DROP TABLE IF EXISTS fiche_competence_canonique")
    conn.execute(
        "CREATE TABLE fiche_competence_canonique ("
        "numero_fiche TEXT, competence_id TEXT, methode TEXT, "
        "PRIMARY KEY (numero_fiche, competence_id))")
    conn.executemany(
        "INSERT OR IGNORE INTO fiche_competence_canonique "
        "(numero_fiche, competence_id, methode) VALUES (?, ?, ?)",
        taxo.fiche_mapping)
    nb_rattachements = conn.execute(
        "SELECT COUNT(*) FROM fiche_competence_canonique").fetchone()[0]
    nb_fiches = conn.execute(
        "SELECT COUNT(DISTINCT numero_fiche) FROM fiche_competence_canonique").fetchone()[0]
    conn.commit()
    return {"nb_rattachements_fiche": nb_rattachements,
            "nb_fiches_rattachees": nb_fiches}


def creer_vue_certification_competence(conn: sqlite3.Connection) -> None:
    """Vue diplôme -> compétences canoniques couvertes.

    UNION de deux chemins : les blocs mappés (blocs non classés exclus) et le
    rattachement par fiche (certifications sans bloc dans la source). Le UNION
    (et non UNION ALL) dédoublonne une fiche couverte par les deux chemins.
    """
    # Garantit que la table fiche_competence_canonique existe (même vide)
    # pour que la vue puisse l'unir sans condition.
    conn.execute("CREATE TABLE IF NOT EXISTS fiche_competence_canonique ("
                 "numero_fiche TEXT, competence_id TEXT, methode TEXT, "
                 "PRIMARY KEY (numero_fiche, competence_id))")
    conn.execute("DROP VIEW IF EXISTS certification_competence")
    conn.execute(
        "CREATE VIEW certification_competence AS "
        "SELECT DISTINCT b.numero_fiche, m.competence_id, cc.domaine_id "
        "FROM bloc_competences_xml b "
        "JOIN bloc_competence_canonique m ON m.bloc_code = b.bloc_code "
        "JOIN competence_canonique cc ON cc.competence_id = m.competence_id "
        "UNION "
        "SELECT DISTINCT f.numero_fiche, f.competence_id, cc.domaine_id "
        "FROM fiche_competence_canonique f "
        "JOIN competence_canonique cc ON cc.competence_id = f.competence_id")
    conn.commit()


def indexer_taxonomie(conn: sqlite3.Connection) -> None:
    """Index de jointure sur la table de rattachement."""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bcc_numero "
        "ON bloc_competence_canonique (numero_fiche)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_bcc_competence "
        "ON bloc_competence_canonique (competence_id)")
    conn.commit()


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def download_to(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        log(f"  déjà présent, téléchargement sauté : {dest}")
        return dest
    log(f"  téléchargement de {url}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=600) as resp, open(tmp, "wb") as out:
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
    tmp.rename(dest)
    log(f"  -> {dest} ({dest.stat().st_size / 1e6:.1f} Mo)")
    return dest


def find_latest_resources(dataset: dict) -> dict[str, dict]:
    """Repère, pour chaque type d'export, la ressource la plus récente."""
    found: dict[str, tuple[str, dict]] = {}
    for res in dataset.get("resources", []):
        label = f"{res.get('title', '')} {res.get('url', '')}"
        for kind, pattern in RESOURCE_KINDS.items():
            if not pattern.search(label):
                continue
            m = DATE_IN_NAME.search(label)
            sort_key = m.group(1) if m else res.get("last_modified", "")
            if kind not in found or sort_key > found[kind][0]:
                found[kind] = (sort_key, res)
    return {kind: res for kind, (_, res) in found.items()}


def fetch_exports(data_dir: Path) -> dict[str, Path]:
    log(f"Interrogation de l'API data.gouv.fr : {DATASET_API}")
    dataset = json.loads(http_get(DATASET_API))
    resources = find_latest_resources(dataset)
    missing = [k for k in ("csv", "xml_rncp", "xml_rs") if k not in resources]
    if missing:
        raise SystemExit(
            f"Ressources introuvables dans la réponse de l'API : {missing}. "
            "La structure du jeu de données a peut-être changé ; utilisez "
            "--csv-zip/--xml-zip avec des fichiers téléchargés manuellement."
        )
    paths: dict[str, Path] = {}
    for kind, res in resources.items():
        url = res["url"]
        name = url.rsplit("/", 1)[-1] or f"{kind}.zip"
        log(f"Export {kind} : {res.get('title', name)}")
        paths[kind] = download_to(url, data_dir / name)
    return paths


# --------------------------------------------------------------------------
# Ingestion CSV
# --------------------------------------------------------------------------

def decode_csv_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def table_name_from_member(member: str) -> str:
    stem = Path(member).stem
    stem = re.sub(r"export[-_]?fiches[-_]?(csv)?", "", stem, flags=re.I)
    stem = DATE_IN_NAME.sub("", stem)
    name = slugify(stem)
    return name or "standard"


def dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for n in names:
        if n in seen:
            seen[n] += 1
            result.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            result.append(n)
    return result


def load_csv_zip(conn: sqlite3.Connection, zip_path: Path) -> list[str]:
    """Charge chaque CSV du zip dans une table SQLite du même nom. Renvoie les tables créées."""
    try:
        csv.field_size_limit(sys.maxsize)
    except OverflowError:
        csv.field_size_limit(2**31 - 1)

    tables: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
        if not members:
            raise SystemExit(f"Aucun CSV trouvé dans {zip_path}")
        for member in members:
            table = table_name_from_member(member)
            text = decode_csv_bytes(zf.read(member))
            first_line = text.split("\n", 1)[0]
            delimiter = ";" if first_line.count(";") >= first_line.count(",") else ","
            reader = csv.reader(text.splitlines(), delimiter=delimiter)
            try:
                header = next(reader)
            except StopIteration:
                log(f"  {member} : vide, ignoré")
                continue
            columns = dedupe([slugify(h) for h in header])
            cols_sql = ", ".join(f'"{c}" TEXT' for c in columns)
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
            conn.execute(f'CREATE TABLE "{table}" ({cols_sql})')
            placeholders = ", ".join("?" for _ in columns)
            insert = f'INSERT INTO "{table}" VALUES ({placeholders})'
            count = 0
            batch = []
            for row in reader:
                if not any(cell.strip() for cell in row):
                    continue
                # Aligne la ligne sur l'en-tête (lignes courtes/longues tolérées).
                if len(row) < len(columns):
                    row = row + [""] * (len(columns) - len(row))
                elif len(row) > len(columns):
                    row = row[: len(columns) - 1] + [delimiter.join(row[len(columns) - 1:])]
                batch.append(row)
                count += 1
                if len(batch) >= 5000:
                    conn.executemany(insert, batch)
                    batch = []
            if batch:
                conn.executemany(insert, batch)
            log(f"  table {table} : {count} lignes (source : {member})")
            tables.append(table)
    conn.commit()
    return tables


def column_names(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


def find_column(conn: sqlite3.Connection, table: str, needle: str) -> str | None:
    for col in column_names(conn, table):
        if needle in col:
            return col
    return None


def active_fiche_numbers(conn: sqlite3.Connection, standard_table: str) -> set[str] | None:
    numero_col = find_column(conn, standard_table, "numero_fiche")
    actif_col = find_column(conn, standard_table, "actif")
    if not numero_col or not actif_col:
        return None
    rows = conn.execute(
        f'SELECT "{numero_col}", "{actif_col}" FROM "{standard_table}"'
    ).fetchall()
    return {
        num.strip()
        for num, actif in rows
        if num and (actif or "").strip().lower() in ACTIVE_VALUES
    }


def filter_tables_to_active(conn: sqlite3.Connection, tables: list[str], active: set[str]) -> None:
    conn.execute("CREATE TEMP TABLE actives (numero TEXT PRIMARY KEY)")
    conn.executemany("INSERT OR IGNORE INTO actives VALUES (?)", ((n,) for n in active))
    for table in tables:
        numero_col = find_column(conn, table, "numero_fiche")
        if not numero_col:
            log(f"  {table} : pas de colonne numero_fiche, table conservée telle quelle")
            continue
        before = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        conn.execute(
            f'DELETE FROM "{table}" WHERE TRIM("{numero_col}") NOT IN (SELECT numero FROM actives)'
        )
        after = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        log(f"  {table} : {before} -> {after} lignes (fiches actives)")
    conn.execute("DROP TABLE actives")
    conn.commit()


# --------------------------------------------------------------------------
# Ingestion XML (texte intégral)
# --------------------------------------------------------------------------

def element_text(elem: ET.Element) -> str:
    return "".join(elem.itertext()).strip()


def strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def ingest_fiche_xml(
    conn: sqlite3.Connection,
    fiche: ET.Element,
    repertoire: str,
    only_active: bool,
    active_csv: set[str] | None,
) -> bool:
    children = {strip_ns(child.tag): child for child in fiche}
    numero = element_text(children["NUMERO_FICHE"]) if "NUMERO_FICHE" in children else ""
    if not numero:
        return False

    if only_active:
        actif_elem = children.get("ACTIF")
        if actif_elem is not None:
            if element_text(actif_elem).lower() not in ACTIVE_VALUES:
                return False
        elif active_csv is not None and numero not in active_csv:
            return False

    rows = []
    for child in fiche:
        tag = strip_ns(child.tag)
        if tag in XML_STRUCTURED_TAGS:
            continue
        text = element_text(child)
        if not text:
            continue
        if tag in XML_TEXT_TAGS or len(text) >= XML_TEXT_FALLBACK_LEN:
            rows.append((numero, repertoire, tag.lower(), text))
    if rows:
        conn.executemany(
            "INSERT INTO fiche_texte (numero_fiche, repertoire, champ, contenu) VALUES (?, ?, ?, ?)",
            rows,
        )

    blocs_parent = children.get("BLOCS_COMPETENCES")
    if blocs_parent is not None:
        bloc_rows = []
        for bloc in blocs_parent:
            bloc_children = {strip_ns(c.tag): c for c in bloc}
            def txt(tag: str) -> str:
                elem = bloc_children.get(tag)
                return element_text(elem) if elem is not None else ""
            bloc_rows.append(
                (
                    numero,
                    repertoire,
                    txt("CODE"),
                    txt("LIBELLE"),
                    txt("LISTE_COMPETENCES"),
                    txt("MODALITES_EVALUATION"),
                )
            )
        if bloc_rows:
            conn.executemany(
                "INSERT INTO bloc_competences_xml "
                "(numero_fiche, repertoire, bloc_code, bloc_libelle, liste_competences, modalites_evaluation) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                bloc_rows,
            )
    return True


def load_xml_zip(
    conn: sqlite3.Connection,
    zip_path: Path,
    only_active: bool,
    active_csv: set[str] | None,
) -> int:
    repertoire = "RS" if re.search(r"[-_]rs[-_.]", zip_path.name, re.I) else "RNCP"
    total = 0
    with zipfile.ZipFile(zip_path) as zf:
        members = [m for m in zf.namelist() if m.lower().endswith(".xml")]
        if not members:
            raise SystemExit(f"Aucun XML trouvé dans {zip_path}")
        for member in members:
            with zf.open(member) as fh:
                for _, elem in ET.iterparse(fh, events=("end",)):
                    if strip_ns(elem.tag) != "FICHE":
                        continue
                    if ingest_fiche_xml(conn, elem, repertoire, only_active, active_csv):
                        total += 1
                    elem.clear()
            log(f"  {member} : fiches {repertoire} chargées (cumul {total})")
    conn.commit()
    return total


# --------------------------------------------------------------------------
# Finitions : index, recherche plein texte, métadonnées
# --------------------------------------------------------------------------

def create_indexes(conn: sqlite3.Connection, tables: list[str]) -> None:
    for table in tables + ["fiche_texte", "bloc_competences_xml"]:
        numero_col = find_column(conn, table, "numero_fiche")
        if numero_col:
            conn.execute(
                f'CREATE INDEX IF NOT EXISTS "idx_{table}_numero" ON "{table}" ("{numero_col}")'
            )
    conn.commit()


def create_fts(conn: sqlite3.Connection, standard_table: str | None) -> bool:
    try:
        conn.execute("DROP TABLE IF EXISTS fiche_fts")
        conn.execute(
            "CREATE VIRTUAL TABLE fiche_fts USING fts5(numero_fiche UNINDEXED, champ, contenu)"
        )
    except sqlite3.OperationalError as exc:
        log(f"  FTS5 indisponible ({exc}) : recherche plein texte non créée")
        return False
    conn.execute(
        "INSERT INTO fiche_fts (numero_fiche, champ, contenu) "
        "SELECT numero_fiche, champ, contenu FROM fiche_texte"
    )
    if standard_table:
        numero_col = find_column(conn, standard_table, "numero_fiche")
        intitule_col = find_column(conn, standard_table, "intitule")
        if numero_col and intitule_col:
            conn.execute(
                f"INSERT INTO fiche_fts (numero_fiche, champ, contenu) "
                f'SELECT "{numero_col}", \'intitule\', "{intitule_col}" '
                f'FROM "{standard_table}" WHERE "{intitule_col}" IS NOT NULL'
            )
    conn.commit()
    return True


def write_meta(conn: sqlite3.Connection, entries: dict[str, str]) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS meta (cle TEXT PRIMARY KEY, valeur TEXT)")
    conn.executemany(
        "INSERT OR REPLACE INTO meta (cle, valeur) VALUES (?, ?)", entries.items()
    )
    conn.commit()


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Construit une base SQLite à partir des exports RNCP/RS de France compétences."
    )
    parser.add_argument("--db", default="rncp.sqlite3", help="chemin de la base SQLite produite")
    parser.add_argument(
        "--data-dir", default="data", help="répertoire de cache des fichiers téléchargés"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="conserver toutes les fiches (actives et inactives) au lieu des seules actives",
    )
    parser.add_argument(
        "--csv-zip",
        type=Path,
        help="zip CSV déjà téléchargé (désactive le téléchargement)",
    )
    parser.add_argument(
        "--xml-zip",
        type=Path,
        action="append",
        default=[],
        help="zip XML déjà téléchargé (répétable : RNCP puis RS)",
    )
    parser.add_argument(
        "--no-xml",
        action="store_true",
        help="ignorer les exports XML (base construite depuis les seuls CSV)",
    )
    parser.add_argument(
        "--taxonomie-dir",
        type=Path,
        default=Path("taxonomie"),
        help="répertoire de l'artefact de taxonomie (défaut : taxonomie/)",
    )
    parser.add_argument(
        "--no-taxonomie",
        action="store_true",
        help="ignorer la phase de taxonomie de compétences",
    )
    args = parser.parse_args()

    only_active = not args.all
    data_dir = Path(args.data_dir)

    if args.csv_zip:
        csv_zip = args.csv_zip
        xml_zips = list(args.xml_zip)
    else:
        paths = fetch_exports(data_dir)
        csv_zip = paths["csv"]
        xml_zips = [paths["xml_rncp"], paths["xml_rs"]]
    if args.no_xml:
        xml_zips = []

    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = OFF")
    conn.execute("PRAGMA synchronous = OFF")

    log(f"\nIngestion CSV : {csv_zip}")
    tables = load_csv_zip(conn, csv_zip)

    standard_table = next((t for t in tables if "standard" in t), None)
    active: set[str] | None = None
    if standard_table:
        active = active_fiche_numbers(conn, standard_table)
    if only_active:
        if active is None:
            log("Avertissement : impossible d'identifier les fiches actives ; tout est conservé.")
        else:
            log(f"\nFiltrage sur {len(active)} fiches actives :")
            filter_tables_to_active(conn, tables, active)

    conn.execute("DROP TABLE IF EXISTS fiche_texte")
    conn.execute(
        "CREATE TABLE fiche_texte ("
        "numero_fiche TEXT, repertoire TEXT, champ TEXT, contenu TEXT)"
    )
    conn.execute("DROP TABLE IF EXISTS bloc_competences_xml")
    conn.execute(
        "CREATE TABLE bloc_competences_xml ("
        "numero_fiche TEXT, repertoire TEXT, bloc_code TEXT, bloc_libelle TEXT, "
        "liste_competences TEXT, modalites_evaluation TEXT)"
    )
    xml_count = 0
    for xml_zip in xml_zips:
        log(f"\nIngestion XML : {xml_zip}")
        xml_count += load_xml_zip(conn, xml_zip, only_active, active)

    log("\nCréation des index et de la recherche plein texte…")
    create_indexes(conn, tables)
    fts_ok = create_fts(conn, standard_table)

    taxo = None
    taxo_stats: dict = {}
    if not args.no_taxonomie:
        taxo = charger_taxonomie(args.taxonomie_dir)
        if taxo is None:
            log(f"\nTaxonomie : artefact absent/incomplet dans {args.taxonomie_dir}, étape ignorée.")
    if taxo is not None:
        log("\nConstruction de la taxonomie de compétences…")
        taxo_stats = construire_taxonomie(conn, taxo)
        creer_vue_certification_competence(conn)
        indexer_taxonomie(conn)
        log(f"  couverture : ia {taxo_stats['blocs_ia_pct']}% · "
            f"lexical {taxo_stats['blocs_lexical_pct']}% · "
            f"non classé {taxo_stats['blocs_non_classe_pct']}%")

    meta_entries = {
        "source": DATASET_API,
        "csv_zip": str(csv_zip),
        "xml_zips": ", ".join(str(p) for p in xml_zips),
        "perimetre": "toutes fiches" if args.all else "fiches actives",
        "fiches_xml": str(xml_count),
        "fts": "oui" if fts_ok else "non",
        "taxonomie": "oui" if taxo is not None else "non",
    }
    if taxo is not None:
        meta_entries.update({
            "nb_domaines": str(len(taxo.domaines)),
            "nb_competences_canoniques": str(len(taxo.competences)),
            "blocs_ia_pct": str(taxo_stats["blocs_ia_pct"]),
            "blocs_lexical_pct": str(taxo_stats["blocs_lexical_pct"]),
            "blocs_non_classe_pct": str(taxo_stats["blocs_non_classe_pct"]),
        })
        for cle in ("version", "date", "modele"):
            if cle in taxo.meta:
                meta_entries[f"taxonomie_{cle}"] = str(taxo.meta[cle])
    write_meta(conn, meta_entries)

    log(f"\nBase construite : {db_path} ({db_path.stat().st_size / 1e6:.1f} Mo)")
    log("Tables : " + ", ".join(
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        )
    ))
    conn.close()


if __name__ == "__main__":
    main()
