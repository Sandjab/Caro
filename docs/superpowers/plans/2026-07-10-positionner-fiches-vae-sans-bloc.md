# Positionner les fiches VAE sans bloc — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rattacher à l'arbre de compétences les 405 certifications VAE aujourd'hui « non positionnables » (396 sans bloc dans la source, 9 tout `non_classé`), via un mapping **par fiche** alimenté par une passe LLM sur leur texte libre.

**Architecture :** Nouvel artefact versionné `taxonomie/mapping_fiches.csv` (keyé sur `numero_fiche`). `build_db.py` (stdlib, déterministe) le lit dans une table `fiche_competence_canonique` ; la vue `certification_competence` devient une **UNION** du chemin blocs (inchangé) et de ce chemin fiche. `build_ihm.py` n'est pas modifié : les fiches dotées de compétences basculent automatiquement de `sans_comp` vers `certifs`. L'artefact est produit hors dépôt par une passe de curation LLM (runbook, Partie B) décalquée sur la passe `non_classé`.

**Tech Stack :** Python 3.9+ stdlib uniquement (`sqlite3`, `csv`, `json`, `pathlib`, `unittest`). Passe de curation : Workflow Claude Code (Sonnet/Opus), gitignorée sous `data/curation/fiches/`.

## Global Constraints

- **stdlib uniquement** pour `build_db.py` : aucune dépendance tierce, pas d'éclatement en paquet.
- **Langue française** : code, messages, docstrings, commits.
- **Déterminisme** de `build_db.py` : il lit l'artefact, ne le fabrique jamais.
- **Dégradation gracieuse** : `mapping_fiches.csv` est **optionnel** (comme FTS5). Absent → aucune régression sur le chemin blocs, build vert.
- **Séparation stricte** outil de curation (occasionnel, LLM, gitignoré) / pipeline (stdlib). Les scripts de curation **ne sont pas committés** — seul l'artefact `taxonomie/mapping_fiches.csv` l'est.
- **Ne jamais éditer `ihm/index.html`** (généré, gitignoré). Régénérer via `build_ihm.py`.
- **Tests hors ligne, fixtures synthétiques** : réseau bloqué (`data.gouv.fr` interdit) côté agent.
- Séparateur CSV de l'artefact taxonomie : **`;`**, encodage **utf-8**.
- Format artefact : `mapping_fiches.csv` = colonnes `numero_fiche;competence_id;methode`. `methode` ∈ {`ia`, `humain`}.

---

# Partie A — Pipeline `build_db.py` (committé, TDD)

C'est le livrable du dépôt : vérifiable entièrement hors ligne avec des fixtures. Il est sûr avant même que l'artefact existe (dégradation gracieuse).

