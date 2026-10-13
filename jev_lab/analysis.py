"""Analyse : relit le journal brut (calls.jsonl), ré-interprète chaque réponse, calcule toutes les statistiques.

Rien n'est lu dans un résumé intermédiaire : tout est recalculable depuis les réponses brutes."""
import math
from . import config as C, tasks as T, synth as SY, metrics as M

P = C.PREREG


def _dict_gold(g):
    return isinstance(g, dict)


def tidy(recs):
    """Un enregistrement par appel, réponse interprétée.  Les appels multi-questions gardent leurs réponses brutes."""
    out = []
    for r in recs:
        exp = r.get("experiment")
        if exp == "throughput_batch" or not r.get("task") or r["task"] not in T.TASKS:
            continue
        t = T.TASKS[r["task"]]
        u = r.get("usage") or {}
        row = {"experiment": exp, "task": r["task"], "item": r["item"], "system": r["system"], "variant": r.get("variant", "base"),
               "rep": r.get("rep", 0), "gold": r.get("gold"), "primitive": r.get("primitive", t.primitive), "ok": bool(r.get("ok")),
               "status": r.get("status"), "error": r.get("error"), "error_text": r.get("error_text"), "wall_s": r.get("wall_s"),
               "total_s": r.get("total_s"), "n_attempts": r.get("n_attempts", 1), "attempts": r.get("attempts", []),
               "in_tok": u.get("input_tokens"), "out_tok": u.get("output_tokens"), "cost": u.get("cost"),
               "resolved_model": r.get("resolved_model"), "size_tokens": r.get("size_tokens"), "request": r.get("request"),
               "model": (r.get("request") or {}).get("model")}
        row["pred"], row["conf"], row["p_yes"], row["probs"], row["score"], row["answers"] = None, None, None, None, None, None
        if r.get("ok") and not _dict_gold(r.get("gold")):
            if r["system"] == "jev":
                ans = ((r.get("response") or {}).get("answers") or {}).get("q")
                p = T.parse_jev(t, ans)
            else:
                p = T.parse_chat(t, r.get("text"))
            row.update({k: p.get(k) for k in ("pred", "conf", "p_yes", "probs", "score")})
        elif r.get("ok") and r["system"] == "jev":
            row["answers"] = (r.get("response") or {}).get("answers")
        row["valid"] = row["ok"] and (row["pred"] is not None or _dict_gold(r.get("gold")))
        row["correct"] = bool(row["valid"] and not _dict_gold(r.get("gold")) and row["pred"] == r.get("gold"))
        out.append(row)
    return out


def _by(rows, *keys):
    d = {}
    for r in rows:
        d.setdefault(tuple(r[k] for k in keys), []).append(r)
    return d


def _price_per_call(rows):
    c = [r["cost"] for r in rows if r.get("cost") is not None]
    return M.mean(c) if c else float("nan")


