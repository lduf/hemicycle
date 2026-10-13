/* Tirage du quiz, le moins biaisé possible. Fonctions pures : aucun accès à la page, testables avec Node
   (tests/draw_sim.js, tests/test_draw.py). Inclus tel quel dans le template par build_site.py.

   Pool : [{ n, cat, bloc, pol }]
     cat  = thème ; bloc = origine politique du texte (gouvernement, gauche, centre, droite, autre ; jamais affichée pendant le quiz) ;
     pol  = 'adopt' (« Pour adopter ») ou 'remove' (« Pour supprimer / rejeter »).

   Règle : on choisit les questions une à une ; à chaque pas, on prend la question qui rend la sélection la plus équilibrée
   (thème d'abord, puis origine, puis polarité), avec un tirage aléatoire pour départager. Les thèmes prioritaires de
   l'utilisateur gardent leur logique : jusqu'à 60 % des places leur sont réservées, tirées avec la même règle d'équilibre.
   Ensuite l'ordre final est mélangé. */

function rng(seed) { let a = seed >>> 0; return () => { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function shuffle(arr, seed) { const r = typeof seed === 'function' ? seed : rng(seed); for (let i = arr.length - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [arr[i], arr[j]] = [arr[j], arr[i]]; } return arr; }

const DRAW_PRIO_SHARE = 0.6;
function drawQuiz(pool, o) {
  o = o || {};
  const rand = o.rand || Math.random, prio = o.prio || [], already = o.already || [];
  const want = Math.min(o.n == null ? 15 : o.n, pool.length - already.length);
  const share = o.prioShare == null ? DRAW_PRIO_SHARE : o.prioShare;
  const byN = {}; pool.forEach(q => byN[q.n] = q);
  const nOf = f => new Set(pool.map(f)).size;
  const nc = nOf(q => q.cat), nb = nOf(q => q.bloc || '?'), np = nOf(q => q.pol || '?');
  const K = want + already.length;
  const cnt = { cat: {}, bloc: {}, pol: {} };
  const add = q => { [['cat', q.cat], ['bloc', q.bloc || '?'], ['pol', q.pol || '?']].forEach(([k, v]) => cnt[k][v] = (cnt[k][v] || 0) + 1); };
  already.forEach(n => byN[n] && add(byN[n]));
  const taken = new Set(already), out = [];
  const cost = q => (cnt.cat[q.cat] || 0) / Math.max(1, K / nc) + (cnt.bloc[q.bloc || '?'] || 0) / Math.max(1, K / nb)
    + (np > 1 ? 0.7 * (cnt.pol[q.pol || '?'] || 0) / Math.max(1, K / np) : 0) + rand() * 0.35;
  function take(cands, k) {
    for (let i = 0; i < k; i++) {
      let best = null, bc = Infinity;
      for (const q of cands) { if (taken.has(q.n)) continue; const c = cost(q); if (c < bc) { bc = c; best = q; } }
      if (!best) return;
      taken.add(best.n); out.push(best.n); add(best);
    }
  }
  const kp = prio.length ? Math.min(Math.round(want * share), pool.filter(q => prio.includes(q.cat) && !taken.has(q.n)).length) : 0;
  take(pool.filter(q => prio.includes(q.cat)), kp);
  take(pool, want - out.length);
  return shuffle(out, rand);
}

/* Ordre d'affichage « arguments en faveur / en défaveur » : tiré une fois par question puis mémorisé par l'appelant. */
function argFirst(memo, n, rand) { if (!(n in memo)) memo[n] = (rand || Math.random)() < 0.5 ? 'pro' : 'con'; return memo[n]; }

if (typeof module !== 'undefined' && module.exports) module.exports = { DRAW_PRIO_SHARE, drawQuiz, shuffle, rng, argFirst };
