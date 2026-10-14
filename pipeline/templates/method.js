/* ---------- Page Méthode ----------
   Tout chiffre vient de METHOD (injecté par build_site.py depuis curated.json, content/questions et content/jev_summary.json).
   Le texte ci-dessous est de la mise en forme et de l'explication ; il ne contient aucun chiffre du pipeline. */
const MC = METHOD.curated_info || {}, MF = METHOD.fiches || {}, MP = METHOD.pool || {}, MJ = METHOD.jev;
const nf = n => Number(n).toLocaleString('fr-FR');
const pct1 = (a, b) => b ? Math.round(a / b * 100) : 0;
const BLOC_NAME = { gouvernement: 'Gouvernement', gauche: 'Gauche', centre: 'Centre', droite: 'Droite', autre: 'Autre ou non attribuée' };
const BLOC_ORDER = ['gouvernement', 'gauche', 'centre', 'droite', 'autre'];
const TYPE_NAME = { 'proposition de loi': 'Proposition de loi', 'projet de loi': 'Projet de loi', 'résolution': 'Résolution', 'budget': 'Budget', 'constitutionnel/organique': 'Constitution ou loi organique' };
const TYPE_DEF = { 'proposition de loi': 'texte déposé par des députés ou des sénateurs', 'projet de loi': 'texte déposé par le gouvernement', 'résolution': 'prise de position, sans force de loi', 'budget': 'lois de finances et de financement de la Sécurité sociale', 'constitutionnel/organique': 'textes qui touchent aux règles de base des institutions' };
const bcol = b => `var(--b-${BLOC_NAME[b] ? b : 'autre'})`;
const FUNNEL_TITLES = ['Tout ce qui a été discuté', 'Soumis à un vote public', 'Avec un vote facile à comprendre', 'Retenus pour le quiz'];
const INDIC = { orateurs: 'le nombre de personnes qui ont pris la parole', interventions: 'le nombre de prises de parole', duree_min: 'la durée du débat', mots: 'le nombre de mots prononcés' };
const hours = m => m >= 90 ? `${nf(Math.round(m / 60))} h` : `${nf(Math.round(m))} min`;
const msec = (id, no, title, lead, body) => `<section class="msec" id="${id}" aria-labelledby="${id}-h"><h2 id="${id}-h"><span class="no" aria-hidden="true">${no}</span>${title}</h2>${lead ? `<p class="lead">${lead}</p>` : ''}${body}</section>`;