Rappel du code existant (référence, ne pas recopier à l'aveugle) :
- `Taxonomie.__init__(self, domaines, competences, mapping, meta)` — `build_db.py:151`
- `charger_taxonomie(taxo_dir)` — `build_db.py:166`
- `construire_taxonomie(conn, taxo, seuil)` — `build_db.py:211`
- `creer_vue_certification_competence(conn)` — `build_db.py:282`
- `indexer_taxonomie(conn)` — `build_db.py:294`
- Séquence de build — `build_db.py:745-780`

### Task 1 : `Taxonomie` porte `fiche_mapping`, `charger_taxonomie` lit `mapping_fiches.csv`

**Files:**
- Modify: `build_db.py:151-158` (classe `Taxonomie`)
- Modify: `build_db.py:166-208` (`charger_taxonomie`)
- Test: `tests/test_mapping_fiches.py` (créer)

**Interfaces:**
- Produces: `Taxonomie.fiche_mapping : list[tuple[str, str, str]]` — liste de `(numero_fiche, competence_id, methode)`, vide si le fichier est absent. Les rattachements dont la `competence_id` est inconnue sont **ignorés avec log** (comme `mapping_blocs`).

- [ ] **Step 1 : Écrire le test qui échoue**

Créer `tests/test_mapping_fiches.py` :

```python
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build_db  # noqa: E402
import tempfile
import shutil
import unittest
from pathlib import Path


def ecrire_taxo(base: Path, avec_fiches: bool):
    """Écrit un artefact taxonomie minimal ; ajoute mapping_fiches.csv si demandé."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "domaines.csv").write_text(
        "domaine_id;libelle;description;ordre\nnumerique;Numérique;;1\n",
        encoding="utf-8")
    (base / "competences_canoniques.csv").write_text(
        "competence_id;domaine_id;libelle;description;mots_cles\n"
        "site_web;numerique;Créer un site web;;site|web\n",
        encoding="utf-8")
    (base / "mapping_blocs.csv").write_text(
        "bloc_code;competence_id;methode;score\nRNCP0001BC01;site_web;ia;0.9\n",
        encoding="utf-8")
    if avec_fiches:
        (base / "mapping_fiches.csv").write_text(
            "numero_fiche;competence_id;methode\n"
            "RS0009;site_web;ia\n"            # valide
            "RS0009;inconnue;ia\n"            # competence inconnue -> ignorée
            "RNCP0003;site_web;humain\n",     # valide, methode humain
            encoding="utf-8")


class TestChargerMappingFiches(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, ignore_errors=True)

    def test_fiche_mapping_absent_vide(self):
        ecrire_taxo(self.d, avec_fiches=False)
        taxo = build_db.charger_taxonomie(self.d)
        self.assertEqual(taxo.fiche_mapping, [])

    def test_fiche_mapping_charge_et_filtre_orphelins(self):
        ecrire_taxo(self.d, avec_fiches=True)
        taxo = build_db.charger_taxonomie(self.d)
        self.assertEqual(
            sorted(taxo.fiche_mapping),
            [("RNCP0003", "site_web", "humain"), ("RS0009", "site_web", "ia")])
```

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run: `python -m unittest tests.test_mapping_fiches -v`
Expected: FAIL — `AttributeError: 'Taxonomie' object has no attribute 'fiche_mapping'`

- [ ] **Step 3 : Implémenter**

Dans `build_db.py`, modifier la classe `Taxonomie` :

```python
class Taxonomie:
    """Artefact de taxonomie chargé depuis taxonomie/*.csv."""

    def __init__(self, domaines, competences, mapping, meta, fiche_mapping=None):
        self.domaines = domaines        # list[dict]
        self.competences = competences  # list[dict]
        self.mapping = mapping          # dict[str, tuple[str, str, float | None]]
        self.meta = meta                # dict[str, str]
        self.fiche_mapping = fiche_mapping or []  # list[tuple[str, str, str]]
```

Dans `charger_taxonomie`, juste avant le bloc `meta = {}` (actuellement `build_db.py:200`), insérer le chargement optionnel :

```python
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
```

Puis modifier le `return` final :

```python
    return Taxonomie(domaines, competences, mapping, meta, fiche_mapping)
```

- [ ] **Step 4 : Lancer le test, vérifier le succès**

Run: `python -m unittest tests.test_mapping_fiches -v`
Expected: PASS (2 tests)

- [ ] **Step 5 : Commit**

```bash
git add build_db.py tests/test_mapping_fiches.py
git commit -m "Charge mapping_fiches.csv (optionnel) dans Taxonomie"
```

---

### Task 2 : `construire_fiche_competence` crée et peuple `fiche_competence_canonique`

**Files:**
- Modify: `build_db.py` (ajouter la fonction après `construire_taxonomie`, vers `build_db.py:280`)
- Test: `tests/test_mapping_fiches.py` (ajouter une classe)

**Interfaces:**
- Consumes: `Taxonomie.fiche_mapping` (Task 1).
- Produces: `construire_fiche_competence(conn, taxo) -> dict` avec les clés `nb_rattachements_fiche` (int) et `nb_fiches_rattachees` (int). Crée **toujours** la table `fiche_competence_canonique (numero_fiche, competence_id, methode, PRIMARY KEY(numero_fiche, competence_id))`, même vide, pour que la vue puisse l'unir sans condition.

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à `tests/test_mapping_fiches.py` :

```python
import sqlite3


def taxo_avec_fiches():
    domaines = [{"domaine_id": "numerique", "libelle": "Numérique",
                 "description": "", "ordre": "1"}]
    competences = [{"competence_id": "site_web", "domaine_id": "numerique",
                    "libelle": "Créer un site web", "description": "",
                    "mots_cles": "site|web"}]
    t = build_db.Taxonomie(domaines, competences, {}, {},
                           fiche_mapping=[("RS0009", "site_web", "ia"),
                                          ("RS0009", "site_web", "ia"),   # doublon
                                          ("RNCP0003", "site_web", "humain")])
    return t


class TestConstruireFicheCompetence(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        # competence_canonique doit préexister (créée par construire_taxonomie)
        self.conn.execute(
            "CREATE TABLE competence_canonique (competence_id TEXT PRIMARY KEY, "
            "domaine_id TEXT, libelle TEXT, description TEXT, mots_cles TEXT, "
            "nb_blocs INTEGER DEFAULT 0)")
        self.conn.execute(
            "INSERT INTO competence_canonique (competence_id, domaine_id) "
            "VALUES ('site_web', 'numerique')")
        self.stats = build_db.construire_fiche_competence(self.conn, taxo_avec_fiches())

    def test_table_creee_et_dedupe(self):
        rows = self.conn.execute(
            "SELECT numero_fiche, competence_id, methode "
            "FROM fiche_competence_canonique ORDER BY numero_fiche").fetchall()
        self.assertEqual(
            rows, [("RNCP0003", "site_web", "humain"),
                   ("RS0009", "site_web", "ia")])  # doublon RS0009 fusionné

    def test_stats(self):
        self.assertEqual(self.stats["nb_rattachements_fiche"], 2)
        self.assertEqual(self.stats["nb_fiches_rattachees"], 2)

    def test_table_vide_si_mapping_vide(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE competence_canonique (competence_id TEXT)")
        t = build_db.Taxonomie([], [], {}, {}, fiche_mapping=[])
        stats = build_db.construire_fiche_competence(conn, t)
        n = conn.execute("SELECT COUNT(*) FROM fiche_competence_canonique").fetchone()[0]
        self.assertEqual(n, 0)
        self.assertEqual(stats["nb_fiches_rattachees"], 0)
```

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run: `python -m unittest tests.test_mapping_fiches -v`
Expected: FAIL — `AttributeError: module 'build_db' has no attribute 'construire_fiche_competence'`

- [ ] **Step 3 : Implémenter**

Ajouter dans `build_db.py`, après `construire_taxonomie` :

```python
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
```

- [ ] **Step 4 : Lancer le test, vérifier le succès**

Run: `python -m unittest tests.test_mapping_fiches -v`
Expected: PASS (5 tests)

- [ ] **Step 5 : Commit**

```bash
git add build_db.py tests/test_mapping_fiches.py
git commit -m "Ajoute construire_fiche_competence (table fiche_competence_canonique)"
```

---

### Task 3 : Vue `certification_competence` en UNION (blocs + fiches)

**Files:**
- Modify: `build_db.py:282-291` (`creer_vue_certification_competence`)
- Modify: `tests/test_vue.py:10-14` (setUp — appeler `construire_fiche_competence`)
- Test: `tests/test_mapping_fiches.py` (ajouter une classe de vue)

**Interfaces:**
- Consumes: tables `bloc_competence_canonique` (existante) et `fiche_competence_canonique` (Task 2), `competence_canonique`.
- Produces: vue `certification_competence (numero_fiche, competence_id, domaine_id)` = UNION dédoublonnée des deux chemins.

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à `tests/test_mapping_fiches.py` :

```python
class TestVueUnion(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        # Chemin blocs : une fiche RNCP0001 avec un bloc mappé.
        self.conn.execute(
            "CREATE TABLE bloc_competences_xml (numero_fiche TEXT, repertoire TEXT, "
            "bloc_code TEXT, bloc_libelle TEXT, liste_competences TEXT, "
            "modalites_evaluation TEXT)")
        self.conn.execute(
            "INSERT INTO bloc_competences_xml VALUES "
            "('RNCP0001','RNCP','RNCP0001BC01','B','x','')")
        self.conn.execute(
            "CREATE TABLE competence_canonique (competence_id TEXT PRIMARY KEY, "
            "domaine_id TEXT, libelle TEXT, description TEXT, mots_cles TEXT, "
            "nb_blocs INTEGER DEFAULT 0)")
        self.conn.executemany(
            "INSERT INTO competence_canonique (competence_id, domaine_id) VALUES (?,?)",
            [("site_web", "numerique"), ("gestion", "numerique")])
        self.conn.execute(
            "CREATE TABLE bloc_competence_canonique (bloc_code TEXT PRIMARY KEY, "
            "numero_fiche TEXT, competence_id TEXT, methode TEXT, score REAL)")
        self.conn.execute(
            "INSERT INTO bloc_competence_canonique VALUES "
            "('RNCP0001BC01','RNCP0001','site_web','ia',0.9)")
        # Chemin fiches : RS0009 (sans bloc) -> gestion ; RNCP0001 -> site_web (doublon).
        t = build_db.Taxonomie([], [], {}, {}, fiche_mapping=[
            ("RS0009", "gestion", "ia"), ("RNCP0001", "site_web", "ia")])
        build_db.construire_fiche_competence(self.conn, t)
        build_db.creer_vue_certification_competence(self.conn)

    def test_union_des_deux_chemins(self):
        rows = sorted(self.conn.execute(
            "SELECT numero_fiche, competence_id FROM certification_competence"))
        # RNCP0001/site_web n'apparaît qu'une fois (UNION), RS0009/gestion ajouté.
        self.assertEqual(rows, [("RNCP0001", "site_web"), ("RS0009", "gestion")])
```

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run: `python -m unittest tests.test_mapping_fiches.TestVueUnion -v`
Expected: FAIL — la vue actuelle ne connaît que le chemin blocs → `RS0009` absent (`AssertionError`).

- [ ] **Step 3 : Implémenter**

Remplacer `creer_vue_certification_competence` dans `build_db.py` :

```python
def creer_vue_certification_competence(conn: sqlite3.Connection) -> None:
    """Vue diplôme -> compétences canoniques couvertes.

    UNION de deux chemins : les blocs mappés (blocs non classés exclus) et le
    rattachement par fiche (certifications sans bloc dans la source). Le UNION
    (et non UNION ALL) dédoublonne une fiche couverte par les deux chemins.
    """
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
```

Puis corriger `tests/test_vue.py` setUp — la vue référence désormais `fiche_competence_canonique`, qui doit exister avant le premier `SELECT`. Insérer l'appel entre `construire_taxonomie` et `creer_vue_certification_competence` :

```python
    def setUp(self):
        self.conn = conn_avec_blocs()
        build_db.construire_taxonomie(self.conn, taxo_test())
        build_db.construire_fiche_competence(self.conn, taxo_test())
        build_db.creer_vue_certification_competence(self.conn)
        build_db.indexer_taxonomie(self.conn)
```

- [ ] **Step 4 : Lancer les tests, vérifier le succès**

Run: `python -m unittest tests.test_mapping_fiches tests.test_vue -v`
Expected: PASS (test_vue inchangé dans ses assertions : `taxo_test()` a un `fiche_mapping` vide, donc `certification_competence` reste `[("RNCP0001","site_web","numerique")]`).

- [ ] **Step 5 : Commit**

```bash
git add build_db.py tests/test_vue.py tests/test_mapping_fiches.py
git commit -m "Vue certification_competence en UNION blocs + fiches"
```

---

### Task 4 : Index, câblage dans la séquence de build, compteurs `meta`, test bout-en-bout

**Files:**
- Modify: `build_db.py:294-302` (`indexer_taxonomie`)
- Modify: `build_db.py:751-780` (séquence de build + `meta_entries`)
- Modify: `tests/test_end_to_end.py:19-91` (fixtures + assertions)

**Interfaces:**
- Consumes: `construire_fiche_competence` (Task 2), vue UNION (Task 3).
- Produces: meta `nb_fiches_rattachees` ; index `idx_fcc_numero`, `idx_fcc_competence`.

- [ ] **Step 1 : Écrire le test qui échoue**

Dans `tests/test_end_to_end.py`, étendre `fabriquer_fixtures` :

- Ajouter une fiche VAE **sans bloc** au CSV Standard (ligne à insérer dans le `writestr` du Standard) :
  ```
  RNCP0003;Diplôme sans bloc;ACTIVE\n
  ```
- Ajouter le fichier `mapping_fiches.csv` à l'artefact taxonomie (après l'écriture de `mapping_blocs.csv`) :
  ```python
    (taxo / "mapping_fiches.csv").write_text(
        "numero_fiche;competence_id;methode\nRNCP0003;site_web;ia\n",
        encoding="utf-8")
  ```

