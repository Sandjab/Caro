# Combler les non_classé — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to run this plan **inline** (controller-driven). This is NOT a subagent-driven plan: most phases are LLM Workflows the controller launches and a human validation gate — they cannot be delegated to a fresh implementer subagent. Only the stdlib scripts (Tasks 1, 6, 8) follow TDD. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Rattacher les 544 libellés de blocs `non_classé` à une compétence canonique — existante ou nouvelle, sous validation humaine — et certifier le résultat, en ne modifiant que l'artefact `taxonomie/`.

**Architecture:** Sept phases (spec §« Les sept phases »). Les phases 2, 3, 5-balayage, 6-certification sont des Workflows LLM lancés par le contrôleur, avec repêchage incrémental. Les phases 1, 5-rescue, 6-reconstruction sont des scripts stdlib déterministes testés sur fixtures. La phase 4 est un gate humain (édition d'un CSV). Base de vérité : `taxonomie/mapping_blocs.csv` + `rncp.sqlite3`.

**Tech Stack:** Python 3.9+ stdlib (`sqlite3`, `csv`, `json`, `re`, `unicodedata`), Workflow (agents Haiku/Sonnet/Opus), `build_db.py` (rebuild, inchangé), `build_ihm.py` (régénération, inchangé).

**Spec:** `docs/superpowers/specs/2026-07-09-taxonomie-combler-non-classe-design.md`

## Global Constraints

- **Langue : français** — code, messages, docstrings, commits, prompts d'agents.
- **Seul `taxonomie/` est committé** : `competences_canoniques.csv`, `domaines.csv`, `mapping_blocs.csv`, `meta.json`. Les scripts et fichiers intermédiaires vivent dans `data/curation/nonclasse/` (gitignoré via `data/`), jamais committés.
- **`build_db.py` et `build_ihm.py` ne sont pas modifiés.** Ils lisent l'artefact.
- **Stdlib uniquement** pour les scripts déterministes (Tasks 1, 6, 8) — aucune dépendance tierce, comme `build_db.py`.
- **Base de vérité = artefact committé**, jamais les scratchpads d'anciennes sessions.
- **Unité de jugement = libellé de bloc distinct**, propagé à tous les `bloc_code` partageant ce libellé via rejointure sur la base.
- **Échouer/refuser plutôt que produire un artefact faux** : le script d'application refuse d'écrire si un verdict manque ou si un `competence_id` cité n'existe pas.
- **Croissance du menu sous validation humaine** : aucune compétence nouvelle n'entre dans l'artefact sans passer le gate CSV de la phase 4.
- **Limite de longueur des scripts Workflow** : lignes courtes (~<90 car), sinon rejet du dialogue d'approbation ("control characters"). Données lues depuis le disque, jamais embarquées dans le script.
- **Répertoire de travail** : `WORK = data/curation/nonclasse/` (relatif au dépôt). Créé à la Task 0.
- **Repêchage incrémental** (agents qui tronquent leur JSON) : recréer un sous-dossier `rescueN/` sans jamais écraser les sorties déjà obtenues — motif éprouvé aux passes 1-3.

---

## File Structure

Tout dans `data/curation/nonclasse/` (noté `WORK`), gitignoré :

| Fichier | Rôle | Phase |
|---|---|---|
| `prep_juge.py` | extraction stdlib : libellés non_classé + menu.txt + lots | 1 |
| `juge/` | menu.txt, work/batch_*.json, out/out_*.json | 1-2 |
| `juge.js` | Workflow : jugement par libellé | 2 |
| `assemble_verdicts.py` | collationne les verdicts, couverture, entrée synthèse | 2-3 |
| `synthese.js` | Workflow : regroupe les brouillons en candidates | 3 |
| `candidates_a_valider.csv` | **gate humain** (colonne `decision`) | 4 |
| `prep_balayage.py` | sélectionne les blocs mappés proches des nouvelles | 5 |
| `balayage.js` | Workflow : juge garder/déplacer | 5 |
| `apply_nonclasse.py` | reconstruit mapping_blocs.csv (déterministe) | 6 |
| `test_apply_nonclasse.py` | tests sur fixtures de l'application | 6 |
| `prep_certif.py` / `certif.js` / `certif_rate.py` | certification du delta | 6 |

Sorties committées : `taxonomie/{competences_canoniques,domaines,mapping_blocs}.csv`, `taxonomie/meta.json`.

---

## Task 0: Branche et répertoire de travail

**Files:**
- Create: `data/curation/nonclasse/` (répertoire)

- [ ] **Step 1: Vérifier la branche et créer le répertoire**

La branche `feat/taxonomie-combler-non-classe` existe déjà (elle porte le spec). Sinon la créer depuis `main`. Puis :

```bash
cd D:/Dev/Caro
git branch --show-current   # feat/taxonomie-combler-non-classe attendu
mkdir -p data/curation/nonclasse
git check-ignore data/curation/nonclasse   # doit renvoyer le chemin (ignoré)
```

Expected : le répertoire est ignoré par git (couvert par `data/`).

- [ ] **Step 2: Snapshot de l'état de départ**

```bash
python -c "import sqlite3; c=sqlite3.connect('rncp.sqlite3'); print(dict(c.execute('SELECT methode,COUNT(*) FROM bloc_competence_canonique GROUP BY 1')))"
```
Expected : `{'ia': 27237, 'lexical': 79, 'non_classe': 973}`. Noter ces chiffres : ils bornent le travail et servent de référence au delta.

Pas de commit (aucun fichier suivi modifié).

---

## Task 1: Extraction des non_classé et du menu (stdlib, TDD)

**Files:**
- Create: `data/curation/nonclasse/prep_juge.py`
- Test: `data/curation/nonclasse/test_prep_juge.py`

**Interfaces:**
- Consumes: `rncp.sqlite3`, `taxonomie/competences_canoniques.csv`, `taxonomie/domaines.csv`.
- Produces:
  - `norm(s: str) -> str` — normalisation NFKD minuscule, espaces réduits.
  - `libelles_non_classe(conn) -> list[dict]` — `[{"lib","exemples":[bloc_code],"n_certifs":int,"nsf":[str]}]`, triés par libellé.
  - un `menu.txt` : une ligne `index | competence_id | libelle [domaine_libelle]`.
  - des lots `juge/work/batch_%03d.json` (taille 60).

- [ ] **Step 1: Écrire le test qui échoue**

Créer `data/curation/nonclasse/test_prep_juge.py` :

```python
import os, sqlite3, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import prep_juge  # noqa: E402


def base_synthetique():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE bloc_competences_xml (numero_fiche TEXT, bloc_code TEXT,
            bloc_libelle TEXT);
        CREATE TABLE bloc_competence_canonique (bloc_code TEXT, numero_fiche TEXT,
            competence_id TEXT, methode TEXT, score TEXT);
        CREATE TABLE nsf (numero_fiche TEXT, nsf_code TEXT, nsf_intitule TEXT);
    """)
    conn.executemany("INSERT INTO bloc_competences_xml VALUES (?,?,?)", [
        ("RNCP1", "RNCP1BC1", "Enseigner l'histoire-géographie"),
        ("RNCP2", "RNCP2BC1", "Enseigner l'histoire-géographie"),  # même libellé
        ("RNCP3", "RNCP3BC1", "Réaliser des opérations"),
        ("RNCP4", "RNCP4BC1", "Créer un site web"),               # mappé, exclu
    ])
    conn.executemany("INSERT INTO bloc_competence_canonique VALUES (?,?,?,?,?)", [
        ("RNCP1BC1", "RNCP1", "", "non_classe", ""),
        ("RNCP2BC1", "RNCP2", "", "non_classe", ""),
        ("RNCP3BC1", "RNCP3", "", "non_classe", ""),
        ("RNCP4BC1", "RNCP4", "site_web", "ia", ""),
    ])
    conn.executemany("INSERT INTO nsf VALUES (?,?,?)", [
        ("RNCP1", "333", "333 : Enseignement"),
        ("RNCP2", "333", "333 : Enseignement"),
        ("RNCP3", "200", "200 : Industrie"),
    ])
    conn.commit()
    return conn


class TestExtraction(unittest.TestCase):
    def test_libelles_distincts_non_classe_seulement(self):
        libs = prep_juge.libelles_non_classe(base_synthetique())
        textes = [x["lib"] for x in libs]
        self.assertEqual(textes, ["Enseigner l'histoire-géographie",
                                  "Réaliser des opérations"])
        self.assertNotIn("Créer un site web", textes)

    def test_compte_certifs_et_exemples(self):
        libs = prep_juge.libelles_non_classe(base_synthetique())
        hist = next(x for x in libs if x["lib"].startswith("Enseigner"))
        self.assertEqual(hist["n_certifs"], 2)
        self.assertEqual(len(hist["exemples"]), 2)
        self.assertEqual(sorted(hist["nsf"]), ["333"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd data/curation/nonclasse && python -m unittest test_prep_juge -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'prep_juge'`

- [ ] **Step 3: Écrire `prep_juge.py`**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 1 : extrait les libellés de blocs non_classé distincts, génère le
menu des compétences canoniques, et découpe en lots pour le juge LLM.
Stdlib uniquement. Base de vérité : rncp.sqlite3 + taxonomie/ committé."""
from __future__ import annotations
import csv, json, os, re, shutil, sqlite3, unicodedata

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.abspath(os.path.join(ICI, "..", "..", ".."))
DB = os.path.join(RACINE, "rncp.sqlite3")
TAX = os.path.join(RACINE, "taxonomie")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.strip().lower())


def libelles_non_classe(conn: sqlite3.Connection) -> "list[dict]":
    """Libellés de blocs non_classé distincts, avec exemples, compte de
    certifications et codes NSF (contexte pour le juge)."""
    rows = conn.execute("""
        SELECT b.bloc_libelle, b.bloc_code, b.numero_fiche
        FROM bloc_competence_canonique m
        JOIN bloc_competences_xml b ON b.bloc_code = m.bloc_code
        WHERE m.methode = 'non_classe' AND TRIM(b.bloc_libelle) != ''
    """).fetchall()
    nsf = {}
    for num, code in conn.execute("SELECT numero_fiche, nsf_code FROM nsf"):
        nsf.setdefault(num, set()).add((code or "")[:3])
    agg: dict = {}
    for lib, code, num in rows:
        d = agg.setdefault(lib, {"lib": lib, "exemples": [], "certifs": set(),
                                 "nsf": set()})
        if len(d["exemples"]) < 2:
            d["exemples"].append(code)
        d["certifs"].add(num)
        d["nsf"] |= nsf.get(num, set())
    out = []
    for lib in sorted(agg):
        d = agg[lib]
        out.append({"lib": lib, "exemples": d["exemples"],
                    "n_certifs": len(d["certifs"]), "nsf": sorted(d["nsf"])})
    return out


def ecrire_menu(chemin: str) -> int:
    """menu.txt : index | competence_id | libelle [domaine]. Renvoie le nombre
    de compétences."""
    dom = {r["domaine_id"]: r["libelle"] for r in csv.DictReader(
        open(os.path.join(TAX, "domaines.csv"), encoding="utf-8"), delimiter=";")}
    comp = list(csv.DictReader(
        open(os.path.join(TAX, "competences_canoniques.csv"), encoding="utf-8"),
        delimiter=";"))
    with open(chemin, "w", encoding="utf-8") as f:
        for i, c in enumerate(comp):
            f.write("%d | %s | %s [%s]\n" % (
                i, c["competence_id"], c["libelle"],
                dom.get(c["domaine_id"], c["domaine_id"])))
    return len(comp)


def main():
    conn = sqlite3.connect(DB)
    libs = libelles_non_classe(conn)
    print("libellés non_classé distincts :", len(libs))
    jdir = os.path.join(ICI, "juge")
    if os.path.isdir(jdir):
        shutil.rmtree(jdir)
    os.makedirs(os.path.join(jdir, "work"))
    os.makedirs(os.path.join(jdir, "out"))
    n = ecrire_menu(os.path.join(jdir, "menu.txt"))
    print("menu.txt :", n, "compétences")
    # index global stable j
    for j, it in enumerate(libs):
        it["j"] = j
    json.dump(libs, open(os.path.join(ICI, "population.json"), "w",
              encoding="utf-8"), ensure_ascii=False)
    B, k = 60, 0
    for s in range(0, len(libs), B):
        lot = [{"j": it["j"], "lib": it["lib"], "nsf": it["nsf"],
                "n_certifs": it["n_certifs"]} for it in libs[s:s + B]]
        json.dump(lot, open(os.path.join(jdir, "work", "batch_%03d.json" % k),
                  "w", encoding="utf-8"), ensure_ascii=False)
        k += 1
    print("lots :", k, "(taille", B, ")")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd data/curation/nonclasse && python -m unittest test_prep_juge -v`
Expected: PASS — 2 tests.

- [ ] **Step 5: Exécuter contre la vraie base**

Run: `cd data/curation/nonclasse && python prep_juge.py`
Expected :
```
libellés non_classé distincts : 544
menu.txt : 227 compétences
lots : 10 (taille 60)
```
Si le nombre de libellés diffère de 544, l'artefact/base a changé : le constater, ne pas forcer.

- [ ] **Step 6: Pas de commit** (fichiers gitignorés). Continuer.

---

## Task 2: Jugement par libellé (Workflow LLM, contrôleur)

**Files:**
- Create: `data/curation/nonclasse/juge.js`
- Uses: `juge/menu.txt`, `juge/work/*.json` (Task 1)
- Produces: `juge/out/out_*.json`

**Interfaces:**
- Consumes: `population.json`, lots de la Task 1.
- Produces: verdicts `[{"j":int,"v":"inclassable|existante|nouvelle","cid":"...","brouillon":{"libelle","domaine","pourquoi"}}]`.

- [ ] **Step 1: Écrire le script de Workflow**

Créer `data/curation/nonclasse/juge.js` (lignes courtes — limite Workflow) :

```js
export const meta = {
  name: 'juge-non-classe',
  description: 'Juge chaque libelle non_classe : inclassable/existante/nouvelle',
  phases: [{ title: 'Juger' }],
}
const A = typeof args === 'string' ? JSON.parse(args) : args
const dir = A.dir
const n = A.n
function pad(k) { return String(k).padStart(3, '0') }
phase('Juger')
const thunks = []
for (let k = 0; k < n; k++) {
  const nn = pad(k)
  thunks.push(() => agent(
    [
      'Tu es expert des competences professionnelles (RNCP/RS).',
      '',
      'Lis avec Read :',
      '1. Le menu des competences canoniques : ' + dir + '/menu.txt',
      '   (index | competence_id | libelle [domaine])',
      '2. Ton lot : ' + dir + '/work/batch_' + nn + '.json',
      '   (liste de {j, lib, nsf, n_certifs})',
      '',
      'Chaque "lib" est un libelle de bloc de competences qui',
      'n a PAS pu etre rattache au menu. Pour chacun, tranche :',
      '- "inclassable" : trop generique/vague pour un metier',
      '  (ex. "Realiser des operations", "bloc optionnel").',
      '- "existante" : une competence du menu convient en fait,',
      '  on l a manquee -> donne son competence_id dans "cid".',
      '- "nouvelle" : aucune ne convient mais le bloc a un vrai',
      '  sens metier -> propose un brouillon {libelle, domaine,',
      '  pourquoi}. "domaine" = un domaine du menu, ou',
      '  "nouveau: <nom>" si aucun ne convient.',
      '',
      'Juge le sens metier, pas les mots communs.',
      '',
      'Ecris avec Write : ' + dir + '/out/out_' + nn + '.json',
      'Tableau JSON compact, une entree par item, meme ordre :',
      '[{"j":<j>,"v":"...","cid":"","brouillon":null}]',
      'Pour "existante" remplis cid. Pour "nouvelle" remplis',
      'brouillon. Sinon laisse cid="" et brouillon=null.',
      'Aucun autre texte, pas de BOM. Reponse finale = "ok".',
    ].join('\n'),
    { label: 'juge:' + nn, phase: 'Juger',
      agentType: 'general-purpose', model: 'sonnet' }
  ))
}
const res = await parallel(thunks)
log('lots juges: ' + res.filter(Boolean).length + '/' + n)
return { done: res.filter(Boolean).length, n }
```

Note : modèle `sonnet` (jugement fin à trois voies, plus exigeant qu'un simple triage ; le volume est faible — 544 items).

- [ ] **Step 2: Lancer le Workflow**

Le contrôleur lance (10 lots) via l'outil Workflow, `args = {"dir": "<chemin absolu>/juge", "n": 10}`. Attendre la notification de fin.

- [ ] **Step 3: Assembler et vérifier la couverture (stdlib)**

Créer `assemble_verdicts.py` qui lit `juge/out/*.json` + `juge/rescue*/out/*.json`, joint à `population.json`, et affiche : nombre de verdicts / 544, répartition `inclassable/existante/nouvelle`, et la liste des `j` manquants. Refuser de continuer si des verdicts manquent.

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Collationne les verdicts du juge, contrôle la couverture, prépare l'entrée
de la synthèse. Stdlib."""
from __future__ import annotations
import glob, json, os, sys
from collections import Counter
ICI = os.path.dirname(os.path.abspath(__file__))
pop = json.load(open(os.path.join(ICI, "population.json"), encoding="utf-8"))
verd = {}
for p in sorted(glob.glob(os.path.join(ICI, "juge", "out", "*.json"))) + \
         sorted(glob.glob(os.path.join(ICI, "juge", "rescue*", "out", "*.json"))):
    try:
        for e in json.load(open(p, encoding="utf-8-sig")):
            if isinstance(e, dict) and isinstance(e.get("j"), int):
                verd[e["j"]] = e
    except Exception as ex:
        print("illisible:", os.path.basename(p), ex)
manq = sorted({it["j"] for it in pop} - set(verd))
print("verdicts:", len(verd), "/", len(pop))
print("repartition:", dict(Counter(v.get("v") for v in verd.values())))
if manq:
    print("MANQUANTS:", len(manq), "-> lots", sorted({j // 60 for j in manq}))
    json.dump(manq, open(os.path.join(ICI, "manquants.json"), "w"))
    sys.exit(1)
# entrée synthèse : les brouillons "nouvelle" avec leur libellé source
brouillons = []
for it in pop:
    e = verd[it["j"]]
    if e.get("v") == "nouvelle" and e.get("brouillon"):
        b = dict(e["brouillon"]); b["lib_source"] = it["lib"]; b["j"] = it["j"]
        brouillons.append(b)
json.dump(brouillons, open(os.path.join(ICI, "brouillons.json"), "w",
          encoding="utf-8"), ensure_ascii=False)
json.dump(verd, open(os.path.join(ICI, "verdicts.json"), "w",
          encoding="utf-8"), ensure_ascii=False)
print("brouillons 'nouvelle':", len(brouillons))
```

Run: `python assemble_verdicts.py`

- [ ] **Step 4: Repêchage si nécessaire**

Si `assemble_verdicts.py` sort en 1 (manquants), créer `prep_rescue.py` (motif des passes 1-3 : lit `manquants.json`, écrit `juge/rescueN/work/*.json` en lots de 25, incrémental sans écraser), relancer `juge.js` sur `rescueN`, puis re-`assemble_verdicts.py`. Répéter jusqu'à couverture 100 %.

- [ ] **Step 5: Pas de commit.** Noter la répartition dans le rapport de phase.

---

## Task 3: Synthèse des candidates (Workflow LLM, contrôleur)

**Files:**
- Create: `data/curation/nonclasse/synthese.js`
- Uses: `brouillons.json` (Task 2)
- Produces: `candidates.json` → `candidates_a_valider.csv`

**Interfaces:**
- Consumes: `brouillons.json` (`[{libelle, domaine, pourquoi, lib_source, j}]`), `juge/menu.txt`.
- Produces: `candidates.json` = `[{competence_id, libelle, domaine_id, mots_cles, libs_sources:[str], js:[int]}]`.

- [ ] **Step 1: Écrire `synthese.js`**

Un seul agent (ou deux si >200 brouillons) qui lit `brouillons.json` + `menu.txt`, fusionne les doublons sémantiques, et écrit `candidates.json`. Le prompt impose : `competence_id` unique suivant la convention du dépôt (préfixe court de domaine + `_` + slug ; ex. `g_histoire_geo` pour `enseignement_general` dont les compétences commencent par `g_`), `domaine_id` **existant** du menu (ou `nouveau:<slug>`), `mots_cles` séparés par `|`, et **la liste exhaustive des `lib_source` (et leurs `j`)** couverts par chaque candidate. Lignes courtes.

```js
export const meta = {
  name: 'synthese-candidates',
  description: 'Regroupe les brouillons en competences candidates',
  phases: [{ title: 'Synthetiser' }],
}
const A = typeof args === 'string' ? JSON.parse(args) : args
const dir = A.dir
phase('Synthetiser')
const r = await agent(
  [
    'Tu construis des competences canoniques candidates a partir',
    'de brouillons proposes par un premier juge.',
    '',
    'Lis avec Read :',
    '1. Le menu actuel : ' + dir + '/menu.txt',
    '2. Les brouillons : ' + dir + '/brouillons.json',
    '   (liste de {libelle, domaine, pourquoi, lib_source, j})',
    '',
    'Regroupe les brouillons qui designent la MEME competence',
    '(meme si formules differemment). Pour chaque groupe, produis',
    'UNE candidate :',
    '- competence_id : unique, non present dans le menu, convention',
    '  = prefixe court du domaine + "_" + slug court sans accents',
    '  (ex. domaine enseignement_general -> prefixe "g" -> g_histoire).',
    '- libelle : clair, a l infinitif, style du menu.',
    '- domaine_id : un domaine_id EXISTANT du menu, ou "nouveau:<slug>"',
    '  si vraiment aucun ne convient.',
    '- mots_cles : 3 a 8, separes par des barres verticales.',
    '- libs_sources : la liste EXHAUSTIVE des lib_source du groupe.',
    '- js : la liste des j correspondants.',
    '',
    'Sois econome : fusionne largement, evite les competences a un',
    'seul bloc sauf metier clairement distinct.',
    '',
    'Ecris avec Write : ' + dir + '/candidates.json',
    'Tableau JSON compact [{"competence_id","libelle","domaine_id",',
    '"mots_cles","libs_sources":[],"js":[]}]. Pas de BOM.',
    'Reponse finale = "ok".',
  ].join('\n'),
  { label: 'synthese', phase: 'Synthetiser',
    agentType: 'general-purpose', model: 'sonnet' }
)
log('synthese: ' + (r ? 'ok' : 'echec'))
return { done: r ? 1 : 0 }
```

- [ ] **Step 2: Lancer le Workflow**, `args = {"dir": "<abs>/"}` (le dir contenant `brouillons.json` et `juge/menu.txt` — adapter les chemins du prompt en conséquence : `menu.txt` est dans `juge/`).

Note d'implémentation : ajuster le chemin `menu.txt` du prompt à `dir + '/juge/menu.txt'`.

- [ ] **Step 3: Générer le CSV de validation (stdlib)**

Créer `to_csv_candidates.py` : lit `candidates.json`, écrit `candidates_a_valider.csv` avec colonnes `decision;competence_id;libelle;domaine_id;mots_cles;nb_libs;libs_sources`. `decision` vide, `libs_sources` = les libellés joints par ` || ` (lecture humaine). Contrôle : `competence_id` unique et absent des 227 ; sinon signaler.

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""candidates.json -> candidates_a_valider.csv (gate humain)."""
from __future__ import annotations
import csv, json, os
ICI = os.path.dirname(os.path.abspath(__file__))
TAX = os.path.abspath(os.path.join(ICI, "..", "..", "..", "taxonomie"))
existants = {r["competence_id"] for r in csv.DictReader(
    open(os.path.join(TAX, "competences_canoniques.csv"), encoding="utf-8"),
    delimiter=";")}
cand = json.load(open(os.path.join(ICI, "candidates.json"), encoding="utf-8"))
vus = set()
with open(os.path.join(ICI, "candidates_a_valider.csv"), "w",
          encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f, delimiter=";")
    w.writerow(["decision", "competence_id", "libelle", "domaine_id",
                "mots_cles", "nb_libs", "libs_sources"])
    for c in cand:
        cid = c["competence_id"]
        alerte = ""
        if cid in existants or cid in vus:
            alerte = " [COLLISION - renommer]"
        vus.add(cid)
        w.writerow(["", cid, c["libelle"] + alerte, c["domaine_id"],
                    c["mots_cles"], len(c["libs_sources"]),
                    " || ".join(c["libs_sources"])])
print(len(cand), "candidates ->", "candidates_a_valider.csv")
```

Run: `python to_csv_candidates.py`

- [ ] **Step 4: Pas de commit.** Passer le CSV à l'utilisateur (Task 4).

---

## Task 4: Gate humain — validation des candidates

**Files:**
- Modify (par l'humain) : `data/curation/nonclasse/candidates_a_valider.csv`

- [ ] **Step 1: Présenter le CSV à l'utilisateur**

Le contrôleur affiche un résumé lisible des candidates (libellé, domaine, nb de blocs, exemples de libellés sources) et **demande à l'utilisateur** de renseigner la colonne `decision` (`oui`/`non`) dans `candidates_a_valider.csv`, en l'invitant à éditer `libelle`/`domaine_id`/`mots_cles`/`competence_id` s'il le souhaite, et à résoudre toute `[COLLISION]`.

- [ ] **Step 2: Attendre et valider le CSV rempli**

Après retour de l'utilisateur, `valider_gate.py` contrôle : toutes les lignes ont une `decision` non vide ∈ {oui,non} ; les `oui` ont un `competence_id` unique (entre eux et vs les 227) ; leur `domaine_id` est un domaine existant ou `nouveau:<slug>`. **Refuser (exit 1)** sinon, en listant les problèmes.

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Valide candidates_a_valider.csv rempli par l'humain. Refuse si incomplet."""
from __future__ import annotations
import csv, os, sys
ICI = os.path.dirname(os.path.abspath(__file__))
TAX = os.path.abspath(os.path.join(ICI, "..", "..", "..", "taxonomie"))
existants = {r["competence_id"] for r in csv.DictReader(
    open(os.path.join(TAX, "competences_canoniques.csv"), encoding="utf-8"),
    delimiter=";")}
domaines = {r["domaine_id"] for r in csv.DictReader(
    open(os.path.join(TAX, "domaines.csv"), encoding="utf-8"), delimiter=";")}
rows = list(csv.DictReader(open(os.path.join(ICI, "candidates_a_valider.csv"),
            encoding="utf-8-sig"), delimiter=";"))
pb, vus = [], set()
for i, r in enumerate(rows, 1):
    d = (r["decision"] or "").strip().lower()
    if d not in ("oui", "non"):
        pb.append(f"ligne {i}: decision='{r['decision']}' (attendu oui/non)")
        continue
    if d == "non":
        continue
    cid = (r["competence_id"] or "").strip()
    if cid in existants or cid in vus:
        pb.append(f"ligne {i}: competence_id '{cid}' en collision")
    vus.add(cid)
    dom = (r["domaine_id"] or "").strip()
    if dom not in domaines and not dom.startswith("nouveau:"):
        pb.append(f"ligne {i}: domaine_id '{dom}' inconnu")
approuvees = [r for r in rows if (r["decision"] or "").strip().lower() == "oui"]
if pb:
    print("GATE REFUSE :"); [print(" -", x) for x in pb]; sys.exit(1)
print("gate OK :", len(approuvees), "candidates approuvees /", len(rows))
```

Run: `python valider_gate.py`
Expected (une fois le CSV rempli) : `gate OK : <N> candidates approuvees / <M>`

- [ ] **Step 3: Pas de commit** à ce stade (l'écriture de l'artefact se fait en Task 6, après le balayage).

---

## Task 5: Balayage ciblé des nouvelles compétences (stdlib + Workflow)

**Files:**
- Create: `data/curation/nonclasse/prep_balayage.py`, `balayage.js`

**Interfaces:**
- Consumes: `candidates_a_valider.csv` (approuvées), `mapping_blocs.csv`, base.
- Produces: `balayage/out/*.json` = `[{"i":int,"action":"garder|deplacer"}]` ; `balayage_items.json`.

- [ ] **Step 1: Écrire `prep_balayage.py`**

Pour chaque candidate approuvée, sélectionner les libellés **déjà mappés** dont les tokens recoupent ceux du libellé + mots-clés de la candidate (recouvrement lexical non nul, `norm`/`toks` stdlib comme dans les passes). Exclure les libellés déjà couverts par la candidate (ses `libs_sources`). Produire des lots pour le juge : chaque item = `{i, lib, cur_cid, cur_libelle, cand_cid, cand_libelle}`.

Réutiliser `norm` de `prep_juge.py` (import). `toks(s)` = ensemble de tokens >2 hors stopwords (repris de `prep_juge` ou défini ici). Bâtir `label -> competence_id` depuis `mapping_blocs.csv` joint à la base.

**Toujours** écrire `balayage_items.json` (liste, éventuellement vide si aucune candidate approuvée). Si la liste est vide, sauter les steps 2-3 (pas de Workflow à lancer) et aller directement au step 4, qui produira `deplacements.json = []`.

- [ ] **Step 2: Écrire `balayage.js`**

Workflow (Sonnet). Prompt : « le libellé `lib` est aujourd'hui rattaché à `cur` ; une nouvelle compétence `cand` existe. Laquelle décrit le mieux le bloc ? Réponds `garder` (cur reste meilleur) ou `deplacer` (cand est meilleure). » Sortie `[{"i":int,"action":"garder|deplacer"}]`. Lignes courtes, repêchage incrémental.

- [ ] **Step 3: Lancer, assembler, repêcher** jusqu'à couverture complète des items (même procédure que Task 2).

- [ ] **Step 4: Construire `deplacements.json` (stdlib)**

`assemble_balayage.py` joint `balayage_items.json` (produit par `prep_balayage.py`, `[{i, lib, cur_cid, cand_cid, ...}]`) avec `balayage/out/*.json` + `balayage/rescue*/out/*.json` (`[{i, action}]`), et écrit `deplacements.json` = la liste des `{"lib": <lib>, "cand_cid": <cand_cid>}` pour les items dont `action == "deplacer"`. Refuser (exit 1) si un item n'a pas d'action (couverture incomplète → repêcher).

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Joint le balayage : items proposes + verdicts garder/deplacer -> deplacements."""
from __future__ import annotations
import glob, json, os, sys
ICI = os.path.dirname(os.path.abspath(__file__))
items = json.load(open(os.path.join(ICI, "balayage_items.json"), encoding="utf-8"))
act = {}
for p in sorted(glob.glob(os.path.join(ICI, "balayage", "out", "*.json"))) + \
         sorted(glob.glob(os.path.join(ICI, "balayage", "rescue*", "out", "*.json"))):
    try:
        for e in json.load(open(p, encoding="utf-8-sig")):
            if isinstance(e, dict) and isinstance(e.get("i"), int):
                act[e["i"]] = e.get("action")
    except Exception as ex:
        print("illisible:", os.path.basename(p), ex)
manq = [it["i"] for it in items if it["i"] not in act]
if manq:
    print("MANQUANTS:", len(manq), "-> repecher le balayage"); sys.exit(1)
dep = [{"lib": it["lib"], "cand_cid": it["cand_cid"]}
       for it in items if act.get(it["i"]) == "deplacer"]
json.dump(dep, open(os.path.join(ICI, "deplacements.json"), "w",
          encoding="utf-8"), ensure_ascii=False)
print("deplacements:", len(dep), "/", len(items), "items balayes")
```

Run: `python assemble_balayage.py`

- [ ] **Step 5: Pas de commit.** `deplacements.json` alimente la Task 6. Si aucune candidate n'est approuvée, `prep_balayage.py` produit 0 item : `assemble_balayage.py` écrit `deplacements.json = []`. Le noter et passer.

---

## Task 6: Reconstruction déterministe + certification du delta

**Files:**
- Create: `data/curation/nonclasse/apply_nonclasse.py`, `test_apply_nonclasse.py`
- Modify: `taxonomie/competences_canoniques.csv`, `taxonomie/domaines.csv`, `taxonomie/mapping_blocs.csv`
- Then: `prep_certif.py`, `certif.js`, `certif_rate.py`

**Interfaces:**
- Consumes: `verdicts.json`, `candidates_a_valider.csv` (approuvées), `balayage` (déplacer), `mapping_blocs.csv` committé, base.
- Produces: artefact `taxonomie/` mis à jour ; `delta.json`.

- [ ] **Step 1: Écrire les tests de l'application (fixtures)**

Créer `test_apply_nonclasse.py`. Tests (spec §Tests) :
- un libellé jugé `existante:X` (X valide) → rattaché à X ;
- un libellé source d'une candidate **approuvée** → mappé à son `competence_id` (y compris si renommé dans le CSV) ;
- un libellé d'une candidate **refusée** → reste non mappé ;
- un `inclassable` → reste non mappé ;
- un déplacement du balayage → change le `competence_id` d'un libellé déjà mappé ;
- un `competence_id` inconnu (rescue vers un cid absent, ou candidate approuvée dont le domaine n'existe pas) → **lève** ;
- deux exécutions successives → `mapping_blocs.csv` identique (déterminisme).

Le test construit une mini-base + un mini-artefact temporaires et appelle `apply_nonclasse.appliquer(...)` avec des chemins injectés (pas de constantes globales en dur — la fonction prend `db_path`, `tax_dir`, `work_dir`).

```python
import csv, json, os, sqlite3, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_nonclasse  # noqa: E402


def artefact(tmp):
    tax = os.path.join(tmp, "taxonomie"); os.makedirs(tax)
    with open(os.path.join(tax, "domaines.csv"), "w", encoding="utf-8") as f:
        f.write("domaine_id;libelle;description;ordre\n")
        f.write("num;Numérique;;1\n")
    with open(os.path.join(tax, "competences_canoniques.csv"), "w",
              encoding="utf-8") as f:
        f.write("competence_id;domaine_id;libelle;description;mots_cles\n")
        f.write("n_site;num;Créer un site web;;web\n")
        f.write("n_bdd;num;Gérer une base de données;;sql\n")
    with open(os.path.join(tax, "mapping_blocs.csv"), "w", encoding="utf-8") as f:
        f.write("bloc_code;competence_id;methode;score\n")
        f.write("B_SITE;n_site;ia;\n")   # "Créer un site" déjà mappé
    return tax


def base(tmp):
    db = os.path.join(tmp, "rncp.sqlite3")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE bloc_competences_xml (numero_fiche TEXT, "
                 "bloc_code TEXT, bloc_libelle TEXT)")
    conn.executemany("INSERT INTO bloc_competences_xml VALUES (?,?,?)", [
        ("R1", "B_SITE", "Créer un site"),
        ("R2", "B_HIST", "Enseigner l'histoire"),
        ("R3", "B_VAGUE", "Réaliser des opérations"),
    ])
    conn.commit(); conn.close()
    return db


def work(tmp, verdicts, candidates, deplacements):
    w = os.path.join(tmp, "work"); os.makedirs(w)
    json.dump(verdicts, open(os.path.join(w, "verdicts.json"), "w"))
    with open(os.path.join(w, "candidates_a_valider.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f, delimiter=";")
        wr.writerow(["decision", "competence_id", "libelle", "domaine_id",
                     "mots_cles", "nb_libs", "libs_sources"])
        for c in candidates:
            wr.writerow(c)
    json.dump(deplacements, open(os.path.join(w, "deplacements.json"), "w"))
    # population.json : j -> lib
    json.dump([{"j": 0, "lib": "Enseigner l'histoire"},
               {"j": 1, "lib": "Réaliser des opérations"}],
              open(os.path.join(w, "population.json"), "w"))
    return w


class TestAppliquer(unittest.TestCase):
    def test_nouvelle_approuvee_rattache_ses_libs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tax, db = artefact(tmp), base(tmp)
            verd = {"0": {"j": 0, "v": "nouvelle"},
                    "1": {"j": 1, "v": "inclassable"}}
            cand = [["oui", "g_histoire", "Enseigner l'histoire", "num",
                     "histoire", 1, "Enseigner l'histoire"]]
            w = work(tmp, verd, cand, [])
            apply_nonclasse.appliquer(db, tax, w)
            m = dict((r["bloc_code"], r["competence_id"]) for r in csv.DictReader(
                open(os.path.join(tax, "mapping_blocs.csv"), encoding="utf-8"),
                delimiter=";"))
            self.assertEqual(m["B_HIST"], "g_histoire")   # rescapé
            self.assertNotIn("B_VAGUE", m)                # inclassable
            self.assertEqual(m["B_SITE"], "n_site")       # inchangé
            comp = {r["competence_id"] for r in csv.DictReader(
                open(os.path.join(tax, "competences_canoniques.csv"),
                     encoding="utf-8"), delimiter=";")}
            self.assertIn("g_histoire", comp)             # ajoutee au menu

    def test_candidate_refusee_reste_non_classe(self):
        with tempfile.TemporaryDirectory() as tmp:
            tax, db = artefact(tmp), base(tmp)
            verd = {"0": {"j": 0, "v": "nouvelle"},
                    "1": {"j": 1, "v": "inclassable"}}
            cand = [["non", "g_histoire", "Enseigner l'histoire", "num",
                     "histoire", 1, "Enseigner l'histoire"]]
            w = work(tmp, verd, cand, [])
            apply_nonclasse.appliquer(db, tax, w)
            m = dict((r["bloc_code"], r["competence_id"]) for r in csv.DictReader(
                open(os.path.join(tax, "mapping_blocs.csv"), encoding="utf-8"),
                delimiter=";"))
            self.assertNotIn("B_HIST", m)

    def test_cid_inconnu_leve(self):
        with tempfile.TemporaryDirectory() as tmp:
            tax, db = artefact(tmp), base(tmp)
            verd = {"0": {"j": 0, "v": "existante", "cid": "n_inexistant"},
                    "1": {"j": 1, "v": "inclassable"}}
            w = work(tmp, verd, [], [])
            with self.assertRaises(apply_nonclasse.ErreurCuration):
                apply_nonclasse.appliquer(db, tax, w)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd data/curation/nonclasse && python -m unittest test_apply_nonclasse -v`
Expected: FAIL — module absent.

- [ ] **Step 3: Écrire `apply_nonclasse.py`**

Logique (mirroir d'`apply3.py`, base = artefact committé) :
1. `lib_comp` = libellé normalisé → competence_id, reconstruit depuis `mapping_blocs.csv` committé joint à la base (label-consistant).
2. Charger `verdicts.json`, `candidates_a_valider.csv`, `deplacements.json`, `population.json`.
3. Ajouter au menu les candidates `oui` (nouvelles lignes dans `competences_canoniques.csv`) ; créer le domaine si `nouveau:` approuvé (ligne dans `domaines.csv`, `ordre` = max+1).
4. Construire `valides` = 227 existants + candidates approuvées.
5. Rescue : pour chaque libellé (via `population.json[j]`), si verdict `existante:X` et X∈valides → `lib_comp[norm(lib)] = X` ; si libellé ∈ libs_sources d'une candidate approuvée → `lib_comp[norm(lib)] = cid_candidate`. Si `cid` cité ∉ valides → `raise ErreurCuration`.
6. Déplacements : pour chaque `{lib, cand_cid}` marqué `deplacer` → `lib_comp[norm(lib)] = cand_cid` (cand_cid ∈ valides sinon lever).
7. Rejointure : pour chaque `bloc_code, bloc_libelle` de la base, si `norm(libelle)` ∈ `lib_comp` → écrire `(bloc_code, cid, "ia", "")`. Réécrire `mapping_blocs.csv`.
8. `raise ErreurCuration` si un verdict attendu manque.

Signature : `appliquer(db_path, tax_dir, work_dir)`. Classe `ErreurCuration(Exception)`.

- [ ] **Step 4: Lancer les tests, succès**

Run: `cd data/curation/nonclasse && python -m unittest test_apply_nonclasse -v`
Expected: PASS.

- [ ] **Step 5: Appliquer sur le vrai artefact**

D'abord copier les fichiers de décision réels dans `work` (`verdicts.json`, `candidates_a_valider.csv` rempli, `deplacements.json` issu du balayage). Puis :

Run: `python apply_nonclasse.py`  (le `main()` appelle `appliquer(DB, TAX, ICI)` sur les vrais chemins)
Expected : affiche le nombre de rescues, de déplacements, de nouvelles compétences, et `mapping_blocs.csv : N lignes`. Sauvegarder d'abord une copie `mapping_blocs_avant.csv` pour le diff.

- [ ] **Step 6: Rebuild et vérifications**

```bash
cd D:/Dev/Caro
python build_db.py --csv-zip data/export-fiches-csv-*.zip \
  --xml-zip data/export-fiches-rncp-v4-1-*.zip \
  --xml-zip data/export-fiches-rs-v4-1-*.zip 2>&1 | grep -i "couverture"
python -m unittest discover -s tests -p "test_*.py" 2>&1 | tail -3
python -c "import sqlite3;c=sqlite3.connect('rncp.sqlite3');print('orphelins:',c.execute('SELECT COUNT(*) FROM bloc_competence_canonique b LEFT JOIN competence_canonique cc ON cc.competence_id=b.competence_id WHERE b.methode!=\"non_classe\" AND cc.competence_id IS NULL').fetchone()[0])"
```
Expected : couverture `non_classe` en baisse ; suite verte (61 tests) ; **0 orphelin**.

- [ ] **Step 7: Certification du delta**

Écrire `prep_certif.py` (delta = bloc_codes dont le `competence_id` diffère de `mapping_blocs_avant.csv`, y compris nouvellement présents ; échantillon stratifié par domaine de la compétence assignée, ~300, lots), `certif.js` (juge **Opus**, verdict `ok/doute/faux`, posture de réfutation), `certif_rate.py` (estimateur stratifié repondéré + IC 95 % de Wald ; réutiliser la logique de la certification d'origine). Lancer, repêcher, calculer.
Expected : taux d'erreur franche du delta + IC 95 %, et un CSV des désaccords.

- [ ] **Step 8: Commit de l'artefact**

```bash
cd D:/Dev/Caro
git add taxonomie/competences_canoniques.csv taxonomie/domaines.csv taxonomie/mapping_blocs.csv
git commit -F <message>
```
Message (français) : décrit la passe, les compteurs (rescues/nouvelles/déplacements), la couverture avant/après, le taux certifié du delta. **Ne pas committer** `meta.json` encore (Task 7).

---

## Task 7: meta.json, régénération IHM, republication

**Files:**
- Modify: `taxonomie/meta.json`
- Regenerate: `ihm/index.html` (gitignoré)
- Update: branche `gh-pages`

- [ ] **Step 1: Mettre à jour `meta.json`**

Incrémenter `version`, `date` = 2026-07-09, ajouter sous `curation` une entrée `passe_non_classe` : périmètre (544 libellés), modèles (Sonnet juge/synthèse/balayage, Opus certif), compteurs (inclassable / rescue vers existante / nouvelles compétences approuvées / déplacements), et sous `certification` un bloc `delta` avec le taux + IC. Mettre à jour `couverture` (nouveaux %). Vérifier que `build_db.py` relit `meta.json` sans erreur (rebuild déjà fait en Task 6 ; un `json.loads` de contrôle suffit).

- [ ] **Step 2: Régénérer l'IHM**

```bash
python build_ihm.py 2>&1 | tail -3
```
Expected : `ihm/index.html` régénéré (~15,5 Mo), couverture reflétant la baisse de non_classé.

- [ ] **Step 3: Commit de meta.json**

```bash
git add taxonomie/meta.json
git commit -m "Documente la passe non_classe dans meta.json (couverture, delta certifie)"
```

- [ ] **Step 4: Republier gh-pages**

Rejouer la procédure de la session précédente (branche orpheline, plumbing `hash-object`/`mktree`/`commit-tree`, `git push -f origin gh-pages`), puis vérifier le déploiement (`gh api .../pages/builds/latest`, `curl -sI`).

---

## Self-Review

**Couverture du spec :**

| Exigence spec | Task |
|---|---|
| D1 croissance bornée + validation | T3 (candidates), T4 (gate), T6 (ajout au menu) |
| D2 non_classé + balayage ciblé | T5 (balayage), T6 (rescue) |
| D3 certification du delta (Opus) | T6 step 7 |
| D4 fan-out par libellé + synthèse | T2, T3 |
| D5 base = artefact committé | T1, T6 (lib_comp depuis mapping_blocs.csv) |
| Phase 1 extraction + menu.txt | T1 |
| Phase 2 jugement 3 voies + repêchage | T2 |
| Phase 3 synthèse + liste libs sources | T3 |
| Phase 4 gate CSV bloquant | T4 |
| Phase 5 rescue + balayage | T5, T6 |
| Phase 6 reconstruction + certif | T6 |
| Phase 7 meta + IHM + gh-pages | T7 |
| Erreurs : refuse si verdict manquant / cid inconnu | T2 step 3, T6 (ErreurCuration) |
| Erreurs : gate refuse si CSV incomplet | T4 |
| Tests du script d'application | T6 steps 1-4 |
| Suite existante verte, 0 orphelin | T6 step 6 |
| Committé = taxonomie/ seul | T6 step 8, T7 |
| build_db/build_ihm intouchés | (aucune task ne les modifie) |

**Écart assumé, signalé :** ce plan s'exécute **inline** (contrôleur), pas en subagent-driven — les Workflows LLM et le gate humain ne se délèguent pas à un implémenteur. Seuls T1 et T6 (scripts stdlib) suivent le cycle TDD complet ; les autres tasks sont des étapes opératoires avec critères de vérification (couverture, gate, delta certifié).

**Chemins Workflow :** `synthese.js` lit `menu.txt` dans `juge/` — le prompt doit pointer `dir + '/juge/menu.txt'` (noté en T3 step 2). Vérifié cohérent.

**Déterminisme :** l'ordre des libellés (`population.json`, tri par libellé en T1) et la rejointure par `bloc_code` (ordre de la base) fixent un résultat reproductible ; testé en T6.
