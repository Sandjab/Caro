# Combler les blocs non_classé de la taxonomie

**Date** : 2026-07-09
**Statut** : design validé, en attente du plan d'implémentation

## Objectif

Réduire les blocs `non_classé` de la taxonomie de compétences en distinguant, sur
les **544 libellés distincts** aujourd'hui sans compétence canonique, ce qui est
réellement inclassable de ce qui révèle une **lacune du menu** des 227
compétences. Rattacher ce qui peut l'être — soit à une compétence existante
manquée, soit à une **nouvelle compétence** créée pour combler la lacune —
sous validation humaine, puis certifier la qualité du changement.

## Contexte mesuré

Sur `rncp.sqlite3` (fiches actives, 2026-07-09) :

| Fait | Valeur |
|---|---|
| Blocs rattachés (`ia`) | 27 237 |
| Repli lexical (`lexical`) | 79 |
| **Blocs `non_classé`** | **973** (3,4 %) |
| dont libellés **distincts** | **544** |
| Compétences canoniques utilisées | 226 / 227 |
| Exigences par certification (médiane) | 4 |

Deux familles ressortent d'une analyse lexicale des 544 libellés :

- **Cluster « enseignement / sciences humaines »** : *histoire* (19), *théologie*
  (15), *géographie* (13), *moral/civique* (13), *français* (12), *enseignement*
  (13). Probable lacune du menu (ou rattachement manqué au domaine
  `enseignement_general` existant).
- **Cluster « verbes creux »** : *réaliser, assurer, développer, concevoir* +
  *optionnel* (18). Libellés trop vagues — probablement de vrais inclassables.

Cette dichotomie est exactement ce que la passe doit trancher, libellé par
libellé.

## Décisions

### D1 — Croissance bornée du menu, sous validation humaine

Le menu des 227 compétences peut croître, mais de façon **maîtrisée** (~235-245
attendu) : rattachement aux compétences existantes là où un rattachement a été
manqué, **plus** un petit lot curé de compétences clairement absentes. **Chaque
nouvelle compétence est approuvée par l'utilisateur** avant d'entrer dans
l'artefact. Le résiduel vraiment inclassable garde son statut `non_classé`,
assumé.

**Écarté** : croissance pilotée par les données sans plafond (risque de
fragmenter le vocabulaire, compétences à 2-3 certifications) ; aucune nouvelle
compétence (laisse les vraies lacunes ouvertes).

### D2 — Re-mapping = non_classé + balayage ciblé des nouvelles

On re-mappe les blocs `non_classé` contre le menu étendu. Et pour **chaque
nouvelle compétence approuvée**, on balaie les blocs **déjà rattachés** dont le
libellé la recoupe lexicalement, et un juge tranche : la nouvelle compétence
est-elle un meilleur foyer que le rattachement actuel ? Si oui, on déplace.

**Écarté** : re-mapper seulement les `non_classé` (laisse un bloc « histoire »
déjà coincé dans une compétence générique là où il est) ; re-mapping complet des
19 400 libellés (~12M tokens pour un menu qui n'a changé qu'à la marge —
disproportionné).

### D3 — Certification du delta par juge indépendant

Le `delta` — l'ensemble des blocs dont le rattachement a changé (rescues +
déplacements du balayage) — est échantillonné de façon stratifiée (~300) et jugé
par **Opus** en posture de réfutation, comme la certification d'origine. On
obtient un taux d'erreur du delta + IC 95 %, comparable au 1,0 % global.

**Écarté** : validation humaine sans juge (la promesse « certifié » ne couvrirait
plus le delta) ; re-certifier l'ensemble du mapping (redondant sur les 96 %
inchangés).

### D4 — Méthode : fan-out LLM par libellé + synthèse (approche A)

Chaque libellé `non_classé` est jugé par un agent qui tranche en trois
(inclassable / existante / nouvelle) ; une passe de synthèse regroupe les
brouillons « nouvelle » en candidates dédoublonnées. Le clustering **émerge** de
la synthèse plutôt que d'être imposé en amont.

**Écarté** : clustering lexical d'abord (les verbes creux dominants produiraient
des clusters bruités — le biais lexical que tout le projet a combattu) ;
embeddings (hors périmètre stdlib, imposerait de construire une infra que la
décision « pas de reproductibilité » a écartée).

### D5 — Base de vérité : l'artefact committé

La passe bâtit sur `taxonomie/mapping_blocs.csv` + `rncp.sqlite3`, jamais sur les
scratchpads d'anciennes sessions. Elle est ainsi reproductible depuis le dépôt
seul.

## Architecture et périmètre

