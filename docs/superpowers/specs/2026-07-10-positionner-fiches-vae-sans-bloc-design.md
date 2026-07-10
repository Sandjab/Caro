# Positionner les fiches VAE sans bloc — Design

> Rattacher à l'arbre de compétences les 405 certifications accessibles par VAE
> qui restent « non positionnables » aujourd'hui, en extrayant des compétences
> canoniques de leur **texte libre** — puisqu'elles n'ont aucun bloc de
> compétences dans la source.

**Date :** 2026-07-10
**Statut :** validé, prêt pour le plan d'implémentation

## Problème

Sur les **5 582 fiches accessibles par VAE**, **5 177 sont positionnées** dans
l'arbre de compétences et **405 ne le sont pas**. Décomposition des 405 :

| Cause | Nombre | Détail |
|---|---|---|
| Aucun bloc de compétences dans la source | **396** | 196 RS + 200 RNCP |
| Des blocs, mais tous restés `non_classé` | 9 | résidu de la passe précédente |

Le positionnement repose sur `taxonomie/mapping_blocs.csv`, keyé par `bloc_code`
(donc une ligne par (fiche, bloc)). La vue `certification_competence` joint
`bloc_competences_xml → bloc_competence_canonique → competence_canonique`.
**Pas de bloc → rien à quoi rattacher.**

Vérifications factuelles menées :

- Les 396 fiches n'ont **aucun bloc ni dans l'export XML ni dans l'export CSV**
  (`blocs_de_competences`) : France compétences n'en publie pas. Ce n'est pas un
  défaut de parsing — la piste « récupérer des blocs manquants » est un cul-de-sac.
- Les 396 ont **toutes** un `capacités attestées` ET un `activités visées` non
  vides. Le contenu existe ; il n'est simplement pas découpé en blocs.
- Population : Jeunesse-Sport, STAPS (« fiche nationale »), sécurité/protection
  rapprochée, habilitations RS mono-objet. Répartition
  `type_enregistrement` : 170 « de droit », 226 « sur demande ».

Le **seul matériau** pour positionner ces fiches est donc leur texte libre.

## Décisions

1. **Objectif** : les positionner vraiment (extraire des compétences du texte
   libre), pas seulement améliorer leur consultabilité.
2. **Taxonomie** : rattacher aux **264 compétences existantes d'abord** ; créer
   une nouvelle compétence **uniquement sous gate humain** quand rien ne convient
   — exactement le protocole de la passe `non_classé`.
3. **Mécanisme** : **mapping par fiche** (approche A). Rejeté : pseudo-blocs
   synthétiques (invente de la donnée absente de la source, pollue les tables
   sources) ; décomposition en capacités (étape LLM floue, surdimensionnée pour
   405 fiches).

## Architecture

Séparation stricte préservée : l'**outil de curation** (occasionnel, LLM,
gitignoré sous `data/curation/`) produit un artefact versionné ; **`build_db.py`**
(stdlib, déterministe) se contente de le lire. Dégradation gracieuse si l'artefact
est absent, comme pour FTS5 et la taxonomie.

### Nouvel artefact — `taxonomie/mapping_fiches.csv`

```
numero_fiche;competence_id;methode
RNCP35901;an_animation_sportive;ia
RNCP35901;t_responsabilite;ia
RS1234;se_protection_surete;ia
```

