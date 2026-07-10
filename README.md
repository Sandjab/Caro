# Caro

**C**ompétences **A**cquises, **R**econnaissance **O**fficielle (mais d'abord
le prénom de celle qui a la première exprimé le besoin ; l'acronyme est venu
après 😏).

## Pourquoi Caro

L'État donne déjà accès à toutes les certifications professionnelles : le site
de France compétences propose
[une recherche dans les répertoires](https://www.francecompetences.fr/recherche-resultats/?types=certification&search=&pageType=certification&active=1)
— le Répertoire national des certifications professionnelles (**RNCP**) et le
Répertoire spécifique (**RS**). Chaque fiche y détaille ses « voies d'accès »,
dont la voie **« par expérience »** : la validation des acquis de l'expérience
(VAE), qui permet d'obtenir une certification en faisant reconnaître ce que
l'on a appris en travaillant, sans suivre la formation correspondante.

En pratique, cette recherche se prête mal à la question qui nous occupe —
« qu'est-ce que mon expérience me permettrait d'obtenir ? » (constats de
juillet 2026) :

- **aucun filtre VAE** : l'accessibilité par expérience n'apparaît qu'à
  l'intérieur de chaque fiche ; pour savoir si une certification s'obtient
  par VAE, il faut l'ouvrir, une par une ;
- les résultats arrivent **dix par page** — plus de 30 000 fiches au compteur
  avant filtrage, et chaque page de résultats pèse plus de 4 Mo ;
- les filtres sont **administratifs** (certificateur, codes NSF / ROME /
  Formacode, niveau, état de la fiche) : aucun ne parle le langage des
  compétences ;
- c'est une recherche **par mots-clés** : elle retrouve une certification
  dont on connaît déjà le nom, elle ne fait pas découvrir celles qu'on
  pourrait viser.

Le portail officiel [vae.gouv.fr](https://vae.gouv.fr) cible, lui, la VAE,
mais procède aussi par mots-clés : il suppose qu'on sait déjà quel diplôme
on vise.

Reste l'alternative : France compétences publie l'intégralité des répertoires
en **données ouvertes** — environ 30 000 fiches, dont 7 000 actives, sous
forme d'exports CSV et XML régénérés quotidiennement sur
[data.gouv.fr](https://www.data.gouv.fr/datasets/repertoire-national-des-certifications-professionnelles-et-repertoire-specifique).
Exhaustifs, mais bruts : des dizaines de fichiers à croiser, et surtout des
compétences en **texte libre**. Chaque certificateur rédige ses blocs de
compétences comme il l'entend — sa « liste de courses » —, si bien que les
mêmes savoir-faire reviennent sous des milliers de formulations : les quelque
19 400 libellés de blocs distincts des fiches actives se ramènent à
295 compétences canoniques (voir la taxonomie plus bas). Aucun moyen simple,
là non plus, de répondre à « quelles certifications mon expérience
couvre-t-elle ? ».

Caro transforme ces exports en deux choses :

- une **base SQLite requêtable**, pour explorer les certifications en SQL ;
- une **page web de recherche par compétences**, pour découvrir les
  certifications accessibles par validation des acquis de l'expérience (VAE)
  en cochant ce que l'on sait faire.

## Vue d'ensemble

Quatre composants s'enchaînent, du brut vers l'utilisable.

### La base SQLite

Un script unique (Python, bibliothèque standard seulement, aucune dépendance à
installer) télécharge les derniers exports publiés puis construit la base :

- **une table par fichier CSV** de l'export, jointures sur le numéro de fiche ;
  noms de tables et de colonnes normalisés (minuscules, sans accents), valeurs
  conservées telles que fournies ;
- **le texte intégral des référentiels**, extrait des XML : activités visées,
  capacités attestées, blocs de compétences, réglementations… ;
- par défaut, **seules les fiches actives** sont conservées ;
- une **recherche plein texte** (FTS5) sur les intitulés et les contenus, quand
  le SQLite de la machine la supporte ;
- une table de **provenance** (sources, périmètre, compteurs de construction).

### La taxonomie de compétences canoniques

Chaque certification décrit ses exigences en « blocs de compétences » rédigés
en texte libre, tous différents d'une fiche à l'autre : impossible de comparer
deux certifications directement là-dessus. La taxonomie résout ce problème en
rattachant chaque bloc réel à une **compétence canonique** d'un référentiel
pivot : 40 domaines, 295 compétences.

Ce rattachement est un **artefact versionné dans le dépôt** (trois fichiers
CSV et leurs métadonnées), produit hors ligne par un outil séparé et
occasionnel : classification par LLM des quelque 19 400 libellés de blocs
distincts contre le menu canonique, curation en plusieurs passes d'arbitrage,
puis certification par un juge indépendant (modèle différent, posture de
réfutation) qui mesure **environ 1,0 % d'erreur franche** (IC 95 % ± 0,8) sur
le mapping livré. Une passe ultérieure a repris les blocs restés non classés
pour combler les lacunes du menu — d'où 37 compétences et 5 domaines nouveaux
(théologie, marine & maritime, sciences politiques, psychologie, horlogerie) —,
portant la couverture à **99,3 %** des blocs actifs (delta certifié à 0,6 %
d'erreur franche). Une dernière passe traite les **certifications sans bloc**
dans la source (habilitations RS mono-objet, diplômes Jeunesse-Sport/STAPS…) :
faute de bloc à rattacher, elle les classe depuis leur **texte libre**
(capacités attestées, activités visées) via un chemin de rattachement *par
fiche* (`mapping_fiches.csv`) — d'où 31 compétences nouvelles et **0
certification VAE non positionnable** (délta certifié à 1,0 % d'erreur franche).
La construction de la base se contente de **lire** cet
artefact — elle reste déterministe et sans dépendance. Les blocs que
l'artefact ne couvre pas passent par un repli lexical simple : une **similarité
de Jaccard** — taille de l'intersection rapportée à celle de l'union — entre
les mots du bloc et les mots-clés de chaque compétence canonique, la meilleure
l'emportant si elle dépasse un seuil ; les blocs qui restent trop éloignés de
toute compétence demeurent non classés plutôt que rattachés de force. Si l'artefact est absent, la base se construit sans la taxonomie.

### La page de recherche VAE

Une page HTML **autonome** (~15 Mo, aucun serveur, aucune dépendance) qui
embarque toutes les données nécessaires, compressées. On y coche ses
compétences dans un arbre organisé par domaines, on filtre par niveau de
diplôme et par domaine de formation, et la page classe les certifications
accessibles par VAE selon la part de leurs exigences couverte.

### Le matching

Le matching opère en deux étages.

**Premier étage, hors ligne** : la traduction des blocs de texte libre en
compétences canoniques, décrite ci-dessus. C'est elle qui rend les
certifications comparables entre elles — et comparables à une liste de cases
cochées. Une certification dont aucun bloc n'a pu être rattaché est exclue de
la page : on ne peut pas classer par couverture ce dont on ignore les
exigences.

**Second étage, dans le navigateur** : pour chaque certification passant les
filtres (niveau, domaine de formation), la page calcule

```
couverture = compétences exigées et cochées / compétences exigées
```

Ne sont gardées que les certifications au-dessus du seuil de couverture
choisi, triées par couverture décroissante ; à égalité, par nombre absolu de
compétences couvertes ; à égalité encore, par nombre de compétences **métier**
couvertes. Les compétences transversales (savoir-être, communication, matières
générales) comptent dans le score mais sont affichées à part : couvrir
« travailler en équipe » ne dit rien de la certification visée.

Un point à garder en tête : le score est une **couverture des exigences de la
certification**, pas une ressemblance symétrique entre un profil et elle. Une
certification qui n'exige que 2 compétences, toutes deux cochées, sort à
100 % ; une autre qui en exige 20, dont 15 couvertes, sort à 75 %. Le tri par
nombre absolu atténue ce biais en faveur des fiches peu détaillées, sans
l'éliminer. C'est un choix assumé côté VAE : on cherche les certifications
qu'une expérience couvre entièrement, pas celles qui ressemblent le plus à un
profil.

## Utilisation

### Chercher une certification accessible par VAE

La page est publiée ici, sans rien installer :

**<https://sandjab.github.io/Caro/>**

Cochez vos compétences dans l'arbre, ajustez au besoin le seuil de couverture
et les filtres niveau / domaine, et parcourez les certifications classées.
Chaque carte détaille les compétences couvertes et manquantes, et donne accès
au texte de présentation et aux blocs de compétences officiels de la fiche.

Limites à connaître avant de s'appuyer sur le classement :

- **Toutes les certifications accessibles par VAE sont désormais
  positionnées.** Les ~400 fiches sans bloc de compétences dans les exports
  (habilitations RS mono-objet, diplômes Jeunesse-Sport/STAPS…), autrefois
  seulement consultables, sont maintenant classées via le chemin de
  rattachement *par fiche* décrit plus haut — depuis leur texte libre. Leur
  positionnement porte **1,0 % d'erreur franche** certifiée : plus bruité que
  le chemin par bloc, à prendre comme un repère et non une vérité.
- Le taux de couverture est un signal **grossier** : la médiane est de
  4 compétences exigées par certification, donc un « 75 % » signifie souvent
  « 3 sur 4 ».
- Le rattachement bloc → compétence porte environ **1,0 % d'erreur franche**
  (voir plus haut) : suffisant pour orienter, insuffisant pour décider seul
  d'une démarche VAE.
- **La recevabilité réelle d'une VAE n'est pas modélisée** : ni durée
  d'expérience, ni conditions de recevabilité, ni jury. L'outil oriente vers
  des candidats plausibles, il ne présume d'aucune décision.
- **Seules les 200 premières cartes sont affichées** (la page l'indique) :
  au-delà, resserrez la couverture minimale ou les filtres plutôt que de
  parcourir une liste tronquée.
- **Les liens partagés sont fragiles.** Le fragment d'URL encode des positions
  internes, pas des identifiants stables : rouvert après une régénération de
  la page, un lien peut cocher silencieusement d'autres éléments que ceux
  voulus. À réserver à un usage de courte durée, pas à un signet.

### Reconstruire la base

Prérequis : Python 3.9+ (bibliothèque standard uniquement).

```bash
python3 build_db.py
```

Cela télécharge les exports dans `data/` (cache réutilisé au lancement
suivant) puis construit `rncp.sqlite3` avec, par défaut, **les seules fiches
actives** (RNCP + RS). Pour rafraîchir la base, relancez simplement le script
(supprimez le contenu de `data/` pour forcer le re-téléchargement des exports
du jour).

Options :

```bash
python3 build_db.py --all        # inclut aussi les fiches inactives (~20 000 au total)
python3 build_db.py --no-xml     # base allégée, sans le texte intégral des référentiels
python3 build_db.py --db ma.db --data-dir /tmp/exports
python3 build_db.py --taxonomie-dir mon-artefact/   # emplacement de l'artefact taxonomie (défaut : taxonomie/)
python3 build_db.py --no-taxonomie                  # ignore la phase de taxonomie de compétences

# Avec des zips déjà téléchargés (hors ligne) :
python3 build_db.py \
  --csv-zip data/export-fiches-csv-2026-07-04.zip \
  --xml-zip data/export-fiches-rncp-v4-1-2026-07-04.zip \
  --xml-zip data/export-fiches-rs-v4-1-2026-07-04.zip
```

### Mettre à jour la taxonomie

L'artefact `taxonomie/` (`domaines.csv`, `competences_canoniques.csv`,
`mapping_blocs.csv`, `;` en séparateur, plus `meta.json`) est versionné dans le
dépôt : pour un build ordinaire, il n'y a **rien à faire**, la construction de
la base le lit automatiquement.

Sa production, elle, relève d'un outil séparé et occasionnel (embeddings +
LLM, curation humaine), volontairement hors du pipeline : régénérer l'artefact
n'a de sens que lorsque le référentiel canonique évolue ou que la population
de blocs a suffisamment changé. Le pipeline, lui, reste déterministe : à
artefact identique, base identique.

### Régénérer la page de recherche

```bash
python3 build_ihm.py                    # rncp.sqlite3 -> ihm/index.html
python3 build_ihm.py --db autre.sqlite3 -o /tmp/vae.html
```

Prérequis : une base construite **avec** l'artefact `taxonomie/` — sur une
base construite avec `--no-taxonomie`, la génération refuse de produire une
page. Ouvrir ensuite `ihm/index.html` d'un double-clic ; la page publiée sur
GitHub Pages est une copie de ce fichier (branche `gh-pages`).

`ihm/template.html` et `ihm/matcher.js` sont versionnés ; `ihm/index.html` est
un artefact **généré et gitignoré**, à régénérer après chaque mise à jour de
la base ou du moteur. Le moteur de matching est injecté verbatim dans la
page : le code exercé par les tests est exactement celui livré au navigateur.

### Tests

```bash
python -m unittest discover -s tests -p "test_*.py" -v   # pipeline (fixtures synthétiques, hors ligne)
node --test 'ihm/*.test.js'                              # moteur de matching (si node présent)
```

## La solution en détail

### Exports sources

La construction repère les **derniers** exports publiés via l'API
data.gouv.fr :

| Export | Contenu | Usage dans la base |
|---|---|---|
| `export-fiches-csv-AAAA-MM-JJ.zip` | CSV relationnels (fiche standard, blocs de compétences, certificateurs, partenaires, codes ROME / NSF / Formacode, voies d'accès, CCN, filiations ancienne/nouvelle certification), liés par `Numero_Fiche` | une table SQLite par CSV |
| `export-fiches-rncp-v4-1-AAAA-MM-JJ.zip` | XML V4.1 des fiches RNCP (texte intégral) | tables `fiche_texte` et `bloc_competences_xml` |
| `export-fiches-rs-v4-1-AAAA-MM-JJ.zip` | XML V4.1 des fiches RS (texte intégral) | idem |

La documentation du jeu de données (schémas **XSD** et **dictionnaire de
données** PDF) décrit chaque champ ; elle n'est pas chargée en base.

### Schéma de la base

- **Une table par CSV de l'export** (noms normalisés en minuscules sans accents) :
  `standard`, `blocs_de_competences`, `certificateurs`, `partenaires`, `rome`, `nsf`,
  `formacode`, `ccn`, `voies_acces`, `ancienne_nouvelle_certification`, …
  Toutes les colonnes sont en `TEXT`, telles que fournies par France compétences ;
  jointures sur `numero_fiche` (indexé partout).
- **`fiche_texte`** `(numero_fiche, repertoire, champ, contenu)` : champs longs extraits
  des XML — activités visées, capacités attestées, secteurs d'activité, types d'emplois
  accessibles, objectifs et contexte (RS), réglementations, prérequis… Les champs longs
  non répertoriés sont capturés aussi (tolérance aux évolutions du format V4.x).
- **`bloc_competences_xml`** `(numero_fiche, repertoire, bloc_code, bloc_libelle,
  liste_competences, modalites_evaluation)` : détail des blocs issu des XML.
- **`fiche_fts`** : table virtuelle FTS5 de recherche plein texte sur les intitulés et
  tous les contenus de `fiche_texte`.
- **`meta`** : provenance, périmètre et statistiques de construction.

Si l'artefact `taxonomie/` a été fourni au build, quatre tables et une vue
supplémentaires apparaissent :

- **`domaine`** `(domaine_id, libelle, description, ordre)` : domaines sur-mesure de
  regroupement des compétences canoniques.
- **`competence_canonique`** `(competence_id, domaine_id, libelle, description,
  mots_cles, nb_blocs)` : macro-compétences canoniques (grain bloc), rattachées à un
  domaine ; `nb_blocs` est calculé au build.
- **`bloc_competence_canonique`** `(bloc_code, numero_fiche, competence_id, methode,
  score)` : rattachement de chaque bloc réel à sa compétence canonique. `methode` vaut
  `ia` (mapping précalculé par l'outil taxonomie), `lexical` (repli par recouvrement de
  mots-clés au build) ou `non_classe` (sous le seuil, `competence_id` NULL — aucun
  rattachement forcé).
- **`fiche_competence_canonique`** `(numero_fiche, competence_id, methode)` :
  rattachement **par fiche**, pour les certifications sans bloc dans la source
  (classées depuis leur texte libre par l'outil taxonomie). Table toujours créée,
  vide si `mapping_fiches.csv` est absent.
- **`certification_competence`** (vue) `(numero_fiche, competence_id, domaine_id)` :
  diplôme → compétences canoniques couvertes, **UNION** du chemin blocs (les blocs
  `non_classe` sont exclus) et du chemin par fiche.

Les clés `meta` correspondantes : `taxonomie` (oui/non), et si présente `nb_domaines`,
`nb_competences_canoniques`, `nb_fiches_rattachees`, `blocs_ia_pct` / `blocs_lexical_pct`
/ `blocs_non_classe_pct`, `taxonomie_version` / `taxonomie_date` / `taxonomie_modele`.

### Exemples de requêtes

```sql
-- Certifications actives de niveau 5 (bac+2)
SELECT numero_fiche, intitule
FROM standard
WHERE nomenclature_europe_niveau LIKE '%NIV5%';

-- Blocs de compétences d'une fiche
SELECT bloc_competences_code, bloc_competences_libelle
FROM blocs_de_competences
WHERE numero_fiche = 'RNCP12345';

-- Certifications visant un métier ROME donné, avec leur certificateur
SELECT DISTINCT s.numero_fiche, s.intitule, c.nom_certificateur
FROM standard s
JOIN rome r ON r.numero_fiche = s.numero_fiche
JOIN certificateurs c ON c.numero_fiche = s.numero_fiche
WHERE r.codes_rome_code = 'M1805';

-- Recherche plein texte dans les référentiels (FTS5)
SELECT numero_fiche, champ, snippet(fiche_fts, 2, '[', ']', '…', 12)
FROM fiche_fts
WHERE fiche_fts MATCH 'cybersécurité'
LIMIT 20;

-- Diplômes couvrant une compétence canonique donnée (nécessite l'artefact taxonomie/)
SELECT DISTINCT s.numero_fiche, s.intitule
FROM certification_competence cc
JOIN standard s ON s.numero_fiche = cc.numero_fiche
WHERE cc.competence_id = 'creer_gerer_site_web';
```
