// Moteur de matching : fonction pure, sans DOM et sans variable globale.
// Ce fichier est injecté verbatim dans index.html : le code testé sous
// `node --test` est exactement le code livré au navigateur.

function inter(indices, coches) {
  return indices.filter(i => coches.has(i));
}

function passeFiltres(certif, filtres) {
  if (filtres.niveaux && !filtres.niveaux.has(certif[2])) return false;
  if (filtres.nsf && !certif[3].some(g => filtres.nsf.has(g))) return false;
  return true;
}

// data    : l'index (voir build_ihm.construire_index)
// coches  : Set d'indices de compétences cochées
// filtres : {niveaux: Set|null, nsf: Set|null, seuil: number dans [0,1]}
function matcher(data, coches, filtres) {
  const estTransversal = i => data.competences[i][3] === 1;

  return data.certifs
    .filter(c => c[4].length > 0 && passeFiltres(c, filtres))
    .map(c => {
      const req = c[4];
      const metier = req.filter(i => !estTransversal(i));
      const transv = req.filter(i => estTransversal(i));
      const couvertes = inter(req, coches);
      return {
        certif: c,
        couverture: couvertes.length / req.length,
        nbCouvertes: couvertes.length,
        metier: [inter(metier, coches).length, metier.length],
        transv: [inter(transv, coches).length, transv.length],
      };
    })
    .filter(r => r.couverture >= filtres.seuil)
    .sort((a, b) =>
      b.couverture - a.couverture ||
      b.nbCouvertes - a.nbCouvertes ||
      b.metier[0] - a.metier[0]);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { matcher, inter, passeFiltres };
}
