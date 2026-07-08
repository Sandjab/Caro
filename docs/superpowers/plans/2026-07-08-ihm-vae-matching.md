# IHM VAE — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Générer une page HTML autonome où l'utilisateur coche ses compétences dans un arbre et découvre les certifications accessibles par VAE, classées par couverture de leurs exigences.

**Architecture:** `build_ihm.py` (stdlib) lit `rncp.sqlite3`, extrait les certifications VAE, sérialise un index (0,18 Mo gzip) et un blob de détail (11,6 Mo gzip), les encode en base64 et les injecte dans `ihm/template.html` pour écrire `ihm/index.html` (~16 Mo). Le moteur de matching `ihm/matcher.js` est une fonction pure, injectée verbatim dans la page et testée sous `node --test` — le code testé est donc exactement le code livré.

**Tech Stack:** Python 3.9+ stdlib (`sqlite3`, `gzip`, `base64`, `json`, `argparse`), JavaScript sans framework, `DecompressionStream('gzip')` natif navigateur, `unittest`, `node --test`.

**Spec:** `docs/superpowers/specs/2026-07-08-ihm-vae-matching-design.md`

## Global Constraints

- **Langue du projet : français.** Code, messages, docstrings, commits.
- **Aucune dépendance tierce.** `build_ihm.py` : stdlib uniquement, comme `build_db.py`. L'IHM : pas de framework, pas de build, pas de CDN.
- **Node n'est pas une dépendance dure.** `tests/test_matcher_js.py` lève `unittest.SkipTest` si `node` est absent du `PATH` — même convention que FTS5 dans `build_db.py`.
- **`ihm/index.html` est un artefact généré**, jamais commité. `ihm/template.html` et `ihm/matcher.js` sont du code versionné.
- **Échouer bruyamment au build, dégrader gracieusement au navigateur.** Le mode d'échec redouté est la page vide plausible, pas le crash.
- **La valeur VAE est exactement `"Par expérience"`** dans `voixdacces.si_jury` (avec l'accent). Si zéro ligne, le script s'arrête en listant les valeurs réellement présentes.
- **Sont exclus de l'index** : les fiches sans compétence rattachée (408 au 2026-07-05). Leur nombre est affiché dans l'IHM.
- **`filtres.seuil` est une fraction `[0,1]`** dans le moteur. Le fragment d'URL porte un pourcentage entier. La conversion appartient à la couche IHM.
- **Convention de `build_db.py` à reprendre** : `def log(msg: str) -> None: print(msg, flush=True)`, `from __future__ import annotations`, docstrings en français.
- **Import dans les tests** : `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` avant `import build_ihm  # noqa: E402`, comme les tests existants.

---

## File Structure

| Fichier | Responsabilité |
|---|---|
| `build_ihm.py` | Lit la base, valide, extrait, compresse, injecte. Contrat : `rncp.sqlite3` + `template.html` + `matcher.js` → `index.html`. |
| `ihm/matcher.js` | Moteur pur : `(data, coches, filtres) → liste triée`. Aucun DOM, aucune globale. |
| `ihm/matcher.test.js` | `node --test`. Fige l'ordre de tri et ses trois critères. |
| `ihm/template.html` | Squelette, CSS, JS d'interface. Trois marqueurs d'injection. |
| `ihm/index.html` | **Généré**, gitignoré. |
| `tests/test_build_ihm.py` | Extraction, garde-fous, aller-retour gzip. |
| `tests/test_matcher_js.py` | Pont vers `node --test`, `SkipTest` si node absent. |
| `.gitignore` | + `ihm/index.html` |

---

## Task 1: Garde-fous et détection VAE

**Files:**
- Create: `build_ihm.py`
- Test: `tests/test_build_ihm.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `class ErreurIHM(Exception)`
  - `VOIE_VAE = "Par expérience"`
  - `def verifier_base(conn: sqlite3.Connection) -> None` — lève `ErreurIHM`
  - `def numeros_vae(conn: sqlite3.Connection) -> list[str]` — trié, lève `ErreurIHM` si vide

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `tests/test_build_ihm.py` :

```python
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
        build_ihm.verifier_base(conn_minimale())  # ne lève pas

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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m unittest tests.test_build_ihm -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'build_ihm'`

- [ ] **Step 3: Écrire l'implémentation minimale**

Créer `build_ihm.py` :

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m unittest tests.test_build_ihm -v`
Expected: PASS — 4 tests

- [ ] **Step 5: Commit**

```bash
git add build_ihm.py tests/test_build_ihm.py
git commit -m "Ajoute build_ihm.py : garde-fous et détection des fiches VAE"
```

---

## Task 2: Index — internement, groupes NSF, exclusions

**Files:**
- Modify: `build_ihm.py`
- Test: `tests/test_build_ihm.py`

**Interfaces:**
- Consumes: `verifier_base`, `numeros_vae`, `ErreurIHM` (Task 1)
- Produces:
  - `GROUPES_NSF: dict[str, str]` — 16 entrées, préfixe 2 caractères → libellé
  - `DOMAINES_TRANSVERSAUX = {"transversal", "enseignement_general"}`
  - `def construire_index(conn, numeros: list[str]) -> tuple[dict, int]` — renvoie `(index, nb_exclues)`

  Structure de `index` :
  ```python
  {
    "domaines":    ["Compétences transversales", ...],           # libellés, ordre stable
    "competences": [[id, libelle, idx_domaine, 0|1, mots_cles], ...],
    "nsf":         [["31", "Échanges et gestion"], ...],
    "certifs":     [[numero, intitule, niveau, [idx_nsf...], [idx_comp...]], ...],
    "exclues":     408,
  }
  ```
  `competences[i][3]` vaut `1` si la compétence est transversale. `certifs` est trié par numéro. Les compétences d'une certification sont triées par indice.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_build_ihm.py`, avant `if __name__` :

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m unittest tests.test_build_ihm.TestIndex -v`
Expected: FAIL — `AttributeError: module 'build_ihm' has no attribute 'construire_index'`

- [ ] **Step 3: Écrire l'implémentation**

Ajouter à `build_ihm.py`, après `numeros_vae` :

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m unittest tests.test_build_ihm -v`
Expected: PASS — 12 tests

- [ ] **Step 5: Vérifier contre la vraie base**

Run:
```bash
python -c "import sqlite3, build_ihm as b; c=sqlite3.connect('rncp.sqlite3'); b.verifier_base(c); n=b.numeros_vae(c); i,e=b.construire_index(c,n); print(len(n),'VAE |',len(i['certifs']),'retenues |',e,'exclues |',len(i['nsf']),'groupes NSF')"
```
Expected: `5582 VAE | 5174 retenues | 408 exclues | 16 groupes NSF`

Si les nombres diffèrent, l'export a changé : ne pas « corriger » le code, comprendre d'abord.

- [ ] **Step 6: Commit**

```bash
git add build_ihm.py tests/test_build_ihm.py
git commit -m "Construit l'index compact : internement, groupes NSF, exclusions"
```

---

## Task 3: Détail des fiches

**Files:**
- Modify: `build_ihm.py`
- Test: `tests/test_build_ihm.py`

**Interfaces:**
- Consumes: `numeros_vae` (Task 1), `construire_index` (Task 2)
- Produces: `def construire_detail(conn, numeros: list[str]) -> dict`
  ```python
  {"RNCP0001": {"o": "objectifs…", "a": "activités…",
                "b": [[bloc_code, bloc_libelle, liste_competences], ...]}}
  ```
  `capacites_attestees` est **volontairement absent** (27 Mo bruts, redit le contenu des blocs).

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_build_ihm.py` :

```python
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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m unittest tests.test_build_ihm.TestDetail -v`
Expected: FAIL — `AttributeError: ... 'construire_detail'`

- [ ] **Step 3: Écrire l'implémentation**

Ajouter à `build_ihm.py` :

```python
CHAMPS_DETAIL = {"objectifs_contexte": "o", "activites_visees": "a"}


def construire_detail(conn: sqlite3.Connection, numeros: list[str]) -> dict:
    """Texte de présentation et blocs de compétences, par numéro de fiche.

    capacites_attestees n'est pas embarqué : ce champ redit, réagencé, le
    contenu des liste_competences des blocs (27 Mo bruts pour rien).
    """
    ph = _placeholders(len(numeros))
    detail: dict[str, dict] = {n: {"o": "", "a": "", "b": []} for n in numeros}

    champs_ph = _placeholders(len(CHAMPS_DETAIL))
    for num, champ, contenu in conn.execute(
            f"SELECT numero_fiche, champ, contenu FROM fiche_texte "
            f"WHERE numero_fiche IN ({ph}) AND champ IN ({champs_ph})",
            list(numeros) + list(CHAMPS_DETAIL)):
        detail[num][CHAMPS_DETAIL[champ]] = contenu or ""

    for num, code, libelle, comps in conn.execute(
            f"SELECT numero_fiche, bloc_code, bloc_libelle, "
            f"COALESCE(liste_competences, '') FROM bloc_competences_xml "
            f"WHERE numero_fiche IN ({ph}) ORDER BY numero_fiche, bloc_code",
            numeros):
        detail[num]["b"].append([code, libelle, comps])

    return detail
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m unittest tests.test_build_ihm -v`
Expected: PASS — 17 tests

- [ ] **Step 5: Commit**

```bash
git add build_ihm.py tests/test_build_ihm.py
git commit -m "Extrait le détail des fiches : description et blocs de compétences"
```

---

## Task 4: Compression, injection, aller-retour

**Files:**
- Modify: `build_ihm.py`
- Test: `tests/test_build_ihm.py`

**Interfaces:**
- Consumes: `ErreurIHM` (Task 1)
- Produces:
  - `MARQUEURS = ("/*__INDEX_B64__*/", "/*__DETAIL_B64__*/", "/*__MATCHER_JS__*/")`
  - `def compresser(obj) -> str` — JSON compact → gzip(9) → base64 ASCII
  - `def decompresser(b64: str)` — inverse, utilisée par les tests
  - `def injecter(template: str, index_b64: str, detail_b64: str, matcher_js: str) -> str` — lève `ErreurIHM` si un marqueur manque

Le moteur est injecté **verbatim** : le code testé sous `node` est exactement le code livré au navigateur.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_build_ihm.py` :

```python
class TestCompressionInjection(unittest.TestCase):
    def test_aller_retour_gzip_base64(self):
        obj = {"certifs": [["RNCP0001", "Développeur web", "NIV6", [0], [1, 2]]],
               "accents": "éèêç — «»"}
        self.assertEqual(build_ihm.decompresser(build_ihm.compresser(obj)), obj)

    def test_base64_est_ascii_pur(self):
        b64 = build_ihm.compresser({"x": "éàü"})
        b64.encode("ascii")  # ne lève pas

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
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m unittest tests.test_build_ihm.TestCompressionInjection -v`
Expected: FAIL — `AttributeError: ... 'decompresser'`

- [ ] **Step 3: Écrire l'implémentation**

Ajouter les imports en tête de `build_ihm.py` (après `from __future__`) :

```python
import argparse
import base64
import gzip
import json
import sqlite3
import sys
from pathlib import Path
```

Puis, après `construire_detail` :

```python
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
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m unittest tests.test_build_ihm -v`
Expected: PASS — 21 tests

- [ ] **Step 5: Commit**

```bash
git add build_ihm.py tests/test_build_ihm.py
git commit -m "Compresse et injecte les données dans le gabarit"
```

---

## Task 5: Moteur de matching et ses tests

**Files:**
- Create: `ihm/matcher.js`
- Create: `ihm/matcher.test.js`
- Create: `tests/test_matcher_js.py`

**Interfaces:**
- Consumes: la structure d'index de Task 2.
- Produces (double export, CommonJS pour node + globales pour le navigateur) :
  - `inter(indices: number[], coches: Set<number>): number[]`
  - `passeFiltres(certif, filtres): boolean`
  - `matcher(data, coches, filtres): Resultat[]` où
    `Resultat = {certif, couverture: number, nbCouvertes: number, metier: [n, total], transv: [n, total]}`
  - `filtres = {niveaux: Set<string>|null, nsf: Set<number>|null, seuil: number /* 0..1 */}`

Tri : `couverture DESC, nbCouvertes DESC, metier[0] DESC`.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `ihm/matcher.test.js` :

```js
const test = require('node:test');
const assert = require('node:assert');
const { matcher, inter, passeFiltres } = require('./matcher.js');

// competences : [id, libelle, idx_domaine, transversal, mots_cles]
//   0 oral (transversal), 1 web, 2 reseau, 3 chantier
const DATA = {
  domaines: ['Transversal', 'Numérique', 'Bâtiment'],
  competences: [
    ['oral', "S'exprimer à l'oral", 0, 1, 'oral'],
    ['web', 'Créer un site web', 1, 0, 'web'],
    ['reseau', 'Administrer un réseau', 1, 0, 'réseau'],
    ['chantier', 'Piloter un chantier', 2, 0, 'chantier'],
  ],
  nsf: [['32', 'Communication et information'], ['23', 'Génie civil']],
  certifs: [
    // [numero, intitule, niveau, [idx_nsf], [idx_comp]]
    ['A', 'Deux métiers', 'NIV6', [0], [1, 2]],
    ['B', 'Un seul métier', 'NIV5', [0], [1]],
    ['C', 'Deux transversales', 'NIV6', [0], [0]],
    ['D', 'Métier + transversal', 'NIV7', [0], [0, 1]],
    ['E', 'Bâtiment', 'NIV3', [1], [3]],
    ['F', 'Sans niveau', '', [0], [1, 2, 3]],
  ],
  exclues: 0,
};

const TOUT = { niveaux: null, nsf: null, seuil: 0 };

test('inter ne garde que les indices cochés', () => {
  assert.deepStrictEqual(inter([1, 2, 3], new Set([2, 3, 9])), [2, 3]);
  assert.deepStrictEqual(inter([1], new Set()), []);
});

test('le taux de couverture prime sur tout', () => {
  // B est 1/1 = 100 % ; A est 1/2 = 50 %
  const r = matcher(DATA, new Set([1]), TOUT);
  assert.strictEqual(r[0].certif[0], 'B');
  assert.strictEqual(r[0].couverture, 1);
});

test('à taux égal, le volume absolu départage', () => {
  // A = 2/2, B = 1/1 : les deux à 100 %, A a plus de volume
  const r = matcher(DATA, new Set([1, 2]), TOUT);
  assert.deepStrictEqual(r.slice(0, 2).map(x => x.certif[0]), ['A', 'B']);
});

test('à volume égal, le métier départage le transversal', () => {
  // coche oral(0) + web(1) : C = 1/1 transversal, B = 1/1 métier
  const r = matcher(DATA, new Set([0, 1]), TOUT);
  const cent = r.filter(x => x.couverture === 1 && x.nbCouvertes === 1);
  assert.deepStrictEqual(cent.map(x => x.certif[0]), ['B', 'C']);
});

test('métier et transversal sont comptés séparément', () => {
  const r = matcher(DATA, new Set([0, 1]), TOUT);
  const d = r.find(x => x.certif[0] === 'D');
  assert.deepStrictEqual(d.metier, [1, 1]);
  assert.deepStrictEqual(d.transv, [1, 1]);
  assert.strictEqual(d.couverture, 1);
});

test('le seuil exclut sous la barre, bornes incluses', () => {
  // coche web(1) : A = 1/2 = 0.5 exactement
  const strict = matcher(DATA, new Set([1]), { ...TOUT, seuil: 0.5 });
  assert.ok(strict.some(x => x.certif[0] === 'A'), 'seuil inclusif');
  const dur = matcher(DATA, new Set([1]), { ...TOUT, seuil: 0.51 });
  assert.ok(!dur.some(x => x.certif[0] === 'A'));
});

test('aucune coche : tout est à 0 % et le seuil 0.5 vide la liste', () => {
  assert.strictEqual(matcher(DATA, new Set(), { ...TOUT, seuil: 0.5 }).length, 0);
  assert.strictEqual(matcher(DATA, new Set(), TOUT).length, DATA.certifs.length);
});

test('filtre niveau, la chaîne vide étant un niveau à part entière', () => {
  const f = { ...TOUT, niveaux: new Set(['']) };
  const r = matcher(DATA, new Set([1]), f);
  assert.deepStrictEqual(r.map(x => x.certif[0]), ['F']);
});

test('filtre NSF : une certification passe si un seul de ses groupes matche', () => {
  const f = { ...TOUT, nsf: new Set([1]) };  // groupe "23"
  assert.deepStrictEqual(
    matcher(DATA, new Set([3]), f).map(x => x.certif[0]), ['E']);
});

test('passeFiltres avec filtres nuls laisse tout passer', () => {
  assert.ok(passeFiltres(DATA.certifs[0], TOUT));
});

test('une certification sans exigence est ignorée, pas une division par zéro', () => {
  const data = { ...DATA, certifs: [['Z', 'Vide', 'NIV6', [0], []]] };
  assert.deepStrictEqual(matcher(data, new Set([1]), TOUT), []);
});
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `node --test ihm/`
Expected: FAIL — `Cannot find module './matcher.js'`

- [ ] **Step 3: Écrire l'implémentation**

Créer `ihm/matcher.js` :

```js
// Moteur de matching : fonction pure, sans DOM et sans variable globale.
// Ce fichier est injecté verbatim dans index.html : le code testé sous
// `node --test` est exactement le code livré au navigateur.

function inter(indices, coches) {
  return indices.filter(i => coches.has(i));
}

function passeFiltres(certif, filtres) {
  if (filtres.niveaux && !filtres.niveaux.has(certif[2])) return false;
  if (filtres.nsf && !certif[3].some(g => filtres.nsf.has(g))) return false;
  return true;
}

// data    : l'index (voir build_ihm.construire_index)
// coches  : Set d'indices de compétences cochées
// filtres : {niveaux: Set|null, nsf: Set|null, seuil: number dans [0,1]}
function matcher(data, coches, filtres) {
  const estTransversal = i => data.competences[i][3] === 1;

  return data.certifs
    .filter(c => c[4].length > 0 && passeFiltres(c, filtres))
    .map(c => {
      const req = c[4];
      const metier = req.filter(i => !estTransversal(i));
      const transv = req.filter(i => estTransversal(i));
      const couvertes = inter(req, coches);
      return {
        certif: c,
        couverture: couvertes.length / req.length,
        nbCouvertes: couvertes.length,
        metier: [inter(metier, coches).length, metier.length],
        transv: [inter(transv, coches).length, transv.length],
      };
    })
    .filter(r => r.couverture >= filtres.seuil)
    .sort((a, b) =>
      b.couverture - a.couverture ||
      b.nbCouvertes - a.nbCouvertes ||
      b.metier[0] - a.metier[0]);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { matcher, inter, passeFiltres };
}
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `node --test ihm/`
Expected: PASS — 11 tests

Note : `ihm/` ne contient pas de `package.json`, donc node traite `matcher.js` en CommonJS. C'est voulu : `module.exports` sert node, l'absence d'`import`/`export` sert le navigateur.

- [ ] **Step 5: Écrire le pont Python, avec SkipTest**

Créer `tests/test_matcher_js.py` :

```python
import os
import shutil
import subprocess
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestMatcherJS(unittest.TestCase):
    """Délègue à `node --test`. Node n'est pas une dépendance dure du dépôt :
    absent, la suite est ignorée — comme pour FTS5 dans build_db.py."""

    def test_suite_node(self):
        node = shutil.which("node")
        if node is None:
            raise unittest.SkipTest("node absent du PATH : moteur JS non testé")
        r = subprocess.run([node, "--test", os.path.join(RACINE, "ihm")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Lancer toute la suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: PASS — les 24 tests existants + 21 de `test_build_ihm` + 1 pont node

- [ ] **Step 7: Commit**

```bash
git add ihm/matcher.js ihm/matcher.test.js tests/test_matcher_js.py
git commit -m "Ajoute le moteur de matching pur et ses tests node"
```

---

## Task 6: Gabarit HTML — chargement, arbre, résultats

**Files:**
- Create: `ihm/template.html`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `matcher(data, coches, filtres)` (Task 5), les marqueurs de Task 4.
- Produces: un gabarit contenant les trois marqueurs, prêt pour Task 7 (`main()`).

Fonctions JS d'interface définies ici, utilisées par Task 8 :
- `ungzip(b64): Promise<object>`
- `etatDepuisURL(): {coches: Set<number>, niveaux: Set|null, nsf: Set|null, seuil: number}`
- `ecrireURL()`
- `rendre()` — recalcule et réaffiche

- [ ] **Step 1: Écrire le gabarit**

Créer `ihm/template.html` :

```html
<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Certifications accessibles par VAE</title>
<style>
  :root { --bord:#d8d8d8; --gris:#666; --fond:#fafafa; --acc:#1a5f9e; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.45 system-ui, sans-serif; }
  #erreur { display:none; padding:1rem; background:#fde8e8; border-bottom:2px solid #c00; }
  main { display:flex; height:100vh; }
  #arbre { width:340px; overflow-y:auto; border-right:1px solid var(--bord);
           padding:.75rem; background:var(--fond); }
  #droite { flex:1; overflow-y:auto; padding:.75rem 1rem; }
  #recherche { width:100%; padding:.4rem; margin-bottom:.5rem; }
  .domaine > summary { cursor:pointer; font-weight:600; padding:.25rem 0; }
  .feuille { display:block; padding:.15rem 0 .15rem 1.25rem; }
  #transversales { margin-top:1rem; padding-top:.5rem;
                   border-top:1px dashed var(--bord); opacity:.75; }
  #pied { font-size:.85rem; color:var(--gris); padding:.5rem 0; }
  .carte { border:1px solid var(--bord); border-radius:6px; padding:.6rem .8rem;
           margin-bottom:.6rem; }
  .carte h3 { margin:0 0 .3rem; font-size:1rem; }
  .taux { font-weight:700; color:var(--acc); margin-right:.5rem; }
  .barre { display:flex; align-items:center; gap:.5rem; font-size:.85rem; }
  .jauge { width:120px; height:8px; background:#e5e5e5; border-radius:4px; }
  .jauge > i { display:block; height:100%; background:var(--acc); border-radius:4px; }
  .meta { font-size:.8rem; color:var(--gris); margin-top:.3rem; }
  .vide { color:var(--gris); padding:2rem 0; }
  @media (max-width:768px) { main { flex-direction:column; height:auto; }
    #arbre { width:auto; border-right:none; border-bottom:1px solid var(--bord); } }
</style>
</head>
<body>
<div id="erreur"></div>
<main>
  <aside id="arbre">
    <input id="recherche" type="search" placeholder="filtrer l'arbre…" aria-label="Filtrer les compétences">
    <div id="metiers"></div>
    <div id="transversales"></div>
    <p id="compteur"></p>
    <button id="reset" type="button">Tout décocher</button>
  </aside>
  <section id="droite">
    <h1 id="titre">Chargement…</h1>
    <div id="filtres"></div>
    <div id="resultats"></div>
    <p id="pied"></p>
  </section>
</main>

<script>
const IDX_B64 = "/*__INDEX_B64__*/";
const DET_B64 = "/*__DETAIL_B64__*/";
</script>
<script>
/*__MATCHER_JS__*/
</script>
<script>
"use strict";

let DATA = null, DETAIL = null;
const coches = new Set();
const filtres = { niveaux: null, nsf: null, seuil: 0.5 };

function erreurFatale(msg) {
  const el = document.getElementById("erreur");
  el.textContent = msg;
  el.style.display = "block";
}

async function ungzip(b64) {
  const s = atob(b64);                      // chaîne latin-1, un octet par code
  const bin = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i++) bin[i] = s.charCodeAt(i);
  const flux = new Blob([bin]).stream()
    .pipeThrough(new DecompressionStream("gzip"));
  return JSON.parse(await new Response(flux).text());
}

// --- état dans le fragment d'URL : #c=1,2&niv=NIV6&nsf=0&seuil=50 ---
function etatDepuisURL() {
  const p = new URLSearchParams(location.hash.slice(1));
  coches.clear();
  (p.get("c") || "").split(",").forEach(x => {
    const i = Number(x);
    if (Number.isInteger(i) && i >= 0 && i < DATA.competences.length) coches.add(i);
  });
  const niv = p.get("niv");
  filtres.niveaux = niv === null ? null : new Set(niv.split(","));
  const nsf = p.get("nsf");
  filtres.nsf = nsf === null ? null
    : new Set(nsf.split(",").map(Number).filter(i => i >= 0 && i < DATA.nsf.length));
  const s = Number(p.get("seuil"));
  filtres.seuil = Number.isFinite(s) && s >= 0 && s <= 100 ? s / 100 : 0.5;
}

function ecrireURL() {
  const p = new URLSearchParams();
  if (coches.size) p.set("c", [...coches].sort((a, b) => a - b).join(","));
  if (filtres.niveaux) p.set("niv", [...filtres.niveaux].join(","));
  if (filtres.nsf) p.set("nsf", [...filtres.nsf].join(","));
  p.set("seuil", Math.round(filtres.seuil * 100));
  history.replaceState(null, "", "#" + p);
}

// --- arbre ---
function construireArbre() {
  const parDomaine = new Map();
  DATA.competences.forEach((c, i) => {
    if (!parDomaine.has(c[2])) parDomaine.set(c[2], []);
    parDomaine.get(c[2]).push(i);
  });
  const metiers = document.getElementById("metiers");
  const transv = document.getElementById("transversales");
  for (const [idxDom, indices] of parDomaine) {
    const estTransv = DATA.competences[indices[0]][3] === 1;
    const d = document.createElement("details");
    d.className = "domaine";
    const s = document.createElement("summary");
    s.textContent = DATA.domaines[idxDom];
    d.appendChild(s);
    for (const i of indices) {
      const lab = document.createElement("label");
      lab.className = "feuille";
      lab.dataset.mots = (DATA.competences[i][1] + " " + DATA.competences[i][4]).toLowerCase();
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.dataset.i = i;
      cb.addEventListener("change", () => {
        cb.checked ? coches.add(i) : coches.delete(i);
        ecrireURL(); rendre();
      });
      lab.append(cb, " " + DATA.competences[i][1]);
      d.appendChild(lab);
    }
    (estTransv ? transv : metiers).appendChild(d);
  }
}

function synchroniserCases() {
  document.querySelectorAll("#arbre input[type=checkbox]").forEach(cb => {
    cb.checked = coches.has(Number(cb.dataset.i));
  });
  document.getElementById("compteur").textContent =
    coches.size + (coches.size > 1 ? " compétences cochées" : " compétence cochée");
}

document.getElementById("recherche").addEventListener("input", e => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll(".feuille").forEach(l => {
    l.style.display = !q || l.dataset.mots.includes(q) ? "" : "none";
  });
  if (q) document.querySelectorAll("details.domaine").forEach(d => d.open = true);
});

