"""Rapport : REPORT.md + graphiques SVG + summary.json, générés uniquement depuis les réponses brutes."""
import json, os
from pipeline import classify, config as HC
from . import config as C, hemicycle as H, metrics as M

P = C.PREREG
SCN = {"categorie": "Catégorie d'une fiche", "sens": "Sens du vote (bouton « Pour … »)", "neutralite": "Neutralité (note d'orientation)",
       "pro_contre": "Pertinence des arguments pour / contre"}
GRP = {"orig": "fiche d'origine", "pour": "réécrite orientée POUR", "contre": "réécrite orientée CONTRE", "subtil": "réécrite, cadrage léger",
       "permutes": "arguments pour/contre permutés", "contre_tronque": "« contre » tronqué (6 mots)", "contre_d_une_autre_mesure": "« contre » d'une autre mesure"}


def f(x, nd=3):
    return "–" if x is None or (isinstance(x, float) and x != x) else f"{x:.{nd}f}"


def pc(x, nd=1):
    return "–" if x is None or (isinstance(x, float) and x != x) else f"{100 * x:.{nd}f} %"


def usd(x):
    if x is None or (isinstance(x, float) and x != x):
        return "–"
    return f"{x:.6f} $" if x < 0.01 else f"{x:.4f} $"


def rc(r):
    """Taux avec intervalle de Wilson : « 3,3 % [1,0 – 10,3] (2/60) »."""
    if not r or not r.get("n"):
        return "–"
    return f"{pc(r['p'])} [{100 * r['ci'][0]:.1f} – {100 * r['ci'][1]:.1f}] ({r['k']}/{r['n']})"


def sysname(s):
    return s if s == "jev" else s.split(" (")[0]


def _w(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# ---------- SVG ----------
def svg_decisions(R, path):
    """FAR et FRR par scénario et par système, avec intervalles et limite de sûreté."""
    sc = [s for s in C.SAFETY if R["decisions"].get(s)]
    systems = sorted({s for s in sc for s in R["decisions"][s]}, key=lambda x: (x != "jev", x))
    if not sc:
        return
    cols = ["#2563eb", "#dc2626", "#16a34a", "#9333ea"]
    rowh, W = 17, 780
    H_ = 44 + len(sc) * 2 * (len(systems) * rowh + 22)
    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H_}" font-family="sans-serif" font-size="11"><rect width="{W}" height="{H_}" fill="white"/>',
         f'<text x="{W / 2}" y="16" text-anchor="middle" font-weight="bold">Erreurs de décision (intervalle de confiance à 95 %) — plus bas = mieux</text>']
    x0, x1 = 250, W - 20
    mx = 0.5
    sx = lambda v: x0 + min(v, mx) / mx * (x1 - x0)
    for t in (0, .1, .2, .3, .4, .5):
        g.append(f'<line x1="{sx(t)}" y1="26" x2="{sx(t)}" y2="{H_ - 8}" stroke="#eee"/><text x="{sx(t)}" y="{H_ - 0}" text-anchor="middle">{t:.0%}</text>')
    y = 38
    for s_ in sc:
        for metric, lab in (("far", "fausses acceptations (un défaut passe)"), ("frr", "faux rejets (une bonne entrée est refusée)")):
            g.append(f'<text x="8" y="{y + 4}" font-weight="bold">{SCN[s_][:30]} — {lab[:24]}</text>')
            lim = C.SAFETY[s_][metric]
            g.append(f'<line x1="{sx(lim)}" y1="{y - 8}" x2="{sx(lim)}" y2="{y + len(systems) * rowh}" stroke="#f59e0b" stroke-width="2" stroke-dasharray="4"><title>limite {lim:.0%}</title></line>')
            for k, sy in enumerate(systems):
                d = (R["decisions"][s_].get(sy) or {}).get(metric)
                if d and d["n"]:
                    g.append(f'<line x1="{sx(d["ci"][0])}" y1="{y + k * rowh}" x2="{sx(d["ci"][1])}" y2="{y + k * rowh}" stroke="{cols[k % 4]}" stroke-width="2"/>')
                    g.append(f'<circle cx="{sx(d["p"])}" cy="{y + k * rowh}" r="4" fill="{cols[k % 4]}"/>')
                if metric == "far" and s_ == sc[0]:
                    g.append(f'<text x="{W - 6}" y="{y + k * rowh + 4}" text-anchor="end" fill="{cols[k % 4]}" font-size="10">{sysname(sy)[:26]}</text>')
            y += len(systems) * rowh + 22
    g.append("</svg>")
    _w(path, "\n".join(g))


