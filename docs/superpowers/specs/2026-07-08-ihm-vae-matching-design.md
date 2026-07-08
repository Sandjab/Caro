# IHM VAE — arbre de compétences et matching de certifications

**Date** : 2026-07-08
**Statut** : design validé, en attente du plan d'implémentation

## Objectif

Permettre à un utilisateur de déclarer ses compétences en cochant les feuilles
d'un arbre, puis de découvrir les certifications qu'il peut viser par
**validation des acquis de l'expérience (VAE)**, classées par taux de
couverture de leurs exigences.

L'utilisateur filtre par niveau de diplôme et par domaine. Les certifications
qu'il couvre intégralement remontent en premier, jusqu'à celles qu'il ne
couvre qu'à moitié.

## Ce que les données permettent

Vérifié sur `rncp.sqlite3` (fiches actives, export du 2026-07-05) :

| Fait | Valeur | Conséquence |
|---|---|---|
| VAE identifiable | `voixdacces.si_jury = 'Par expérience'` | 5 582 fiches actives |
| dont au moins une compétence rattachée | 5 174 | 408 fiches inexploitables |
| Compétences exigées par certification | médiane **4**, moyenne 4,2, max 16 | mapping grossier |
| Certifications n'exigeant qu'une compétence | 535 | pathologie de classement |
| Part des compétences transversales | **31,5 %** des exigences | gonflement du score |
| Niveaux | NIV3 à NIV8, 196 fiches sans niveau | filtre exploitable |
| Domaine NSF | 388 codes fins, 16 groupes, 100 % des fiches | filtre exploitable |

Deux de ces faits ont façonné le design et méritent d'être énoncés
franchement.

**Le classement par taux de couverture pur est trompeur.** Une certification
qui n'exige qu'une compétence est couverte à 100 % dès que l'utilisateur coche
cette compétence. Un tri par ratio remonterait donc en tête les certifications
les *moins bien décrites*. Ce n'est pas un défaut du réel : c'est notre mapping
qui est grossier (227 compétences canoniques pour 28 289 blocs).

**Les compétences transversales gonflent le score sans rien dire.** Un
utilisateur coche « s'exprimer à l'oral » sans effort ; cette compétence est
exigée par 734 certifications. Test du scénario extrême — l'utilisateur ne
coche *que* les 21 compétences transversales et d'enseignement général : 21
certifications sortent à 100 % (0,4 %), mais 1 246 sortent à ≥ 50 % (24 %).

## Décisions

### D1 — Page HTML autonome, données embarquées

Un fichier unique, ouvrable au double-clic, sans serveur ni dépendance.

| Charge utile | Brut | gzip |
|---|---|---|
| Index (intitulé, niveau, NSF, compétences) | 1,0 Mo | 0,18 Mo |
| Détail (description, activités, blocs) | 50,0 Mo | 11,6 Mo |

Les deux blobs sont embarqués en base64 et décompressés par
`DecompressionStream('gzip')`, natif au navigateur. Le fichier généré pèse
~16 Mo.

`capacites_attestees` (27 Mo bruts) est **exclu** : ce champ redit, réagencé,
le contenu des `liste_competences` des blocs. Deux mégaoctets gagnés pour zéro
perte d'information.

Le détail n'est décompressé qu'à l'ouverture de la première fiche. La page
s'affiche instantanément ; une session qui ne consulte aucune fiche ne paie
jamais les 11,6 Mo.

**Écarté** : précalculer des scores par profil-type (2²²⁷ combinaisons) ;
serveur HTTP local (impose un process et la base de 315 Mo).

### D2 — Classement à deux composantes, puis départage métier

```
tri = (couverture DESC, nb_couvertes DESC, nb_metier_couvertes DESC)
```

Le taux prime, conformément à la demande. À taux égal, le **volume absolu**
départage : une certification couverte 8/8 passe devant une couverte 1/1. À
volume égal, les exigences **métier** passent devant les transversales.

Ce classement a la propriété qui compte : l'utilisateur peut le vérifier de
tête en regardant les chiffres affichés. Aucun paramètre magique.

**Écarté** : pondération TF-IDF par rareté de la compétence (plus juste
sémantiquement, mais produit un score abstrait invérifiable) ; seuil minimal
d'exigences (amputerait 28 à 49 % du catalogue VAE).