document.getElementById("reset").addEventListener("click", () => {
  coches.clear(); synchroniserCases(); ecrireURL(); rendre();
});

// --- résultats ---
function jauge(n, total) {
  const pct = total ? Math.round(100 * n / total) : 0;
  return `<span class="jauge"><i style="width:${pct}%"></i></span> ${n}/${total}`;
}

function rendre() {
  synchroniserCases();
  const res = matcher(DATA, coches, filtres);
  document.getElementById("titre").textContent =
    res.length + " certification" + (res.length > 1 ? "s" : "") +
    " accessible" + (res.length > 1 ? "s" : "") + " par VAE";

  const zone = document.getElementById("resultats");
  if (coches.size === 0) {
    zone.innerHTML = '<p class="vide">Cochez vos compétences à gauche pour ' +
      'découvrir les certifications que vous pouvez viser par VAE.</p>';
    return;
  }
  if (res.length === 0) {
    zone.innerHTML = '<p class="vide">Aucune certification ne correspond. ' +
      'Baissez la couverture minimale, ou élargissez les filtres.</p>';
    return;
  }
  zone.innerHTML = res.slice(0, 200).map(r => {
    const c = r.certif;
    const nsf = c[3].map(i => DATA.nsf[i][1]).join(", ") || "—";
    const niv = c[2] || "niveau non renseigné";
    return `<article class="carte">
      <h3><span class="taux">${Math.round(r.couverture * 100)} %</span>${esc(c[1])}</h3>
      <div class="barre">métier ${jauge(r.metier[0], r.metier[1])}</div>
      <div class="barre">transversal ${jauge(r.transv[0], r.transv[1])}</div>
      <p class="meta">${niv} · ${esc(nsf)} ·
        <a href="https://www.francecompetences.fr/recherche/rncp/${encodeURIComponent(c[0].replace(/^RNCP/, ""))}/"
           target="_blank" rel="noopener">fiche officielle</a></p>
    </article>`;
  }).join("") + (res.length > 200
    ? `<p class="meta">… ${res.length - 200} autres, affinez vos filtres.</p>` : "");
}

