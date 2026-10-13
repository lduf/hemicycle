"""Rapport : REPORT.md + graphiques SVG + summary.json, générés uniquement depuis les réponses brutes."""
import json, os
from . import config as C, tasks as T, metrics as M

P = C.PREREG


def f(x, nd=3):
    return "–" if x is None or (isinstance(x, float) and x != x) else f"{x:.{nd}f}"


def pc(x, nd=1):
    return "–" if x is None or (isinstance(x, float) and x != x) else f"{100 * x:.{nd}f} %"


def usd(x):
    if x is None or (isinstance(x, float) and x != x):
        return "–"
    return f"{x:.6f} $" if x < 0.01 else f"{x:.4f} $"


def ci(c, nd=1):
    return f"[{pc(c[0], nd)} – {pc(c[1], nd)}]" if c and c[0] == c[0] else ""


def _w(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


# ---------- SVG ----------
def svg_reliability(bins, path, title):
    W = H = 320
    pad = 40
    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="11">',
         f'<rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{W / 2}" y="16" text-anchor="middle" font-weight="bold">{title}</text>']
    sx = lambda v: pad + v * (W - 2 * pad)
    sy = lambda v: H - pad - v * (H - 2 * pad)
    g.append(f'<line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(1)}" y2="{sy(1)}" stroke="#bbb" stroke-dasharray="4"/>')
    g.append(f'<line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(1)}" y2="{sy(0)}" stroke="#444"/><line x1="{sx(0)}" y1="{sy(0)}" x2="{sx(0)}" y2="{sy(1)}" stroke="#444"/>')
    for t in (0, .5, 1):
        g.append(f'<text x="{sx(t)}" y="{H - 22}" text-anchor="middle">{t:g}</text><text x="{pad - 6}" y="{sy(t) + 4}" text-anchor="end">{t:g}</text>')
    g.append(f'<text x="{W / 2}" y="{H - 6}" text-anchor="middle">confiance annoncée</text>')
    g.append(f'<text x="12" y="{H / 2}" transform="rotate(-90 12 {H / 2})" text-anchor="middle">précision observée</text>')
    for b in bins:
        r = 3 + 9 * min(1, b["n"] / max(1, max(x["n"] for x in bins)))
        g.append(f'<circle cx="{sx(b["conf"])}" cy="{sy(b["acc"])}" r="{r:.1f}" fill="#2563eb" fill-opacity=".7"><title>n={b["n"]}</title></circle>')
    g.append("</svg>")
    _w(path, "\n".join(g))


def svg_latency(samples, path):
    W, H, pad = 460, 300, 44
    allv = [v for xs in samples.values() for v in xs]
    if not allv:
        return
    hi = M.percentile(allv, 99) or 1
    cols = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c"]
    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="11"><rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{W / 2}" y="16" text-anchor="middle" font-weight="bold">Latence : distribution cumulée (appels en série)</text>']
    sx = lambda v: pad + min(1, v / hi) * (W - pad - 12)
    sy = lambda v: H - pad - v * (H - pad - 28)
    g.append(f'<line x1="{pad}" y1="{sy(0)}" x2="{W - 12}" y2="{sy(0)}" stroke="#444"/><line x1="{pad}" y1="{sy(0)}" x2="{pad}" y2="{sy(1)}" stroke="#444"/>')
    for t in (0, .5, .95, 1):
        g.append(f'<text x="{pad - 4}" y="{sy(t) + 4}" text-anchor="end">{t:g}</text>')
    for t in (0, .25, .5, .75, 1):
        g.append(f'<text x="{sx(hi * t)}" y="{H - 28}" text-anchor="middle">{hi * t:.2f}s</text>')
    for k, (name, xs) in enumerate(sorted(samples.items())):
        xs = sorted(xs)
        pts = " ".join(f"{sx(v):.1f},{sy((i + 1) / len(xs)):.1f}" for i, v in enumerate(xs))
        g.append(f'<polyline fill="none" stroke="{cols[k % 5]}" stroke-width="2" points="{pts}"/>')
        g.append(f'<text x="{W - 14}" y="{40 + 14 * k}" text-anchor="end" fill="{cols[k % 5]}">{name[:34]}</text>')
    g.append("</svg>")
    _w(path, "\n".join(g))


