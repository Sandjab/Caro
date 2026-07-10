# Handoff — passe « positionner les fiches VAE sans bloc » (2026-07-10)

> État après la passe qui rattache à l'arbre de compétences les certifications
> accessibles par VAE qui n'avaient aucune compétence. Pour qui reprend le sujet
> — humain ou agent.

## Ce qui a été fait

**405 certifications VAE non positionnables → 0.** Ces fiches (396 sans aucun
bloc de compétences dans la source XML *et* CSV — France compétences n'en publie
pas —, plus 9 dont tous les blocs étaient `non_classé`) ne pouvaient pas passer
par `mapping_blocs` (pas de bloc à rattacher). Elles sont désormais classées
**par leur texte libre** (`capacités attestées` + `activités visées`) contre le
menu des compétences canoniques.

| | Avant | Après |
|---|---|---|
| VAE non positionnables | **405** | **0** |
| Compétences canoniques | 264 | **295** (+31) |
| Domaines | 40 | 40 (0 nouveau) |
| Rattachements « par fiche » | 0 | **756** |

**Certifié 1,0 % de faux** (IC 95 % Wilson [0,3 ; 2,9], n=299) par juge Opus
indépendant — au niveau des passes par bloc. Détail dans `taxonomie/meta.json`
(version 5, `curation.passe_fiches` + `certification.delta_fiches`).

## Mécanisme (code du pipeline, committé — Partie A, PR #3 mergée)

Nouvel artefact versionné **`taxonomie/mapping_fiches.csv`**
(`numero_fiche;competence_id;methode`), keyé par fiche. `build_db.py` le lit
(optionnel, dégradation gracieuse) dans une table `fiche_competence_canonique` ;
la vue `certification_competence` devient une **UNION** du chemin blocs (inchangé)
et de ce chemin fiche. `build_ihm.py` est inchangé : les fiches dotées de
compétences basculent d'elles-mêmes de `sans_comp` vers `certifs`.

## Itération sur la précision — à connaître

Une **première passe** classait plus large (1044 rattachements) et certifiait
**4,7 % de faux** : sur-attribution du contexte sectoriel (« métier du paysage »
→ `an_paysage` sur de la maçonnerie) et des compétences **transversales
génériques** (`t_communiquer`, `gm_decision`…). Le **prompt de classification a
été durci** (le contexte n'est pas une compétence ; une transversale seulement si
centrale et explicite ; distinguer les compétences adjacentes — naviguer ≠
entretenir les machines, surveiller ≠ maintenir ; retirer au moindre doute), ce
qui a ramené le taux à **1,0 %** et allégé le delta (756 rattachements). Le doute
résiduel (14,7 % faux+doute) reste concentré sur les compétences génériques.

## Où vivent les scripts (rien n'est committé)

Tout sous **`data/curation/fiches/`** (gitignoré via `data/`). Chaînage complet,
tous testés hors ligne (`python -m unittest discover` dans ce dossier) :

| Script | Rôle | Type |
|---|---|---|
| `prep_fiches.py` | extrait les 405 fiches + textes, `menu.txt`, lots | stdlib |
| `classe_fiches.js` | classification (1 agent Sonnet/lot) → `verdicts/lot_XX.json` | Workflow |
| `assemble_fiches.py` | collationne → `mapping_brut.json` + `besoins_nouvelles.json` ; signale les lots à rescuer | stdlib |
| `consolidation.js` | regroupe les besoins en `candidates.json` (1 agent Sonnet) | Workflow |
| `valider_gate.py preparer` | `candidates.json` → `candidates_a_valider.csv` (colonne `decision`) | stdlib |
| — | **GATE HUMAIN** : remplir `decision` oui/non | — |
| `valider_gate.py appliquer` | gate décidé → `verdicts.json` (refuse si incomplet) | stdlib |
| `apply_fiches.py` | reconstruit l'artefact `taxonomie/` (refuse si incohérent) | stdlib |
| `prep_certif.py` | échantillon déterministe du delta + lots | stdlib |
| `certif.js` | juge Opus indépendant (1 agent/lot) → verdicts | Workflow |
| `certif_rate.py` | taux de faux + IC de Wilson + ventilation par domaine | stdlib |

**Piège `args` des Workflows** : `args` peut arriver en chaîne JSON ; les trois
`.js` la parsent défensivement (sinon `args.lots` = undefined → tous les lots
tournent). Ne pas retirer ce garde-fou.

**Reproduire** : régénérer `rncp.sqlite3` (`build_db.py`), puis dérouler les
scripts ci-dessus. `apply_fiches.py` part de l'artefact committé (source de
vérité) ; **réinitialiser d'abord `git checkout -- taxonomie/` et supprimer
`taxonomie/mapping_fiches.csv`** avant de ré-appliquer (sinon collision d'ids).

## Ce qui reste ouvert

- **Grain / précision des génériques** : le doute résiduel vient des compétences
  transversales et de gestion, évoquées mais pas nettement établies par les
  capacités attestées. Un menu de transversales plus discriminant les
  réduirait.
- **1 rattachement non jugé** sur les 300 de la certification (négligeable, taux
  calculé sur 299).
- **Vérification navigateur de l'IHM** après régénération (surlignage, cartes)
  toujours à la main de l'humain — aucun agent n'a de navigateur.
- Les **8→34 fiches « seulement besoin »** dépendent entièrement d'une des 31
  nouvelles compétences : si l'une était rejetée à un futur gate, ces fiches
  redeviendraient non positionnables.

## Fichiers de référence

- Spec : `docs/superpowers/specs/2026-07-10-positionner-fiches-vae-sans-bloc-design.md`
- Plan : `docs/superpowers/plans/2026-07-10-positionner-fiches-vae-sans-bloc.md`
- Provenance : `taxonomie/meta.json` (blocs `passe_fiches`, `delta_fiches`)
- Passe analogue (par bloc) : `handoff/2026-07-10-passe-non-classe.md`