# ---------- E1 : qualité ----------
def quality(rows):
    q = [r for r in rows if r["experiment"] == "quality"]
    res = {"cells": {}, "pairs": [], "systems": sorted({r["system"] for r in q}), "tasks": sorted({r["task"] for r in q}, key=lambda t: list(T.TASKS).index(t))}
    for (task, system), rs in _by(q, "task", "system").items():
        t = T.TASKS[task]
        n, nv = len(rs), sum(1 for r in rs if r["valid"])
        cor = [r["correct"] for r in rs]
        cell = {"n": n, "valid_rate": nv / n if n else float("nan"), "acc": M.accuracy(cor), "acc_ci": M.bootstrap_ci([1.0 if c else 0.0 for c in cor]),
                "cost_call": _price_per_call(rs), "primitive": t.primitive, "errors": sum(1 for r in rs if not r["ok"])}
        cell["cost_1k"] = cell["cost_call"] * 1000
        cell["cost_per_correct"] = (cell["cost_call"] * n / max(1, sum(cor))) if cell["cost_call"] == cell["cost_call"] else float("nan")
        if t.primitive == "choice":
            cell["macro_f1"] = M.macro_f1([r["pred"] for r in rs], [r["gold"] for r in rs])
        if t.primitive == "noul":
            vv = [r for r in rs if r["p_yes"] is not None]
            cell["auc"] = M.auc([r["p_yes"] for r in vv], [bool(r["gold"]) for r in vv]) if vv else float("nan")
            if vv:
                cell["brier"] = M.brier([r["p_yes"] for r in vv], [bool(r["gold"]) for r in vv])
                cell["bal_acc_2fold"], cell["thresholds"] = M.threshold_two_fold([r["p_yes"] for r in vv], [bool(r["gold"]) for r in vv])
        if t.primitive == "score":
            vv = [r for r in rs if r["pred"] is not None]
            cell["mae"] = M.mean(abs(r["pred"] - r["gold"]) for r in vv) if vv else float("nan")
            cell["within1"] = M.mean(abs(r["pred"] - r["gold"]) <= 1 for r in vv) if vv else float("nan")
            sc = [(r["score"], r["gold"]) for r in vv if r["score"] is not None]
            cell["spearman"] = M.spearman([a for a, _ in sc], [b for _, b in sc]) if len(sc) > 2 else float("nan")
        res["cells"][(task, system)] = cell
    # comparaisons appariées Jev - référence
    ps = []
    for task in res["tasks"]:
        a = {r["item"]: r for r in q if r["task"] == task and r["system"] == "jev"}
        for s in res["systems"]:
            if s == "jev":
                continue
            b = {r["item"]: r for r in q if r["task"] == task and r["system"] == s}
            common = sorted(set(a) & set(b))
            if len(common) < 10:
                continue
            ja = [1.0 if a[i]["correct"] else 0.0 for i in common]
            jb = [1.0 if b[i]["correct"] else 0.0 for i in common]
            diff = [x - y for x, y in zip(ja, jb)]
            bb = sum(1 for x, y in zip(ja, jb) if x and not y)
            cc = sum(1 for x, y in zip(ja, jb) if y and not x)
            lo, hi = M.bootstrap_ci(diff)
            ps.append({"task": task, "vs": s, "n": len(common), "acc_jev": M.mean(ja), "acc_ref": M.mean(jb), "diff": M.mean(diff), "lo": lo, "hi": hi,
                       "p": M.mcnemar_exact(bb, cc), "b": bb, "c": cc,
                       "cost_ratio": (res["cells"][(task, s)]["cost_call"] / res["cells"][(task, "jev")]["cost_call"]) if res["cells"].get((task, "jev"), {}).get("cost_call") else float("nan")})
    adj = M.holm([p["p"] for p in ps])
    for p, a in zip(ps, adj):
        p["p_holm"] = a
        p["label"] = ("supérieur" if p["lo"] > 0 else "équivalent" if p["lo"] > -P["delta_non_inferiorite"] else
                      "inférieur" if p["hi"] < 0 else "inconclusif")
    res["pairs"] = ps
    return res


# ---------- E2 : calibration ----------
def calibration(rows):
    j = [r for r in rows if r["experiment"] == "quality" and r["system"] == "jev" and r["valid"] and r["conf"] is not None]
    out = {"pooled": None, "by_task": {}, "by_primitive": {}}
    if j:
        ece, tab = M.calibration([r["conf"] for r in j], [r["correct"] for r in j])
        out["pooled"] = {"ece": ece, "ece_ci": M.ece_ci([r["conf"] for r in j], [r["correct"] for r in j]), "bins": tab, "n": len(j), "risk_coverage": M.risk_coverage([r["conf"] for r in j], [r["correct"] for r in j])}
    for k, rs in _by(j, "task").items():
        ece, tab = M.calibration([r["conf"] for r in rs], [r["correct"] for r in rs])
        out["by_task"][k[0]] = {"ece": ece, "ece_ci": M.ece_ci([r["conf"] for r in rs], [r["correct"] for r in rs]), "n": len(rs), "risk_coverage": M.risk_coverage([r["conf"] for r in rs], [r["correct"] for r in rs])}
    for k, rs in _by(j, "primitive").items():
        ece, tab = M.calibration([r["conf"] for r in rs], [r["correct"] for r in rs])
        out["by_primitive"][k[0]] = {"ece": ece, "n": len(rs)}
    # confiance verbalisée des modèles de chat (comparaison indicative)
    out["chat"] = {}
    for (s,), rs in _by([r for r in rows if r["experiment"] == "quality" and r["system"] != "jev" and r["valid"] and r["conf"] is not None], "system").items():
        ece, _ = M.calibration([r["conf"] for r in rs], [r["correct"] for r in rs])
        out["chat"][s] = {"ece": ece, "n": len(rs)}
    return out