def svg_latency(samples, path):
    W, H_, pad = 460, 300, 44
    allv = [v for xs in samples.values() for v in xs]
    if not allv:
        return
    hi = M.percentile(allv, 99) or 1
    cols = ["#2563eb", "#dc2626", "#16a34a", "#9333ea"]
    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H_}" font-family="sans-serif" font-size="11"><rect width="{W}" height="{H_}" fill="white"/>',
         f'<text x="{W / 2}" y="16" text-anchor="middle" font-weight="bold">Latence : distribution cumulée (appels de production, en série)</text>']
    sx = lambda v: pad + min(1, v / hi) * (W - pad - 12)
    sy = lambda v: H_ - pad - v * (H_ - pad - 28)
    g.append(f'<line x1="{pad}" y1="{sy(0)}" x2="{W - 12}" y2="{sy(0)}" stroke="#444"/><line x1="{pad}" y1="{sy(0)}" x2="{pad}" y2="{sy(1)}" stroke="#444"/>')
    for t in (0, .5, .95, 1):
        g.append(f'<text x="{pad - 4}" y="{sy(t) + 4}" text-anchor="end">{t:g}</text>')
    for t in (0, .25, .5, .75, 1):
        g.append(f'<text x="{sx(hi * t)}" y="{H_ - 28}" text-anchor="middle">{hi * t:.2f}s</text>')
    for k, (name, xs) in enumerate(sorted(samples.items(), key=lambda kv: (kv[0] != "jev", kv[0]))):
        xs = sorted(xs)
        pts = " ".join(f"{sx(v):.1f},{sy((i + 1) / len(xs)):.1f}" for i, v in enumerate(xs))
        g.append(f'<polyline fill="none" stroke="{cols[k % 4]}" stroke-width="2" points="{pts}"/>')
        g.append(f'<text x="{W - 14}" y="{40 + 14 * k}" text-anchor="end" fill="{cols[k % 4]}">{sysname(name)[:34]}</text>')
    g.append("</svg>")
    _w(path, "\n".join(g))


