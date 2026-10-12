"""Banc d'essai : Jev vs Claude sur les classifications du pipeline.   python -m pipeline.bench_jev [--engines jev,claude] [--gen]

Jeux de test (la vérité terrain est connue PAR CONSTRUCTION ou vient du MVP, jamais devinée) :
  categorie   : les 34 fiches du MVP (catégorie choisie à la main) -> exactitude, top-3
  sens        : titres officiels réels dont le sens est certain (ensemble / suppression / amendement), bouton exact vs bouton inversé
                -> exactitude du sens, taux d'acceptation du bon bouton (TPR) et du mauvais (FPR)
  neutralite  : fiches non relues du lot, + variantes réécrites par Claude : orientée pour, orientée contre, cadrage subtil
                -> AUC (neutre vs orienté), note moyenne par groupe
  pro_contre  : fiches telles quelles (doivent passer) vs arguments pour/contre permutés, et « contre » tronqué
                -> taux de rejet des défauts, taux de faux rejets
Sorties : data/bench_jev.json (détail) + BENCH_JEV.md (résumé). Seuils proposés = maximum de l'indice de Youden.
--gen régénère les variantes (appels Claude) ; sinon le cache data/bench_neutrality.json est réutilisé.
"""
import argparse, json, os, random, statistics as st, time
from . import config as C, classify, direction as D, jev, llm, store

CACHE = os.path.join(C.DATA, "bench_neutrality.json")
FIELDS = ("title", "label", "hook", "sum", "pro", "con", "surp")


def auc(pos, neg):
    """P(score positif > score négatif), égalités = 1/2."""
    if not pos or not neg:
        return None
    w = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(w / (len(pos) * len(neg)), 3)


def youden(pos, neg):
    """Seuil maximisant TPR - FPR pour « score >= seuil => positif »."""
    best = (None, -1)
    for t in sorted(set(pos + neg)):
        j = sum(p >= t for p in pos) / len(pos) - sum(n >= t for n in neg) / len(neg)
        if j > best[1]:
            best = (t, j)
    return best[0], round(best[1], 3)


class Timer:
    def __init__(self): self.t = []
    def __call__(self, fn, *a, **k):
        t0 = time.time(); r = fn(*a, **k); self.t.append(time.time() - t0); return r
    def p50(self): return round(st.median(self.t), 2) if self.t else None


# ---------------------------------------------------------------- jeux de test
def fiches(statuses):
    return [q for q in store.all_questions() if q["status"] in statuses and q.get("pro") and q.get("con")]