### D3 — Transversales : comptées, mais séparées à l'affichage

Les 21 compétences transversales et d'enseignement général restent dans le
score — le référentiel les exige réellement. Mais l'IHM affiche **deux barres
distinctes** : couverture métier et couverture transversale.

L'utilisateur voit qu'un « 60 % » composé de `1/3 métier + 2/2 transversal` ne
vaut pas un « 60 % » composé de `3/5 métier`. Aucune information cachée, aucun
coefficient arbitraire.

Dans l'arbre, ces compétences sont reléguées sous un séparateur, en bas,
visuellement atténuées.

**Écarté** : les exclure du score (certaines certifications n'exigent que du
transversal, leur score deviendrait indéfini — et le référentiel les exige
vraiment).

### D4 — Filtre domaine sur les 16 groupes NSF

Vocabulaire officiel, présent sur 100 % des fiches, **indépendant de la qualité
de notre mapping**. L'utilisateur voit donc deux taxonomies (35 domaines dans
l'arbre, 16 groupes NSF dans le filtre) : c'est le prix d'un filtre qui ne
dépend pas d'une déduction fragile.

**Écarté** : déduire le domaine d'une certification du domaine dominant de ses
compétences. Avec une médiane de 4 compétences dont 31 % de transversales,
« CAP Pâtisserie » ressortirait en domaine « transversal ».

### D5 — L'état vit dans le fragment d'URL

`#c=12,45,90&niv=6,7&nsf=32&seuil=50`

Rechargement sans perte, profil partageable par simple copie du lien, retour
arrière navigable. Pas de `localStorage` à purger.

## Architecture

```
Caro/
  build_db.py           existant — inchangé
  taxonomie/            existant — inchangé
  rncp.sqlite3          lu seulement

  build_ihm.py          NOUVEAU — stdlib, lit la base, écrit ihm/index.html
  ihm/
    template.html       NOUVEAU — squelette + CSS + JS, versionné
    matcher.js          NOUVEAU — moteur pur, testable sans navigateur
    matcher.test.js     NOUVEAU — tests node --test
    index.html          GÉNÉRÉ — gitignoré, ~16 Mo
  tests/
    test_build_ihm.py   NOUVEAU
  .gitignore            + ligne `ihm/index.html`
```

`index.html` est un artefact généré, au même titre que `rncp.sqlite3` et
`data/` : jamais commité. Seuls `template.html` et `matcher.js` — du code
lisible et diffable — le sont.

Trois unités, chacune compréhensible et testable seule :

- **`build_ihm.py`** — contrat : `rncp.sqlite3` + `template.html` → `index.html`.
  Extrait, filtre (VAE + actives + ≥1 compétence), sérialise, compresse, injecte.
  Stdlib uniquement, comme `build_db.py`.
- **`matcher.js`** — contrat : `(Set d'indices cochés, filtres) → liste triée`.
  Fonction pure, sans DOM.
- **L'IHM** — consomme le moteur, ne calcule rien.

Le moteur ignore le DOM ; l'IHM ignore la structure des données compressées.

## Format des données

Les identifiants sont **internés** : une certification référence ses
compétences par indice entier.

```js
DATA = {
  domaines:    ["Compétences transversales", "Numérique & informatique", …],   // 35
  competences: [[id, libellé, idx_domaine, transversal?], …],                  // 227
  nsf:         [["31", "Échanges et gestion"], …],                             // 16
  certifs:     [[numéro, intitulé, "NIV6", [idx_nsf…], [idx_comp…]], …]        // 5 174
}

DETAIL["RNCP38112"] = {
  o: "objectifs et contexte…",
  a: "activités visées…",
  b: [[code_bloc, libellé_bloc, liste_competences], …]
}
```

## Moteur de matching

`data` est passé en paramètre, jamais lu depuis une globale : c'est ce qui rend
la fonction testable sous `node --test`, sans navigateur ni DOM.