# ---------- E3 : latence ----------
def _pcts(xs, boot=True):
    d = {"n": len(xs)}
    for q in (50, 90, 95, 99):
        d[f"p{q}"] = M.percentile(xs, q)
    if boot and len(xs) >= 20:
        d["p50_ci"] = M.bootstrap_ci(xs, lambda v: M.percentile(v, 50), b=500)
        d["p95_ci"] = M.bootstrap_ci(xs, lambda v: M.percentile(v, 95), b=500)
    d["mean"] = M.mean(xs)
    return d


def latency(rows):
    lat = [r for r in rows if r["experiment"] == "latency"]
    out = {"serial": {}, "size": {}, "retry": {}}
    for (s,), rs in _by(lat, "system").items():
        ok = [r for r in rs if r["ok"]]
        out["serial"][s] = {**_pcts([r["wall_s"] for r in ok]), "total": _pcts([r["total_s"] for r in ok], boot=False),
                            "fail": sum(1 for r in rs if not r["ok"]), "calls": len(rs)}
    sz = [r for r in rows if r["experiment"] == "latency_size" and r["ok"]]
    for (s, tok), rs in _by([dict(r, tok=r["size_tokens"]) for r in sz], "system", "tok").items():
        out["size"].setdefault(s, {})[tok] = {"p50": M.percentile([r["wall_s"] for r in rs], 50), "n": len(rs),
                                              "in_tok": M.mean(r["in_tok"] for r in rs if r["in_tok"] is not None) if any(r["in_tok"] for r in rs) else None}
    allc = [r for r in rows if r["experiment"] in ("quality", "latency", "robust", "limits") and r["system"]]
    for (s,), rs in _by(allc, "system").items():
        out["retry"][s] = {"calls": len(rs), "retried": sum(1 for r in rs if r["n_attempts"] > 1),
                           "n429": sum(1 for r in rs for a in r["attempts"] if a.get("status") == 429),
                           "n5xx": sum(1 for r in rs for a in r["attempts"] if (a.get("status") or 0) >= 500),
                           "net": sum(1 for r in rs for a in r["attempts"] if a.get("error")), "failed": sum(1 for r in rs if not r["ok"])}
    return out


def throughput(recs):
    return sorted([r for r in recs if r.get("experiment") == "throughput_batch"], key=lambda r: r["conc"])


# ---------- E5 : coût ----------
def pricing(rows, meta):
    j = [r for r in rows if r["system"] == "jev" and r["ok"] and r["in_tok"] and r["cost"] is not None]
    price = C.CLAIMS["prix_entree_par_M"][0]
    out = {"n": len(j)}
    if j:
        ratio = [r["cost"] / (r["in_tok"] * price / 1e6) for r in j]
        out["ratio_median"] = M.percentile(ratio, 50)
        out["ratio_p5_p95"] = (M.percentile(ratio, 5), M.percentile(ratio, 95))
        out["implied_price_per_M"] = M.percentile([r["cost"] / r["in_tok"] * 1e6 for r in j], 50)
        out["out_free"] = M.spearman([r["out_tok"] or 0 for r in j], [r["cost"] / r["in_tok"] for r in j]) if len({r["out_tok"] for r in j}) > 2 else float("nan")
        out["tol_ok"] = abs(out["ratio_median"] - 1) <= P["tolerance_prix"]
    # facturation multi-questions
    b = [r for r in rows if r["experiment"] == "billing" and r["ok"] and r["in_tok"]]
    if b:
        tab = {}
        for (v,), rs in _by(b, "variant").items():
            tab[int(v.split(":")[1])] = {"in_tok": M.mean(r["in_tok"] for r in rs), "cost": M.mean(r["cost"] for r in rs if r["cost"] is not None), "n": len(rs)}
        out["multiq"] = dict(sorted(tab.items()))
    # réconciliation avec le compte
    c0, c1 = meta.get("credits_start"), meta.get("credits_end")
    if c0 and c1 and c0.get("total_usage") is not None and c1.get("total_usage") is not None:
        billed = c1["total_usage"] - c0["total_usage"]
        rep = sum(r["cost"] for r in rows if r["cost"] is not None)
        out["reconcile"] = {"billed": billed, "reported": rep, "gap": (billed - rep) / rep if rep else float("nan")}
    return out


