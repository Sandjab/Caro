# Taxonomie de compétences canoniques — Design (livrable 1)

**Date :** 2026-07-06
**Statut :** validé (brainstorming), en attente relecture avant plan d'implémentation
**Périmètre :** socle de données uniquement (l'IHM de sélection/classement VAE est un livrable 2 distinct)

## 1. Objectif

Permettre, à terme, à un utilisateur de sélectionner les certifications qu'il peut viser
par **VAE** en rapprochant ses compétences acquises par l'expérience des blocs de
compétences exigés par chaque diplôme.

Ce **livrable 1** construit le **socle de données** nécessaire :

1. une **liste canonique restreinte** de « macro-compétences » (grain **bloc**), dérivée
   des ~19 600 libellés de blocs distincts de la base ;
2. un **regroupement** de ces macro-compétences en **domaines mutuellement exclusifs**
   sur-mesure (~15-25) ;
3. une **correspondance** de chaque bloc réel → sa macro-compétence canonique, et donc,
   par transitivité, de chaque diplôme → l'ensemble des compétences canoniques qu'il couvre.

Le tout **requêtable en SQL** dans `rncp.sqlite3`.

### Hors périmètre (livrable 2)

Saisie du profil utilisateur, moteur de matching profil→certifications, classement des
diplômes éligibles, interface. Le socle est conçu pour les rendre triviaux (cf. vue
`certification_competence`).

## 2. Rappel du domaine

- Un **bloc de compétences** est une subdivision autonome d'une certification, validable
  indépendamment (VAE bloc par bloc depuis la loi « Avenir professionnel » de 2018).
- Chaque `bloc_code` (ex. `RNCP35959BC01`) est **globalement unique** — vérifié sur les
  données : 0 code partagé entre deux fiches. Il n'existe donc **pas** de référentiel
  de blocs réutilisables : les 28 289 blocs actifs sont la somme de ~5 200 certifications
  × ~5,4 blocs. D'où le besoin de **construire** une forme canonique.
- La base contient déjà NSF / ROME / Formacode, mais au niveau **fiche**, pas bloc. On ne
  les réutilise pas ici : les domaines sont **sur-mesure** (choix produit, lisibilité
  grand public).

## 3. Principe d'architecture

Séparer l'étape **intelligente** (occasionnelle, assistée IA, non déterministe) du
**pipeline quotidien** (déterministe, stdlib), reliées par un **artefact versionné**.

```
OUTIL TAXONOMIE · build_taxonomie.py (occasionnel, hors pipeline autonome)
  peut utiliser embeddings + LLM
  blocs réels → embeddings → clustering → LLM (libellé canonique + domaine)
             → curation humaine → ARTEFACT VERSIONNÉ (commité)
                                    taxonomie/domaines.csv
                                    taxonomie/competences_canoniques.csv
                                    taxonomie/mapping_blocs.csv
                          │  (fichiers lus, jamais régénérés par le pipeline)
PIPELINE QUOTIDIEN · build_db.py (100 % stdlib)
  charge l'artefact → tables domaine / competence_canonique
                    → mappe chaque bloc : précalculé (ia) | repli lexical | non_classe
```

**Trois invariants :**

1. `build_db.py` **ne gagne aucune dépendance** : il lit des CSV et applique un mapping.
   Contrainte `CLAUDE.md` (stdlib, autonome, sans réseau) respectée.
2. L'artefact est du **texte versionné** (CSV français, revu à la main) : auditable,
   diff-able, stable même si les données France compétences changent chaque jour.
3. Les **nouveaux blocs quotidiens** ne cassent rien : repli lexical stdlib pour une
   couverture 100 %, marqués « approximatifs » jusqu'à la prochaine passe de l'outil.

Comme la sortie de l'outil est **gelée par la curation**, ni le clustering ni le LLM
n'ont besoin d'être déterministes.

## 4. Modèle de données

Valeurs en français ; clés en slug ASCII (cohérent avec `slugify` existant).

### 4.1 Tables créées par `build_db.py`

**`domaine`** — les ~15-25 domaines sur-mesure

| colonne | type | rôle |
|---|---|---|
| `domaine_id` | TEXT PK | slug, ex. `numerique_data` |
| `libelle` | TEXT | ex. `Numérique & data` |
| `description` | TEXT | une phrase (optionnel) |
| `ordre` | INTEGER | ordre d'affichage |

**`competence_canonique`** — les ~200-400 macro-compétences (grain bloc)

| colonne | type | rôle |
|---|---|---|
| `competence_id` | TEXT PK | slug, ex. `creer_gerer_site_web` |
| `domaine_id` | TEXT FK→domaine | rattachement à **un** domaine (exclusif) |
| `libelle` | TEXT | ex. `Créer et gérer un site web dynamique` |
| `description` | TEXT | phrase d'auto-évaluation (optionnel) |
| `mots_cles` | TEXT | termes/phrases séparés par `\|` — **alimente le repli lexical** |
| `nb_blocs` | INTEGER | nb de blocs réels rattachés (calculé au build, signal qualité) |

**`bloc_competence_canonique`** — un enregistrement par bloc réel

| colonne | type | rôle |
|---|---|---|
| `bloc_code` | TEXT PK | ex. `RNCP35959BC01` |
| `numero_fiche` | TEXT | dénormalisé (index/requêtes) |
| `competence_id` | TEXT FK→competence_canonique, **nullable** | forme canonique |
| `methode` | TEXT | `ia` \| `lexical` \| `non_classe` |
| `score` | REAL | similarité/confiance (optionnel) |

### 4.2 Vue de commodité

**`certification_competence`** — diplôme → compétences canoniques couvertes (base du livrable 2)

```sql
CREATE VIEW certification_competence AS
SELECT DISTINCT b.numero_fiche, m.competence_id, cc.domaine_id
FROM bloc_competences_xml b
JOIN bloc_competence_canonique m ON m.bloc_code = b.bloc_code
JOIN competence_canonique cc     ON cc.competence_id = m.competence_id;
```

### 4.3 Artefact versionné (source de vérité de la taxonomie)

```
taxonomie/
  domaines.csv                → domaine_id ; libelle ; description ; ordre
  competences_canoniques.csv  → competence_id ; domaine_id ; libelle ; description ; mots_cles
  mapping_blocs.csv           → bloc_code ; competence_id ; methode(=ia) ; score
```

CSV délimités `;` (cohérent avec les exports FC), encodage UTF-8.

## 5. Outil taxonomie — `build_taxonomie.py` (occasionnel, hors périmètre stdlib)

L'outil **assiste** ; la **curation humaine fait foi**. Pipeline en 4 étapes :

1. **Définir les domaines (top-down, une fois).** Le LLM propose ~15-25 domaines à partir
   d'un échantillon de libellés ; l'humain édite `domaines.csv`. Structure stable.
2. **Regrouper les blocs.** Extraction des ~19 600 libellés distincts, **enrichis de leurs
   premières compétences** (meilleur signal) ; embeddings ; clustering en ~200-400 groupes
   (agglomératif à seuil, ou k-means sur cible k).
3. **Nommer et ranger (LLM).** Par cluster : `libelle` canonique, rattachement à un domaine
   de l'étape 1, `mots_cles` (pour le repli lexical stdlib).
4. **Curation humaine → artefact.** Revue de `competences_canoniques.csv`
   (fusionner/scinder/renommer/corriger un domaine), puis émission de `mapping_blocs.csv`.
   Commit.

### Choix technique retenu

- **Embeddings : modèle multilingue local** (`sentence-transformers`) — hors-ligne,
  gratuit, rejouable ; fidèle à l'esprit d'autonomie du projet.
- **Nommage/rangement : Claude via API** — peu d'appels (~300), coût négligeable,
  excellente qualité FR.

Coût d'une génération : quelques centimes, quelques minutes. Le cœur embeddings/LLM
**n'est pas testable hors-ligne** dans l'environnement agent (réseau bloqué) ; il est
exécuté sur la machine de l'utilisateur.

### Réglages par défaut (ajustables)

- Taille cible de la liste canonique : **~200-400**.
- Seuil de rattachement lexical : **à calibrer sur les fixtures** (départ conservateur ;
  en dessous → `non_classe` plutôt que rattachement douteux).

## 6. Intégration dans `build_db.py`

Nouvelle **phase** après l'ingestion XML, sur le modèle de FTS (encadrée, dégradation
gracieuse) :

