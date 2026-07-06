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

# Avec des zips déjà téléchargés (hors ligne) :
python3 build_db.py \
  --csv-zip data/export-fiches-csv-2026-07-04.zip \
  --xml-zip data/export-fiches-rncp-v4-1-2026-07-04.zip \
  --xml-zip data/export-fiches-rs-v4-1-2026-07-04.zip
```

Pour rafraîchir la base, relancez simplement le script (supprimez le contenu de `data/`
pour forcer le re-téléchargement des exports du jour).

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
```