# ---------- E6 : robustesse ----------
def robustness(rows):
    rb = [r for r in rows if r["experiment"] == "robust"]
    out = {"noise": [], "desc": [], "shuffle": []}
    key = lambda r: (r["task"], r["system"], r["item"])
    base = {key(r): r for r in rb if r["variant"] == "base"}
    for (task, system, variant), rs in _by(rb, "task", "system", "variant").items():
        if variant == "base":
            continue
        pairs = [(base[key(r)], r) for r in rs if key(r) in base]
        if len(pairs) < 10:
            continue
        diff = [(1.0 if b["correct"] else 0.0) - (1.0 if v["correct"] else 0.0) for b, v in pairs]
        flips = M.mean(1.0 if b["pred"] != v["pred"] else 0.0 for b, v in pairs)
        row = {"task": task, "system": system, "variant": variant, "n": len(pairs), "acc_base": M.mean(1.0 if b["correct"] else 0.0 for b, _ in pairs),
               "acc_var": M.mean(1.0 if v["correct"] else 0.0 for _, v in pairs), "drop": M.mean(diff), "drop_ci": M.bootstrap_ci(diff), "flip": flips,
               "valid_var": M.mean(1.0 if v["valid"] else 0.0 for _, v in pairs)}
        (out["noise"] if variant.startswith("noise") else out["shuffle"] if variant.startswith("shuffle") else out["desc"]).append(row)
    return out


# ---------- E7 : déterminisme ----------
def determinism(rows):
    d = [r for r in rows if r["experiment"] == "determinism" and r["valid"]]
    out = {"by_task": {}}
    for (task,), rs in _by(d, "task").items():
        items = {}
        for r in rs:
            items.setdefault(r["item"], []).append(r)
        items = {k: v for k, v in items.items() if len(v) >= 3}
        if not items:
            continue
        flip = M.mean(1.0 if len({r["pred"] for r in v}) > 1 else 0.0 for v in items.values())
        def spread(v):
            xs = [r["p_yes"] if r["p_yes"] is not None else (r["conf"] if r["conf"] is not None else None) for r in v]
            xs = [x for x in xs if x is not None]
            return (max(xs) - min(xs)) if len(xs) > 1 else 0.0
        sp = [spread(v) for v in items.values()]
        out["by_task"][task] = {"items": len(items), "reps": M.mean(len(v) for v in items.values()), "flip": flip, "spread_mean": M.mean(sp), "spread_max": max(sp),
                                "identical": M.mean(1.0 if spread(v) == 0 else 0.0 for v in items.values())}
    if out["by_task"]:
        out["flip"] = M.mean(v["flip"] for v in out["by_task"].values())
    return out


# ---------- E8 : limites annoncées ----------
def limits(rows):
    lm = [r for r in rows if r["experiment"] == "limits"]
    out = {"cells": {}, "probe": []}
    for (task, system), rs in _by(lm, "task", "system").items():
        cor = [r["correct"] for r in rs]
        t = T.TASKS[task]
        chance = 1 / len(t.options) if t.primitive == "choice" else 0.5
        out["cells"][(task, system)] = {"n": len(rs), "acc": M.accuracy(cor), "ci": M.bootstrap_ci([1.0 if c else 0.0 for c in cor]), "chance": chance,
                                        "above_chance": M.bootstrap_ci([1.0 if c else 0.0 for c in cor])[0] > chance}
    for r in sorted([r for r in rows if r["experiment"] == "ctx_probe"], key=lambda r: r["size_tokens"]):
        out["probe"].append({"size": r["size_tokens"], "ok": r["ok"], "status": r["status"], "in_tok": r["in_tok"], "wall_s": r["wall_s"],
                             "error": (r.get("error_text") or r.get("error") or "")[:160]})
    return out