Travail de **curation de taxonomie** : occasionnel, LLM, validation humaine —
dans le « hors périmètre stdlib » que `CLAUDE.md` distingue du pipeline.

- **Committé** : `taxonomie/competences_canoniques.csv` (menu étendu),
  `taxonomie/domaines.csv` (si un domaine nouveau est requis),
  `taxonomie/mapping_blocs.csv` (rattachements mis à jour), `taxonomie/meta.json`.
- **Scratchpad (jetable)** : tous les scripts de préparation, d'application
  déterministe et de calcul — comme `apply3.py`, `prep_judge.py` l'étaient.
- **Intouchés** : `build_db.py` (stdlib, lit l'artefact) et `build_ihm.py`
  (régénère la page). Aucune modification de code du pipeline.

Unité de jugement : le **libellé distinct**. La décision se propage à tous les
`bloc_code` qui partagent ce libellé, via une rejointure sur la base — même
principe que les passes 1 à 3.

## Les sept phases

### Phase 1 — Extraction (stdlib)

Depuis la base : les 544 libellés `non_classé` distincts, chacun avec 1-2
`bloc_code` d'exemple, le domaine NSF de la certification porteuse (indice de
contexte), et le nombre de certifications concernées. Découpage en lots JSON pour
le juge. Génération de `menu.txt` (227 compétences + 35 domaines) **depuis
l'artefact committé**.

### Phase 2 — Jugement par libellé (LLM, fan-out)

Un agent par lot. Verdict par libellé :

```json
{"lib": "<libellé>", "v": "inclassable" | "existante" | "nouvelle",
 "cid": "<competence_id si existante>",
 "brouillon": {"libelle": "...", "domaine": "<domaine_id existant | nouveau:...>",
               "pourquoi": "..."}}
```

Le prompt insiste sur le **sens métier**, pas le recouvrement de mots (biais
mesuré comme non prédictif). Repêchage incrémental des lots dont le JSON est
tronqué (motif éprouvé aux passes précédentes).

### Phase 3 — Synthèse des candidates (LLM)

Un ou deux agents regroupent tous les brouillons `nouvelle`, fusionnent les
doublons sémantiques, et produisent une liste courte. Chaque candidate :
`competence_id` proposé (convention du dépôt : préfixe court de domaine + `_` +
slug, ex. `eg_histoire_geo`), `libelle`, `domaine_id`, `mots_cles`, et **la liste
explicite des libellés `non_classé` qui la réclament** (pas seulement leur
nombre). Cette liste est le lien qui permettra, après approbation, de rattacher
ces libellés à la compétence — la fusion de doublons est donc tracée jusqu'aux
libellés sources.

### Phase 4 — Validation humaine (gate bloquant)

Sortie : `candidates_a_valider.csv`, une ligne par candidate, colonne `decision`
vide. L'utilisateur inscrit `oui`/`non`, édite `libelle`/`domaine_id`/`mots_cles`
si besoin, peut renommer le `competence_id`. **Aucune phase suivante ne démarre
sans ce fichier renseigné.** Les candidates `oui` sont ajoutées à
`competences_canoniques.csv` (et un domaine nouveau, si approuvé, à
`domaines.csv` avec son `ordre`).

### Phase 5 — Re-mapping (LLM ciblé + déterministe)

- **Rescue** : chaque libellé `non_classé` jugé `existante:X` (avec X valide) est
  rattaché à X. Chaque libellé figurant dans la liste des libellés sources d'une
  candidate **approuvée** est rattaché au `competence_id` de cette candidate — tel
  qu'il figure dans le CSV validé, donc en suivant un éventuel renommage par
  l'utilisateur (le lien est l'identité de ligne de la candidate, pas le
  `competence_id` proposé en phase 3). Les `inclassable`, et les libellés dont la
  seule candidate a été refusée, restent `non_classé`.
- **Balayage ciblé** : pour chaque nouvelle compétence approuvée, sélection des
  libellés déjà mappés dont les tokens la recoupent (seuil stdlib), puis un juge
  tranche `garder` / `déplacer vers la nouvelle`. Repêchage incrémental.

### Phase 6 — Reconstruction + certification du delta

- Reconstruction déterministe de `mapping_blocs.csv` :
  `mapping committé + rescues + déplacements`, rejointure sur `bloc_code`.
- Rebuild `rncp.sqlite3`, vérification : couverture (`ia`/`lexical`/`non_classe`),
  **zéro `competence_id` orphelin**, la vue `certification_competence` tient.
