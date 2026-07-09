# Design system Caro — repères pour Claude Code

> Bloc à ajouter à la fin du `CLAUDE.md` racine (section « Interface / design »).
> Il fixe les règles permanentes pour que le style de l'app reste cohérent à
> chaque intervention, sans avoir à les rappeler.

## Où vit le design

- **Tout le style de l'interface vit dans le bloc `<style>` de `ihm/template.html`.**
- **Ne jamais éditer `ihm/index.html`** : c'est un artefact **généré et gitignoré**.
  Après toute modif de `template.html`, régénérer avec :
  ```bash
  python3 build_ihm.py
  ```
  et publier en copiant `ihm/index.html` sur la branche `gh-pages`.
- La feuille de style de référence est `handoff/ihm-style.css` : c'est le contenu
  attendu du bloc `<style>`. En cas de doute, s'y aligner.

## Tokens (source de vérité)

Palette « papier chaud + un accent vert », déclarée en variables CSS dans `:root` :

| Token | Valeur | Usage |
|---|---|---|
| `--canvas` | `#faf7f2` | fond papier chaud |
| `--surface` | `#ffffff` | cartes, panneaux |
| `--ink` | `#1b1a17` | texte principal |
| `--muted` | `#6f685c` | texte secondaire |
| `--faint` | `#a39a8a` | labels / compteurs discrets |
| `--line` | `#e7e1d7` | bordures |
| `--line-soft` | `#f0ece3` | séparateurs internes |
| `--field` | `#faf7f2` | fond des champs |
| `--field-line` | `#e0d9cd` | bordure des champs |
| `--acc` | `#0f6d5f` | vert accent (couverture, coches, jauge métier) |
| `--acc-ink` | `#0b5346` | liens |
| `--acc-track` | `#eee7db` | piste des jauges |
| `--transv` | `#b7a98c` | jauge transversale (beige) |
| `--mark` | `#ffe39e` | surlignage dans les fiches |

Les anciens noms `--bord / --gris / --fond / --acc` restent définis en **alias**
des nouveaux, pour ne rien casser dans le HTML/JS existant.

## Typographie

- Titres (`h1/h2/h3`, `.taux`, marque) : **Spectral** (serif éditoriale).
- Interface et corps de texte : **Public Sans** (sans humaniste).
- Chargées via Google Fonts dans le `<head>` de `template.html` :
  ```html
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,500;0,600;0,700;1,400&family=Public+Sans:ital,wght@0,400;0,500;0,600;0,700&display=swap" rel="stylesheet">
  ```

## Règles à tenir

- **Un seul accent** (`--acc`, vert). Ne pas introduire d'autre couleur vive.
  Le taux de couverture est le chiffre héros de chaque carte.
- Jauge **métier** en vert (`--acc`), jauge **transversale** en beige (`--transv`) :
  elles ne doivent pas se ressembler.
- Rayons : champs/boutons `8–9px`, cartes/panneaux `12–13px`.
- Case de branche dans l'arbre : état **`indeterminate`** (tiret) quand seules
  certaines feuilles sont cochées — le JS pose déjà `cbDom.indeterminate`, ne pas
  le retirer ; `accent-color: var(--acc)` colore le tiret.
- Cibles tactiles ≥ 40px, texte ≥ 12.5px, contraste AA.
- Rester **sans dépendance** : pas de framework CSS, pas de build front. Le style
  est du CSS écrit à la main dans `template.html`, injecté verbatim comme le reste.
- Langue : **français** (cohérent avec le reste du projet).

## En-tête (ajout)

L'app n'avait pas d'en-tête. En ajouter un juste après `<body>`, avant `<main>`
(le `body` passe en `display:flex; flex-direction:column`, `main` en `flex:1`) :

```html
<header class="caro-header">
  <span class="marque">Caro</span>
  <p class="baseline">Les certifications professionnelles que votre expérience
    vous permet de viser par <strong>validation des acquis (VAE)</strong>.</p>
  <a class="source" href="https://www.data.gouv.fr/datasets/repertoire-national-des-certifications-professionnelles-et-repertoire-specifique"
     target="_blank" rel="noopener">données ouvertes · France compétences</a>
</header>
```