function esc(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// --- démarrage ---
(async function () {
  if (typeof DecompressionStream === "undefined") {
    erreurFatale("Votre navigateur ne sait pas décompresser les données " +
      "(DecompressionStream). Utilisez Chrome 80+, Firefox 113+ ou Safari 16.4+.");
    return;
  }
  try {
    DATA = await ungzip(IDX_B64);
  } catch (e) {
    erreurFatale("Données illisibles : le fichier est probablement tronqué. " + e);
    return;
  }
  construireArbre();
  etatDepuisURL();
  document.getElementById("pied").textContent =
    DATA.exclues + " certifications accessibles par VAE ne sont pas listées : " +
    "leurs blocs de compétences n'ont pas pu être rattachés.";
  rendre();
  window.addEventListener("hashchange", () => { etatDepuisURL(); rendre(); });
})();
</script>
</body>
</html>
```

- [ ] **Step 2: Ajouter l'artefact généré au .gitignore**

Ajouter à la fin de `.gitignore` :

```
# IHM générée (artefact, ~16 Mo)
ihm/index.html
```

- [ ] **Step 3: Vérifier que le gabarit contient bien les trois marqueurs**

Run:
```bash
python -c "import build_ihm as b; t=open('ihm/template.html',encoding='utf-8').read(); print([m for m in b.MARQUEURS if m in t])"
```
Expected: les trois marqueurs listés.

- [ ] **Step 4: Commit**

```bash
git add ihm/template.html .gitignore
git commit -m "Ajoute le gabarit HTML : arbre, filtres, résultats"
```

---

## Task 7: CLI, écriture, garde-fou de taille

**Files:**
- Modify: `build_ihm.py`
- Test: `tests/test_build_ihm.py`

**Interfaces:**
- Consumes: tout ce qui précède.
- Produces:
  - `TAILLE_ALERTE = 25 * 1024 * 1024`
  - `def generer(db: Path, gabarit: Path, moteur: Path, sortie: Path) -> int` — renvoie le nombre de certifications retenues
  - `def main(argv: "list[str] | None" = None) -> int` — code de retour processus

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `tests/test_build_ihm.py` (avec `import tempfile`, `from pathlib import Path` en tête du fichier) :

```python
class TestGenerer(unittest.TestCase):
    def test_generation_bout_en_bout(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            db = tmp / "test.sqlite3"
            src = conn_minimale()
            dst = sqlite3.connect(db)
            src.backup(dst)
            dst.close()

            (tmp / "template.html").write_text(
                'A"/*__INDEX_B64__*/"B"/*__DETAIL_B64__*/"C/*__MATCHER_JS__*/D',
                encoding="utf-8")
            (tmp / "matcher.js").write_text("function matcher(){return [];}",
                                            encoding="utf-8")
            sortie = tmp / "index.html"

            n = build_ihm.generer(db, tmp / "template.html",
                                  tmp / "matcher.js", sortie)
            self.assertEqual(n, 2)

            html = sortie.read_text(encoding="utf-8")
            self.assertIn("function matcher(){return [];}", html)
            for marqueur in build_ihm.MARQUEURS:
                self.assertNotIn(marqueur, html)

            # le blob d'index, extrait puis décompressé, redonne les 2 fiches
            b64 = html.split('A"')[1].split('"B')[0]
            index = build_ihm.decompresser(b64)
            self.assertEqual([c[0] for c in index["certifs"]],
                             ["RNCP0001", "RNCP0004"])
            self.assertEqual(index["exclues"], 1)

    def test_base_absente(self):
        with self.assertRaises(build_ihm.ErreurIHM) as ctx:
            build_ihm.generer(Path("nexiste_pas.sqlite3"), Path("t.html"),
                              Path("m.js"), Path("o.html"))
        self.assertIn("build_db.py", str(ctx.exception))

    def test_main_retourne_1_et_affiche_l_erreur(self):
        code = build_ihm.main(["--db", "nexiste_pas.sqlite3"])
        self.assertEqual(code, 1)
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `python -m unittest tests.test_build_ihm.TestGenerer -v`
Expected: FAIL — `AttributeError: ... 'generer'`

- [ ] **Step 3: Écrire l'implémentation**

Ajouter à la fin de `build_ihm.py` :

```python
TAILLE_ALERTE = 25 * 1024 * 1024  # ~16 Mo attendus ; au-delà, quelque chose a enflé


def generer(db: Path, gabarit: Path, moteur: Path, sortie: Path) -> int:
    """Écrit la page autonome. Renvoie le nombre de certifications retenues."""
    db, gabarit, moteur, sortie = Path(db), Path(gabarit), Path(moteur), Path(sortie)
    if not db.exists():
        raise ErreurIHM(f"base {db} absente : lancer build_db.py d'abord.")
    if not gabarit.exists():
        raise ErreurIHM(f"gabarit {gabarit} absent.")
    if not moteur.exists():
        raise ErreurIHM(f"moteur {moteur} absent.")

    conn = sqlite3.connect(db)
    try:
        verifier_base(conn)
        numeros = numeros_vae(conn)
        log(f"  fiches accessibles par VAE : {len(numeros)}")
        index, exclues = construire_index(conn, numeros)
        if not index["certifs"]:
            raise ErreurIHM(
                "aucune certification VAE n'a de compétence rattachée : "
                "le mapping taxonomie est vide.")
        retenus = [c[0] for c in index["certifs"]]
        log(f"  retenues : {len(retenus)} · exclues (sans compétence) : {exclues}")
        detail = construire_detail(conn, retenus)
    finally:
        conn.close()

    html = injecter(gabarit.read_text(encoding="utf-8"),
                    compresser(index), compresser(detail),
                    moteur.read_text(encoding="utf-8"))
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(html, encoding="utf-8")

    taille = sortie.stat().st_size
    log(f"  {sortie} : {taille / 1e6:.1f} Mo")
    if taille > TAILLE_ALERTE:
        log(f"  ATTENTION : page de {taille / 1e6:.1f} Mo, au-delà du seuil "
            f"de {TAILLE_ALERTE / 1e6:.0f} Mo attendu.")
    return len(retenus)


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db", default="rncp.sqlite3", type=Path)
    p.add_argument("--gabarit", default=Path("ihm") / "template.html", type=Path)
    p.add_argument("--moteur", default=Path("ihm") / "matcher.js", type=Path)
    p.add_argument("-o", "--sortie", default=Path("ihm") / "index.html", type=Path)
    args = p.parse_args(argv)

    log("Génération de l'IHM VAE…")
    try:
        generer(args.db, args.gabarit, args.moteur, args.sortie)
    except ErreurIHM as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: PASS — toute la suite

- [ ] **Step 5: Générer la vraie page**

Run: `python build_ihm.py`
Expected:
```
Génération de l'IHM VAE…
  fiches accessibles par VAE : 5582
  retenues : 5174 · exclues (sans compétence) : 408
  ihm\index.html : 15.x Mo
```
Aucun avertissement de taille.

- [ ] **Step 6: Commit**

```bash
git add build_ihm.py tests/test_build_ihm.py
git commit -m "Ajoute la CLI de génération et le garde-fou de taille"
```

---

## Task 8: Filtres, panneau de fiche, surlignage

**Files:**
- Modify: `ihm/template.html`

**Interfaces:**
- Consumes: `DATA`, `filtres`, `coches`, `rendre()`, `ungzip`, `esc` (Task 6).
- Produces: `construireFiltres()`, `ouvrirFiche(numero)`, chargement paresseux de `DETAIL`.

Le détail (11,6 Mo gzip) n'est décompressé qu'au premier clic. Une session qui ne consulte aucune fiche ne le paie jamais.

- [ ] **Step 1: Ajouter le CSS du panneau**

Dans `ihm/template.html`, avant `@media`, ajouter :

```css
  #panneau { position:fixed; top:0; right:0; width:min(560px,90vw); height:100vh;
             background:#fff; border-left:1px solid var(--bord); overflow-y:auto;
             padding:1rem 1.25rem; box-shadow:-4px 0 16px rgba(0,0,0,.08);
             transform:translateX(100%); transition:transform .15s; }
  #panneau.ouvert { transform:none; }
  #panneau mark { background:#fff2a8; }
  #panneau .bloc { border-top:1px solid var(--bord); padding:.6rem 0; }
  #fermer { float:right; font-size:1.2rem; background:none; border:none; cursor:pointer; }
  #filtres { display:flex; gap:1rem; flex-wrap:wrap; align-items:center;
             margin-bottom:.75rem; font-size:.9rem; }
  #filtres select { min-width:150px; }