1. **Chargement de l'artefact** `taxonomie/`. Absent → on saute proprement (log) ; la base
   se construit comme avant (**rétro-compatible**).
2. Création/remplissage de `domaine` et `competence_canonique` (+ `nb_blocs`).
3. **Rattachement de chaque bloc** de `bloc_competences_xml` :
   - `bloc_code` présent dans `mapping_blocs.csv` → `methode='ia'` ;
   - sinon **repli lexical stdlib** : tokenisation de `libelle`+compétences du bloc,
     score de recouvrement (Jaccard pondéré) avec les `mots_cles` de chaque canonique,
     meilleur au-dessus du seuil → `methode='lexical'` ;
   - sous le seuil → `competence_id=NULL`, `methode='non_classe'`.
4. Création de la vue `certification_competence` ; index sur `(numero_fiche, competence_id)`.
5. Écriture des stats de couverture dans `meta`.

**Drapeaux CLI ajoutés :** `--taxonomie-dir` (défaut `taxonomie/`), `--no-taxonomie`.
Le filtrage actif étant appliqué en amont, seuls les blocs des fiches actives sont rattachés.

## 7. Provenance & honnêteté du taux de couverture

Ajouts à la table `meta` : `taxonomie_version`, `taxonomie_date`, `taxonomie_modele`,
`nb_domaines`, `nb_competences_canoniques`, et les taux **`blocs_ia_pct`**,
**`blocs_lexical_pct`**, **`blocs_non_classe_pct`**.