- `delta` = blocs dont le `competence_id` diffère de l'artefact committé. Cela
  inclut les blocs **nouvellement rescapés** (absents du mapping committé car
  `non_classé`, désormais rattachés) autant que les blocs **déplacés** par le
  balayage. Échantillon stratifié par domaine (~300), juge Opus indépendant,
  verdict `ok`/`doute`/`faux`. Estimateur stratifié repondéré + IC 95 % de Wald.

### Phase 7 — Mise à jour finale

`meta.json` : nouvelle version, provenance de la passe (compteurs : inclassable /
rescue vers existante / nouvelles compétences / déplacements du balayage), taux
d'erreur certifié du delta. Régénération de `ihm/index.html`. Republication
`gh-pages` (branche orpheline, `git push -f`).

## Artefacts et flux de données

```
Phase 1  base → libellés non_classé (lots) + menu.txt
Phase 2  lots + menu.txt → verdicts/*.json                 [LLM]
Phase 3  verdicts → candidates_a_valider.csv               [LLM]
Phase 4  candidates_a_valider.csv → (édité par l'humain)   [GATE]
         → competences_canoniques.csv (+ domaines.csv)     [committé]
Phase 5  verdicts + candidates approuvées → rescues        [déterministe]
         balayage : blocs mappés proches → déplacements     [LLM]
Phase 6  committé + rescues + déplacements → mapping_blocs.csv [committé]
         → rebuild base → delta → certif Opus → taux         [LLM + stdlib]
Phase 7  meta.json [committé] → ihm/index.html → gh-pages
```

Les fichiers intermédiaires (lots, verdicts, décisions) vivent dans le
scratchpad. Seuls les quatre fichiers de `taxonomie/` sont committés.

## Gestion des erreurs

Principe repris du projet : **échouer/refuser plutôt que produire un artefact
faux en silence.**

- **Agents qui tronquent leur JSON** : repêchage incrémental jusqu'à couverture
  100 % des libellés, sans écraser les verdicts déjà obtenus (motif des
  `prep_rescue*.py`).
- **Script d'application déterministe** : refuse d'écrire `mapping_blocs.csv` si
  un libellé attendu manque de verdict, ou si un `competence_id` cité (rescue,
  balayage, ou candidate approuvée) n'existe pas dans le
  `competences_canoniques.csv` final. Symétrique du garde-fou `domaine_id` de
  `build_ihm.py`.
- **Nouvelles compétences** : `competence_id` unique (collision avec les 227
  existants → arrêt), `domaine_id` référençant un domaine existant ou approuvé
  (sinon arrêt).
- **Gate humain** : l'application refuse de démarrer si
  `candidates_a_valider.csv` n'est pas renseigné (colonne `decision` non vide sur
  toutes les lignes).
- **Reproductibilité** : rejeu depuis `mapping_blocs.csv` committé + fichiers de
  décision → résultat identique.

## Tests

Les phases LLM ne sont pas testées unitairement ; leur qualité est établie par le
gate humain (phase 4) et la certification (phase 6).

Le **script d'application déterministe** (stdlib) est testé sur fixtures
synthétiques, dans l'esprit de `tests/` :

- un libellé `non_classé` jugé `existante:X` est rattaché à X ;
- un libellé rattaché à une candidate approuvée est mappé ; à une candidate
  refusée, reste `non_classé` ;
- un `inclassable` reste `non_classé` ;
- un déplacement du balayage change le `competence_id` d'un bloc déjà mappé ;
- un `competence_id` inconnu (rescue ou candidate) fait **lever**, pas produire ;
- une nouvelle compétence dupliquant un `competence_id` existant fait lever ;
- rejeu déterministe : deux exécutions → mapping identique.

Après reconstruction, la **suite existante** (`python -m unittest discover -s
tests`) doit rester verte : `build_db.py` lit l'artefact, sa logique ne change
pas. Zéro `competence_id` orphelin en base.

## Limites connues

- La passe ne rouvre **pas** les rattachements qui pointent déjà vers une
  compétence **existante** (hors balayage des nouvelles) : un bloc mal rangé dans
  une compétence existante que seule une **autre existante** corrigerait n'est pas
  revu. C'est le re-mapping complet, écarté (D2).
- La certification mesure le **delta**, pas le taux global : après cette passe, le
  1,0 % global d'origine reste la référence sur les 96 % inchangés, et le taux du
  delta s'y ajoute pour la partie modifiée.
- Le résiduel `inclassable` est **assumé** : certains blocs (« Réaliser… »,
  « bloc optionnel ») n'ont pas de sens métier rattachable, et les forcer
  reproduirait l'erreur de classement forcé que le projet a documentée.
- La qualité des nouvelles compétences dépend du jugement LLM + de la curation
  humaine ; le menu n'est pas garanti exhaustif ni orthogonal.