```

- [ ] **Step 2: Ajouter le panneau au HTML**

Juste avant `</main>`, ajouter :

```html
  <aside id="panneau" aria-hidden="true">
    <button id="fermer" type="button" aria-label="Fermer">×</button>
    <div id="fiche"></div>
  </aside>
```

- [ ] **Step 3: Rendre les cartes cliquables**

Dans `rendre()`, remplacer la ligne du lien officiel :

```js
      <p class="meta">${niv} · ${esc(nsf)} ·
        <a href="https://www.francecompetences.fr/recherche/rncp/${encodeURIComponent(c[0].replace(/^RNCP/, ""))}/"
           target="_blank" rel="noopener">fiche officielle</a></p>
```

par :

```js
      <p class="meta">${niv} · ${esc(nsf)} ·
        <button type="button" class="voir" data-num="${esc(c[0])}">voir la fiche</button> ·
        <a href="https://www.francecompetences.fr/recherche/rncp/${encodeURIComponent(c[0].replace(/^RNCP/, ""))}/"
           target="_blank" rel="noopener">fiche officielle</a></p>
```

et, juste après l'affectation de `zone.innerHTML` dans `rendre()`, ajouter :

```js
  zone.querySelectorAll("button.voir").forEach(b =>
    b.addEventListener("click", () => ouvrirFiche(b.dataset.num)));