def svg_accuracy(R, path):
    Q = R["quality"]
    systems, tasks = Q["systems"], Q["tasks"]
    if not tasks:
        return
    rowh, W = 18, 760
    H = 50 + rowh * len(tasks) * (len(systems) + 1)
    cols = ["#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c"]
    g = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="sans-serif" font-size="11"><rect width="{W}" height="{H}" fill="white"/>',
         f'<text x="{W / 2}" y="16" text-anchor="middle" font-weight="bold">Précision par tâche (intervalle de confiance à 95 %)</text>']
    x0, x1 = 200, W - 20
    sx = lambda v: x0 + v * (x1 - x0)
    for t in (0, .25, .5, .75, 1):
        g.append(f'<line x1="{sx(t)}" y1="28" x2="{sx(t)}" y2="{H - 14}" stroke="#eee"/><text x="{sx(t)}" y="{H - 2}" text-anchor="middle">{t:.0%}</text>')
    y = 38
    for task in tasks:
        g.append(f'<text x="8" y="{y + 4}" font-weight="bold">{T.TASKS[task].title[:34]}</text>')
        for k, s in enumerate(systems):
            c = Q["cells"].get((task, s))
            if not c:
                continue
            col = cols[k % 5]
            g.append(f'<line x1="{sx(c["acc_ci"][0])}" y1="{y}" x2="{sx(c["acc_ci"][1])}" y2="{y}" stroke="{col}" stroke-width="2"/>')
            g.append(f'<circle cx="{sx(c["acc"])}" cy="{y}" r="4" fill="{col}"/>')
            if task == tasks[0]:
                g.append(f'<text x="{x1}" y="{y - 6 + 0}" text-anchor="end" fill="{col}" font-size="10">{s[:30]}</text>')
            y += rowh
        y += rowh
    g.append("</svg>")
    _w(path, "\n".join(g))