Dans `test_construction_avec_taxonomie`, ajouter après l'assertion sur `vue` :

```python
        # RNCP0003 n'a aucun bloc mais est rattachée par fiche : présente dans la vue.
        fiches = sorted(r[0] for r in conn.execute(
            "SELECT DISTINCT numero_fiche FROM certification_competence"))
        self.assertEqual(fiches, ["RNCP0001", "RNCP0003"])
        self.assertEqual(meta["nb_fiches_rattachees"], "1")
```

- [ ] **Step 2 : Lancer le test, vérifier l'échec**

Run: `python -m unittest tests.test_end_to_end.TestBoutEnBout.test_construction_avec_taxonomie -v`
Expected: FAIL — `RNCP0003` absente de la vue (câblage manquant) et/ou `KeyError: 'nb_fiches_rattachees'`.

- [ ] **Step 3 : Implémenter**

Dans `indexer_taxonomie` (`build_db.py:294`), ajouter avant `conn.commit()` :

```python
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fcc_numero "
        "ON fiche_competence_canonique (numero_fiche)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_fcc_competence "
        "ON fiche_competence_canonique (competence_id)")
```

Dans la séquence de build (`build_db.py:751-758`), insérer l'appel entre `construire_taxonomie` et `creer_vue_certification_competence`, et journaliser :

