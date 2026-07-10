# Handoff — passe « combler les non_classé » (2026-07-10)

> État de la taxonomie après la passe qui a rattaché les blocs restés sans
> compétence canonique. Pour qui reprend le sujet — humain ou agent.

## Ce qui a été fait

Sur les **544 libellés de blocs distincts** restés `non_classé` (3,4 % des blocs),
une passe de curation LLM a tranché libellé par libellé, puis créé les
compétences manquantes sous validation humaine.

| | Avant | Après |
|---|---|---|
| Couverture `ia` | 96,3 % | **99,3 %** |
| Blocs `non_classé` | 973 (3,4 %) | **148 (0,5 %)** |
| Compétences (`competences_canoniques.csv`) | 227 | **264** |
| Domaines (`domaines.csv`) | 35 | **40** |

**5 domaines nouveaux** : `theologie_sciences_religieuses`, `marine_maritime`,
`sciences_politiques_relations_internationales`, `psychologie`, `horlogerie`.

Le delta (658 rattachements changés) est **certifié par juge Opus indépendant** :
**0,6 % d'erreur franche** (IC 95 % ± 0,8), 7,1 % faux+doute. Détail dans
`taxonomie/meta.json` (version 4, bloc `curation.passe_non_classe` +
`certification.delta_non_classe`).

Mergé dans `main` par la **PR #2**. IHM régénérée et republiée sur
`https://sandjab.github.io/Caro/`.

## Point faible connu — à corriger en priorité si on y revient

**`com_techniques_editoriales`** (domaine `communication_media`) est un
**fourre-tout trop large**. Les 2 seuls `faux` de l'échantillon de certification
en viennent (« SAV audiovisuel » et « diagnostics immobiliers » y ont atterri à
tort). Le domaine Communication ressort à 50 % de faux+doute (n=8). Piste :
scinder cette compétence, ou renvoyer ses blocs douteux vers un meilleur foyer.

Le CSV des désaccords Opus est dans `data/curation/certif_nonclasse_desaccords.csv`
(gitignoré).

## Où vivent les scripts (rien n'est committé)

Tout dans **`data/curation/nonclasse/`** (gitignoré via `data/`). Le pipeline,
dans l'ordre — c'est la recette pour refaire une passe équivalente sur un export
futur (il n'existe pas de `build_taxonomie.py` : cette passe est la référence) :

| Script | Rôle |
|---|---|
| `prep_juge.py` | extrait les libellés non_classé + `menu.txt` + lots |
| `juge.js` (Workflow Sonnet) | inclassable / existante / nouvelle |
| `assemble_verdicts.py` | collationne, couverture, `brouillons.json` |
| `prep_synthese.py` + `synthese.js` | brouillons → candidates (par lot) |
| `assemble_candidates.py` | 195 candidates brutes |
| `consolidation.js` + `assemble_consolidation.py` | fusion des doublons → **38** |
| `candidates_a_valider.csv` | **GATE HUMAIN** : colonne `decision` oui/non |
| `valider_gate.py` | refuse un CSV incomplet |
| `prep_balayage.py` + `balayage.js` | blocs déjà mappés proches des nouvelles |
| `assemble_balayage.py` | → `deplacements.json` (219 déplacements) |
| `apply_nonclasse.py` (+ `test_apply_nonclasse.py`) | **reconstruit l'artefact**, déterministe, refuse si incohérent |
| `prep_certif.py` + `certif.js` (Opus) + `certif_rate.py` | certification du delta |

Chaque phase LLM a son repêchage incrémental (`prep_rescue*.py`) : les agents
tronquent parfois leur JSON, on relance sans écraser l'acquis.

**Reproduire** : régénérer `rncp.sqlite3` (`build_db.py`), puis dérouler les
scripts ci-dessus. `apply_nonclasse.py` part de l'artefact committé (source de
vérité) ; réinitialiser d'abord avec `git checkout -- taxonomie/` pour une base
propre avant de ré-appliquer.

## Ce qui reste ouvert

- **Résiduel `non_classé`** : 148 blocs (0,5 %) restent inclassables ou non
  couverts — assumé (libellés génériques type « Réaliser des opérations »).
- **Le juge sur-crée** : Sonnet a proposé 344 « nouvelle » contre 102
  rattachements à l'existant. La synthèse + consolidation + le gate humain
  rattrapent, mais un juge plus conservateur réduirait le bruit en amont.
- **Grain toujours grossier** : 264 compétences pour ~19 400 libellés ; le taux
  de couverture de l'IHM reste un signal grossier (médiane 4 exigences/certif).
  C'est le volet « affiner le grain » écarté au design de cette passe.
- **Vérification navigateur de l'IHM** (surlignage `<mark>`, etc.) toujours à la
  main de l'humain — aucun agent n'a de navigateur.

## Fichiers de référence

- Spec : `docs/superpowers/specs/2026-07-09-taxonomie-combler-non-classe-design.md`
- Plan : `docs/superpowers/plans/2026-07-09-taxonomie-combler-non-classe.md`
- Provenance : `taxonomie/meta.json`