# ---------- E9 : multi-questions ----------
def multi(rows):
    m = [r for r in rows if r["experiment"] == "multi" and r["ok"] and r["answers"]]
    out = {}
    pair = [r for r in m if r["variant"] == "pair_noul"]
    if pair:
        inc = [abs(r["answers"]["pos"]["noul"] + r["answers"]["neg"]["noul"] - 1) for r in pair if "pos" in r["answers"] and "neg" in r["answers"]]
        acc_pos = M.mean(1.0 if (r["answers"]["pos"]["noul"] >= .5) == bool(r["gold"]["pos"]) else 0.0 for r in pair)
        both = M.mean(1.0 if ((r["answers"]["pos"]["noul"] >= .5) != (r["answers"]["neg"]["noul"] >= .5)) else 0.0 for r in pair)
        out["pair_noul"] = {"n": len(pair), "inconsistency": M.mean(inc), "acc_pos": acc_pos, "coherent_labels": both}
    ch = [r for r in m if r["variant"] == "one_choice"]
    if ch:
        out["one_choice"] = {"n": len(ch), "acc": M.mean(1.0 if r["answers"]["c"].get("choice") == r["gold"]["c"] else 0.0 for r in ch)}
    alone = {r["item"]: r for r in m if r["variant"] == "alone"}
    joint = {r["item"]: r for r in m if r["variant"] == "joint"}
    common = sorted(set(alone) & set(joint))
    if common:
        flips = M.mean(1.0 if alone[i]["answers"]["a"].get("choice") != joint[i]["answers"]["a"].get("choice") else 0.0 for i in common)
        out["alone_vs_joint"] = {"n": len(common), "flip": flips,
                                 "cost_alone": M.mean(alone[i]["cost"] for i in common if alone[i]["cost"] is not None),
                                 "cost_joint": M.mean(joint[i]["cost"] for i in common if joint[i]["cost"] is not None),
                                 "lat_alone": M.mean(alone[i]["wall_s"] for i in common), "lat_joint": M.mean(joint[i]["wall_s"] for i in common)}
    return out


# ---------- erreurs les plus confiantes ----------
def confident_errors(rows, k=12):
    e = [r for r in rows if r["experiment"] == "quality" and r["system"] == "jev" and r["valid"] and not r["correct"] and r["conf"] is not None]
    e.sort(key=lambda r: -r["conf"])
    out = []
    for r in e[:k]:
        st = (r.get("request") or {}).get("state")
        txt = " | ".join(f"{a}: {str(b)[:160]}" for a, b in (st or {}).items()) if isinstance(st, dict) else str(st)[:200]
        out.append({"task": r["task"], "gold": r["gold"], "pred": r["pred"], "conf": r["conf"], "state": txt})
    return out