/* 1. Sujets */
function mFunnel() {
  const E = MC.entonnoir || []; if (!E.length) return '';
  const mx = Math.max(...E.map(e => e[1])), last = E[E.length - 1][1], named = E.length === FUNNEL_TITLES.length;
  return `<div class="mcard"><h3>De tout ce qui s’est discuté à ${nf(last)} sujets</h3><div class="funnel obs">${E.map((e, i) => `<div class="fstep"><div class="top"><span class="num">${nf(e[1])}</span><span class="ttl">${esc(named ? FUNNEL_TITLES[i] : e[0])}</span></div>
    <div class="ftrack" aria-hidden="true"><i style="--w:${Math.max(1.5, e[1] / mx * 100).toFixed(1)}%;--i:${i}"></i></div><div class="cap">${esc(e[0])}</div>${i ? `<div class="drop">− ${nf(E[i - 1][1] - e[1])} écartés à cette étape</div>` : ''}</div>`).join('')}</div>
    <p class="small muted">Environ un sujet sur ${nf(Math.round(E[0][1] / (last || 1)))} est retenu. Chaque étape est comptée, et la liste complète est publique (plus bas).</p></div>`;
}
function mCriteria() {
  const ind = (MC.indicateurs || []).map(k => INDIC[k]).filter(Boolean), ref = (MC.refuses_par_plafond || []).length;
  const li = (ic, t, d) => `<li><span class="ic" aria-hidden="true">${ic}</span><div><b>${t}</b><span class="d">${d}</span></div></li>`;
  return `<div class="mcard"><h3>Les critères, en clair</h3><ul class="crit">
    ${li('🗳️', 'Il y a eu un vote public', 'On part des textes qui ont donné lieu à au moins un vote public. Les traités à ratifier sont écartés : ce ne sont pas des choix de société lisibles en une question.')}
    ${li('🧭', 'Le sens du vote est certain', '« Pour » doit vouloir dire sans ambiguïté adopter ou supprimer. Dans le doute, on écarte.')}
    ${MC.min_votants != null ? li('👥', `Au moins ${nf(MC.min_votants)} députés ont voté`, 'Pour que le résultat compte vraiment.') : ''}
    ${MC.min_div != null ? li('⚖️', 'Les groupes ne votent pas tous pareil', `Indice de désaccord d’au moins ${String(MC.min_div).replace('.', ',')} (0 : tout le monde d’accord, 1 : moitié-moitié). Un vote sur lequel tous sont d’accord ne t’apprend rien.`) : ''}
    ${ind.length ? li('🎤', 'Le texte a compté au Parlement', `On mesure ${ind.join(', ')}. Le classement se fait à la fois sur tous les textes et à l’intérieur de chaque type de texte, pour ne pas favoriser les textes du gouvernement.`) : ''}
    ${MC.cap_bloc != null ? li('🧮', `Pas plus de ${nf(MC.cap_bloc)} sujets de la même origine`, ref ? `Sur ${nf(MC.n_cible)} places, ce plafond a écarté ${nf(ref)} sujet${ref > 1 ? 's' : ''}.` : `Sur ${nf(MC.n_cible)} places, aucune origine n’a atteint le plafond : il n’a écarté aucun sujet cette fois.`) : ''}
    ${li('1️⃣', 'Un seul vote par texte', 'Le vote sur l’ensemble du texte s’il existe, sinon le vote qui divise le plus.')}</ul></div>`;
}
function mDist() {
  const R = MC.repartition; if (!R) return '';
  const mode = R[state.mtab] ? state.mtab : 'bloc', data = R[mode];
  const pops = [['univers', 'Tous les dossiers'], ['eligibles', 'Avec un vote lisible'], ['selection', 'Retenus']].filter(p => data[p[0]]);
  const keys = mode === 'bloc' ? BLOC_ORDER.filter(k => pops.some(p => data[p[0]][k])) : Object.keys(data.univers || data.selection).sort((a, b) => (data.univers || data.selection)[b] - (data.univers || data.selection)[a]);
  const col = (k, i) => mode === 'bloc' ? bcol(k) : `var(--t${i % 5 + 1})`, nm = k => mode === 'bloc' ? BLOC_NAME[k] || k : TYPE_NAME[k] || k;
  const tot = p => keys.reduce((s, k) => s + (data[p][k] || 0), 0);
  const label = (p) => keys.map(k => `${nm(k)} : ${nf(data[p][k] || 0)}`).join(', ');
  const def = METHOD.bloc_def || {};
  return `<div class="mcard"><h3>Est-ce que la sélection penche d’un côté ?</h3>
    <p class="small muted">On compare trois populations : tout ce qui a été voté, ce qui est éligible, et ce qui est retenu.</p>
    <div class="mseg" role="group" aria-label="Regrouper par">${R.bloc ? `<button data-act="mtab" data-v="bloc" aria-pressed="${mode === 'bloc'}">Origine du texte</button>` : ''}${R.type ? `<button data-act="mtab" data-v="type" aria-pressed="${mode === 'type'}">Type de texte</button>` : ''}</div>
    <div class="dist obs">${pops.map((p, r) => { const T = tot(p[0]) || 1; return `<div class="drow"><div class="lab"><b>${p[1]}</b><span>${nf(tot(p[0]))} sujets</span></div>
      <div class="stack" role="img" aria-label="${esc(p[1] + ' : ' + label(p[0]))}">${keys.map((k, i) => `<i style="--c:${col(k, i)};--w:${((data[p[0]][k] || 0) / T * 100).toFixed(2)}%;--i:${i + r * 2}"></i>`).join('')}</div></div>`; }).join('')}</div>
    <div class="dlegend">${keys.map((k, i) => `<span style="--c:${col(k, i)}">${esc(nm(k))}</span>`).join('')}</div>
    <table class="dtable"><caption class="fine" style="text-align:left;caption-side:bottom;padding-top:6px">Nombre de sujets, et part de la population.</caption><thead><tr><th scope="col">${mode === 'bloc' ? 'Origine' : 'Type'}</th>${pops.map(p => `<th scope="col">${p[1].replace('Tous les dossiers', 'Tous').replace('Avec un vote lisible', 'Éligibles')}</th>`).join('')}</tr></thead>
    <tbody>${keys.map(k => `<tr><td>${esc(nm(k))}</td>${pops.map(p => `<td>${nf(data[p[0]][k] || 0)} · ${pct1(data[p[0]][k] || 0, tot(p[0]))} %</td>`).join('')}</tr>`).join('')}</tbody></table>
    ${mode === 'bloc' ? `<details><summary>Qu’est-ce que « l’origine du texte » ?</summary><div class="body"><p class="small">C’est le camp de celui qui a déposé le texte. Un projet de loi vient du gouvernement. Pour une proposition de loi, on prend le groupe du député qui l’a le plus souvent signée.${Object.keys(def).length ? ' Le classement des groupes est un choix de méthode, donc discutable :' : ''}</p>
      ${Object.keys(def).length ? `<ul class="m small">${BLOC_ORDER.filter(b => def[b] && def[b].length).map(b => `<li><b>${BLOC_NAME[b]}</b> : ${def[b].map(esc).join(', ')}</li>`).join('')}</ul>` : ''}<p class="small muted">Cette information n’apparaît jamais pendant le quiz.</p></div></details>`
      : `<details><summary>Que veulent dire ces types ?</summary><div class="body"><ul class="m small">${keys.map(k => `<li><b>${esc(nm(k))}</b> : ${esc(TYPE_DEF[k] || '')}</li>`).join('')}</ul></div></details>`}</div>`;
}
function mNot() {
  const L = MC.limites || []; if (!L.length) return '';
  return `<div class="callout not"><h3>Ce que cette sélection ne mesure pas</h3><ul>${L.map(l => `<li>${esc(l)}</li>`).join('')}</ul></div>`;
}
function mItemWhy(it) {
  const s = it.signaux || {}, bits = [];
  if (s.orateurs != null) bits.push(`${nf(s.orateurs)} orateurs`);
  if (s.interventions != null) bits.push(`${nf(s.interventions)} interventions`);
  if (s.duree_min != null) bits.push(`${hours(s.duree_min)} de débat`);
  if (it.votants != null) bits.push(`${nf(it.votants)} votants au scrutin retenu`);
  return bits.join(' · ');
}
function mList() {
  const items = METHOD.items || []; if (!items.length) return '';
  const f = state.mfilter, shown = items.filter(it => f === 'all' || (f === 'quiz' ? it.in_quiz : !it.in_quiz));
  const nq = items.filter(i => i.in_quiz).length, st = it => it.in_quiz ? ['on', 'Dans le quiz (non relue)'] : it.fiche === 'blocked' ? ['off', 'Fiche bloquée'] : it.fiche ? ['off', 'Fiche hors quiz'] : ['off', 'Fiche à écrire'];
  return `<div class="mcard"><button class="mbtn" data-act="mlist" aria-expanded="${state.mopen}" aria-controls="mlist"><span>Voir les ${nf(items.length)} sujets et pourquoi ils sont là</span><span class="chev" aria-hidden="true">▾</span></button>
    ${state.mopen ? `<div id="mlist" style="display:flex;flex-direction:column;gap:10px"><div class="mfilt" role="group" aria-label="Filtrer">${[['all', `Tous (${nf(items.length)})`], ['quiz', `Dans le quiz (${nf(nq)})`], ['no', `Pas encore (${nf(items.length - nq)})`]].map(a => `<button data-act="mfilter" data-v="${a[0]}" aria-pressed="${f === a[0]}">${a[1]}</button>`).join('')}</div>
    <ol class="mlist" style="list-style:none;padding:0">${shown.map(it => { const s = st(it); return `<li class="mi"><span class="r">${it.rang}</span><div><b>${esc(it.titre)}</b><div class="tags"><span class="mtag">${esc(TYPE_NAME[it.type] || it.type || '')}</span><span class="mtag bloc" style="--c:${bcol(it.bloc)}">${esc(BLOC_NAME[it.bloc] || it.bloc || '')}</span><span class="mtag ${s[0]}">${s[1]}</span></div><div class="why">Retenu parce que : ${esc(mItemWhy(it))}. Vote du ${fmtD(it.date)}.</div></div></li>`; }).join('')}</ol></div>` : ''}</div>`;
}
function sujets() {
  if (!METHOD.curated) return msec('m-sujets', 1, 'Comment on choisit les sujets', '', `<div class="callout warn"><h3>Sélection transparente indisponible</h3><p class="small">Le fichier de sélection (content/curated.json) est absent de cette version. Le quiz propose donc toutes les fiches disponibles (${nf(MP.n)}), sans critères d’importance ni plafond par origine.</p></div>`);
  return msec('m-sujets', 1, 'Comment on choisit les sujets', 'Pas au feeling : des règles publiques, appliquées à toutes les données de la législature, et comptées à chaque étape.', mFunnel() + mCriteria() + mDist() + mNot() + mList());
}