```

- [ ] **Step 4: Écrire les filtres et le panneau**

Avant le bloc `// --- démarrage ---`, ajouter :

```js
// --- filtres ---
function construireFiltres() {
  const niveaux = [...new Set(DATA.certifs.map(c => c[2]))].sort();
  const opt = v => `<option value="${esc(v)}">${v || "niveau non renseigné"}</option>`;
  document.getElementById("filtres").innerHTML = `
    <label>Niveau <select id="fNiv" multiple size="3">${niveaux.map(opt).join("")}</select></label>
    <label>Domaine <select id="fNsf" multiple size="3">${
      DATA.nsf.map((n, i) => `<option value="${i}">${esc(n[1])}</option>`).join("")}</select></label>
    <label>Couverture min. <input id="fSeuil" type="range" min="0" max="100" step="5">
      <output id="oSeuil"></output></label>`;

  const fNiv = document.getElementById("fNiv");
  const fNsf = document.getElementById("fNsf");
  const fSeuil = document.getElementById("fSeuil");

  const lire = () => {
    const niv = [...fNiv.selectedOptions].map(o => o.value);
    filtres.niveaux = niv.length ? new Set(niv) : null;
    const nsf = [...fNsf.selectedOptions].map(o => Number(o.value));
    filtres.nsf = nsf.length ? new Set(nsf) : null;
    filtres.seuil = Number(fSeuil.value) / 100;
    document.getElementById("oSeuil").textContent = fSeuil.value + " %";
    ecrireURL(); rendre();
  };
  [fNiv, fNsf].forEach(el => el.addEventListener("change", lire));
  fSeuil.addEventListener("input", lire);
  synchroniserFiltres();
}

function synchroniserFiltres() {
  const fSeuil = document.getElementById("fSeuil");
  fSeuil.value = Math.round(filtres.seuil * 100);
  document.getElementById("oSeuil").textContent = fSeuil.value + " %";
  [...document.getElementById("fNiv").options].forEach(o => {
    o.selected = filtres.niveaux ? filtres.niveaux.has(o.value) : false;
  });
  [...document.getElementById("fNsf").options].forEach(o => {
    o.selected = filtres.nsf ? filtres.nsf.has(Number(o.value)) : false;
  });
}

// --- panneau de fiche ---
const panneau = document.getElementById("panneau");
document.getElementById("fermer").addEventListener("click", fermerFiche);
document.addEventListener("keydown", e => { if (e.key === "Escape") fermerFiche(); });

function fermerFiche() {
  panneau.classList.remove("ouvert");
  panneau.setAttribute("aria-hidden", "true");
}

// Surligne dans le texte du bloc les libellés des compétences cochées.
function surligner(texte, libelles) {
  let html = esc(texte);
  for (const mot of libelles) {
    if (mot.length < 4) continue;
    const motif = new RegExp(mot.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    html = html.replace(motif, m => "<mark>" + m + "</mark>");
  }
  return html;
}

async function ouvrirFiche(numero) {
  const zone = document.getElementById("fiche");
  panneau.classList.add("ouvert");
  panneau.setAttribute("aria-hidden", "false");

  if (DETAIL === null) {
    zone.innerHTML = "<p>Chargement du détail (une seule fois)…</p>";
    try {
      DETAIL = await ungzip(DET_B64);
    } catch (e) {
      DETAIL = {};
    }
  }
  const c = DATA.certifs.find(x => x[0] === numero);
  const d = DETAIL[numero];
  const lien = "https://www.francecompetences.fr/recherche/rncp/" +
    encodeURIComponent(numero.replace(/^RNCP/, "")) + "/";

  if (!d) {
    zone.innerHTML = `<h2>${esc(c ? c[1] : numero)}</h2>
      <p>Détail indisponible pour cette fiche.</p>
      <p><a href="${lien}" target="_blank" rel="noopener">Fiche officielle</a></p>`;
    return;
  }
  const mots = [...coches].map(i => DATA.competences[i][1]);
  zone.innerHTML = `<h2>${esc(c[1])}</h2>
    <p class="meta">${c[2] || "niveau non renseigné"} ·
      ${c[3].map(i => esc(DATA.nsf[i][1])).join(", ")} ·
      <a href="${lien}" target="_blank" rel="noopener">fiche officielle</a></p>
    ${d.o ? `<h3>Objectifs et contexte</h3><p>${esc(d.o)}</p>` : ""}
    ${d.a ? `<h3>Activités visées</h3><p>${esc(d.a)}</p>` : ""}
    <h3>Blocs de compétences</h3>
    ${d.b.map(b => `<div class="bloc"><strong>${esc(b[1])}</strong>
      <p>${surligner(b[2], mots)}</p></div>`).join("")}`;
}
```