# ---------- synthèse et verdict ----------
def verdict(Q, cal, lat, det, price, lim, rb):
    """Applique la grille FIXÉE dans PROTOCOL.md.  Renvoie des constats, jamais une opinion."""
    v = {"par_tache": {}, "global": []}
    refs = [s for s in Q["systems"] if s != "jev"]
    for task in Q["tasks"]:
        prs = [p for p in Q["pairs"] if p["task"] == task]
        if not prs:
            continue
        v["par_tache"][task] = [{"vs": p["vs"], "label": p["label"], "diff": p["diff"], "lo": p["lo"], "hi": p["hi"], "cost_ratio": p["cost_ratio"],
                                 "recommande": p["label"] in ("supérieur", "équivalent") and p["cost_ratio"] >= P["gain_cout_significatif"]} for p in prs]
    # calibration
    if cal.get("pooled"):
        e, (lo, hi) = cal["pooled"]["ece"], cal["pooled"]["ece_ci"]
        # le biais de l'ECE est positif sur petit échantillon : on ne conclut « bonne » que si la borne HAUTE est sous le seuil
        lab = ("bonne" if hi <= P["ece_bon"] else "acceptable" if hi <= P["ece_acceptable"] else "mauvaise" if lo > P["ece_acceptable"] else "inconclusive")
        v["global"].append(("calibration", lab, f"ECE {e:.3f} [IC 95 % {lo:.3f} – {hi:.3f}] sur {cal['pooled']['n']} réponses" if hi == hi else f"ECE {e:.3f} sur {cal['pooled']['n']} réponses (trop peu pour un intervalle)"))
    # latence
    if lat["serial"].get("jev"):
        j = lat["serial"]["jev"]
        for s, d in lat["serial"].items():
            if s != "jev" and d["p50"] and j["p50"]:
                r = d["p50"] / j["p50"]
                v["global"].append((f"latence vs {s}", "nettement plus rapide" if r >= P["gain_latence_significatif"] else "comparable ou plus lent", f"p50 {j['p50']:.3f}s contre {d['p50']:.3f}s (×{r:.1f})"))
    # déterminisme
    if det.get("flip") is not None:
        v["global"].append(("déterminisme", "conforme" if det["flip"] <= P["flip_max_determinisme"] else "instable", f"{det['flip']:.1%} d'étiquettes qui changent à l'identique"))
    # robustesse (Jev)
    for r in rb["noise"]:
        if r["system"] == "jev" and r["variant"] in ("noise:600:before", "noise:2400:both"):
            lo, hi = r["drop_ci"]
            lab = "résiste" if hi <= P["chute_bruit_max"] else "sensible au bruit" if lo > P["chute_bruit_max"] else "inconclusif"
            v["global"].append((f"bruit {r['variant']} : {r['task']}", lab, f"chute {r['drop']:+.1%} [{lo:+.1%} ; {hi:+.1%}]"))
    for r in rb["shuffle"]:
        if r["system"] == "jev":
            lab = "stable" if r["flip"] <= P["flip_permutation_max"] else "dépend de l'ordre des options"
            v["global"].append((f"{r['variant']} : {r['task']}", lab, f"{r['flip']:.1%} d'étiquettes changées"))
    # prix
    if price.get("ratio_median"):
        v["global"].append(("prix", "conforme au tarif annoncé" if price["tol_ok"] else "écart au tarif annoncé", f"coût facturé / (tokens × 0,042 $/M) = {price['ratio_median']:.3f}"))
    # limites annoncées
    for task in SY.SYNTH_IDS:
        c = lim["cells"].get((task, "jev"))
        if c:
            lab = ("limite confirmée (non utilisable)" if c["ci"][1] < P["utilisable"] else "limite non confirmée (utilisable)" if c["ci"][0] >= P["utilisable"] else "inconclusif")
            v["global"].append((f"limite annoncée : {task}", lab, f"précision {c['acc']:.0%} [{c['ci'][0]:.0%}–{c['ci'][1]:.0%}], hasard {c['chance']:.0%}, seuil d'usage {P['utilisable']:.0%}"))
    return v


def run(store):
    recs = store.read()
    meta = store.meta()
    rows = tidy(recs)
    Q = quality(rows)
    cal, lat, thr, pr = calibration(rows), latency(rows), throughput(recs), pricing(rows, meta)
    rb, det, lim, mu = robustness(rows), determinism(rows), limits(rows), multi(rows)
    vd = verdict(Q, cal, lat, det, pr, lim, rb)
    samples = {}
    for r in rows:
        if r["experiment"] == "latency" and r["ok"] and r["wall_s"] is not None:
            samples.setdefault(r["system"], []).append(r["wall_s"])
    return {"latency_samples": samples, "resolved_models": sorted({r["resolved_model"] for r in rows if r["system"] == "jev" and r["resolved_model"]}), "meta": meta, "n_calls": len(recs), "quality": Q, "calibration": cal, "latency": lat, "throughput": thr, "pricing": pr, "robust": rb,
            "determinism": det, "limits": lim, "multi": mu, "errors": confident_errors(rows), "verdict": vd,
            "spend": sum(r["cost"] for r in rows if r["cost"] is not None), "by_system_spend": {k[0]: sum(r["cost"] for r in rs if r["cost"] is not None) for k, rs in _by(rows, "system").items()}}
