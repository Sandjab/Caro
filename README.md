# Caro

Base SQLite requêtable construite à partir des données ouvertes de **France compétences** :
le Répertoire national des certifications professionnelles (**RNCP**) et le Répertoire
spécifique (**RS**).

Source : [Répertoire national des certifications professionnelles et répertoire spécifique — data.gouv.fr](https://www.data.gouv.fr/datasets/repertoire-national-des-certifications-professionnelles-et-repertoire-specifique)
(producteur : France compétences, exports régénérés quotidiennement).

## Fichiers utilisés

Le script télécharge automatiquement les **derniers** exports publiés, repérés via
l'API data.gouv.fr :

| Export | Contenu | Usage dans la base |
|---|---|---|
| `export-fiches-csv-AAAA-MM-JJ.zip` | CSV relationnels (fiche standard, blocs de compétences, certificateurs, partenaires, codes ROME / NSF / Formacode, voies d'accès, CCN, filiations ancienne/nouvelle certification), liés par `Numero_Fiche` | une table SQLite par CSV |
| `export-fiches-rncp-v4-1-AAAA-MM-JJ.zip` | XML V4.1 des fiches RNCP (texte intégral) | tables `fiche_texte` et `bloc_competences_xml` |
| `export-fiches-rs-v4-1-AAAA-MM-JJ.zip` | XML V4.1 des fiches RS (texte intégral) | idem |

La documentation du jeu de données (schémas **XSD** et **dictionnaire de données** PDF)
décrit chaque champ ; elle n'est pas chargée en base.

## Utilisation

Prérequis : Python 3.9+ (bibliothèque standard uniquement).

```bash
python3 build_db.py
```

Cela télécharge les exports dans `data/` (cache réutilisé au lancement suivant) puis
construit `rncp.sqlite3` avec, par défaut, **les seules fiches actives** (RNCP + RS).

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

Pour rafraîchir la base, relancez simplement le script (supprimez le contenu de `data/`
pour forcer le re-téléchargement des exports du jour).

### Taxonomie de compétences canoniques (optionnelle)

Si un répertoire `taxonomie/` (artefact versionné `domaines.csv`,
`competences_canoniques.csv`, `mapping_blocs.csv`, `;` en séparateur) est présent à côté
du script, `build_db.py` l'utilise pour rattacher chaque bloc de compétences réel à une
« macro-compétence » canonique et enrichir la base en conséquence (voir schéma
ci-dessous). Cet artefact est produit par un **outil séparé** (`build_taxonomie.py`,
occasionnel, embeddings + LLM, curation humaine) — `build_db.py` se contente de le lire.
Si le répertoire est absent ou incomplet (ou avec `--no-taxonomie`), l'étape est
proprement ignorée et la base se construit comme avant.

## IHM : certifications accessibles par VAE

`build_ihm.py` génère une page HTML autonome (~15,4 Mo, sans serveur ni
dépendance) permettant de cocher ses compétences dans un arbre et de découvrir
les certifications accessibles par validation des acquis de l'expérience,
classées par couverture de leurs exigences.

```bash
python3 build_ihm.py                    # rncp.sqlite3 -> ihm/index.html
python3 build_ihm.py --db autre.sqlite3 -o /tmp/vae.html
```

Prérequis : une base construite **avec** l'artefact `taxonomie/` (la vue
`certification_competence` est nécessaire) — avec `--no-taxonomie`,
`build_ihm.py` refuse de produire une page. Ouvrir ensuite `ihm/index.html`
d'un double-clic.

`ihm/template.html` et `ihm/matcher.js` sont versionnés ; `ihm/index.html` est
un artefact **généré et gitignoré**, à régénérer après chaque mise à jour de la
base ou du moteur. Le moteur de matching (`matcher.js`) est injecté verbatim
dans la page : le code exercé par `node --test 'ihm/*.test.js'` est exactement
celui livré au navigateur.

Le classement trie par taux de couverture, puis par nombre absolu de
compétences couvertes, puis par compétences métier — de sorte qu'une
certification exigeant huit compétences toutes couvertes passe devant une
certification n'en exigeant qu'une. Les compétences transversales comptent dans
le score mais sont affichées séparément.

Limites, à garder à l'esprit avant de s'appuyer sur le classement :

- **408 des 5 582 certifications accessibles par VAE n'ont aucune compétence
  rattachée** et ne sont donc pas listées (la page l'indique). Les 196 fiches
  VAE sans niveau de diplôme renseigné en font toutes partie — aucune n'a de
  compétence rattachée — ce qui explique qu'aucune entrée « niveau non
  renseigné » n'apparaisse dans le filtre par niveau.
- Le taux de couverture est un signal **grossier**, pas une mesure fine : la
  médiane est de 4 compétences exigées par certification, donc un « 75 % »
  signifie souvent « 3 sur 4 ».
- Le mapping bloc → compétence porte environ **1,0 % d'erreur franche** (mesuré
  par un juge indépendant, IC 95 % ± 0,8) : suffisant pour orienter,
  insuffisant pour décider seul d'une démarche VAE.
- **La recevabilité réelle d'une VAE n'est pas modélisée** : ni durée
  d'expérience, ni conditions de recevabilité, ni jury. L'outil oriente vers
  des candidats plausibles, il ne présume d'aucune décision.

## Schéma de la base

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

Si l'artefact `taxonomie/` a été fourni au build (voir ci-dessus), trois tables et une
vue supplémentaires apparaissent :

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
- **`certification_competence`** (vue) `(numero_fiche, competence_id, domaine_id)` :
  diplôme → compétences canoniques couvertes (les blocs `non_classe` sont exclus).

Les clés `meta` correspondantes : `taxonomie` (oui/non), et si présente `nb_domaines`,
`nb_competences_canoniques`, `blocs_ia_pct` / `blocs_lexical_pct` / `blocs_non_classe_pct`,
`taxonomie_version` / `taxonomie_date` / `taxonomie_modele`.

## Exemples de requêtes

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