- [ ] **Step 5: Brancher les filtres au démarrage**

Dans le bloc `// --- démarrage ---`, entre `etatDepuisURL();` et le texte du pied, ajouter :

```js
  construireFiltres();
```

et dans le gestionnaire `hashchange`, remplacer :

```js
  window.addEventListener("hashchange", () => { etatDepuisURL(); rendre(); });
```

par :

```js
  window.addEventListener("hashchange", () => {
    etatDepuisURL(); synchroniserFiltres(); rendre();
  });
```

- [ ] **Step 6: Régénérer et vérifier à la main dans un navigateur**

Run: `python build_ihm.py`

Ouvrir `ihm/index.html` (double-clic, protocole `file://`) et vérifier :

1. La page s'affiche en moins d'une seconde, l'arbre est peuplé, les transversales sont en bas sous un séparateur.
2. Aucune compétence cochée → message d'invitation, pas de liste.
3. Cocher « Créer un site web » → la liste apparaît, le titre compte les résultats, l'URL contient `#c=…&seuil=50`.
4. Copier l'URL, la rouvrir dans un onglet neuf → mêmes cases cochées, mêmes filtres.
5. Passer le seuil à 100 % → il ne reste que des certifications à 100 %, chacune avec ses deux barres.
6. Monter le seuil jusqu'à vider la liste → message « Aucune certification ne correspond », distinct du message d'invitation.
7. Cliquer « voir la fiche » → « Chargement du détail… » puis la fiche ; les libellés des compétences cochées sont surlignés dans les blocs. Le deuxième clic est instantané.
8. `Échap` ferme le panneau.
9. Saisir « soudure » dans le champ de recherche → l'arbre se filtre sur les mots-clés, pas seulement les intitulés.
10. Modifier l'URL en `#c=99999,abc` puis recharger → la page s'ouvre vide, sans erreur en console.
11. Le pied affiche « 408 certifications accessibles par VAE ne sont pas listées ».