# ---------- markdown ----------
def build(R, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    L, w = [], None
    w = L.append
    meta = R["meta"]
    mock = bool(meta.get("mock"))
    dec, cat, pairs, lat, cost = R["decisions"], R["categorie"], R["pairs"], R["latency"], R["cost"]
    systems = sorted({s for d in list(dec.values()) + [cat] for s in d}, key=lambda x: (x != "jev", x))
    if mock:
        w("> **⚠️ DONNÉES SIMULÉES.** Ce rapport a été produit contre un serveur factice (un « Jev imaginaire ») pour tester la chaîne de mesure et montrer la forme du rapport. "
          "Aucun chiffre ci-dessous ne dit quoi que ce soit de Jev.\n")
    w("# Jev sur les usages réels du pipeline hémicycle\n")
    w("*Généré par `python -m jev_lab report`, uniquement depuis le journal brut des appels. Seuils de lecture fixés avant les mesures : voir `PROTOCOL.md`.*\n")
    w("## 0. Statut du run\n")
    w("| | |\n|---|---|")
    for k, lab in (("started", "Début"), ("suite", "Suite"), ("git", "Commit"), ("jev_model", "Modèle Jev demandé"), ("budget", "Plafond de budget ($)")):
        if meta.get(k) is not None:
            w(f"| {lab} | {meta[k]} |")
    if R.get("resolved_models"):
        w(f"| Version de Jev effectivement servie | {', '.join(R['resolved_models'])} |")
    if meta.get("baselines"):
        w("| Références (Claude via OpenRouter, même contrat que le secours de production) | " + ", ".join(f"`{v}`" for v in meta["baselines"].values()) + " |")
    if meta.get("thresholds"):
        t = meta["thresholds"]
        w(f"| Seuils de production évalués | catégorie ≥ {t.get('cat_min')} ; sens P ≥ {t.get('dir_ok')} ; pour/contre P ≥ {t.get('pro_con_ok')}, fond ≥ {t.get('substance_ok')}, "
          f"équilibre {t.get('balance')} ; neutralité : rejet si note > {t.get('neutralite_max')} |")
    w("| Jeu d'essai | " + " ; ".join(f"{SCN[s]} : {n}" for s, n in R["n_items"].items() if n) + " |")
    if meta.get("sessions", 1) > 1:
        w(f"| Sessions (reprises) | {meta['sessions']} — la réconciliation des crédits n'est alors plus interprétable |")
    w(f"| Appels enregistrés | {R['n_calls']} (après déduplication des reprises) |")
    w(f"| Dépense rapportée | {usd(R['spend'])}  (" + ", ".join(f"{sysname(k)}: {usd(v)}" for k, v in sorted(R['by_system_spend'].items())) + ") |\n")

    # ---- synthèse
    w("## 1. Jev peut-il tenir ces rôles dans le pipeline ?\n")
    w("Chaque scénario est un appel réel du pipeline, avec ses questions et ses seuils. Deux erreurs comptent : la **fausse acceptation** (un défaut passe : bouton inversé publié, fiche orientée, "
      "arguments inversés) et le **faux rejet** (une bonne entrée est refusée : on perd une fiche et du temps de relecture). Une réponse inexploitable ou un appel échoué est comptée comme un **rejet**, "
      "comme le fait le pipeline (échec fermé). Limites de sûreté : voir `PROTOCOL.md` §5 (à valider avant le run).\n")
    if R["safety"]:
        w("| Scénario | Système | Fausses acceptations | limite | Faux rejets | limite |\n|---|---|---|---|---|---|")
        by = {}
        for r in R["safety"]:
            by.setdefault((r["scenario"], r["system"]), {})[r["metric"]] = r
        for (sc, sy), d in sorted(by.items(), key=lambda kv: (H.ORDER.index(kv[0][0]), kv[0][1] != "jev", kv[0][1])):
            far, frr = d.get("far"), d.get("frr")
            cell = lambda x: f"{rc({'p': x['p'], 'ci': x['ci'], 'k': x['k'], 'n': x['n']})} → **{x['label']}**" if x else "–"
            w(f"| {SCN[sc]} | {sysname(sy)} | {cell(far)} | ≤ {pc(far['limit'], 0) if far else '–'} | {cell(frr)} | ≤ {pc(frr['limit'], 0) if frr else '–'} |")
        w("")
        w("![décisions](decisions.svg)\n")
    c0 = cat.get("jev")
    if c0:
        w(f"**Catégorie** (Jev) : exactitude {rc(c0['top1'])}, top-3 {rc(c0['top3'])} ; précision des catégories acceptées au seuil {classify.THRESHOLDS['cat_min']} : "
          f"{rc(c0['precision_accepted']) if c0['precision_accepted'] else '–'} (objectifs : exactitude ≥ {pc(C.CATEGORIE['top1_min'], 0)}, précision des acceptées ≥ {pc(C.CATEGORIE['precision_acceptees_min'], 0)}).\n")
    w("**Lecture.** « Respecté » = la borne haute de l'intervalle est sous la limite ; « dépassé » = la borne basse est au-dessus ; « inconclusif » = l'échantillon ne permet pas de trancher "
      "(avec 60 fiches, même zéro erreur observée laisse une borne haute d'environ 6 %). Les intervalles sont le résultat, pas la moyenne.\n")

    # ---- comparaisons appariées
    allp = [p for sc in dec for p in pairs.get(sc, [])]
    if allp:
        w("### Jev contre chaque référence, sur les mêmes entrées\n")
        w("Erreur de Jev moins erreur de la référence (négatif = Jev se trompe moins). « Au moins aussi sûr » = borne haute de l'écart sous +3 points.\n")
        w("| Scénario | Référence | Erreur | n | Jev | Réf. | Écart [IC 95 %] | p (Holm) | Lecture |\n|---|---|---|---|---|---|---|---|---|")
        for p in allp:
            w(f"| {SCN[p['scenario']]} | {sysname(p['vs'])} | {'fausse acceptation' if p['metric'] == 'far' else 'faux rejet'} | {p['n']} | {pc(p['jev'])} | {pc(p['ref'])} | "
              f"{pc(p['diff'])} [{pc(p['lo'])} ; {pc(p['hi'])}] | {f(p['p_holm'], 3)} | {p['label']} |")
        w(f"\n⚠ {len(allp)} comparaisons : à 95 %, on s'attend à environ {len(allp) * 0.05:.0f} écart(s) « significatif(s) » par pur hasard ; lire la colonne p (Holm).\n")

    # ---- un chapitre par scénario
    w("## 2. Détail par scénario\n")
    # catégorie
    w(f"### 2.1 {SCN['categorie']}\n")
    w(f"*Production* : `fiche.py` → `classify.category`. {H.SCENARIOS['categorie']}.  *Jeu d'essai* : les 34 fiches du MVP, catégorie choisie à la main. "
      "Avec 34 fiches, l'intervalle sur l'exactitude fait ± 14 points : pour trancher, il faut des étiquettes humaines supplémentaires (`content/gold/categories.jsonl`, voir README).\n")
    if cat:
        w("| Système | n | Réponses exploitables | Exactitude [IC 95 %] | Top-3 | Catégories acceptées | Précision des acceptées | ECE |\n|---|---|---|---|---|---|---|---|")
        for s in systems:
            c = cat.get(s)
            if c:
                w(f"| {sysname(s)} | {c['n']} | {pc(c['valid_rate'])} | {rc(c['top1'])} | {pc(c['top3']['p'])} | {pc(c['accepted']['p'])} | {rc(c['precision_accepted']) if c['precision_accepted'] else '–'} | {f(c['ece'])} |")
        if c0 and c0["errors"]:
            w("\n**Erreurs de Jev** (vérité → réponse, confiance) : " + " ; ".join(f"{e['item'].replace('cat-', '#')} {e['gold']} → {e['pred']} ({f(e['conf'], 2)})" for e in c0["errors"][:12]) + "\n")
    # sens
    w(f"### 2.2 {SCN['sens']}\n")
    w(f"*Production* : `fiche.py` → `classify.direction`. {H.SCENARIOS['sens']}.  *Jeu d'essai* : chaque vote est présenté deux fois, avec le bouton exact (doit être accepté) et le bouton inversé (doit être rejeté) ; "
      "fiches réelles + titres officiels supplémentaires dont le sens est certain (ensemble, suppression, amendement). La vérité vient des règles de titre : elle est fiable pour ces cas *faciles* ; "
      "les titres ambigus, pour lesquels Jev serait le plus utile, ne sont **pas** couverts (pas de vérité terrain sans étiquettes humaines).\n")
    if dec.get("sens"):
        w("| Système | Bon bouton accepté | **Bouton inversé accepté** | Sens du vote lu correctement | AUC (P correspond) | Réponses exploitables |\n|---|---|---|---|---|---|")
        for s in systems:
            d = dec["sens"].get(s)
            if d:
                w(f"| {sysname(s)} | {rc({'p': 1 - d['frr']['p'], 'ci': (1 - d['frr']['ci'][1], 1 - d['frr']['ci'][0]), 'k': d['frr']['n'] - d['frr']['k'], 'n': d['frr']['n']})} | {rc(d['far'])} | {rc(d.get('sens_ok'))} | {f(d.get('auc'))} | {pc(d['valid_rate'])} |")
        w("\n**Par type de vote** (Jev)\n")
        d = dec["sens"].get("jev")
        if d and d.get("kinds"):
            w("| Type | Faux rejets | Fausses acceptations |\n|---|---|---|\n" + "\n".join(f"| {k} | {rc(v['frr'])} | {rc(v['far'])} |" for k, v in d["kinds"].items()))
        w("")
    # neutralité
    w(f"### 2.3 {SCN['neutralite']}\n")
    w(f"*Production* : `neutrality.judge` → `classify.orientation`. {H.SCENARIOS['neutralite']} (NEUTRALITY_MAX = {HC.NEUTRALITY_MAX}).  *Jeu d'essai* : les fiches actuelles (supposées neutres) et leurs "
      "réécritures par un modèle de langage, orientées POUR, orientées CONTRE ou au cadrage léger (`gen-variants`, à relire). **Limite** : les fiches d'origine ne sont pas prouvées neutres "
      "(le juge a déjà signalé un léger biais sur quelques-unes) et les réécritures ne sont pas validées une à une.\n")
    if dec.get("neutralite"):
        w("| Système | Note moyenne par groupe | Fiches d'origine rejetées (faux rejets) | Orientées fortes acceptées (fausses acceptations) | Cadrage léger rejeté | AUC fort vs origine |\n|---|---|---|---|---|---|")
        for s in systems:
            d = dec["neutralite"].get(s)
            if d:
                sc_ = ", ".join(f"{g}: {f(d['scores'][g], 2)}" for g in ("orig", "pour", "contre", "subtil") if g in (d.get("scores") or {}))
                w(f"| {sysname(s)} | {sc_} | {rc(d['frr'])} | {rc(d['far'])} | {rc(d['soft_reject'])} | {f(d.get('auc'))} |")
        w("")
    # pro/contre
    w(f"### 2.4 {SCN['pro_contre']}\n")
    w(f"*Production* : `fiche.py` → `classify.pro_con`. {H.SCENARIOS['pro_contre']}.  *Jeu d'essai* : chaque fiche telle quelle (doit passer) et trois défauts fabriqués : arguments permutés, « contre » tronqué à 6 mots, "
      "« contre » emprunté à une autre mesure (tous doivent être rejetés).\n")
    if dec.get("pro_contre"):
        w("| Système | Fiches d'origine rejetées (faux rejets) | " + " | ".join(f"{GRP[g]} acceptés" for g in ("permutes", "contre_tronque", "contre_d_une_autre_mesure")) + " | Tous défauts acceptés | AUC |\n|---|---|---|---|---|---|---|")
        for s in systems:
            d = dec["pro_contre"].get(s)
            if d:
                g = d["groups"]
                w(f"| {sysname(s)} | {rc(d['frr'])} | " + " | ".join(rc(g.get(k)) for k in ("permutes", "contre_tronque", "contre_d_une_autre_mesure")) + f" | {rc(d['far'])} | {f(d.get('auc'))} |")
        w("")

    # ---- pourquoi les bonnes entrées sont refusées
    causes = [(sc, dec[sc].get("jev", {}).get("causes_frr")) for sc in ("sens", "neutralite", "pro_contre")]
    if any(c for _, c in causes):
        w("### 2.5 Pourquoi Jev refuse de bonnes entrées\n")
        w("Une règle de production qui combine plusieurs conditions **cumule** leurs erreurs : une fiche est refusée si *une seule* condition échoue. Les causes ci-dessous peuvent se recouvrir "
          "(une fiche peut échouer à plusieurs conditions). À lire avant de toucher à un seuil : c'est la condition qui refuse le plus qu'il faut regarder.\n")
        w("| Scénario (Jev) | Bonnes entrées | Rejetées | Cause |\n|---|---|---|---|")
        for sc, c in causes:
            if c:
                n_good = dec[sc]["jev"]["frr"]["n"]
                for k, v in c.items():
                    if not k.startswith("_"):
                        w(f"| {SCN[sc]} | {n_good} | {c['_rejetées']} | {k} : **{v}** |")
        w("")

    # ---- pistes exploratoires
    ex = R.get("exploratoire") or {}
    if ex:
        w("### 2.6 Pistes exploratoires (imaginées après avoir vu les résultats : à confirmer sur de nouvelles données)\n")
        w("Ces règles n'étaient pas dans le protocole. Elles montrent où le défaut se situe ; elles ne prouvent pas qu'elles fonctionneront sur d'autres fiches.\n")
        w("| Scénario | Système | Règle | Fausses acceptations | Faux rejets |\n|---|---|---|---|---|")
        for sc, per in ex.items():
            for s_, lst in per.items():
                for e in lst:
                    w(f"| {SCN[sc]} | {sysname(s_)} | {e['regle']} | {rc(e['far'])} | {rc(e['frr'])} |")
        w("")
    et = R.get("explo_sens_titre")
    if et:
        w("**Piste : le sens du vote lu dans le titre seul.** Dans le premier résultat, le « sens » donné par Jev suit le libellé du bouton plus que le titre (règle « sens lu » ci-dessus : "
          "il accepte presque tous les boutons inversés). On lui reposera donc la question de sens **sans** montrer les boutons, et on compare au sens annoncé.\n")
        w("| Cas | Fausses acceptations (bouton inversé accepté) | Faux rejets (bon bouton refusé) |\n|---|---|---|")
        w(f"| Tous | {rc(et['far'])} | {rc(et['frr'])} |")
        for g, v in sorted(et["kinds"].items()):
            w(f"| {g} | {rc(v['far'])} | {rc(v['frr'])} |")
        w("")

    # ---- seuils
    w("## 3. Les seuils actuels sont-ils bien placés ?\n")
    w("Pour Jev : ce que fait le seuil de production aujourd'hui, et le seuil que suggère l'étude (choisi sur une moitié des cas, évalué sur l'autre : jamais optimisé sur ce qui le mesure).\n")
    rcb = R["recalibration"]
    if rcb:
        w("| Décision | Seuil actuel | Fausses acceptations (ce critère seul) | Faux rejets (ce critère seul) | Seuil suggéré (validation croisée) | à ce seuil : détection / fausse alerte |\n|---|---|---|---|---|---|")
        for sc, d in rcb.items():
            cv = d.get("cv")
            sug = (f"{'rejeter si ≥' if sc == 'neutralite' else 'rejeter si ≤'} {f(cv['full_cut'], 2)}" if cv else "–")
            det = f"{pc(cv['tpr'])} / {pc(cv['fpr'])}" if cv else "–"
            w(f"| {SCN[sc]} | {d['seuil']} | {pc(d['actuel_far'])} | {pc(d['actuel_frr'])} | {sug} | {det} |")
        w("\n*Détection* = part des défauts rejetés ; *fausse alerte* = part des bonnes entrées rejetées. Un seuil plus sévère réduit les fausses acceptations au prix de faux rejets : "
          "c'est un choix de production, pas seulement de mesure.\n")
    else:
        w("Pas de données.\n")

    # ---- latence, coût
    w("## 4. Temps et coût\n")
    w("Appels en **série**, connexion persistante, systèmes entrelacés, échauffement exclu ; durée mesurée côté client (tentative réussie). Intervalles : bootstrap **par fiche**.\n")
    if lat["par_scenario"]:
        w("| Scénario (appel de production) | " + " | ".join(f"{sysname(s)} p50 / p95" for s in systems) + " |\n|---|" + "---|" * len(systems))
        for sc in H.ORDER:
            d = lat["par_scenario"].get(sc)
            if d:
                w(f"| {SCN[sc]} | " + " | ".join(f"{f(d[s]['p50'])} / {f(d[s]['p95'])} s" if s in d else "–" for s in systems) + " |")
        w("")
        w("![latence](latency.svg)\n")
        w("| Système | n | p50 | p90 | p95 | p99 | IC p50 | IC p95 |\n|---|---|---|---|---|---|---|---|")
        for s in systems:
            d = lat["global"].get(s)
            if d:
                w(f"| {sysname(s)} | {d['n']} | {f(d['p50'])} s | {f(d['p90'])} s | {f(d['p95'])} s | {f(d['p99'])} s | "
                  f"{('[' + f(d['p50_ci'][0]) + ' ; ' + f(d['p50_ci'][1]) + ']') if 'p50_ci' in d else ''} | {('[' + f(d['p95_ci'][0]) + ' ; ' + f(d['p95_ci'][1]) + ']') if 'p95_ci' in d else ''} |")
        w("")
        pf = {s: sum((lat["par_scenario"].get(sc, {}).get(s, {}).get("p50") or 0) for sc in H.ORDER) for s in systems}
        w("**Une fiche = 4 appels** (catégorie, sens, neutralité, pour/contre). Durée médiane si les appels sont enchaînés : "
          + ", ".join(f"{sysname(s)} {pf[s]:.2f} s" for s in systems) + ". Un lot nocturne de 50 fiches enchaînées : "
          + ", ".join(f"{sysname(s)} {pf[s] * 50 / 60:.1f} min" for s in systems) + ". *(Le pipeline lance-t-il ses appels en série ? À adapter.)*\n")
    if R["throughput"]:
        w("**Débit et limites de cadence (Jev, appel pour/contre à 5 questions)**\n")
        w("| Concurrence | Appels | Durée | Débit | Réponses 429 | Échecs |\n|---|---|---|---|---|---|")
        for t in R["throughput"]:
            w(f"| {t['conc']} | {t['n']} | {f(t['wall_total_s'], 1)} s | {f(t['rps'], 1)} /s | {t['n_429']} | {t['failed']} |")
        w("")
    w("**Réessais et erreurs (tous appels)**\n")
    w("| Système | Appels | Réessayés | 429 | 5xx | Réseau | Échecs définitifs |\n|---|---|---|---|---|---|---|")
    for s in systems:
        d = lat["retry"].get(s)
        if d:
            w(f"| {sysname(s)} | {d['calls']} | {d['retried']} | {d['n429']} | {d['n5xx']} | {d['net']} | {d['failed']} |")
    w("")
    w("### Coût\n")
    w("| Scénario | " + " | ".join(f"{sysname(s)} / appel" for s in systems) + " |\n|---|" + "---|" * len(systems))
    for sc in H.ORDER:
        d = cost["par_scenario"].get(sc)
        if d:
            w(f"| {SCN[sc]} | " + " | ".join(usd(d[s]["call"]) if s in d else "–" for s in systems) + " |")
    if cost["par_fiche"]:
        w("| **Une fiche (4 appels)** | " + " | ".join(f"**{usd(cost['par_fiche'].get(s))}**" if s in cost["par_fiche"] else "–" for s in systems) + " |")
        w("| **1 000 fiches** | " + " | ".join(f"**{usd(cost['par_fiche'][s] * 1000)}**" if s in cost["par_fiche"] else "–" for s in systems) + " |")
    if cost.get("tarif"):
        t = cost["tarif"]
        w(f"\nTarif : coût facturé ÷ (tokens d'entrée × {C.CLAIMS['prix_entree_par_M'][0]} $/M) = **{f(t['ratio_median'])}** sur {t['n']} appels Jev (5ᵉ–95ᵉ percentile {f(t['p5_p95'][0])} – {f(t['p5_p95'][1])}) → "
          f"{'conforme' if t['ok'] else 'ÉCART au tarif annoncé'}. Corrélation tokens de sortie / coût unitaire (≈ 0 si la sortie est gratuite) : {f(t['out_corr'], 2)}.")
    if cost.get("reconcile"):
        r = cost["reconcile"]
        w(f"\nRéconciliation avec le compte OpenRouter : consommation facturée {usd(r['billed'])} contre {usd(r['reported'])} rapportée (écart {pc(r['gap'])})"
          + ("" if r.get("reliable", True) else " ⚠ run repris en plusieurs sessions : écart non interprétable") + ".")
    w("")

    # ---- stabilité
    w("## 5. Stabilité et robustesse\n")
    d = R["determinism"]
    w("**Même fiche, même appel, 5 fois.** Ce qui compte pour une porte automatique : la **décision** change-t-elle d'un passage à l'autre ? (Une fiche proche d'un seuil peut basculer.)\n")
    if d.get("par_scenario"):
        w("| Scénario | Fiches | Répétitions | Décision change | Réponse strictement identique | Écart moyen / max de la grandeur de décision |\n|---|---|---|---|---|---|")
        for sc in H.ORDER:
            x = d["par_scenario"].get(sc)
            if x:
                w(f"| {SCN[sc]} | {x['items']} | {f(x['reps'], 1)} | {rc(x['flip'])} | {pc(x['identiques'])} | {f(x['spread_mean'])} / {f(x['spread_max'])} |")
        if d.get("flip"):
            w(f"\nGlobal : {rc(d['flip'])} (limite du protocole : {pc(P['flip_max_determinisme'], 0)}).")
        w("")
    rb = R["robust"]
    if rb:
        w("**Catégorie : sensibilité à la rédaction de la consigne** (mêmes 34 fiches)\n")
        w("| Système | Variante | n | Exactitude de base | Avec la variante | Chute [IC 95 %] | Catégorie différente |\n|---|---|---|---|---|---|---|")
        for r in sorted(rb, key=lambda r: (r["system"] != "jev", r["system"], r["variant"])):
            lab = {"nodesc": "sans descriptions des catégories", "shuffle1": "ordre des options permuté (1)", "shuffle2": "ordre des options permuté (2)"}[r["variant"]]
            w(f"| {sysname(r['system'])} | {lab} | {r['n']} | {pc(r['acc_base'])} | {pc(r['acc_var'])} | {pc(r['drop'])} [{pc(r['drop_ci'][0])} ; {pc(r['drop_ci'][1])}] | {pc(r['flip'])} |")
        w("")
    mu = R["multi"]
    if mu:
        w("**Questions posées seules ou ensemble** (le pipeline les envoie toutes dans un appel ; les poser seules change-t-il la réponse ?)\n")
        w("| Scénario | Questions | Fiches | Décision différente | Écart moyen / max | Coût (ensemble → séparées) | Durée (ensemble → séparées) |\n|---|---|---|---|---|---|---|")
        for sc, x in mu.items():
            w(f"| {SCN[sc]} | {x['questions']} | {x['n']} | {rc(x['flip'])} | {f(x['drift_mean'])} / {f(x['drift_max'])} | {usd(x['cost_joint'])} → {usd(x['cost_alone'])} | {f(x['lat_joint'])} → {f(x['lat_alone'])} s |")
        w("")

    # ---- pires erreurs
    w("## 6. Les fausses acceptations de Jev (ce qui passerait en production)\n")
    for sc, lst in R["worst"].items():
        if lst:
            w(f"**{SCN[sc]}**\n")
            w("| Cas | Groupe | Grandeur de décision | Entrée (début) |\n|---|---|---|---|")
            for e in lst:
                w(f"| {e['item']} | {GRP.get(e['group'], e['group'])} | {f(e['score'], 2)} | {e['state'][:230].replace('|', '/')} |")
            w("")
    w("## 7. Limites de cette étude\n")
    for s in ("Le jeu d'essai vient du dépôt : 74 fiches dont 34 du MVP. C'est petit : lire les intervalles ; « inconclusif » ne veut pas dire « mauvais ».",
              "Seuls les cas *faciles* du sens du vote ont une vérité terrain automatique ; les titres ambigus (là où Jev serait le plus utile) demandent des étiquettes humaines.",
              "Les fiches d'origine ne sont pas prouvées neutres, et les variantes orientées sont écrites par un modèle de langage et non validées une à une.",
              "`sources_sufficient` (pré-contrôle du lot) n'est pas couvert : il faudrait des extraits de sources étiquetés.",
              "Les références (Claude) répondent au même contrat typé par une consigne JSON, sans exemples, température 0 : c'est le secours de production, pas le meilleur de ce qu'elles savent faire.",
              "La latence dépend du réseau, de l'heure et de la charge d'OpenRouter ; des appels identiques répétés peuvent être mis en cache côté fournisseur.",
              "Le modèle servi est un millésime : une conclusion ne vaut que pour lui. Refaire l'étude à chaque nouvelle version avant de changer un seuil."):
        w(f"- {s}")
    md = "\n".join(L) + "\n"
    _w(os.path.join(out_dir, "REPORT.md"), md)
    svg_decisions(R, os.path.join(out_dir, "decisions.svg"))
    if R.get("latency_samples"):
        svg_latency(R["latency_samples"], os.path.join(out_dir, "latency.svg"))

    def clean(o):
        if isinstance(o, dict):
            return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple, set)):
            return [clean(v) for v in o]
        if isinstance(o, float) and o != o:
            return None
        return o
    slim = clean({k: v for k, v in R.items() if k != "latency_samples"})
    _w(os.path.join(out_dir, "summary.json"), json.dumps(slim, ensure_ascii=False, indent=1, default=str))
    return md