```js
// coches : Set d'indices de compétences
// filtres : { niveaux: Set|null, nsf: Set|null, seuil: number /* fraction 0..1 */ }
export function matcher(data, coches, filtres) {
  const estTransversal = i => data.competences[i][3];
  return data.certifs
    .filter(c => passeFiltres(c, filtres))
    .map(c => {
      const req    = c[4];
      const metier = req.filter(i => !estTransversal(i));
      const transv = req.filter(i =>  estTransversal(i));
      return {
        certif:      c,
        couverture:  inter(req, coches).length / req.length,
        nbCouvertes: inter(req, coches).length,
        metier:      [inter(metier, coches).length, metier.length],
        transv:      [inter(transv, coches).length, transv.length],
      };
    })
    .filter(r => r.couverture >= filtres.seuil)
    .sort((a, b) =>
      b.couverture  - a.couverture ||
      b.nbCouvertes - a.nbCouvertes ||
      b.metier[0]   - a.metier[0]);
}
```

**Unités** : `filtres.seuil` est une fraction dans `[0, 1]`. Le fragment d'URL
porte un pourcentage entier (`seuil=50`) ; la conversion est faite par la
couche IHM, jamais par le moteur.

5 174 certifications × 4,2 compétences ≈ 22 000 paires : le recalcul complet à
chaque clic coûte moins d'une milliseconde. Rien à indexer, rien à mémoïser.

## Interface

```
┌─ MES COMPÉTENCES ──────┐┌─ 1 247 certifications accessibles par VAE ─────────┐
│ [🔍 filtrer l'arbre  ] ││ Niveau ▾  Domaine ▾  Couverture min. ▓▓▓▓░░ 50 %   │
│                        ││────────────────────────────────────────────────────│
│ ▾ ■ Numérique & info…  ││ ┏━ 100 %  Manager de projet informatique     NIV7 ┓│
│    ☑ Gérer un projet   ││ ┃ métier      ████████ 4/4                        ┃│
│    ☑ Administrer les…  ││ ┃ transversal ████     2/2                        ┃│
│    ☐ Développer une…   ││ ┗━ 326 Informatique ─────────────── voir la fiche ┛│
│ ▸ ☐ Bâtiment & TP      ││                                                    │
│ ▸ ▪ Gestion, manage…   ││ ┏━  83 %  Chef de projet digital             NIV6 ┓│
│                        ││ ┃ métier      █████░░░ 4/5                        ┃│
│ ── transversales ───── ││ ┃ transversal ████     1/1                        ┃│
│ ▾ ▪ Compétences tra…   ││ ┗━ 320 Communication ───────────── voir la fiche ┛ │
│    ☑ S'exprimer à l'…  ││                                                    │
│    ☐ Agir en respon…   ││ … 1 245 autres                                     │
│                        ││                                                    │
│ 5 compétences cochées  ││ ⓘ 408 certifications VAE non listées : leurs blocs │
│         [tout décocher]││   de compétences n'ont pas pu être rattachés.      │
└────────────────────────┘└────────────────────────────────────────────────────┘
```

**Arbre** : 35 domaines, 227 feuilles. Case de domaine en tri-état (vide,
partielle, pleine), cliquable pour tout cocher ou décocher. Le champ de
recherche filtre sur le libellé **et les `mots_cles`** de l'artefact : taper
« soudure » trouve la compétence même si le mot n'est pas dans son intitulé.

**Filtres** :

| Filtre | Valeurs | Défaut |
|---|---|---|
| Niveau | NIV3 … NIV8, plus « non renseigné » (196 fiches), multi-sélection | tous |
| Domaine NSF | 16 groupes, multi-sélection | tous |
| Couverture minimale | curseur 0–100 % | 50 % |

Les 196 fiches sans `nomenclature_europe_niveau` ne sont pas écartées : elles
forment une entrée « niveau non renseigné », cochée par défaut comme les autres.
Les exclure silencieusement reviendrait à masquer 4 % du catalogue au premier
usage du filtre.

**Résultats** : une carte par certification, deux barres. Compteur en tête,
remis à jour à chaque coche.

**Fiche** : panneau latéral. Intitulé, niveau, NSF, objectifs et contexte,
activités visées, blocs de compétences avec leur `liste_competences` intégrale.
Les compétences cochées par l'utilisateur sont **surlignées** dans les blocs —
c'est ce qui lui montre *pourquoi* la certification est remontée. Lien vers la
fiche officielle France compétences, seule faisant autorité pour une démarche
réelle.

**Transparence obligatoire** : le pied de résultats affiche en permanence
« 408 certifications accessibles par VAE ne sont pas listées : leurs blocs de
compétences n'ont pas pu être rattachés. » Les masquer sans le dire ferait
croire que le catalogue est complet.