Si l'un de ces points échoue, corriger avant de commiter — ne pas cocher l'étape sur la foi du code.

- [ ] **Step 7: Commit**

```bash
git add ihm/template.html
git commit -m "Ajoute les filtres, le panneau de fiche et le surlignage"
```

---

## Task 9: Documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Documenter dans le README**

Ajouter une section après celle consacrée à la taxonomie :

```markdown
## IHM : certifications accessibles par VAE

`build_ihm.py` génère une page HTML autonome (~16 Mo, sans serveur ni
dépendance) permettant de cocher ses compétences dans un arbre et de découvrir
les certifications accessibles par validation des acquis de l'expérience,
classées par couverture de leurs exigences.

```bash
python3 build_ihm.py                    # rncp.sqlite3 -> ihm/index.html
python3 build_ihm.py --db autre.sqlite3 -o /tmp/vae.html
```

Prérequis : une base construite **avec** l'artefact `taxonomie/` (la vue
`certification_competence` est nécessaire). Ouvrir ensuite `ihm/index.html`
d'un double-clic.

Le classement trie par taux de couverture, puis par nombre absolu de
compétences couvertes, puis par compétences métier — de sorte qu'une
certification exigeant huit compétences toutes couvertes passe devant une
certification n'en exigeant qu'une. Les compétences transversales comptent dans
le score mais sont affichées séparément.

Limites : 408 des 5 582 certifications VAE n'ont aucune compétence rattachée et
ne sont pas listées (la page l'indique). Le taux de couverture est un signal
grossier — la médiane est de 4 compétences exigées par certification. La
recevabilité réelle d'une VAE (durée d'expérience, jury) n'est pas modélisée.
```