/* 2. Fiches */
function stageCard(h, n, cls) { return `<span class="num-chip ${cls || ''}"><b>${nf(n)}</b> ${h}</span>`; }
function fiches() {
  const S = MF.par_statut || {}, B = MF.bloquees_par_etape || {}, C = MF.controles || {}, redigees = Math.max(0, MF.fiches - (S.legacy || 0) - (B.sources || 0));
  const plural = (n, a, b) => n > 1 ? b : a;
  const humans = MF.relues === 0
    ? `<div class="callout warn"><h3>À dire franchement</h3><p><b>Les fiches sont rédigées par une IA et n’ont été relues par aucun humain.</b> C’est pourquoi chaque fiche porte l’étiquette « non relue ». Elle ne disparaît que lorsque deux relecteurs de sensibilités opposées ont validé le texte.</p></div>`
    : `<div class="callout warn"><h3>À dire franchement</h3><p>Les fiches sont rédigées par une IA. <b>${nf(MF.relues)} seulement ont été relues</b> par des humains ; les autres portent l’étiquette « non relue ».</p></div>`;
  const nm = (k, t, sub, ok, n) => `<div class="sc2"><span class="nm">${t}</span><span class="vl">${n ? `<b>${nf(n)}</b> bloquée${n > 1 ? 's' : ''}` : 'aucune bloquée'}</span><span class="sub">${sub}</span></div>`;
  const steps = [
    ['📚', 'Sources officielles', 'Pour chaque sujet, on rassemble les pages officielles (Assemblée nationale, Parlement). La fiche n’a le droit de s’appuyer que sur ces extraits.',
      stageCard('sujets à documenter', MF.sujets) + (MF.sans_fiche ? stageCard(`sans fiche pour l’instant`, MF.sans_fiche, 'wait') : '') + stageCard(`bloqué${plural(B.sources || 0, '', 's')} : sources insuffisantes`, B.sources || 0, B.sources ? 'stop' : 'go')],
    ['✍️', 'Rédaction par une IA', 'Une IA (Claude) écrit le résumé, les arguments pour et contre et l’accroche, à partir des seuls extraits. Elle n’a pas le droit d’ajouter un chiffre ou un fait de mémoire.',
      stageCard(`fiche${plural(redigees, '', 's')} rédigée${plural(redigees, '', 's')} dans cette chaîne`, redigees) + (MF.legacy_sans_controles ? stageCard(`fiche${plural(MF.legacy_sans_controles, '', 's')} héritée${plural(MF.legacy_sans_controles, '', 's')} du prototype, sans ces contrôles`, MF.legacy_sans_controles, 'wait') : '')],
    ['🔎', 'Contrôles automatiques', 'Quatre barrières, dans cet ordre. Une seule qui échoue, et la fiche est bloquée : elle ne sera jamais affichée.',
      `<div class="subchecks">${nm('sens', 'Le sens du vote', 'Le bouton « Pour » veut-il bien dire ce que la fiche annonce ? (règles puis second contrôle)', 0, B.sens || 0)}
      ${nm('neutralite', 'La neutralité, notée de 0 à 5', `Un second modèle note l’orientation du texte (0 : neutre, 5 : très orienté). Seuil : ${nf(MF.seuil_neutralite)} au plus.${MF.note_neutralite_moyenne != null ? ` Note moyenne des fiches notées : ${String(MF.note_neutralite_moyenne).replace('.', ',')} sur ${nf(MF.note_neutralite_n)} fiche${MF.note_neutralite_n > 1 ? 's' : ''}.` : ''}`, 0, B.neutralite || 0)}
      ${nm('pro_con', 'La pertinence des arguments pour et contre', `Chaque camp défend-il bien sa position, à poids égal ?${C.pro_con_non_evalue ? ` Pas encore évaluée sur ${nf(C.pro_con_non_evalue)} fiche${C.pro_con_non_evalue > 1 ? 's' : ''}.` : ''}`, 0, B.pro_con || 0)}
      ${nm('noms', 'Aucun nom de parti ni de personne', 'Contrôle par règles : sigles, noms de groupes, noms de députés.', 0, B.noms || 0)}</div>`
      + (B.format || B.autre ? `<div class="nums">${stageCard('bloquées pour une autre raison', (B.format || 0) + (B.autre || 0), 'stop')}</div>` : '')],
    ['👥', 'Relecture humaine croisée', `Deux relecteurs de sensibilités opposées (gauche et droite) doivent chacun valider. Si le texte change, les validations sont annulées.`,
      stageCard(`fiche${plural(MF.relues, '', 's')} relue${plural(MF.relues, '', 's')} à ce jour, sur ${nf(MF.fiches)}`, MF.relues, MF.relues ? 'go' : 'wait')],
    ['🚀', 'Publication', 'Seules les fiches qui ont franchi les barrières apparaissent dans le quiz. Tant qu’elles ne sont pas relues, elles portent l’étiquette « non relue ».',
      stageCard(`dans le quiz, relue${plural(S.published || 0, '', 's')}`, S.published || 0, 'go') + stageCard('dans le quiz, non relues', (S.pending_review || 0) + (S.legacy || 0), 'wait') + stageCard(`jamais affichée${plural(S.blocked || 0, '', 's')} (bloquée${plural(S.blocked || 0, '', 's')})`, S.blocked || 0, 'stop')]
  ];
  const seg = [['Relues', S.published || 0, 'var(--st-ok)'], ['Non relues, contrôles passés', S.pending_review || 0, 'var(--st-wait)'], ['Non relues, prototype', S.legacy || 0, 'color-mix(in srgb, var(--st-wait) 50%, var(--surface))'], ['Bloquées', S.blocked || 0, 'var(--st-no)'], ['Sans fiche', MF.sans_fiche || 0, 'var(--st-none)']];
  const T = seg.reduce((a, s) => a + s[1], 0) || 1;
  return msec('m-fiches', 2, 'Comment une fiche est fabriquée', 'Chaque fiche passe par une chaîne de contrôles. Voici les étapes, et combien de fiches ont été arrêtées à chacune.', humans +
    `<div class="mcard"><ol class="tl obs">${steps.map((s, i) => `<li class="ts ${i === 3 ? 'human' : ''}" style="--i:${i}"><span class="dot" aria-hidden="true">${s[0]}</span><div><h3>${s[1]}</h3><p>${s[2]}</p>${s[3] && s[3].startsWith('<div class="subchecks') ? s[3] : `<div class="nums">${s[3]}</div>`}</div></li>`).join('')}</ol></div>
    <div class="mcard bilan"><h3>Où en sont les ${nf(MF.sujets)} sujets ?</h3><div class="stack obs" role="img" aria-label="${esc(seg.map(s => s[0] + ' : ' + s[1]).join(', '))}">${seg.map((s, i) => `<i style="--c:${s[2]};--w:${(s[1] / T * 100).toFixed(2)}%;--i:${i}"></i>`).join('')}</div>
    <div class="dlegend">${seg.map(s => `<span style="--c:${s[2]}">${s[0]} : <b>${nf(s[1])}</b></span>`).join('')}</div>
    <p class="small muted">Chiffres lus directement dans les fiches (statut et contrôles). Les fiches « prototype » viennent de la première version du site : même IA, mais sans ces contrôles automatiques.</p></div>`);
}