def ds_direction(n=150, seed=7):
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"))
    rng = random.Random(seed); buckets = {"ensemble": [], "suppression": [], "amendement": []}
    for k, s in sc.items():
        c = D.classify(s["titre"])
        if c["polarity"] is None: continue
        if c["kind"] == "ensemble": buckets["ensemble"].append((s["titre"], "adopt"))
        elif c["polarity"] == "remove" and c["kind"] == "amendement": buckets["suppression"].append((s["titre"], "remove"))
        elif c["kind"] == "amendement": buckets["amendement"].append((s["titre"], "adopt"))
    out = []
    for b, L in buckets.items():
        out += rng.sample(L, min(len(L), n // 3))
    return out


def gen_variants(fs, only=None):
    cache = C.jload(CACHE, {})
    slants = {"pour": "clairement orientée EN FAVEUR de la mesure : adjectifs de valeur, formules engagées, arguments des opposants minimisés",
              "contre": "clairement orientée CONTRE la mesure : adjectifs de valeur, formules engagées, arguments des partisans minimisés",
              "subtil": "très légèrement cadrée : change seulement quelques mots (verbes ou adjectifs légèrement connotés) et l'ordre des phrases, sans rien dire de faux"}
    for q in fs:
        for k, desc in slants.items():
            if str(q["n"]) in cache and k in cache[str(q["n"])]: continue
            base = {f: q.get(f) for f in FIELDS}
            r = llm.ask_json(C.MODEL_WRITER, f"Réécris cette fiche pour qu'elle soit {desc}. Garde les mêmes faits et les mêmes clés JSON "
                             f"({', '.join(FIELDS)}). Fiche : {json.dumps(base, ensure_ascii=False)}", max_tokens=1500)
            if isinstance(r, dict) and all(f in r for f in ("sum", "pro", "con")):
                cache.setdefault(str(q["n"]), {})[k] = {f: r.get(f) or q.get(f) for f in FIELDS}
        C.jdump(cache, CACHE)
    return cache


# ---------------------------------------------------------------- évaluations
def ev_category(engine, tm):
    qs = [q for q in store.all_questions() if q["status"] == "legacy"]
    ok = top3 = 0; errs = []
    for q in qs:
        r = tm(classify.category, q, engine)
        ok += r["cat"] == q["cat"]
        pr = r.get("probs") or {}
        top = sorted(pr, key=pr.get, reverse=True)[:3] or [r["cat"]]
        top3 += q["cat"] in top
        if r["cat"] != q["cat"]: errs.append((q["n"], q["cat"], r["cat"], r.get("confidence")))
    return dict(n=len(qs), accuracy=round(ok / len(qs), 3), top3=round(top3 / len(qs), 3), errors=errs)


def ev_direction(engine, tm, items):
    sens_ok = tp = fp = 0
    for titre, pol in items:
        good = tm(classify.direction, titre, "la mesure examinée", pol, engine)
        bad = tm(classify.direction, titre, "la mesure examinée", "remove" if pol == "adopt" else "adopt", engine)
        tp += good[0]; fp += bad[0]; sens_ok += good[1]["sens"] == good[1]["attendu"]
    n = len(items)
    return dict(n=n, sens_accuracy=round(sens_ok / n, 3), accepts_exact_button=round(tp / n, 3), accepts_inverted_button=round(fp / n, 3))


def ev_neutrality(engine, tm, fs, variants):
    neutral, groups = [], {"pour": [], "contre": [], "subtil": []}
    for q in fs:
        neutral.append(tm(classify.orientation, q, engine)["score"])
        for k in groups:
            v = (variants.get(str(q["n"])) or {}).get(k)
            if v: groups[k].append(tm(classify.orientation, v, engine)["score"])
    strong = groups["pour"] + groups["contre"]
    return dict(n_neutral=len(neutral), mean_neutral=round(st.mean(neutral), 2) if neutral else None,
                mean={k: round(st.mean(v), 2) for k, v in groups.items() if v},
                auc_strong=auc(strong, neutral), auc_subtle=auc(groups["subtil"], neutral),
                threshold_strong=youden(strong, neutral) if strong and neutral else None,
                current_threshold=C.NEUTRALITY_MAX, flagged_neutral=sum(s > C.NEUTRALITY_MAX for s in neutral))


def ev_procon(engine, tm, fs):
    ok_pass = swapped_rej = trunc_rej = 0
    for q in fs:
        ok_pass += bool(tm(classify.pro_con, q, engine)["ok"])
        sw = dict(q, pro=q["con"], con=q["pro"])
        swapped_rej += not tm(classify.pro_con, sw, engine)["ok"]
        tr = dict(q, con=" ".join(q["con"].split()[:6]) + ".")
        trunc_rej += not tm(classify.pro_con, tr, engine)["ok"]
    n = len(fs)
    return dict(n=n, good_fiches_pass=round(ok_pass / n, 3), swapped_rejected=round(swapped_rej / n, 3), truncated_rejected=round(trunc_rej / n, 3))


def run(engines, gen=False, n_dir=150):
    if "jev" in engines and not jev.available():
        raise SystemExit("OPENROUTER_API_KEY absente : ajouter le secret GitHub (Settings > Secrets and variables > Actions)")
    if ("claude" in engines or gen or not os.path.exists(CACHE)) and not llm.available():
        raise SystemExit("claude -p indisponible : installer le CLI et définir CLAUDE_CODE_OAUTH_TOKEN")
    fs = fiches({"pending_review", "published"})
    variants = gen_variants(fs) if gen or not os.path.exists(CACHE) else C.jload(CACHE, {})
    items = ds_direction(n_dir)
    report = {"jev_model": jev.MODEL, "datasets": dict(category=34, direction=len(items), neutrality=len(fs), pro_con=len(fs))}
    for eng in engines:
        tm = Timer(); jev.STATS.update(calls=0, input_tokens=0, cost=0.0)
        report[eng] = dict(category=ev_category(eng, tm), direction=ev_direction(eng, tm, items),
                           neutrality=ev_neutrality(eng, tm, fs, variants), pro_con=ev_procon(eng, tm, fs),
                           latency_p50_s=tm.p50(), calls=len(tm.t), jev_cost_usd=round(jev.STATS["cost"], 5) if eng == "jev" else None)
    C.jdump(report, os.path.join(C.DATA, "bench_jev.json"), indent=1)
    md = ["# Banc d'essai Jev vs Claude", "", f"Modèle Jev : `{jev.MODEL}`. Jeux de test : {report['datasets']}.", ""]
    for eng in engines:
        r = report[eng]
        md += [f"## {eng}", f"- latence médiane par appel : {r['latency_p50_s']} s ({r['calls']} appels)" + (f", coût Jev : {r['jev_cost_usd']} $" if r["jev_cost_usd"] is not None else ""),
               f"- catégorie : exactitude {r['category']['accuracy']}, top-3 {r['category']['top3']}",
               f"- sens du vote : exactitude {r['direction']['sens_accuracy']}, bon bouton accepté {r['direction']['accepts_exact_button']}, bouton inversé accepté {r['direction']['accepts_inverted_button']}",
               f"- neutralité : AUC fort {r['neutrality']['auc_strong']}, AUC subtil {r['neutrality']['auc_subtle']}, notes moyennes {r['neutrality']['mean']} (neutres {r['neutrality']['mean_neutral']})",
               f"- pour/contre : bonnes fiches acceptées {r['pro_con']['good_fiches_pass']}, permutées rejetées {r['pro_con']['swapped_rejected']}, tronquées rejetées {r['pro_con']['truncated_rejected']}", ""]
    open(os.path.join(C.ROOT, "BENCH_JEV.md"), "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--engines", default="jev"); ap.add_argument("--gen", action="store_true")
    ap.add_argument("--n-dir", type=int, default=150); a = ap.parse_args()
    run(a.engines.split(","), a.gen, a.n_dir)