- [ ] **Step 2: Documenter dans CLAUDE.md**

Dans la section « Structure du dépôt », ajouter après la ligne `build_db.py` :

```markdown
- `build_ihm.py` — génère `ihm/index.html`, page autonome de recherche de
  certifications par VAE (stdlib, lit la base, n'écrit jamais dedans).
- `ihm/` — `template.html` et `matcher.js` sont versionnés ; `index.html` est
  généré et gitignoré. Le moteur `matcher.js` est injecté verbatim dans la page
  et testé sous `node --test` : le code testé est le code livré.
```

Dans « Commandes », ajouter :

```bash
python3 build_ihm.py           # génère ihm/index.html depuis rncp.sqlite3
node --test ihm/               # teste le moteur de matching (si node présent)
```

- [ ] **Step 3: Lancer la suite complète une dernière fois**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`
Expected: PASS

Run: `node --test ihm/`
Expected: PASS — 11 tests

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Documente build_ihm.py et l'IHM VAE"
```

---

## Self-Review

**Couverture du spec :**

| Exigence du spec | Tâche |
|---|---|
| D1 page autonome, index + détail gzip/base64 | T4, T6, T7 |
| `capacites_attestees` exclu | T3 (test dédié) |
| Détail décompressé à la demande | T8 |
| D2 tri à trois composantes | T5 (trois tests dédiés) |
| D3 transversales comptées, affichées à part | T5, T6 |
| D4 filtre 16 groupes NSF | T2, T8 |
| D5 état dans le fragment d'URL | T6 |
| 196 fiches sans niveau conservées | T2 (test), T5 (test filtre) |
| 408 fiches exclues, comptées et affichées | T2, T6 |
| Garde-fous build (6 conditions) | T1, T2, T4, T7 |
| Dégradation navigateur (4 cas) | T6, T8 |
| Tests Python + node avec SkipTest | T1–T5 |
| `.gitignore` | T6 |

**Cohérence des types :** `index["competences"][i][3]` (transversalité) est lu par `matcher.js` via `data.competences[i][3] === 1` — Python écrit `1`/`0`, JSON les transporte en nombres. `certif[2]` est toujours une chaîne (`""` si niveau absent), et `filtres.niveaux` est un `Set` de chaînes : le test `test_filtre_niveau` du moteur couvre le cas `""`. `filtres.nsf` contient des **indices** (nombres), cohérent avec `certif[3]`.

**Écart assumé :** `rendre()` plafonne l'affichage à 200 cartes. Ce n'est pas dans le spec ; c'est une protection contre 5 174 nœuds DOM injectés à chaque clic. Le nombre total reste affiché dans le titre et un message indique combien de résultats sont masqués — aucune troncature silencieuse.
