// Simulation reproductible du tirage du quiz.
//   node tests/draw_sim.js [pool.json] [--draws 2000] [--n 15] [--seed 1] [--prio "Thème A,Thème B"]
// Sans pool.json, utilise un pool synthétique déséquilibré (le cas le plus défavorable pour un tirage au hasard).
// Écrit un JSON sur la sortie standard : répartition moyenne par bloc / thème / polarité, avec le tirage équilibré
// (drawQuiz) comparé à un tirage au hasard simple (témoin). Utilisé par tests/test_draw.py.
const fs = require('fs'), path = require('path');
const { drawQuiz, shuffle, rng } = require(path.join(__dirname, '..', 'pipeline', 'templates', 'draw.js'));
const args = process.argv.slice(2), opt = { draws: 2000, n: 15, seed: 1, prio: [] }, files = [];
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--draws') opt.draws = +args[++i]; else if (args[i] === '--n') opt.n = +args[++i];
  else if (args[i] === '--seed') opt.seed = +args[++i]; else if (args[i] === '--prio') opt.prio = args[++i].split(',').filter(Boolean);
  else files.push(args[i]);
}
function synthetic() {
  const cats = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'], blocs = ['gouvernement', 'gouvernement', 'gouvernement', 'gauche', 'gauche', 'centre', 'droite', 'autre'];
  const pool = []; let n = 1;
  cats.forEach((c, i) => { const k = i === 0 ? 14 : 4; for (let j = 0; j < k; j++, n++) pool.push({ n, cat: c, bloc: blocs[(n * 7 + i) % blocs.length], pol: n % 4 === 0 ? 'remove' : 'adopt' }); });
  return pool;
}
const pool = files.length ? JSON.parse(fs.readFileSync(files[0], 'utf8')) : synthetic();
const byN = {}; pool.forEach(q => byN[q.n] = q);
const keys = ['cat', 'bloc', 'pol'];
function tally(draws) {
  const t = { cat: {}, bloc: {}, pol: {} }, maxCat = [], seen = new Set();
  draws.forEach(d => {
    const per = {};
    d.forEach(n => { const q = byN[n]; seen.add(n); keys.forEach(k => { const v = q[k] || '?'; t[k][v] = (t[k][v] || 0) + 1; }); per[q.cat] = (per[q.cat] || 0) + 1; });
    maxCat.push(Math.max(...Object.values(per)));
  });
  const tot = draws.length * draws[0].length, out = { maxCatPerDraw: { mean: maxCat.reduce((a, b) => a + b, 0) / maxCat.length, max: Math.max(...maxCat) }, coverage: seen.size / pool.length };
  keys.forEach(k => { out[k] = {}; Object.keys(t[k]).sort().forEach(v => out[k][v] = t[k][v] / tot); });
  return out;
}
const r = rng(opt.seed), A = [], B = [];
for (let i = 0; i < opt.draws; i++) {
  A.push(drawQuiz(pool, { n: opt.n, prio: opt.prio, rand: r }));
  B.push(shuffle(pool.map(q => q.n), r).slice(0, opt.n));
}
const share = k => { const o = {}; pool.forEach(q => o[q[k] || '?'] = (o[q[k] || '?'] || 0) + 1); Object.keys(o).forEach(v => o[v] /= pool.length); return o; };
const spread = (s) => { const v = Object.values(s); return Math.max(...v) - Math.min(...v); };
const bal = tally(A), naive = tally(B);
const prioShare = opt.prio.length ? A.reduce((s, d) => s + d.filter(n => opt.prio.includes(byN[n].cat)).length, 0) / (opt.draws * opt.n) : null;
console.log(JSON.stringify({
  options: opt, pool: { n: pool.length, cat: share('cat'), bloc: share('bloc'), pol: share('pol') },
  equilibre: bal, temoin_hasard: naive,
  ecart_bloc: { equilibre: spread(bal.bloc), temoin_hasard: spread(naive.bloc), pool: spread(share('bloc')) },
  ecart_pol: { equilibre: spread(bal.pol), temoin_hasard: spread(naive.pol) },
  taille_ok: A.every(d => d.length === Math.min(opt.n, pool.length) && new Set(d).size === d.length), prio_share: prioShare
}, null, 1));