**Non fait** : pas de framework, pas de build, pas de dépendance — la
contrainte du dépôt appliquée au front. Pas de responsive élaboré : sous
768 px, l'arbre passe en accordéon plein écran.

## Gestion des erreurs

Principe : **échouer bruyamment au build, dégrader gracieusement au navigateur.**

Le mode d'échec redouté n'est pas le crash, c'est la **page vide plausible** :
un `WHERE si_jury='Par expérience'` qui ne retourne rien parce que France
compétences a renommé la valeur produirait un `index.html` fonctionnel affichant
zéro certification.

`build_ihm.py` s'arrête, avec un message actionnable :

| Condition | Message |
|---|---|
| `rncp.sqlite3` absent | lancer `build_db.py` d'abord |
| Vue `certification_competence` absente | base construite avec `--no-taxonomie` |
| 0 fiche `si_jury='Par expérience'` | **liste les valeurs réellement présentes** |
| 0 certification VAE avec compétence | le mapping taxonomie est vide |
| `template.html` sans marqueurs d'injection | gabarit corrompu |
| Fichier généré > 25 Mo | avertissement, pas erreur (actuel ~16 Mo) |

La troisième ligne est la plus importante : le jour où l'export change, on saura
en une seconde si `Par expérience` est devenu `Par l'expérience`. Même esprit
que la capture de secours du parseur XML.

Côté navigateur :

- **`DecompressionStream` indisponible** : bandeau explicite avec les versions
  minimales, pas une page morte.
- **Fragment d'URL corrompu** (`#c=999,abc`) : indices invalides ignorés en
  silence. Un lien tronqué par un client mail ne doit pas produire un écran blanc.
- **Détail manquant pour une fiche** : la carte reste, le panneau affiche
  « détail indisponible » et le lien France compétences.
- **Zéro résultat** : distinguer « aucune compétence cochée » (invitation) de
  « vos filtres excluent tout » (proposer de baisser le seuil). Deux états vides,
  deux messages — sinon l'utilisateur croit que l'outil est cassé.

## Tests

**`tests/test_build_ihm.py`** — base SQLite synthétique, comme les fixtures
existantes :

- le filtre VAE retient `Par expérience`, rejette `En contrat d'apprentissage` ;
- une fiche sans compétence rattachée est exclue de l'index et comptée dans le
  compteur d'exclusion ;
- une fiche inactive est absente ;
- aller-retour gzip : le blob décompressé redonne exactement le JSON attendu ;
- chaque garde-fou lève bien, avec le bon message.

**`ihm/matcher.test.js`** — `node --test`, le moteur étant une fonction pure :
ordre de tri, les trois critères de départage, séparation métier/transversal,
seuil de couverture.

Cas de tri figés explicitement :

```
100 % 8/8 métier  passe devant  100 % 1/1 métier       (volume absolu)
100 % 2/2 métier  passe devant  100 % 2/2 transversal  (métier départage)
100 % 1/1         passe devant   80 % 4/5              (le taux prime)
```

La troisième est contre-intuitive et **assumée** : c'est la conséquence directe
de D2. Le test la fige pour que personne ne la « corrige » par mégarde.

Node est présent (v24) mais ne devient pas une dépendance dure : le test Python
appelle `node` s'il est sur le `PATH`, et lève `SkipTest` sinon — la convention
déjà retenue pour FTS5, où la fonctionnalité dégrade sans casser.

## Limites connues

- **1,0 % d'erreur franche** sur les rattachements bloc → compétence (mesuré par
  juge indépendant, IC95 ± 0,8). Sur 27 237 blocs, ~270 sont mal classés. Suffisant
  pour orienter, insuffisant pour décider seul d'une démarche VAE — d'où le lien
  systématique vers la fiche officielle.
- **408 certifications VAE** (8 %) sans compétence rattachée, invisibles pour le
  matching, signalées dans l'IHM.
- **Médiane de 4 compétences** par certification : le taux de couverture est un
  signal grossier, pas une mesure fine. Un « 75 % » signifie souvent « 3 sur 4 ».
- **La VAE réelle ne se décide pas sur un taux de couverture.** Recevabilité,
  durée d'expérience, jury : rien de tout cela n'est modélisé. L'outil oriente
  vers des candidats plausibles, il ne présume d'aucune décision.