```python
    if taxo is not None:
        log("\nConstruction de la taxonomie de compétences…")
        taxo_stats = construire_taxonomie(conn, taxo)
        fiche_stats = construire_fiche_competence(conn, taxo)
        creer_vue_certification_competence(conn)
        indexer_taxonomie(conn)
        log(f"  couverture : ia {taxo_stats['blocs_ia_pct']}% · "
            f"lexical {taxo_stats['blocs_lexical_pct']}% · "
            f"non classé {taxo_stats['blocs_non_classe_pct']}%")
        log(f"  rattachement par fiche : {fiche_stats['nb_fiches_rattachees']} fiches "
            f"({fiche_stats['nb_rattachements_fiche']} rattachements)")
```

Déclarer `fiche_stats: dict = {}` à côté de `taxo_stats: dict = {}` (`build_db.py:746`).

Dans `meta_entries`, sous le bloc `if taxo is not None:` (`build_db.py:769`), ajouter :

```python
            "nb_fiches_rattachees": str(fiche_stats.get("nb_fiches_rattachees", 0)),
```

- [ ] **Step 4 : Lancer toute la suite, vérifier le succès**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: PASS (toute la suite, y compris `test_no_taxonomie` : sans artefact, `fiche_stats` reste `{}` et `nb_fiches_rattachees` n'est pas écrit).

- [ ] **Step 5 : Commit**

```bash
git add build_db.py tests/test_end_to_end.py
git commit -m "Câble le rattachement par fiche dans le build + compteur meta"
```

---

### Task 5 : Régression `build_ihm` — une fiche rattachée par fiche est retenue

**Files:**
- Test: `tests/test_build_ihm.py` (ajouter un cas ; réutiliser les fixtures existantes)

But : garantir noir sur blanc que `build_ihm.py` n'a **pas** besoin de changer — une fiche VAE sans bloc mais présente dans `certification_competence` (chemin fiche) passe bien dans `certifs`, pas dans `sans_comp`.

**Interfaces:**
- Consumes: `build_ihm.construire_index` (existant), vue UNION.

- [ ] **Step 1 : Lire les fixtures existantes**

Run: `python -m unittest tests.test_build_ihm -v` puis ouvrir `tests/test_build_ihm.py` pour repérer le montage de base (table `certification_competence` ou vue, table `voixdacces`, `standard`). Reproduire ce montage.

- [ ] **Step 2 : Écrire le test qui échoue (ou passe déjà — voir note)**

Ajouter un test qui : insère une fiche VAE `RS0009` sans bloc, un rattachement `fiche_competence_canonique(RS0009, <comp>)`, (re)crée la vue en UNION, puis appelle `construire_index` et vérifie :

```python
        index, exclues = build_ihm.construire_index(conn, numeros)
        retenus = {c[0] for c in index["certifs"]}
        sans = {c[0] for c in index["sans_comp"]}
        self.assertIn("RS0009", retenus)
        self.assertNotIn("RS0009", sans)
```

Note : si le montage de `tests/test_build_ihm.py` crée `certification_competence` comme **table** figée (et non la vue de `build_db`), insérer directement `('RS0009', <comp>, <domaine>)` dans cette table suffit — l'important est que `construire_index` lise la fiche comme ayant ≥ 1 compétence. Adapter au montage réel constaté au Step 1.

- [ ] **Step 3 : Lancer, ajuster, vérifier le succès**

Run: `python -m unittest tests.test_build_ihm -v`
Expected: PASS. Aucune modification de `build_ihm.py` attendue ; si le test échoue pour une autre raison que le montage, s'arrêter et diagnostiquer (systematic-debugging) — cela révélerait une hypothèse fausse du design.

- [ ] **Step 4 : Commit**

```bash
git add tests/test_build_ihm.py
git commit -m "Test : une fiche rattachée par fiche est retenue par build_ihm"
```

---

**Fin de la Partie A.** Le dépôt sait désormais lire `mapping_fiches.csv` et positionner les fiches sans bloc, sous test complet et hors ligne. Avant l'artefact réel, `mapping_fiches.csv` est absent → comportement identique à aujourd'hui.

---

# Partie B — Passe de curation (runbook, hors dépôt, sur la machine de l'utilisateur)

> Cette partie **produit l'artefact** `taxonomie/mapping_fiches.csv`. Elle nécessite le réseau (vrais exports), des appels LLM et un **gate humain** : elle ne tourne pas dans l'environnement agent. Les scripts vivent sous `data/curation/fiches/` (gitignoré) — **non committés**, exactement comme la passe `non_classé` (`handoff/2026-07-10-passe-non-classe.md`). Décalquer les scripts de cette passe-là, en adaptant l'unité (fiche au lieu de bloc) et le matériau (texte libre au lieu de libellé de bloc).

**Pré-requis :** `rncp.sqlite3` fraîchement régénéré (`python build_db.py`) avec la Partie A déjà mergée (sinon la vue n'a pas le chemin fiche, mais la sélection ci-dessous reste valable).

**Sélection des cibles (critère « non positionnable ») :**

```sql
SELECT s.numero_fiche
FROM standard s
JOIN voixdacces v ON v.numero_fiche = s.numero_fiche AND v.si_jury = 'Par expérience'
WHERE s.numero_fiche NOT IN (SELECT numero_fiche FROM certification_competence)
GROUP BY s.numero_fiche;
```

Attendu ≈ **405** fiches (396 sans bloc + 9 tout `non_classé`).

### Étape B1 — Extraction (stdlib) — `data/curation/fiches/prep_fiches.py`

- `fiches_non_positionnables(conn) -> list[dict]` : pour chaque cible, `{numero_fiche, intitule, niveau, nsf:[...], capacites, activites, objectifs}` (textes tirés de `fiche_texte` : `capacites_attestees`, `activites_visees`, `objectifs_contexte`).
- Génère `menu.txt` : les 264 compétences existantes (`competence_id · libellé · domaine · mots_cles`) — **menu stable** contre lequel classer.
- Découpe en lots (≈ 30 fiches/lot) → `lots/lot_XX.json`.
- **Écrire `test_prep_fiches.py`** à côté (sur une base synthétique en mémoire) : vérifie que seules les fiches VAE sans compétence ressortent, textes joints.

### Étape B2 — Classification LLM (Workflow, fan-out Sonnet) — `classe_fiches.js`

Un agent par fiche (ou par petit lot). Contrat de sortie (schéma imposé) :

```json
{"numero_fiche": "RS0009",
 "competences": ["se_protection_surete", "t_responsabilite"],
 "besoin_nouvelle": null}
```

ou, si rien du menu ne convient :

```json
{"numero_fiche": "RS1234",
 "competences": [],
 "besoin_nouvelle": {"libelle": "...", "domaine_id": "...", "justification": "..."}}
```

Prompt : biais **existantes d'abord** ; biais **précision** (ne retenir que le clairement attesté par les capacités/activités — les capacités RS sont parfois du discours commercial) ; grain visé ≈ 3-5 compétences/fiche. Repêchage incrémental (`prep_rescue*.py`) pour les JSON tronqués. Respecter la limite de longueur de ligne des scripts Workflow (données sur disque, pas embarquées — cf. mémoire projet).

### Étape B3 — Assemblage (stdlib) — `assemble_fiches.py`

Collationne les verdicts → `mapping_brut.json` (rattachements aux compétences existantes) + `besoins_nouvelles.json` (compétences réclamées). Couverture intermédiaire : combien de fiches ont ≥ 1 compétence existante, combien dépendent d'une nouvelle.

### Étape B4 — Consolidation + **GATE HUMAIN**

- `consolidation.js` : dédoublonne les `besoin_nouvelle` (une même compétence réclamée par plusieurs fiches) → `candidates_a_valider.csv` avec colonnes `libelle;domaine_id;n_fiches;exemples;decision`.
- `valider_gate.py` : refuse un CSV où la colonne `decision` (oui/non) n'est pas entièrement remplie.
- **L'humain tranche** : oui/non par candidate, corrige libellé/domaine si besoin.

### Étape B5 — Apply (stdlib, déterministe) — `apply_fiches.py` (+ `test_apply_fiches.py`)

- Ajoute les compétences validées à `taxonomie/competences_canoniques.csv` (et un domaine à `domaines.csv` si nouveau).
- Reconstruit `taxonomie/mapping_fiches.csv` : rattachements existants + ré-affectation des fiches vers les nouvelles compétences validées (`methode` = `ia`, ou `humain` si saisi au gate).
- **Refuse si incohérent** : `competence_id` absent de la taxonomie finale, `numero_fiche` hors périmètre des 405, doublon contradictoire. Déterministe et idempotent (source de vérité = artefact committé ; réinitialiser via `git checkout -- taxonomie/` avant ré-application).
- `test_apply_fiches.py` : reconstruction correcte, refus sur incohérence.

### Étape B6 — Certification (juge Opus indépendant)

- `prep_certif.py` : échantillonne les rattachements (viser un IC ± 1 %).
- `certif.js` (Opus) : par échantillon, juge fiche↔compétences → `juste` / `faux` / `doute`.
- `certif_rate.py` : taux d'erreur + IC 95 %. Cible : ordre de **1 %** (comparable aux passes précédentes). Si trop haut, itérer B2 avec un prompt plus strict avant de committer l'artefact.

**Sortie committée de la Partie B :** `taxonomie/mapping_fiches.csv`, éventuels ajouts à `taxonomie/competences_canoniques.csv` / `taxonomie/domaines.csv`, et bloc de provenance dans `taxonomie/meta.json` (`curation.passe_fiches` + compteurs). Commit dédié.

---

# Partie C — Finalisation (committé + régénération)

### Task C1 : Régénérer la base et l'IHM, vérifier la bascule

- [ ] **Step 1 :** `python build_db.py` (avec `taxonomie/mapping_fiches.csv` en place). Vérifier le log : `rattachement par fiche : ~405 fiches`.
- [ ] **Step 2 :** Contrôle SQL — la liste des non positionnables doit fondre :

```bash
python -c "import sqlite3;c=sqlite3.connect('rncp.sqlite3');\
vae=set(r[0] for r in c.execute(\"SELECT DISTINCT numero_fiche FROM voixdacces WHERE si_jury='Par expérience'\"));\
pos=set(r[0] for r in c.execute('SELECT DISTINCT numero_fiche FROM certification_competence'));\
print('VAE non positionnables restantes :', len(vae-pos))"
```

Expected : proche de 0 (résiduel assumé = fiches dont toutes les candidates ont été refusées au gate).
- [ ] **Step 3 :** `python build_ihm.py`. Vérifier le log : `non positionnables (sans compétence, consultables)` très réduit.
- [ ] **Step 4 :** Vérification navigateur **manuelle** (aucun agent n'a de navigateur) : ouvrir `ihm/index.html`, confirmer que d'ex-« non positionnables » apparaissent dans l'arbre avec un taux de couverture cohérent.

### Task C2 : Documentation

- [ ] **Step 1 :** `README.md` — actualiser les compteurs (nb compétences/domaines si le gate en a ajouté, couverture VAE, mention du chemin « par fiche » dans le schéma : nouvelle table `fiche_competence_canonique`, vue en UNION).
- [ ] **Step 2 :** `handoff/2026-07-10-passe-fiches.md` — écrire le handoff sur le modèle de `handoff/2026-07-10-passe-non-classe.md` : ce qui a été fait, taux certifié, où vivent les scripts (gitignorés), points ouverts (résiduel refusé au gate, sur-attribution éventuelle sur les capacités RS).
- [ ] **Step 3 :** Commit docs + artefact taxonomie.

```bash
git add README.md handoff/2026-07-10-passe-fiches.md taxonomie/
git commit -m "Positionne les fiches VAE sans bloc : artefact mapping_fiches + docs"
```

- [ ] **Step 4 :** Publier l'IHM : copier `ihm/index.html` régénéré sur la branche `gh-pages` (procédure habituelle).

---

## Self-review (couverture spec → plan)

- Artefact `mapping_fiches.csv` (spec §Architecture) → Task 1 (lecture), Partie B (production). ✓
- Table `fiche_competence_canonique` + validation orphelins (spec §Pipeline 1-2) → Task 1 (orphelins ignorés au chargement), Task 2 (table). ✓
- Vue UNION dédoublonnée (spec §Pipeline 3) → Task 3. ✓
- Index + compteurs meta (spec §Pipeline 4-5) → Task 4. ✓
- `build_ihm` inchangé, bascule `sans_comp`→`certifs` (spec §Pipeline effet) → Task 5 (régression), Task C1. ✓
- Passe LLM existantes-d'abord + gate + apply + certif (spec §Outil) → Partie B B1-B6. ✓
- Chemin fiche LLM-only sans repli lexical (spec §Architecture) → aucune logique lexicale côté fiche (Task 1-2). ✓
- Dégradation gracieuse artefact absent (spec §Périmètre/critère 3) → Task 1 (optionnel), Task 4 (`test_no_taxonomie`). ✓
- Tests énumérés (spec §Tests) → Tasks 1-5. ✓
- Critères de succès 1-4 (spec) → Task C1 (bascule), Partie B B6 (certif), suite verte (Task 4), handoff (Task C2). ✓

Aucun placeholder ; signatures cohérentes entre tâches (`construire_fiche_competence(conn, taxo) -> dict`, clés `nb_fiches_rattachees` / `nb_rattachements_fiche`, `Taxonomie.fiche_mapping`).