Même grain que `mapping_blocs.csv`, keyé sur `numero_fiche`. `methode` = `ia`
(rattachement proposé par l'IA) ou `humain` (saisi au gate).

Le chemin fiche est **LLM-only, sans repli lexical stdlib** — assumé (405 fiches,
pas 19 400 blocs). Artefact absent → ces fiches restent simplement non
positionnables, sans jamais faire échouer le build.

## Côté pipeline — `build_db.py` (stdlib, déterministe)

Changements bornés et testables :

1. `charger_taxonomie()` : `mapping_fiches.csv` devient un **4ᵉ fichier
   optionnel**. Absent → dégradation gracieuse (les autres artefacts restent
   requis, inchangé).
2. Nouvelle table `fiche_competence_canonique (numero_fiche, competence_id,
   methode)`. Chaque `competence_id` **doit exister** dans `competence_canonique`
   — sinon refus, comme le contrôle d'orphelins existant sur `bloc_competence_canonique`.
3. La vue `certification_competence` devient une **UNION** :

   ```sql
   CREATE VIEW certification_competence AS
   -- chemin blocs (inchangé)
   SELECT DISTINCT b.numero_fiche, m.competence_id, cc.domaine_id
     FROM bloc_competences_xml b
     JOIN bloc_competence_canonique m ON m.bloc_code = b.bloc_code
     JOIN competence_canonique cc ON cc.competence_id = m.competence_id
   UNION
   -- chemin fiche (nouveau)
   SELECT DISTINCT f.numero_fiche, f.competence_id, cc.domaine_id
     FROM fiche_competence_canonique f
     JOIN competence_canonique cc ON cc.competence_id = f.competence_id;
   ```

   Le `UNION` (et non `UNION ALL`) dédoublonne : une fiche mappée à la fois par
   bloc et par fiche vers la même compétence n'apparaît pas deux fois.
4. Index sur `fiche_competence_canonique (numero_fiche)` et `(competence_id)`.
5. Compteurs dans `meta` : `nb_fiches_rattachees`, delta de couverture VAE.

**Effet automatique** : `build_ihm.py` ne change pas. Les fiches désormais dotées
de compétences dans la vue basculent de `sans_comp` vers `certifs` et
apparaissent dans l'arbre ; la liste « non positionnables » fond mécaniquement.

## Côté outil — passe de curation LLM (occasionnelle, gitignorée)

Décalque la passe `non_classé` (mêmes garde-fous), mais opère **par fiche**. Tout
sous `data/curation/fiches/`. Seule sortie versionnée : `mapping_fiches.csv`
(+ éventuels ajouts validés à `competences_canoniques.csv` / `domaines.csv`).

**Sélection** : critère « non positionnable » indépendamment de la cause → les
**405** ensemble (`fiches VAE absentes de certification_competence`).

**Matériau par fiche** donné à l'IA : intitulé + `capacités attestées` +
`activités visées` + `objectifs/contexte` + groupe NSF.

| Phase | Script | Rôle |
|---|---|---|
| 1. Extraction (stdlib) | `prep_fiches.py` | 405 fiches + textes, `menu.txt` (264 compétences : id · libellé · domaine · mots-clés), découpage en lots. |
| 2. Classification (Workflow, fan-out) | `classe_fiches.js` | Par fiche : ensemble de `competence_id` du menu (multi-compétences, grain ~4), ou « besoin nouvelle compétence » (libellé/domaine) **si rien ne convient**. Prompt à biais *existantes d'abord* + *précision* (ne retenir que le clairement attesté). |
| 3. Assemblage (stdlib) | `assemble_fiches.py` | Collationne → mapping brut + liste des besoins de nouvelles compétences ; couverture intermédiaire. |
| 4. Consolidation + **GATE HUMAIN** | `consolidation.js` → `candidates_a_valider.csv` | Dédoublonne les nouvelles compétences ; colonne `decision` oui/non (+ domaine). `valider_gate.py` refuse un CSV incomplet. **L'humain tranche.** |
| 5. Apply (stdlib, déterministe) | `apply_fiches.py` (+ `test_apply_fiches.py`) | Reconstruit `mapping_fiches.csv`, ajoute les compétences validées, ré-affecte aux fiches demandeuses. **Refuse si incohérent** (id inconnu, fiche hors périmètre). Source de vérité = artefact committé. |
| 6. Certification (Opus) | `prep_certif.py` + `certif.js` + `certif_rate.py` | Échantillonne, juge Opus indépendant (juste/faux/doute fiche↔compétences), taux d'erreur + IC 95 %. Alimente `meta.json` (`curation.passe_fiches`). |

Chaque phase LLM a son repêchage incrémental (`prep_rescue*.py`) pour les JSON
tronqués, comme `non_classé`.

## Périmètre

**Dans le périmètre :** les 405 fiches ; `mapping_fiches.csv` + ajouts validés ;
les changements `build_db.py` ci-dessus ; les tests `tests/`.

**Hors périmètre (YAGNI) :** affiner le grain des compétences existantes (vœu
connu, écarté) ; retravailler `com_techniques_editoriales` (dette du handoff,
sujet séparé) ; toute passe LLM sur les blocs déjà mappés.

## Tests (fixtures synthétiques, hors ligne)

Le chemin fiche doit être couvert au niveau du chemin bloc :

- `charger_taxonomie` : `mapping_fiches.csv` présent / absent / avec
  `competence_id` orphelin (doit refuser).
- `fiche_competence_canonique` peuplée ; vue `certification_competence` = UNION
  correcte : une fiche sans bloc mais mappée apparaît ; une fiche mappée par bloc
  **et** par fiche vers la même compétence n'est pas dupliquée.
- End-to-end hors ligne : mini-`taxonomie/` avec `mapping_fiches.csv` → base → la
  fiche sans bloc a bien ses compétences.
- `build_ihm` : une fiche VAE mappée par fiche passe de `sans_comp` à `certifs`.
- `test_apply_fiches.py` : reconstruction déterministe, refus si incohérent.

## Critères de succès

1. Les 405 (moins un résiduel assumé) passent de « non positionnables » à
   « positionnées » dans l'IHM régénérée.
2. Delta certifié par juge Opus à un taux d'erreur comparable aux passes
   précédentes (ordre de 1 %, IC 95 %), consigné dans `meta.json`.
3. Suite de tests verte ; build sans `mapping_fiches.csv` = dégradation gracieuse
   (aucune régression sur le chemin bloc existant).
4. Handoff `handoff/2026-07-10-passe-fiches.md` décrivant la recette, comme pour
   `non_classé`.

## Références

- Passe analogue (par bloc) : `handoff/2026-07-10-passe-non-classe.md`,
  `docs/superpowers/specs/2026-07-09-taxonomie-combler-non-classe-design.md`
- Provenance taxonomie : `taxonomie/meta.json`
- Vue et chargement actuels : `build_db.py`
  (`creer_vue_certification_competence`, `charger_taxonomie`,
  `construire_taxonomie`)
- Consommateur : `build_ihm.py` (`construire_index`, tri `certifs`/`sans_comp`)
