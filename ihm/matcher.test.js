const test = require('node:test');
const assert = require('node:assert');
const { matcher, inter, passeFiltres } = require('./matcher.js');

// competences : [id, libelle, idx_domaine, transversal, mots_cles]
//   0 oral (transversal), 1 web, 2 reseau, 3 chantier
const DATA = {
  domaines: ['Transversal', 'Numérique', 'Bâtiment'],
  competences: [
    ['oral', "S'exprimer à l'oral", 0, 1, 'oral'],
    ['web', 'Créer un site web', 1, 0, 'web'],
    ['reseau', 'Administrer un réseau', 1, 0, 'réseau'],
    ['chantier', 'Piloter un chantier', 2, 0, 'chantier'],
  ],
  nsf: [['32', 'Communication et information'], ['23', 'Génie civil']],
  certifs: [
    // [numero, intitule, niveau, [idx_nsf], [idx_comp]]
    ['A', 'Deux métiers', 'NIV6', [0], [1, 2]],
    ['B', 'Un seul métier', 'NIV5', [0], [1]],
    ['C', 'Deux transversales', 'NIV6', [0], [0]],
    ['D', 'Métier + transversal', 'NIV7', [0], [0, 1]],
    ['E', 'Bâtiment', 'NIV3', [1], [3]],
    ['F', 'Sans niveau', '', [0], [1, 2, 3]],
  ],
  exclues: 0,
};

const TOUT = { niveaux: null, nsf: null, seuil: 0 };

test('inter ne garde que les indices cochés', () => {
  assert.deepStrictEqual(inter([1, 2, 3], new Set([2, 3, 9])), [2, 3]);
  assert.deepStrictEqual(inter([1], new Set()), []);
});

test('le taux de couverture prime sur tout', () => {
  // B est 1/1 = 100 % ; A est 1/2 = 50 %
  const r = matcher(DATA, new Set([1]), TOUT);
  assert.strictEqual(r[0].certif[0], 'B');
  assert.strictEqual(r[0].couverture, 1);
});

test('à taux égal, le volume absolu départage', () => {
  // A = 2/2, B = 1/1 : les deux à 100 %, A a plus de volume
  const r = matcher(DATA, new Set([1, 2]), TOUT);
  assert.deepStrictEqual(r.slice(0, 2).map(x => x.certif[0]), ['A', 'B']);
});

test('à volume égal, le métier départage le transversal', () => {
  // coche oral(0) + web(1) : C = 1/1 transversal, B = 1/1 métier
  const r = matcher(DATA, new Set([0, 1]), TOUT);
  const cent = r.filter(x => x.couverture === 1 && x.nbCouvertes === 1);
  assert.deepStrictEqual(cent.map(x => x.certif[0]), ['B', 'C']);
});

test('métier et transversal sont comptés séparément', () => {
  const r = matcher(DATA, new Set([0, 1]), TOUT);
  const d = r.find(x => x.certif[0] === 'D');
  assert.deepStrictEqual(d.metier, [1, 1]);
  assert.deepStrictEqual(d.transv, [1, 1]);
  assert.strictEqual(d.couverture, 1);
});

test('le seuil exclut sous la barre, bornes incluses', () => {
  // coche web(1) : A = 1/2 = 0.5 exactement
  const strict = matcher(DATA, new Set([1]), { ...TOUT, seuil: 0.5 });
  assert.ok(strict.some(x => x.certif[0] === 'A'), 'seuil inclusif');
  const dur = matcher(DATA, new Set([1]), { ...TOUT, seuil: 0.51 });
  assert.ok(!dur.some(x => x.certif[0] === 'A'));
});

test('aucune coche : tout est à 0 % et le seuil 0.5 vide la liste', () => {
  assert.strictEqual(matcher(DATA, new Set(), { ...TOUT, seuil: 0.5 }).length, 0);
  assert.strictEqual(matcher(DATA, new Set(), TOUT).length, DATA.certifs.length);
});

test('filtre niveau, la chaîne vide étant un niveau à part entière', () => {
  const f = { ...TOUT, niveaux: new Set(['']) };
  const r = matcher(DATA, new Set([1]), f);
  assert.deepStrictEqual(r.map(x => x.certif[0]), ['F']);
});

test('filtre NSF : une certification passe si un seul de ses groupes matche', () => {
  const f = { ...TOUT, nsf: new Set([1]) };  // groupe "23"
  assert.deepStrictEqual(
    matcher(DATA, new Set([3]), f).map(x => x.certif[0]), ['E']);
});

test('passeFiltres avec filtres nuls laisse tout passer', () => {
  assert.ok(passeFiltres(DATA.certifs[0], TOUT));
});

test('une certification sans exigence est ignorée, pas une division par zéro', () => {
  const data = { ...DATA, certifs: [['Z', 'Vide', 'NIV6', [0], []]] };
  assert.deepStrictEqual(matcher(data, new Set([1]), TOUT), []);
});