# ---------- markdown ----------
def build(R, out_dir, store=None):
    os.makedirs(out_dir, exist_ok=True)
    L = []
    w = L.append
    meta = R["meta"]
    mock = bool(meta.get("mock"))
    Q, cal, lat, pr, vd = R["quality"], R["calibration"], R["latency"], R["pricing"], R["verdict"]
    if mock:
        w("> **⚠️ DONNÉES SIMULÉES.** Ce rapport a été produit contre un serveur factice pour tester la chaîne de mesure. "
          "Aucun chiffre ci-dessous ne dit quoi que ce soit de Jev.\n")
    w("# Étude de Jev (TypeSafe, via OpenRouter)\n")
    w(f"*Généré par `python -m jev_lab report`. Seuils de lecture fixés avant les mesures : voir `PROTOCOL.md`.*\n")
    w("## 0. Statut du run\n")
    w("| | |\n|---|---|")
    for k, lab in (("started", "Début"), ("suite", "Suite"), ("git", "Commit"), ("jev_model", "Modèle demandé"), ("budget", "Plafond de budget ($)")):
        if meta.get(k) is not None:
            w(f"| {lab} | {meta[k]} |")
    rm = sorted({r for r in R.get("resolved_models", []) if r})
    if rm:
        w(f"| Version de Jev effectivement servie | {', '.join(rm)} |")
    if meta.get("baselines"):
        w("| Modèles de comparaison (figés) | " + ", ".join(f"{k} = `{v}`" for k, v in meta["baselines"].items()) + " |")
    w(f"| Appels enregistrés | {R['n_calls']} |")
    w(f"| Dépense rapportée | {usd(R['spend'])}  (" + ", ".join(f"{k}: {usd(v)}" for k, v in sorted(R['by_system_spend'].items())) + ") |\n")

    # ---- verdict en tête
    w("## 1. Ce qu'on peut dire (grille du protocole)\n")
    if vd["par_tache"]:
        w("Pour chaque tâche et chaque référence : Jev est-il **supérieur**, **équivalent** (non-inférieur à 3 points près), **inférieur** ou **inconclusif** ? "
          "« Recommandé » = au moins équivalent ET au moins 10 fois moins cher.\n")
        w("| Tâche | Référence | Écart de précision (Jev − réf.) | Lecture | Rapport de coût (réf./Jev) | Recommandé |\n|---|---|---|---|---|---|")
        for task, lst in vd["par_tache"].items():
            for p in lst:
                w(f"| {T.TASKS[task].title} | {p['vs']} | {pc(p['diff'])} [{pc(p['lo'])} ; {pc(p['hi'])}] | **{p['label']}** | ×{f(p['cost_ratio'], 1)} | {'oui' if p['recommande'] else 'non'} |")
        w("")
    if vd["global"]:
        w("| Point | Constat | Détail |\n|---|---|---|")
        for a, b, c in vd["global"]:
            w(f"| {a} | **{b}** | {c} |")
        w("")

    # ---- qualité
    w("## 2. Qualité par tâche\n")
    w("![précision](accuracy.svg)\n")
    w("| Tâche | Système | n | Réponses exploitables | Précision [IC 95 %] | Autre mesure | Coût / 1 000 appels | Coût par bonne réponse |\n|---|---|---|---|---|---|---|---|")
    for task in Q["tasks"]:
        for s in Q["systems"]:
            c = Q["cells"].get((task, s))
            if not c:
                continue
            extra = (f"F1 macro {f(c.get('macro_f1'), 3)}" if "macro_f1" in c else f"AUC {f(c.get('auc'), 3)} ; précision équilibrée (seuil réglé sur l'autre moitié) {pc(c.get('bal_acc_2fold'))}" if "auc" in c
                     else f"MAE {f(c.get('mae'), 2)} niveau ; à ±1 : {pc(c.get('within1'))} ; ρ {f(c.get('spearman'), 2)}" if "mae" in c else "")
            w(f"| {T.TASKS[task].title} | {s} | {c['n']} | {pc(c['valid_rate'])} | {pc(c['acc'])} {ci(c['acc_ci'])} | {extra} | {usd(c['cost_1k'])} | {usd(c['cost_per_correct'])} |")
    if Q["pairs"]:
        w("\n### Comparaisons appariées (mêmes exemples)\n")
        w("| Tâche | Réf. | n | Jev | Réf. | Écart [IC 95 %] | p (McNemar) | p (Holm) | Lecture |\n|---|---|---|---|---|---|---|---|---|")
        for p in Q["pairs"]:
            w(f"| {T.TASKS[p['task']].title} | {p['vs']} | {p['n']} | {pc(p['acc_jev'])} | {pc(p['acc_ref'])} | {pc(p['diff'])} [{pc(p['lo'])} ; {pc(p['hi'])}] | {f(p['p'], 4)} | {f(p['p_holm'], 4)} | {p['label']} |")
        w("")

    # ---- calibration
    w("## 3. Calibration (la confiance de Jev est-elle fiable ?)\n")
    if cal.get("pooled"):
        c = cal["pooled"]
        w(f"ECE global : **{f(c['ece'])}** [IC 95 % {f(c['ece_ci'][0])} – {f(c['ece_ci'][1])}] sur {c['n']} réponses (≤ {P['ece_bon']} bon, ≤ {P['ece_acceptable']} acceptable). "
          "Pour une question à oui/non, la confiance est max(p, 1−p).\n")
        w("![calibration](reliability.svg)\n")
        w("**Abstention** : précision si l'on ne garde que la part la plus confiante des réponses.\n")
        w("| Part conservée | 100 % | 90 % | 80 % | 50 % |\n|---|---|---|---|---|")
        rc = c["risk_coverage"]
        w("| Précision | " + " | ".join(pc(rc[k]) for k in (1.0, .9, .8, .5)) + " |\n")
        w("| Tâche | ECE | n | Précision à 80 % de couverture |\n|---|---|---|---|")
        for t, d in cal["by_task"].items():
            w(f"| {T.TASKS[t].title} | {f(d['ece'])} | {d['n']} | {pc(d['risk_coverage'][.8])} |")
        if cal.get("chat"):
            w("\nConfiance *verbalisée* des modèles de comparaison (indicatif) : " + ", ".join(f"{k} ECE {f(v['ece'])}" for k, v in cal["chat"].items()) + "\n")
    else:
        w("Pas de données.\n")

    # ---- latence
    w("## 4. Latence\n")
    w("Mesure côté client, appels **en série** (un à la fois), systèmes entrelacés, après échauffement. `wall` = tentative réussie ; les attentes de réessai sont comptées à part.\n")
    w("| Système | n | p50 | p90 | p95 | p99 | IC p50 | IC p95 | Échecs |\n|---|---|---|---|---|---|---|---|---|")
    for s, d in lat["serial"].items():
        w(f"| {s} | {d['n']} | {f(d['p50'])} s | {f(d['p90'])} s | {f(d['p95'])} s | {f(d['p99'])} s | {('[' + f(d['p50_ci'][0]) + ' ; ' + f(d['p50_ci'][1]) + ']') if 'p50_ci' in d else ''} | {('[' + f(d['p95_ci'][0]) + ' ; ' + f(d['p95_ci'][1]) + ']') if 'p95_ci' in d else ''} | {d['fail']} |")
    w(f"\nRevendication de l'éditeur (blog, tickets courts) : p50 {C.CLAIMS['latence_p50_s'][0]} s, p95 {C.CLAIMS['latence_p95_s'][0]} s.\n")
    if R.get("latency_samples"):
        w("![latence](latency.svg)\n")
    if lat["size"]:
        w("**Effet de la taille d'entrée** (p50, même exemple avec de plus en plus de contexte)\n")
        sizes = sorted({t for d in lat["size"].values() for t in d})
        w("| Système | " + " | ".join(f"+{s} tok" for s in sizes) + " |\n|---|" + "---|" * len(sizes))
        for s, d in lat["size"].items():
            w(f"| {s} | " + " | ".join(f"{f(d[t]['p50'])} s" if t in d else "–" for t in sizes) + " |")
        w("")
    if R["throughput"]:
        w("**Débit et limites de cadence (Jev seul)**\n")
        w("| Concurrence | Appels | Durée | Débit | Réponses 429 | Échecs |\n|---|---|---|---|---|---|")
        for t in R["throughput"]:
            w(f"| {t['conc']} | {t['n']} | {f(t['wall_total_s'], 1)} s | {f(t['rps'], 1)} /s | {t['n_429']} | {t['failed']} |")
        w("")
    w("**Réessais et erreurs réseau (tous appels)**\n")
    w("| Système | Appels | Réessayés | 429 | 5xx | Réseau | Échecs définitifs |\n|---|---|---|---|---|---|---|")
    for s, d in lat["retry"].items():
        w(f"| {s} | {d['calls']} | {d['retried']} | {d['n429']} | {d['n5xx']} | {d['net']} | {d['failed']} |")
    w("")

    # ---- coût
    w("## 5. Prix\n")
    if pr.get("n"):
        w(f"Sur {pr['n']} appels Jev : coût facturé ÷ (tokens d'entrée × {C.CLAIMS['prix_entree_par_M'][0]} $/M) = **{f(pr['ratio_median'])}** (5ᵉ–95ᵉ percentile : {f(pr['ratio_p5_p95'][0])} – {f(pr['ratio_p5_p95'][1])}). "
          f"Prix implicite médian : {f(pr['implied_price_per_M'], 4)} $/M. "
          f"Corrélation rang entre tokens de sortie et coût unitaire (devrait être ≈ 0 si la sortie est gratuite) : {f(pr.get('out_free'), 2)}.\n")
    if pr.get("multiq"):
        w("**Facturation de plusieurs questions dans une requête** (même état, questions identiques répétées)\n")
        w("| Questions | Tokens d'entrée | Coût | Rapport tokens / 1 question |\n|---|---|---|---|")
        b = pr["multiq"].get(1, {}).get("in_tok")
        for k, d in pr["multiq"].items():
            w(f"| {k} | {f(d['in_tok'], 0)} | {usd(d['cost'])} | ×{f(d['in_tok'] / b, 2) if b else '–'} |")
        w("")
    if pr.get("reconcile"):
        rc = pr["reconcile"]
        w(f"**Réconciliation avec le compte OpenRouter** : consommation facturée {usd(rc['billed'])} contre {usd(rc['reported'])} rapportée par les réponses (écart {pc(rc['gap'])}).\n")
    w("**Coût comparé** (par 1 000 appels, voir tableau de la section 2) : le coût par bonne réponse est la métrique à retenir pour décider.\n")

    # ---- robustesse
    rb = R["robust"]
    w("## 6. Robustesse\n")
    if rb["noise"]:
        w("**Détails non pertinents** (texte administratif ajouté avant/après) : chute de précision par rapport à la même consigne sans bruit.\n")
        w("| Tâche | Système | Variante | n | Base | Avec bruit | Chute [IC 95 %] | Étiquettes changées |\n|---|---|---|---|---|---|---|---|")
        for r in rb["noise"]:
            w(f"| {T.TASKS[r['task']].title} | {r['system']} | {r['variant']} | {r['n']} | {pc(r['acc_base'])} | {pc(r['acc_var'])} | {pc(r['drop'])} {ci(r['drop_ci'])} | {pc(r['flip'])} |")
        w("")
    if rb["shuffle"]:
        w("**Ordre des options permuté** (une réponse correcte ne devrait pas dépendre de l'ordre)\n")
        w("| Tâche | Système | Variante | n | Base | Permuté | Étiquettes changées |\n|---|---|---|---|---|---|---|")
        for r in rb["shuffle"]:
            w(f"| {T.TASKS[r['task']].title} | {r['system']} | {r['variant']} | {r['n']} | {pc(r['acc_base'])} | {pc(r['acc_var'])} | {pc(r['flip'])} |")
        w("")
    if rb["desc"]:
        w("**Sans descriptions** (libellés seuls)\n")
        w("| Tâche | Système | n | Avec descriptions | Sans | Chute [IC 95 %] |\n|---|---|---|---|---|---|")
        for r in rb["desc"]:
            w(f"| {T.TASKS[r['task']].title} | {r['system']} | {r['n']} | {pc(r['acc_base'])} | {pc(r['acc_var'])} | {pc(r['drop'])} {ci(r['drop_ci'])} |")
        w("")

    # ---- déterminisme
    d = R["determinism"]
    w("## 7. Déterminisme\n")
    if d.get("by_task"):
        w("Même appel répété. L'éditeur annonce des probabilités « légèrement différentes d'une exécution à l'autre ».\n")
        w("| Tâche | Exemples | Répétitions | Étiquette change | Réponse strictement identique | Écart moyen de probabilité | Écart max |\n|---|---|---|---|---|---|---|")
        for t, x in d["by_task"].items():
            w(f"| {T.TASKS[t].title} | {x['items']} | {f(x['reps'], 1)} | {pc(x['flip'])} | {pc(x['identical'])} | {f(x['spread_mean'])} | {f(x['spread_max'])} |")
        w("")
    else:
        w("Pas de données.\n")

    # ---- limites
    lm = R["limits"]
    w("## 8. Limites annoncées par l'éditeur (tâches à réponse exacte)\n")
    if lm["cells"]:
        w("| Tâche | Système | n | Précision [IC 95 %] | Hasard | Meilleur que le hasard ? |\n|---|---|---|---|---|---|")
        for (t, s), c in lm["cells"].items():
            w(f"| {T.TASKS[t].title} | {s} | {c['n']} | {pc(c['acc'])} {ci(c['ci'])} | {pc(c['chance'], 0)} | {'oui' if c['above_chance'] else 'non'} |")
        w("")
    if lm["probe"]:
        w("**Sonde de longueur de contexte** (documentation : 32 000 tokens d'un côté, 64 000 de l'autre)\n")
        w("| Bruit ajouté (tok) | Tokens facturés | Résultat | Statut | Durée | Message |\n|---|---|---|---|---|---|")
        for p in lm["probe"]:
            w(f"| {p['size']} | {p['in_tok'] or '–'} | {'accepté' if p['ok'] else 'refusé'} | {p['status']} | {f(p['wall_s'])} s | {p['error']} |")
        w("")

    # ---- multi
    mu = R["multi"]
    w("## 9. Plusieurs questions dans un appel\n")
    if mu:
        if "pair_noul" in mu:
            x = mu["pair_noul"]
            w(f"- Deux questions oui/non opposées (« positif ? », « négatif ? ») : incohérence moyenne |p₁+p₂−1| = **{f(x['inconsistency'])}** ; étiquettes cohérentes entre elles dans {pc(x['coherent_labels'])} des cas ({x['n']} exemples).")
        if "one_choice" in mu and "pair_noul" in mu:
            w(f"- Précision : question à choix unique {pc(mu['one_choice']['acc'])} contre question oui/non seule {pc(mu['pair_noul']['acc_pos'])}.")
        if "alone_vs_joint" in mu:
            x = mu["alone_vs_joint"]
            w(f"- Une question seule contre la même question avec deux autres dans l'appel : étiquette différente dans {pc(x['flip'])} des cas ({x['n']} exemples) ; coût {usd(x['cost_alone'])} → {usd(x['cost_joint'])} ; latence {f(x['lat_alone'])} s → {f(x['lat_joint'])} s.")
        w("")
    else:
        w("Pas de données.\n")

    # ---- erreurs
    w("## 10. Erreurs les plus confiantes de Jev\n")
    if R["errors"]:
        w("| Tâche | Vérité | Jev | Confiance | Entrée (début) |\n|---|---|---|---|---|")
        for e in R["errors"]:
            w(f"| {T.TASKS[e['task']].title} | {e['gold']} | {e['pred']} | {f(e['conf'], 2)} | {e['state'][:200].replace('|', '/')} |")
        w("")
    w("## 11. Revendications de l'éditeur\n")
    w("| Revendication | Valeur annoncée | Source |\n|---|---|---|")
    for k, (val, unit, src) in C.CLAIMS.items():
        w(f"| {k} | {val} ({unit}) | {src} |")
    w("\n*Les constats correspondants figurent dans les sections 1, 3, 4, 5, 7 et 8.*\n")
    w("## 12. Limites de cette étude\n")
    for s in ("Jeux publics en anglais et en français ; aucune garantie sur d'autres langues ou domaines.",
              "Critères rédigés à partir des noms d'étiquettes, sans réglage : un utilisateur attentif obtiendrait mieux de Jev ET des modèles de comparaison.",
              "Les références sont des modèles de langage en mode JSON, température 0, sans exemples : ce n'est pas le meilleur de ce qu'ils savent faire.",
              "La latence dépend du réseau, de l'heure et de la charge d'OpenRouter ; une seule session de mesure ne dit rien du long terme.",
              "Les versions de modèles évoluent : le millésime servi est noté ci-dessus ; une conclusion ne vaut que pour lui.",
              "Les échantillons sont de taille finie : lire les intervalles de confiance, pas seulement les moyennes."):
        w(f"- {s}")
    md = "\n".join(L) + "\n"
    with open(os.path.join(out_dir, "REPORT.md"), "w", encoding="utf-8") as fh:
        fh.write(md)
    if cal.get("pooled"):
        svg_reliability(cal["pooled"]["bins"], os.path.join(out_dir, "reliability.svg"), "Calibration de Jev (toutes tâches)")
    if R.get("latency_samples"):
        svg_latency(R["latency_samples"], os.path.join(out_dir, "latency.svg"))
    svg_accuracy(R, os.path.join(out_dir, "accuracy.svg"))
    def clean(o):
        if isinstance(o, dict):
            return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): clean(v) for k, v in o.items()}
        if isinstance(o, (list, tuple, set)):
            return [clean(v) for v in o]
        if isinstance(o, float) and o != o:
            return None
        return o
    slim = clean(R)
    for k in ("latency_samples",):
        slim.pop(k, None)
    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(slim, fh, ensure_ascii=False, indent=1, default=str)
    return md