/* 3. Présentation du quiz */
function simRun(runs) {
  const keyOf = (q, k) => q[k] || '?', n = state.nq, r = { bloc: {}, pol: {} };
  const base = { bloc: {}, pol: {} }, mine = { bloc: {}, pol: {} };
  POOL.forEach(q => ['bloc', 'pol'].forEach(k => base[k][keyOf(q, k)] = (base[k][keyOf(q, k)] || 0) + 1));
  const naive = { bloc: {}, pol: {} };
  for (let i = 0; i < runs; i++) {
    const a = drawQuiz(POOL, { n, prio: [] }), b = shuffle(POOL.map(q => q.n), Math.random).slice(0, a.length);
    a.forEach(x => ['bloc', 'pol'].forEach(k => { const v = keyOf(byN[x], k); mine[k][v] = (mine[k][v] || 0) + 1; }));
    b.forEach(x => ['bloc', 'pol'].forEach(k => { const v = keyOf(byN[x], k); naive[k][v] = (naive[k][v] || 0) + 1; }));
  }
  const tot = Math.min(n, POOL.length) * runs;
  ['bloc', 'pol'].forEach(k => { Object.keys(base[k]).forEach(v => { base[k][v] /= POOL.length; mine[k][v] = (mine[k][v] || 0) / tot; naive[k][v] = (naive[k][v] || 0) / tot; }); });
  return { runs, n: Math.min(n, POOL.length), base, naive, mine };
}
function simView() {
  const S = state.sim; if (!S) return '';
  const POLN = { adopt: 'Pour adopter', remove: 'Pour supprimer ou rejeter' };
  const grp = (k, names, colf) => { const mx = Math.max(...['base', 'naive', 'mine'].flatMap(t => Object.values(S[t][k]))) || 1; return `<div class="sb"><div class="lab"><span>${k === 'bloc' ? 'Origine du texte' : 'Sens du bouton « pour »'}</span></div>${Object.keys(S.base[k]).sort((a, b) => k === 'bloc' ? BLOC_ORDER.indexOf(a) - BLOC_ORDER.indexOf(b) : a < b ? -1 : 1).map(v => `<div class="two"><div class="lab" style="font-weight:500"><span>${esc(names[v] || v)}</span></div>
    ${[['Dans le pool', S.base[k][v], 'ref'], ['Tirage au hasard', S.naive[k][v], 'ref'], ['Notre tirage', S.mine[k][v], '']].map(a => `<div class="ln ${a[2]}"><span>${a[0]}</span><i style="--c:${colf(v)};--w:${Math.max(2, a[1] / mx * 100).toFixed(1)}%${a[2] ? '' : ';opacity:1'}"></i><span>${Math.round(a[1] * 100)} %</span></div>`).join('')}</div>`).join('')}</div>`; };
  return `<div class="simbars" aria-live="polite"><p class="small muted">Résultat de ${nf(S.runs)} tirages de ${nf(S.n)} questions, faits à l’instant dans ton navigateur à partir des fiches du quiz.</p>${grp('bloc', BLOC_NAME, bcol)}${Object.keys(S.base.pol).length > 1 ? grp('pol', POLN, () => 'var(--accent)') : ''}</div>`;
}
function quizPres() {
  const pol = MP.pol || {}, both = (pol.adopt || 0) > 0 && (pol.remove || 0) > 0;
  const bi = (ic, t, d) => `<div class="bi"><span class="ic" aria-hidden="true">${ic}</span><div><b>${t}</b><span class="d">${d}</span></div></div>`;
  return msec('m-quiz', 3, 'Comment le quiz te présente les choses', 'La façon de poser une question peut influencer la réponse. Voici ce qu’on fait pour limiter ça.',
    `<div class="mcard"><h3>Les garde-fous</h3><div class="bias">
    ${bi('🎲', 'Un tirage équilibré par thème', `Les ${nf(state.nq)} questions sont tirées pour qu’aucun des ${nf(MP.n_cats)} thèmes ne domine. Tes thèmes prioritaires gardent la priorité : jusqu’à ${Math.round(DRAW_PRIO_SHARE * 100)} % des places, et ils pèsent double dans le score.`)}
    ${bi('🧩', 'Une origine des textes équilibrée', `Le tirage répartit aussi les questions entre les ${nf(MP.n_blocs || 1)} types d’origine (gouvernement, gauche, centre, droite, autre). Tu ne vois jamais cette origine pendant le quiz.`)}
    ${bi('🔀', 'Un mélange « adopter » et « supprimer »', both ? `Parmi les ${nf(MP.n)} fiches du quiz, ${nf(pol.adopt)} se votent « pour adopter » et ${nf(pol.remove)} « pour supprimer ou rejeter ». Le tirage les mélange, car on a tendance à répondre « oui » quand on hésite.` : `Aujourd’hui, les ${nf(MP.n)} fiches du quiz se votent toutes « pour adopter ». Le mélange avec des questions « pour supprimer ou rejeter » est prévu dans le tirage : il se mettra en route dès que de telles fiches existeront. En attendant, répondre « pour » à tout rapproche mécaniquement de la plupart des groupes.`)}
    ${bi('↕️', 'Un ordre aléatoire', 'Les questions arrivent dans un ordre aléatoire. Dans « Les arguments », le camp qui s’affiche en premier est tiré au sort pour chaque question, puis reste le même si tu rouvres.')}
    ${bi('🏷️', 'Des boutons explicites', 'Chaque bouton dit pour quoi ou contre quoi tu votes (« Pour l’interdiction de… »). Le sens est vérifié, car un amendement de suppression inverse le « pour ».')}
    ${bi('🙈', 'Aucun nom avant le résultat', 'Pas de nom de parti ni de personne pendant le quiz : tu juges la mesure, pas l’étiquette. L’hémicycle montre les votes à leur place réelle, sans étiquette.')}
    ${bi('👀', 'Les absents sont visibles', 'Un point vide est un député qui n’a pas voté. Le résultat dit combien étaient présents.')}
    ${bi('⚪', 'Les non-inscrits ne sont pas notés', 'Ils sont affichés dans l’hémicycle mais exclus du score : ils ne forment pas un groupe qui vote ensemble.')}</div></div>
    <div class="mcard"><h3>Teste le tirage</h3><p class="small">On compare un tirage au hasard simple et le nôtre, sur beaucoup de tirages. Plus la barre « Notre tirage » est homogène, plus le quiz est équilibré.</p>
    <button class="btn primary" data-act="sim">${state.sim ? 'Relancer la simulation' : 'Lancer la simulation'}</button>${simView()}</div>`);
}

