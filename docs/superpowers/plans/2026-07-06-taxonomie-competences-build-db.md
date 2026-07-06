# Taxonomie de compétences canoniques — Plan d'implémentation (livrable 1, partie A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter à `build_db.py` une phase stdlib qui charge un artefact de taxonomie versionné et rattache chaque bloc de compétences réel à une macro-compétence canonique, requêtable en SQL.

**Architecture :** L'artefact (`taxonomie/*.csv`) est produit hors-ligne par un outil séparé (partie B, plan distinct). Ce plan couvre uniquement la partie **déterministe et testable hors-ligne** : parsing de l'artefact, rattachement précalculé (`ia`), repli lexical stdlib pour les blocs nouveaux, marquage `non_classe`, tables + vue + stats de couverture.

**Tech Stack :** Python 3.9+, **bibliothèque standard uniquement** (`csv`, `sqlite3`, `re`, `unicodedata`, `json`, `pathlib`). Tests en **`unittest`** (stdlib, pas de pytest).

## Global Constraints

- `build_db.py` reste **autonome** : aucune dépendance tierce, aucun accès réseau, un seul script (pas d'éclatement en paquet). Valeurs et contraintes issues de `CLAUDE.md`.
- Langue du projet : **français** (code, messages, commits, données).
- Noms de tables/colonnes en **slug ASCII minuscule** (fonction `slugify` existante).
- Toute nouvelle table suit le style existant : `DROP TABLE IF EXISTS` puis `CREATE`, colonnes `TEXT` sauf entiers/réels explicites.
- Dégradation gracieuse obligatoire : artefact absent/incomplet → étape ignorée, la base se construit comme avant (modèle de `create_fts`).
- Pas de `NOT IN (?,…)` sur de grandes listes (limite de variables SQLite).
- CSV de l'artefact : délimiteur `;`, encodage UTF-8. Séparateur interne des `mots_cles` : `|`.
- Périmètre exact de l'artefact : `taxonomie/domaines.csv`, `taxonomie/competences_canoniques.csv`, `taxonomie/mapping_blocs.csv`, plus `taxonomie/meta.json` **optionnel**.

Spec de référence : `docs/superpowers/specs/2026-07-06-taxonomie-competences-canoniques-design.md`.

---

## Structure des fichiers

- **Modifié :** `build_db.py` — ajout de constantes, de 7 fonctions, et d'une phase dans `main()`. Aucune fonction existante supprimée.
- **Créé :** `tests/test_tokeniser.py`, `tests/test_lexical.py`, `tests/test_charger_taxonomie.py`, `tests/test_construire_taxonomie.py`, `tests/test_vue.py`, `tests/test_end_to_end.py`.
- **Créé (à la main, hors code) plus tard :** `taxonomie/*.csv` — produit par la partie B. Les tests fabriquent leurs propres artefacts temporaires.

Chaque fichier de test commence par ce préambule d'import (le script est à la racine du dépôt) :

```python
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
```

Commande de test globale (depuis la racine) : `python -m unittest discover -s tests -p "test_*.py" -v`

---

## Interfaces produites (référence inter-tâches)

```python
# Constantes (Tâche 1 & 4)
MOTS_VIDES: set[str]
SEUIL_LEXICAL: float = 0.12

# Tâche 1
def tokeniser(texte: str) -> set[str]

# Tâche 2
def score_lexical(tokens_a: set[str], tokens_b: set[str]) -> float
def meilleur_match_lexical(
    texte_bloc: str,
    competences_tokens: dict[str, set[str]],
    seuil: float,
) -> tuple[str | None, float]

# Tâche 3
class Taxonomie:
    domaines: list[dict]      # clés: domaine_id, libelle, description, ordre
    competences: list[dict]   # clés: competence_id, domaine_id, libelle, description, mots_cles
    mapping: dict[str, tuple[str, str, float | None]]  # bloc_code -> (competence_id, methode, score)
    meta: dict[str, str]      # version, date, modele (optionnel)
def charger_taxonomie(taxo_dir: "Path") -> "Taxonomie | None"

# Tâche 4
def construire_taxonomie(conn, taxo: "Taxonomie", seuil: float = SEUIL_LEXICAL) -> dict

# Tâche 5
def creer_vue_certification_competence(conn) -> None
def indexer_taxonomie(conn) -> None

# Tâche 6 : intégration dans main() (drapeaux CLI + phase + meta)
```

---

### Tâche 1 : Tokenisation

**Files:**
- Modify: `build_db.py` (ajouter après `slugify`, ~ligne 104)
- Test: `tests/test_tokeniser.py`

**Interfaces:**
- Consumes: rien (fonction pure, stdlib).
- Produces: `MOTS_VIDES: set[str]`, `tokeniser(texte: str) -> set[str]`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_tokeniser.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import unittest


class TestTokeniser(unittest.TestCase):
    def test_minuscule_sans_accent(self):
        self.assertEqual(build_db.tokeniser("Créer"), {"creer"})

    def test_split_et_longueur_min(self):
        # "de" (2 car.) écarté ; "web" gardé
        self.assertEqual(build_db.tokeniser("Développeur de web"), {"developpeur", "web"})

    def test_mots_vides_ecartes(self):
        # "les", "des" sont des mots vides
        self.assertEqual(build_db.tokeniser("les blocs des competences"),
                         {"blocs", "competences"})

    def test_chaine_vide(self):
        self.assertEqual(build_db.tokeniser(""), set())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `python -m unittest tests.test_tokeniser -v`
Expected: FAIL — `AttributeError: module 'build_db' has no attribute 'tokeniser'`
(Note : pour `python -m unittest tests.test_tokeniser`, créer un fichier vide `tests/__init__.py`. Alternative sans package : `python -m unittest discover -s tests -p "test_tokeniser.py" -v`.)

- [ ] **Step 3: Écrire l'implémentation minimale**

Ajouter dans `build_db.py`, juste après la fonction `slugify` :

```python
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
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `python -m unittest discover -s tests -p "test_tokeniser.py" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add build_db.py tests/test_tokeniser.py
git commit -m "Ajoute tokeniser() pour le rapprochement lexical de la taxonomie"
```

---

### Tâche 2 : Score lexical et meilleur match

**Files:**
- Modify: `build_db.py` (après `tokeniser`)
- Test: `tests/test_lexical.py`

**Interfaces:**
- Consumes: `tokeniser` (Tâche 1).
- Produces: `score_lexical(tokens_a, tokens_b) -> float`, `meilleur_match_lexical(texte_bloc, competences_tokens, seuil) -> tuple[str | None, float]`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_lexical.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import unittest


class TestScoreLexical(unittest.TestCase):
    def test_jaccard(self):
        # inter = {b, c} (2) ; union = {a, b, c, d} (4) -> 0.5
        self.assertAlmostEqual(
            build_db.score_lexical({"a", "b", "c"}, {"b", "c", "d"}), 0.5)

    def test_ensemble_vide(self):
        self.assertEqual(build_db.score_lexical(set(), {"a"}), 0.0)


class TestMeilleurMatch(unittest.TestCase):
    def setUp(self):
        self.competences = {
            "site_web": build_db.tokeniser("site web html css serveur"),
            "gestion": build_db.tokeniser("gestion comptabilite budget"),
        }

    def test_match_au_dessus_du_seuil(self):
        cid, score = build_db.meilleur_match_lexical(
            "Créer et gérer un site web avec HTML et CSS", self.competences, 0.12)
        self.assertEqual(cid, "site_web")
        self.assertGreaterEqual(score, 0.12)

    def test_sous_le_seuil_renvoie_none(self):
        cid, score = build_db.meilleur_match_lexical(
            "wobble frobnicate gizmo", self.competences, 0.12)
        self.assertIsNone(cid)
        self.assertLess(score, 0.12)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `python -m unittest discover -s tests -p "test_lexical.py" -v`
Expected: FAIL — `AttributeError: module 'build_db' has no attribute 'score_lexical'`

- [ ] **Step 3: Écrire l'implémentation minimale**

Ajouter dans `build_db.py` après `tokeniser` :

```python
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
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `python -m unittest discover -s tests -p "test_lexical.py" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add build_db.py tests/test_lexical.py
git commit -m "Ajoute score_lexical() et meilleur_match_lexical()"
```

---

### Tâche 3 : Chargement de l'artefact

**Files:**
- Modify: `build_db.py` (après `meilleur_match_lexical`)
- Test: `tests/test_charger_taxonomie.py`

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: `class Taxonomie`, `charger_taxonomie(taxo_dir: Path) -> Taxonomie | None`.
  - Renvoie `None` si le répertoire ou l'un des 3 CSV requis est absent.
  - Écarte (avec avertissement) les lignes de `mapping` dont le `competence_id` n'existe pas.
  - `meta` = contenu de `meta.json` si présent, sinon `{}`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_charger_taxonomie.py
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `python -m unittest discover -s tests -p "test_charger_taxonomie.py" -v`
Expected: FAIL — `AttributeError: module 'build_db' has no attribute 'charger_taxonomie'`

- [ ] **Step 3: Écrire l'implémentation minimale**

Ajouter dans `build_db.py` après `meilleur_match_lexical` :

```python
class Taxonomie:
    """Artefact de taxonomie chargé depuis taxonomie/*.csv."""

    def __init__(self, domaines, competences, mapping, meta):
        self.domaines = domaines        # list[dict]
        self.competences = competences  # list[dict]
        self.mapping = mapping          # dict[str, tuple[str, str, float | None]]
        self.meta = meta                # dict[str, str]


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
        score = float(brut) if brut not in (None, "") else None
        mapping[code] = (cid, row.get("methode", "ia") or "ia", score)

    meta = {}
    meta_path = taxo_dir / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            log(f"  taxonomie : meta.json illisible ({exc})")

    return Taxonomie(domaines, competences, mapping, meta)
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `python -m unittest discover -s tests -p "test_charger_taxonomie.py" -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add build_db.py tests/test_charger_taxonomie.py
git commit -m "Ajoute charger_taxonomie() : parsing de l'artefact versionné"
```

---

### Tâche 4 : Construction des tables et rattachement des blocs

**Files:**
- Modify: `build_db.py` (après `charger_taxonomie`)
- Test: `tests/test_construire_taxonomie.py`

**Interfaces:**
- Consumes: `Taxonomie`, `meilleur_match_lexical`, `tokeniser`.
- Produces: `SEUIL_LEXICAL = 0.12`, `construire_taxonomie(conn, taxo, seuil=SEUIL_LEXICAL) -> dict`.
  - Crée `domaine`, `competence_canonique`, `bloc_competence_canonique`.
  - Rattache chaque bloc de `bloc_competences_xml` (bloc_code non vide) : `ia` si présent dans le mapping, sinon repli lexical (`lexical`/`non_classe`).
  - Met à jour `competence_canonique.nb_blocs`.
  - Renvoie un dict de stats : `nb_blocs`, `blocs_ia`, `blocs_lexical`, `blocs_non_classe`, `blocs_ia_pct`, `blocs_lexical_pct`, `blocs_non_classe_pct`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_construire_taxonomie.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import sqlite3
import unittest


def conn_avec_blocs():
    """Base en mémoire avec un bloc_competences_xml minimal (3 blocs)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE bloc_competences_xml ("
        "numero_fiche TEXT, repertoire TEXT, bloc_code TEXT, bloc_libelle TEXT, "
        "liste_competences TEXT, modalites_evaluation TEXT)")
    conn.executemany(
        "INSERT INTO bloc_competences_xml VALUES (?,?,?,?,?,?)",
        [
            ("RNCP0001", "RNCP", "RNCP0001BC01", "Bloc mappé", "peu importe", ""),
            ("RNCP0001", "RNCP", "RNCP0001BC02",
             "Créer et gérer un site web", "coder html css serveur", ""),
            ("RNCP0001", "RNCP", "RNCP0001BC03",
             "wobble frobnicate", "gizmo widget", ""),
        ])
    conn.commit()
    return conn


def taxo_test():
    domaines = [{"domaine_id": "numerique", "libelle": "Numérique",
                 "description": "", "ordre": "1"}]
    competences = [
        {"competence_id": "site_web", "domaine_id": "numerique",
         "libelle": "Créer un site web", "description": "",
         "mots_cles": "site|web|html|css|serveur"},
        {"competence_id": "gestion", "domaine_id": "numerique",
         "libelle": "Gérer", "description": "", "mots_cles": "gestion|budget"},
    ]
    mapping = {"RNCP0001BC01": ("site_web", "ia", 0.9)}
    return build_db.Taxonomie(domaines, competences, mapping, {})


class TestConstruireTaxonomie(unittest.TestCase):
    def setUp(self):
        self.conn = conn_avec_blocs()
        self.stats = build_db.construire_taxonomie(self.conn, taxo_test())

    def test_tables_creees(self):
        noms = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertLessEqual(
            {"domaine", "competence_canonique", "bloc_competence_canonique"}, noms)

    def test_trois_methodes(self):
        m = dict(self.conn.execute(
            "SELECT bloc_code, methode FROM bloc_competence_canonique"))
        self.assertEqual(m["RNCP0001BC01"], "ia")
        self.assertEqual(m["RNCP0001BC02"], "lexical")
        self.assertEqual(m["RNCP0001BC03"], "non_classe")

    def test_non_classe_competence_nulle(self):
        cid = self.conn.execute(
            "SELECT competence_id FROM bloc_competence_canonique "
            "WHERE bloc_code='RNCP0001BC03'").fetchone()[0]
        self.assertIsNone(cid)

    def test_nb_blocs(self):
        nb = dict(self.conn.execute(
            "SELECT competence_id, nb_blocs FROM competence_canonique"))
        self.assertEqual(nb["site_web"], 2)  # BC01 (ia) + BC02 (lexical)
        self.assertEqual(nb["gestion"], 0)

    def test_stats(self):
        self.assertEqual(self.stats["nb_blocs"], 3)
        self.assertEqual(self.stats["blocs_ia"], 1)
        self.assertEqual(self.stats["blocs_lexical"], 1)
        self.assertEqual(self.stats["blocs_non_classe"], 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `python -m unittest discover -s tests -p "test_construire_taxonomie.py" -v`
Expected: FAIL — `AttributeError: module 'build_db' has no attribute 'construire_taxonomie'`

- [ ] **Step 3: Écrire l'implémentation minimale**

Ajouter dans `build_db.py`. D'abord la constante près des autres réglages (vers la ligne 87, après `XML_TEXT_FALLBACK_LEN`) :

```python
# Seuil de similarité lexicale en deçà duquel un bloc reste non classé.
SEUIL_LEXICAL = 0.12
```

Puis la fonction après `charger_taxonomie` :

```python
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
        c["competence_id"]: tokeniser((c.get("mots_cles") or "").replace("|", " "))
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
            cid, methode, score = taxo.mapping[bloc_code]
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
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `python -m unittest discover -s tests -p "test_construire_taxonomie.py" -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add build_db.py tests/test_construire_taxonomie.py
git commit -m "Ajoute construire_taxonomie() : tables + rattachement des blocs"
```

---

### Tâche 5 : Vue de commodité et index

**Files:**
- Modify: `build_db.py` (après `construire_taxonomie`)
- Test: `tests/test_vue.py`

**Interfaces:**
- Consumes: tables créées par `construire_taxonomie`.
- Produces: `creer_vue_certification_competence(conn) -> None`, `indexer_taxonomie(conn) -> None`.
  - La vue exclut les blocs `non_classe` (JOIN interne sur `competence_id`).

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_vue.py
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import unittest
from tests.test_construire_taxonomie import conn_avec_blocs, taxo_test


class TestVue(unittest.TestCase):
    def setUp(self):
        self.conn = conn_avec_blocs()
        build_db.construire_taxonomie(self.conn, taxo_test())
        build_db.creer_vue_certification_competence(self.conn)
        build_db.indexer_taxonomie(self.conn)

    def test_vue_certification_competence(self):
        rows = self.conn.execute(
            "SELECT numero_fiche, competence_id, domaine_id "
            "FROM certification_competence ORDER BY competence_id").fetchall()
        # BC01+BC02 -> site_web (distinct) ; BC03 non_classe exclu
        self.assertEqual(rows, [("RNCP0001", "site_web", "numerique")])

    def test_index_crees(self):
        idx = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertIn("idx_bcc_numero", idx)
        self.assertIn("idx_bcc_competence", idx)


if __name__ == "__main__":
    unittest.main()
```

Note : ce test importe `conn_avec_blocs`/`taxo_test` depuis `tests.test_construire_taxonomie` ; créer un fichier vide `tests/__init__.py` s'il n'existe pas encore, et lancer via `discover` depuis la racine.

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `python -m unittest discover -s tests -p "test_vue.py" -v`
Expected: FAIL — `AttributeError: module 'build_db' has no attribute 'creer_vue_certification_competence'`

- [ ] **Step 3: Écrire l'implémentation minimale**

Ajouter dans `build_db.py` après `construire_taxonomie` :

```python
def creer_vue_certification_competence(conn: sqlite3.Connection) -> None:
    """Vue diplôme -> compétences canoniques couvertes (blocs non classés exclus)."""
    conn.execute("DROP VIEW IF EXISTS certification_competence")
    conn.execute(
        "CREATE VIEW certification_competence AS "
        "SELECT DISTINCT b.numero_fiche, m.competence_id, cc.domaine_id "
        "FROM bloc_competences_xml b "
        "JOIN bloc_competence_canonique m ON m.bloc_code = b.bloc_code "
        "JOIN competence_canonique cc ON cc.competence_id = m.competence_id")
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
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `python -m unittest discover -s tests -p "test_vue.py" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add build_db.py tests/test_vue.py tests/__init__.py
git commit -m "Ajoute la vue certification_competence et les index de taxonomie"
```

---

### Tâche 6 : Intégration dans `main()` (CLI, phase, meta) + test bout-en-bout

**Files:**
- Modify: `build_db.py` — `argparse` (~lignes 449-479), phase après FTS (~ligne 533), bloc `meta` (~lignes 535-545)
- Test: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: `charger_taxonomie`, `construire_taxonomie`, `creer_vue_certification_competence`, `indexer_taxonomie`.
- Produces: drapeaux CLI `--taxonomie-dir` (défaut `taxonomie`), `--no-taxonomie` ; clés `meta` : `taxonomie`, et si présente `nb_domaines`, `nb_competences_canoniques`, `blocs_ia_pct`, `blocs_lexical_pct`, `blocs_non_classe_pct`, `taxonomie_version/date/modele`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_end_to_end.py
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `python -m unittest discover -s tests -p "test_end_to_end.py" -v`
Expected: FAIL — `meta["taxonomie"]` KeyError (l'intégration n'existe pas encore).

- [ ] **Step 3: Écrire l'implémentation minimale**

**3a.** Dans `main()`, ajouter deux arguments après le bloc `--no-xml` (~ligne 478) :

```python
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
```

**3b.** Après la création de la FTS (juste après `fts_ok = create_fts(conn, standard_table)`, ~ligne 533), insérer la phase taxonomie :

```python
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
```

**3c.** Remplacer l'appel `write_meta(...)` existant (~lignes 535-545) par une construction de dict enrichie :

```python
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
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `python -m unittest discover -s tests -p "test_end_to_end.py" -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Lancer toute la suite et committer**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: PASS (tous les tests des tâches 1-6)

```bash
git add build_db.py tests/test_end_to_end.py
git commit -m "Intègre la phase taxonomie dans build_db.py (CLI, meta, bout-en-bout)"
```

---

## Mise à jour de la documentation (fin de plan)

- [ ] **Mettre à jour `README.md`** : documenter les tables `domaine`, `competence_canonique`, `bloc_competence_canonique`, la vue `certification_competence`, les drapeaux `--taxonomie-dir`/`--no-taxonomie`, et un exemple de requête (« diplômes couvrant telle compétence canonique »).
- [ ] **Mettre à jour `CLAUDE.md`** : mentionner l'artefact `taxonomie/`, la séparation outil-taxonomie / pipeline, et la commande de tests `python -m unittest discover -s tests -p "test_*.py" -v`.
- [ ] **Commit** : `git commit -am "Documente la taxonomie de compétences (README, CLAUDE.md)"`

---

## Auto-revue (couverture de la spec)

- **§3 Architecture (2 outils + artefact)** → ce plan couvre le versant pipeline ; l'outil `build_taxonomie.py` (§5) est un **plan distinct, partie B** (non testable hors-ligne : réseau/embeddings/LLM). Signalé explicitement ci-dessous.
- **§4.1 Tables** `domaine`, `competence_canonique`, `bloc_competence_canonique` → Tâche 4.
- **§4.2 Vue** `certification_competence` → Tâche 5.
- **§4.3 Artefact** (3 CSV `;` + `meta.json` optionnel) → Tâche 3.
- **§6 Intégration** (chargement, 3 méthodes de rattachement, drapeaux CLI, dégradation gracieuse) → Tâches 3, 4, 6.
- **§7 Provenance/couverture** (stats meta, `non_classe` visibles) → Tâches 4, 6.
- **§8 Tests par fixtures** (bloc ia / lexical / non_classe, vue, meta) → Tâches 4, 5, 6.
- **`competence_id` nullable** → Tâche 4 (`test_non_classe_competence_nulle`).

**Non couvert par ce plan (volontairement) :** l'outil `build_taxonomie.py` (embeddings + clustering + nommage LLM + émission de l'artefact). Il fera l'objet d'un **plan partie B** distinct, car son cœur n'est pas testable dans l'environnement agent (réseau bloqué). Ce plan A produit néanmoins un logiciel **complet et testable** : dès qu'un artefact `taxonomie/` existe (même fabriqué à la main), la base est enrichie et requêtable.
```