Aucun bloc n'est rattaché de force : les `non_classe` sont **comptés et visibles**
(pas de troncature silencieuse — conforme à l'esprit du projet).

## 8. Reproductibilité, robustesse, tests

### Reproductibilité

`build_db.py` reste **déterministe** (mapping figé + heuristique stdlib). Le
non-déterminisme (embeddings/LLM) est **cantonné à l'outil taxonomie**, gelé par la curation.

### Robustesse

- Artefact manquant ou partiel → dégradation gracieuse (comme FTS5).
- `competence_id` d'un mapping pointant sur une canonique inexistante → ignoré + averti.
- Pas de `NOT IN (?,…)` (mêmes contraintes de variables SQLite qu'aujourd'hui ; table
  temporaire si besoin).

### Tests (fixtures synthétiques, mode hors-ligne)

- Mini `taxonomie/` de test : 2 domaines, ~4 canoniques, mapping partiel + `mots_cles`
  choisis ; combiné aux mini zips CSV/XML synthétiques déjà prévus au `CLAUDE.md`.
- Vérifications SQL :
  - `domaine` et `competence_canonique` remplies ; `nb_blocs` cohérent ;
  - un bloc **mappé IA**, un bloc **nouveau rattaché en lexical**, un bloc **`non_classe`**
    sous le seuil ;
  - vue `certification_competence` cohérente (un diplôme → ses compétences) ;
  - stats `meta` de couverture justes (somme des pourcentages = 100).
- Outil taxonomie : tests unitaires du **repli lexical** (déterministe) et du **parsing
  d'artefact**. Le cœur embeddings/LLM est documenté comme non testable hors-ligne.

## 9. Décisions actées (brainstorming)

| Décision | Choix |
|---|---|
| Grain de la liste canonique | **Bloc** (macro-compétence), pas la compétence élémentaire |
| Source des domaines | **Sur-mesure** (~15-25), lisibles grand public |
| Périmètre livrable 1 | **Taxonomie + mapping seuls** (socle SQL) |
| Approche de construction | **A** — artefact curé assisté IA hors-ligne, chargé en stdlib |
| Embeddings / nommage | **Local (sentence-transformers) / Claude API** |
| `competence_id` | **Nullable** (traçabilité honnête des `non_classe`) |
| Vue `certification_competence` | **Oui** |

## 10. Risques & points ouverts

- **Qualité du clustering FR** : à valider sur données réelles ; la curation humaine est
  le garde-fou. Le choix du modèle d'embeddings multilingue sera confirmé à l'implémentation.
- **Dérive temporelle** : plus l'artefact vieillit, plus la part `blocs_lexical`/`non_classe`
  monte. Mitigation : les stats `meta` rendent la dérive visible → signal pour relancer
  l'outil taxonomie.
- **Calibrage du seuil lexical** : compromis rappel/précision à régler sur fixtures puis
  sur un échantillon réel.
- **Taille cible exacte** (~200-400) : à affiner après la première passe de clustering.