/* 4. IA */
function iaStudy() {
  if (!MJ) return `<div class="study" role="status"><h3>Étude en cours</h3><p class="small">On mesure à quel point Jev se trompe, et dans quels cas. Les résultats seront publiés ici, avec le rapport complet. <span class="dots" aria-hidden="true"><i></i><i></i><i></i></span></p></div>`;
  return `<div class="study ready"><h3>${esc(MJ.titre || 'Étude sur Jev')}</h3>${MJ.lede ? `<p class="small">${esc(MJ.lede)}</p>` : ''}
    ${MJ.chiffres ? `<div class="kv">${MJ.chiffres.map(c => `<div><b>${esc(c.valeur)}</b>${esc(c.label)}${c.note ? `<br><span class="fine">${esc(c.note)}</span>` : ''}</div>`).join('')}</div>` : ''}
    ${MJ.verdict ? `<p><b>En clair :</b> ${esc(MJ.verdict)}</p>` : ''}${MJ.rapport_url ? `<a class="btn primary wide" style="display:grid;place-items:center;text-decoration:none" href="${esc(MJ.rapport_url)}" target="_blank" rel="noopener">Lire le rapport d’étude ↗</a>` : ''}</div>`;
}
function ia() {
  return msec('m-ia', 4, 'Et l’IA là-dedans ?', 'Deux IA différentes, avec deux métiers très différents.',
    `<div class="mcard"><div class="roles"><div class="role"><span class="verb">Rédige</span><span class="who">Claude</span><ul><li>Écrit le résumé, les arguments pour et contre, l’accroche.</li><li>Ne travaille qu’à partir des extraits de sources fournis.</li>${(MF.modeles || []).length ? `<li>Modèle utilisé : ${MF.modeles.map(esc).join(', ')}.</li>` : ''}</ul></div>
    <div class="role"><span class="verb">Classe et note</span><span class="who">Jev</span><ul><li>Choisit une catégorie, vérifie le sens du vote, note la neutralité de 0 à 5, juge si les arguments sont pertinents.</li><li>Ne rédige rien : il renvoie des probabilités, pas du texte.</li></ul></div></div>
    <p class="small muted">Une IA qui écrit peut se tromper ou pencher sans le vouloir. C’est pourquoi un autre modèle contrôle, que des règles simples vérifient les noms de partis, et qu’une relecture humaine croisée est prévue.</p></div>
    <div class="mcard"><h3>Peut-on se fier à Jev ?</h3>${iaStudy()}</div>`);
}

