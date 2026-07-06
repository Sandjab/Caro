# CLAUDE.md

Repères pour Claude Code lorsqu'il travaille dans ce dépôt.

## Objet du projet

Caro construit une **base SQLite requêtable** à partir des données ouvertes de
**France compétences** : le Répertoire national des certifications professionnelles
(RNCP) et le Répertoire spécifique (RS).

Source des données :
https://www.data.gouv.fr/datasets/repertoire-national-des-certifications-professionnelles-et-repertoire-specifique
(exports régénérés quotidiennement ; ~20 000 fiches dont ~7 500 actives).

## Structure du dépôt

- `build_db.py` — script unique d'ingestion (Python 3.9+, **stdlib uniquement**,
  aucune dépendance à installer). Télécharge les derniers exports via l'API
  data.gouv.fr, puis construit `rncp.sqlite3`.
- `README.md` — documentation utilisateur : fichiers sources, options, schéma de la
  base, exemples de requêtes SQL.
- `data/` et `*.sqlite3` — ignorés par git (téléchargements et base générée ne sont
  jamais commités).

## Commandes

```bash
python3 build_db.py            # télécharge dans data/ puis construit rncp.sqlite3
python3 build_db.py --all      # inclut les fiches inactives (défaut : actives seules)
python3 build_db.py --no-xml   # sans le texte intégral des référentiels
python3 build_db.py --csv-zip … --xml-zip … --xml-zip …   # mode hors ligne
python3 build_db.py --taxonomie-dir … / --no-taxonomie    # artefact taxonomie / phase ignorée
```

Il existe une suite de tests unitaires sous `tests/` (fixtures synthétiques, mode
hors ligne) :

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

Pour valider une autre modification de `build_db.py` non couverte par ces tests,
générer des fixtures synthétiques (mini zips CSV `;` + XML V4.1 imitant les exports,
éventuellement un mini `taxonomie/`) et lancer le script dessus en mode hors ligne,
puis vérifier le contenu de la base par requêtes SQL (filtrage actif, encodages,
`fiche_texte`, blocs, FTS, taxonomie).

## Points d'architecture à connaître

- **Trois exports sources** : `export-fiches-csv-*.zip` (CSV relationnels, une table
  SQLite par CSV, clé de jointure `numero_fiche`), `export-fiches-rncp-v4-1-*.zip` et
  `export-fiches-rs-v4-1-*.zip` (XML V4.1, texte intégral). Les ressources les plus
  récentes sont repérées dans la réponse de l'API par motifs regex + date dans le nom.
- **Normalisation** : noms de tables et colonnes passés en minuscules ASCII
  (`slugify`) ; toutes les colonnes CSV sont typées `TEXT`, valeurs conservées telles
  quelles (dates incluses).
- **Filtrage actif** : la table `standard` fournit l'ensemble des `numero_fiche`
  actifs (`Actif` = ACTIVE/Oui) ; les autres tables sont purgées via une table temp
  (pas de `NOT IN (?,…)` — limite de variables SQLite).
- **XML** : parsing en flux (`iterparse`), champs texte connus listés dans
  `XML_TEXT_TAGS` + capture de secours de tout champ ≥ 300 caractères hors
  `XML_STRUCTURED_TAGS` (tolérance aux évolutions du format V4.x). Sorties :
  `fiche_texte` (clé/valeur) et `bloc_competences_xml`.
- **Encodages CSV** : essai utf-8-sig puis cp1252 puis latin-1 ; délimiteur détecté
  (`;` attendu).
- **FTS5** : table `fiche_fts` (intitulés + contenus de `fiche_texte`), création
  entourée de try/except — certains builds SQLite n'ont pas FTS5.
- **`meta`** : table de provenance (sources, périmètre, compteurs) écrite en fin de
  construction.
- **Taxonomie de compétences canoniques** : phase optionnelle qui charge l'artefact
  versionné `taxonomie/` (`domaines.csv`, `competences_canoniques.csv`,
  `mapping_blocs.csv`) s'il est présent, et crée `domaine`, `competence_canonique`,
  `bloc_competence_canonique` ainsi que la vue `certification_competence`. Séparation
  stricte entre l'**outil taxonomie** (`build_taxonomie.py`, occasionnel, embeddings +
  LLM, curation humaine, hors périmètre stdlib) qui produit l'artefact, et le
  **pipeline `build_db.py`** (stdlib, déterministe) qui se contente de le lire et
  applique un repli lexical stdlib pour les blocs non couverts par le mapping.
  Artefact absent/incomplet ou `--no-taxonomie` → dégradation gracieuse, comme pour
  FTS5.

## Contraintes d'environnement

Dans l'environnement Claude Code distant, la politique réseau **bloque
`data.gouv.fr` et `francecompetences.fr`** : impossible d'y télécharger les vrais
exports. Le script est donc prévu pour être exécuté sur la machine de l'utilisateur ;
côté agent, tester exclusivement avec des fixtures synthétiques en mode
`--csv-zip`/`--xml-zip`.

## Conventions

- Langue du projet : **français** (code, messages du script, documentation, commits).
- Garder `build_db.py` autonome : pas de dépendances tierces, pas d'éclatement en
  paquet tant que le besoin ne l'impose pas.