/* 5. Limites, sources, licence */
function limites() {
  const L = ['Les fiches sont rédigées par une IA et ne sont pas relues par des humains. Elles peuvent contenir des erreurs ou une orientation involontaire : chaque fiche renvoie au scrutin officiel pour vérifier.',
    'La sélection mesure l’importance au Parlement, pas dans l’opinion publique. Elle écarte les textes sur lesquels tout le monde est d’accord.',
    'Peu de députés votent à chaque scrutin : la position d’un groupe peut reposer sur très peu de voix.',
    'Une position de groupe est la tendance de ses députés présents. Un « contre » peut venir d’une seule mesure d’un long texte, ou d’une tactique. Les deux composantes du groupe UDR sont fusionnées.',
    'Un petit nombre de questions donne un signal, pas un verdict : un autre tirage peut donner un autre classement.',
    'L’hémicycle est schématique : l’ordre gauche-droite est réel, la géométrie exacte des rangées est simplifiée.',
    'Les promesses viennent d’articles de presse et d’un comparatif tiers, avec paraphrase. Plusieurs groupes (droite républicaine, UDR, LIOT) ne sont pas encore couverts.',
    'Les chiffres de présence mesurent la participation aux scrutins publics, pas le travail total d’un député (commissions, circonscription).',
    'Ce site n’est pas un site officiel de l’Assemblée nationale et ne donne aucune consigne de vote.'];
  const SRCS = Object.keys(SRC);
  return msec('m-limites', 5, 'Limites connues, sources et licence', '', `<div class="mcard"><h3>Ce qu’il faut garder en tête</h3><ul class="m small">${L.map(l => `<li>${esc(l)}</li>`).join('')}</ul></div>
    <div class="mcard"><h3>D’où viennent les données</h3><ul class="mlinks small"><li>Votes, sièges et députés : <a href="https://data.assemblee-nationale.fr" target="_blank" rel="noopener">data.assemblee-nationale.fr</a> (open data de l’Assemblée nationale, 17e législature).</li>
    <li>Licence : ${esc((METHOD.licence || '').split(' : ')[0])}${(METHOD.licence || '').includes('https://') ? ` — <a href="${esc((METHOD.licence.match(/https:\S+/) || [''])[0])}" target="_blank" rel="noopener">texte de la licence</a>` : ''}. Réutilisation libre à condition de citer la source et la date de mise à jour.</li>
    <li>Site généré le ${fmtD(METHOD.generated)}. Les données reprises sont aussi publiées dans <a href="data.json">data.json</a>.</li>
    ${SRCS.length ? `<li>Sources des promesses : ${SRCS.map(k => `<a href="${esc(SRC[k][1])}" target="_blank" rel="noopener">${esc(SRC[k][0])}</a>`).join(' ; ')}.</li>` : ''}
    <li>Code et méthode ouverts : <a href="https://github.com/lduf/hemicycle" target="_blank" rel="noopener">github.com/lduf/hemicycle</a>.</li></ul></div>`);
}

function viewMethod() {
  const S = MF.par_statut || {}, inQuiz = MP.n;
  return `${topbar()}<button class="link" data-act="back" style="align-self:flex-start">← Retour</button>
  <div class="mhero"><h1>Comment c’est <span class="hl">fait</span></h1><p>Pas de boîte noire : voici comment les sujets sont choisis, comment les fiches sont écrites, et comment on limite les biais.</p>
  <div class="mchips"><div><b>${nf(METHOD.curated ? MC.n : MP.n)}</b>${METHOD.curated ? 'sujets choisis par des règles publiques' : 'fiches dans le quiz'}</div><div><b>${nf(inQuiz)}</b>fiches dans le quiz aujourd’hui</div><div><b>${nf(MF.relues)}</b>fiche${MF.relues > 1 ? 's' : ''} relue${MF.relues > 1 ? 's' : ''} par un humain</div></div></div>
  <nav class="mnav" aria-label="Sections de la page">${[['m-sujets', '1 · Sujets'], ['m-fiches', '2 · Fiches'], ['m-quiz', '3 · Quiz'], ['m-ia', '4 · IA'], ['m-limites', '5 · Limites']].map(a => `<button data-act="msec" data-v="${a[0]}">${a[1]}</button>`).join('')}</nav>
  ${sujets()}${fiches()}${quizPres()}${ia()}${limites()}
  <button class="btn primary" data-act="back">← Retour</button>`;
}
function initMethod() {
  const els = document.querySelectorAll('.obs');
  if (!('IntersectionObserver' in window) || REDUCED.matches || state.still) { els.forEach(e => e.classList.add('in')); return; }
  const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } }), { threshold: .2 });
  els.forEach(e => io.observe(e));
}
