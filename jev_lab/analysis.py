"""Analyse : relit le journal brut (calls.jsonl), ré-interprète chaque réponse, applique les décisions de PRODUCTION et calcule tout.

Principes :
  - un seul enregistrement par appel logique (le réussi l'emporte après une reprise) ;
  - une réponse inexploitable ou un appel échoué n'est JAMAIS exclu : en production la fiche serait refusée (échec fermé), on compte donc un rejet ;
  - rien n'est lu dans un résumé intermédiaire : tout est recalculable depuis les réponses brutes."""
import math
from pipeline import config as HC, classify
from . import config as C, hemicycle as H, metrics as M
from .store import rec_key

P = C.PREREG
ORDER = H.ORDER


def dedupe(recs):
    """Après une reprise, un appel échoué puis réussi figure deux fois dans le journal : on garde le réussi."""
    latest = {}
    for r in recs:
        k = ("tb", r.get("conc")) if r.get("experiment") == "throughput_batch" else rec_key(r)
        prev = latest.get(k)
        if prev is not None and prev.get("ok") and not r.get("ok"):
            continue
        latest[k] = r
    return list(latest.values())


def qs_for(scenario, variant):
    """Questions réellement posées pour (scénario, variante) : nécessaires pour relire les réponses d'un modèle de langage."""
    if variant.startswith("alone:"):
        name = variant.split(":", 1)[1]
        return {name: H.questions(scenario)[name]}
    if scenario == "categorie" and variant in ("nodesc", "shuffle1", "shuffle2"):
        return H.questions(scenario, variant)
    return H.questions(scenario)


def tidy(recs, thresholds=None):
    out = []
    for r in dedupe(recs):
        if r.get("experiment") == "throughput_batch" or r.get("scenario") not in H.SCENARIOS:
            continue
        sc, variant, u = r["scenario"], r.get("variant", "base"), r.get("usage") or {}
        row = {"experiment": r["experiment"], "scenario": sc, "item": r["item"], "group": r.get("group"), "system": r["system"], "variant": variant,
               "rep": r.get("rep", 0), "gold": r.get("gold") or {}, "meta": r.get("meta") or {}, "ok": bool(r.get("ok")), "status": r.get("status"),
               "error": r.get("error"), "error_text": r.get("error_text"), "wall_s": r.get("wall_s"), "total_s": r.get("total_s"),
               "n_attempts": r.get("n_attempts", 1), "attempts": r.get("attempts", []), "in_tok": u.get("input_tokens"), "out_tok": u.get("output_tokens"),
               "cost": u.get("cost"), "resolved_model": r.get("resolved_model"), "state": (r.get("request") or {}).get("state"),
               "answers": None, "verdict": None}
        if r.get("ok"):
            qs = qs_for(sc, variant)
            ans = H.normalize(qs, (r.get("response") or {}).get("answers")) if r["system"] == "jev" else H.chat_answers(qs, r.get("text"))
            row["answers"] = ans
            full = not variant.startswith("alone:")
            if ans is not None and full:
                row["verdict"] = H.verdict(sc, {"gold": row["gold"], "meta": row["meta"]}, ans, thresholds)
        row["valid"] = row["verdict"] is not None
        row["accept"] = bool(row["valid"] and row["verdict"]["accept"])      # échec fermé : inexploitable = rejeté
        out.append(row)
    return out


def _by(rows, *keys):
    d = {}
    for r in rows:
        d.setdefault(tuple(r[k] for k in keys), []).append(r)
    return d


def rate(flags):
    flags = list(flags)
    n, k = len(flags), sum(1 for f in flags if f)
    return {"k": k, "n": n, "p": k / n if n else float("nan"), "ci": M.wilson(k, n)}


def _score_of(scenario, v):
    """Grandeur continue sur laquelle la décision de production se fonde (pour AUC, seuils, déterminisme)."""
    return {"categorie": v.get("conf"), "sens": v.get("p_correspond"), "neutralite": v.get("score"), "pro_contre": v.get("min_ok")}[scenario]


# ---------------------------------------------------------------- E1 : scénarios
def _cv_cut(pos, neg, higher_pos=True, seed=1):
    """Seuil choisi sur une moitié (Youden), évalué sur l'autre (et inversement).  pos/neg : scores des cas à détecter / à laisser passer."""
    import random
    n = min(len(pos), len(neg))
    if n < 6:
        return None
    rnd = random.Random(seed)
    ip, ineg = list(range(len(pos))), list(range(len(neg)))
    rnd.shuffle(ip)
    rnd.shuffle(ineg)
    halves = [(ip[: len(ip) // 2], ineg[: len(ineg) // 2]), (ip[len(ip) // 2:], ineg[len(ineg) // 2:])]

    def tpr_fpr(ps, ns, cut):
        f = (lambda x: x >= cut) if higher_pos else (lambda x: x <= cut)
        return sum(f(x) for x in ps) / len(ps), sum(f(x) for x in ns) / len(ns)

    def best(ps, ns):
        cands = sorted(set(ps) | set(ns))
        return max(cands, key=lambda c: tpr_fpr(ps, ns, c)[0] - tpr_fpr(ps, ns, c)[1])
    res, cuts = [], []
    for a, b in ((0, 1), (1, 0)):
        ps, ns = [pos[i] for i in halves[a][0]], [neg[i] for i in halves[a][1]]
        c = best(ps, ns)
        cuts.append(c)
        t, f = tpr_fpr([pos[i] for i in halves[b][0]], [neg[i] for i in halves[b][1]], c)
        res.append((t, f))
    full = best(pos, neg)
    return {"cuts": cuts, "full_cut": full, "tpr": M.mean(r[0] for r in res), "fpr": M.mean(r[1] for r in res)}


def scenario_categorie(rows):
    q = [r for r in rows if r["experiment"] == "quality" and r["scenario"] == "categorie"]
    out = {}
    for (s,), rs in _by(q, "system").items():
        n = len(rs)
        cor = [bool(r["valid"] and r["verdict"]["correct"]) for r in rs]
        top3 = [bool(r["valid"] and r["verdict"]["top3"]) for r in rs]
        acc_rows = [r for r in rs if r["valid"] and r["verdict"]["accept"]]
        conf = [(r["verdict"]["conf"] if r["verdict"]["conf"] is not None else None, r["verdict"]["correct"]) for r in rs if r["valid"]]
        ece, bins = M.calibration([c for c, _ in conf], [k for _, k in conf])
        out[s] = {"n": n, "valid_rate": sum(1 for r in rs if r["valid"]) / n if n else float("nan"), "top1": rate(cor), "top3": rate(top3),
                  "accepted": rate([bool(r["valid"] and r["verdict"]["accept"]) for r in rs]),
                  "precision_accepted": rate([r["verdict"]["correct"] for r in acc_rows]) if acc_rows else None, "ece": ece,
                  "errors": [{"item": r["item"], "gold": r["gold"].get("cat"), "pred": r["verdict"]["pred"], "conf": r["verdict"]["conf"]}
                             for r in rs if r["valid"] and not r["verdict"]["correct"]]}
    return out


def _decision_stats(rs):
    """Pour un système : taux d'acceptation par groupe + FAR (défauts acceptés) et FRR (bonnes entrées rejetées)."""
    good = [r for r in rs if r["gold"].get("accept") is True]
    bad = [r for r in rs if r["gold"].get("accept") is False]
    soft = [r for r in rs if r["gold"].get("accept") is None]
    groups = {g: rate([r["accept"] for r in v]) for (g,), v in _by(rs, "group").items()}
    return {"n": len(rs), "valid_rate": sum(1 for r in rs if r["valid"]) / len(rs) if rs else float("nan"),
            "frr": rate([not r["accept"] for r in good]), "far": rate([r["accept"] for r in bad]),
            "soft_reject": rate([not r["accept"] for r in soft]) if soft else None, "groups": groups,
            "invalid_among_rejects": sum(1 for r in good + bad if not r["valid"])}


def scenario_decision(rows, scenario):
    q = [r for r in rows if r["experiment"] == "quality" and r["scenario"] == scenario]
    out = {}
    for (s,), rs in _by(q, "system").items():
        d = _decision_stats(rs)
        good = [r for r in rs if r["gold"].get("accept") is True]
        bad = [r for r in rs if r["gold"].get("accept") is False]
        # AUC sur la grandeur de décision : un cas invalide reçoit la valeur la PIRE pour son camp
        sc_all = [_score_of(scenario, r["verdict"]) for r in good + bad if r["valid"]]
        if sc_all:
            lo, hi = min(sc_all), max(sc_all)
            # neutralité : score élevé = orienté = à rejeter ; sens/pro_contre : score élevé = à accepter
            if scenario == "neutralite":
                pos = [(_score_of(scenario, r["verdict"]) if r["valid"] else lo) for r in bad]       # défauts : score devrait être haut
                neg = [(_score_of(scenario, r["verdict"]) if r["valid"] else hi) for r in good]
                d["auc"] = M.auc(pos + neg, [True] * len(pos) + [False] * len(neg))
                d["cv_cut"] = _cv_cut(pos, neg, higher_pos=True)
                d["scores"] = {g: M.mean(_score_of(scenario, r["verdict"]) for r in v if r["valid"]) if any(r["valid"] for r in v) else float("nan")
                               for (g,), v in _by(rs, "group").items()}
            else:
                pos = [(_score_of(scenario, r["verdict"]) if r["valid"] else lo) for r in good]      # bonnes entrées : score devrait être haut
                neg = [(_score_of(scenario, r["verdict"]) if r["valid"] else hi) for r in bad]
                d["auc"] = M.auc(pos + neg, [True] * len(pos) + [False] * len(neg))
                d["cv_cut"] = _cv_cut(neg, pos, higher_pos=False)        # on cherche la coupure « accepter si score ≥ c » : défauts = score bas
        T = classify.THRESHOLDS
        rej = [r for r in good if r["valid"] and not r["accept"]]
        if scenario == "pro_contre" and good:
            d["causes_frr"] = {"réponse inexploitable ou appel échoué": sum(1 for r in good if not r["valid"]),
                               f"pro_ok ou con_ok < {T['pro_con_ok']}": sum(1 for r in rej if r["verdict"]["min_ok"] < T["pro_con_ok"]),
                               f"argument pas « de fond » (< {T['substance_ok']})": sum(1 for r in rej if min(r["verdict"]["pro_fond"], r["verdict"]["con_fond"]) < T["substance_ok"]),
                               f"équilibre hors de {T['balance']}": sum(1 for r in rej if not (T["balance"][0] <= r["verdict"]["equilibre"] <= T["balance"][1])),
                               "_rejetées": len(rej)}
        if scenario == "sens" and good:
            d["causes_frr"] = {"réponse inexploitable ou appel échoué": sum(1 for r in good if not r["valid"]),
                               f"P(correspond) < {T['dir_ok']}": sum(1 for r in rej if r["verdict"]["p_correspond"] < T["dir_ok"]),
                               "sens lu autrement que prévu": sum(1 for r in rej if r["verdict"]["sens"] != r["verdict"]["attendu"]), "_rejetées": len(rej)}
        if scenario == "neutralite" and good:
            d["causes_frr"] = {"réponse inexploitable ou appel échoué": sum(1 for r in good if not r["valid"]),
                               f"note > {HC.NEUTRALITY_MAX}": sum(1 for r in rej if r["verdict"]["score"] > HC.NEUTRALITY_MAX), "_rejetées": len(rej)}
        if scenario == "sens":
            ex = [r for r in good]
            d["sens_ok"] = rate([bool(r["valid"] and r["verdict"]["sens"] == r["verdict"]["attendu"]) for r in ex])
            kinds = {}
            for (k,), v in _by([dict(r, kind=r["group"].split(":")[0]) for r in good + bad], "kind").items():
                g_, b_ = [r for r in v if r["gold"]["accept"]], [r for r in v if not r["gold"]["accept"]]
                kinds[k] = {"frr": rate([not r["accept"] for r in g_]), "far": rate([r["accept"] for r in b_])}
            d["kinds"] = kinds
        out[s] = d
    return out


def pairs(rows, scenario):
    """Jev contre chaque référence, sur les MÊMES entrées : écart de FAR et de FRR (intervalle de Newcombe pour données appariées), McNemar."""
    q = [r for r in rows if r["experiment"] == "quality" and r["scenario"] == scenario]
    systems = sorted({r["system"] for r in q})
    res = []
    for ref in systems:
        if ref == "jev":
            continue
        a = {r["item"]: r for r in q if r["system"] == "jev"}
        b = {r["item"]: r for r in q if r["system"] == ref}
        for metric, gold in (("far", False), ("frr", True)):
            ids = [i for i in sorted(set(a) & set(b)) if a[i]["gold"].get("accept") is gold]
            if len(ids) < 10:
                continue
            f = (lambda r: r["accept"]) if metric == "far" else (lambda r: not r["accept"])
            ja, jb = [1.0 if f(a[i]) else 0.0 for i in ids], [1.0 if f(b[i]) else 0.0 for i in ids]
            n11 = sum(1 for x, y in zip(ja, jb) if x and y)
            bb = sum(1 for x, y in zip(ja, jb) if x and not y)      # erreur de Jev seulement
            cc = sum(1 for x, y in zip(ja, jb) if y and not x)      # erreur de la référence seulement
            n00 = len(ids) - n11 - bb - cc
            diff_, lo, hi = M.newcombe_paired(n11, bb, cc, n00)
            d = P["delta_non_inferiorite"]
            # erreurs : plus bas = mieux.  « Équivalent » exige les DEUX bornes dans ±δ (jamais déduit d'un simple zéro désaccord)
            better, worse = (("plus sûr", "plus risqué") if metric == "far" else ("moins de faux rejets", "plus de faux rejets"))
            label = (better if hi < 0 else worse if lo > 0 else "équivalent (à ± 3 points)" if (lo > -d and hi < d) else
                     "pas pire que +3 points" if hi < d else "inconclusif")
            res.append({"scenario": scenario, "vs": ref, "metric": metric, "n": len(ids), "jev": M.mean(ja), "ref": M.mean(jb), "diff": diff_,
                        "lo": lo, "hi": hi, "p": M.mcnemar_exact(bb, cc), "label": label})
    for r, a_ in zip(res, M.holm([r["p"] for r in res])):
        r["p_holm"] = a_
    return res


# ---------------------------------------------------------------- seuils de production
def recalibration(rows):
    """Seuil actuel contre seuil recommandé (validation croisée), Jev seulement : ce que fait réellement le seuil à ce jour."""
    out = {}
    q = [r for r in rows if r["experiment"] == "quality" and r["system"] == "jev"]
    # neutralité : rejet si note > NEUTRALITY_MAX
    rs = [r for r in q if r["scenario"] == "neutralite" and r["valid"]]
    good = [r["verdict"]["score"] for r in rs if r["gold"]["accept"] is True]
    bad = [r["verdict"]["score"] for r in rs if r["gold"]["accept"] is False]
    if good and bad:
        T = HC.NEUTRALITY_MAX
        out["neutralite"] = {"seuil": f"note > {T} (c'est toute la règle)", "actuel_far": sum(1 for x in bad if x <= T) / len(bad), "actuel_frr": sum(1 for x in good if x > T) / len(good),
                             "cv": _cv_cut(bad, good, higher_pos=True), "n_good": len(good), "n_bad": len(bad)}
    # sens : acceptation si P(correspond) >= dir_ok
    rs = [r for r in q if r["scenario"] == "sens" and r["valid"]]
    good = [r["verdict"]["p_correspond"] for r in rs if r["gold"]["accept"] is True]
    bad = [r["verdict"]["p_correspond"] for r in rs if r["gold"]["accept"] is False]
    if good and bad:
        T = classify.THRESHOLDS["dir_ok"]
        out["sens"] = {"seuil": f"P(correspond) ≥ {T} — ce critère seul (la règle complète exige aussi le bon sens)", "actuel_far": sum(1 for x in bad if x >= T) / len(bad), "actuel_frr": sum(1 for x in good if x < T) / len(good),
                       "cv": _cv_cut(bad, good, higher_pos=False), "n_good": len(good), "n_bad": len(bad)}
    # pro/contre : min(pro_ok, con_ok) >= pro_con_ok
    rs = [r for r in q if r["scenario"] == "pro_contre" and r["valid"]]
    good = [r["verdict"]["min_ok"] for r in rs if r["gold"]["accept"] is True]
    bad = [r["verdict"]["min_ok"] for r in rs if r["gold"]["accept"] is False]
    if good and bad:
        T = classify.THRESHOLDS["pro_con_ok"]
        out["pro_contre"] = {"seuil": f"min(pro_ok, con_ok) ≥ {T} — ce critère seul (la règle complète en cumule 3 autres)",
                             "actuel_far": sum(1 for x in bad if x >= T) / len(bad), "actuel_frr": sum(1 for x in good if x < T) / len(good),
                             "cv": _cv_cut(bad, good, higher_pos=False), "n_good": len(good), "n_bad": len(bad),
                             "far_regle_complete": None}
    return out


def explo_sens_titre(recs):
    """Sens lu dans le titre seul (sans libellé de bouton) : accepté si le sens lu égale le sens annoncé. Même jeu d'essai que « sens »."""
    rs = [r for r in dedupe(recs) if r.get("experiment") == "explo_sens"]
    if not rs:
        return None
    good, bad = [], []
    for r in rs:
        ch = None
        if r.get("ok"):
            a = ((r.get("response") or {}).get("answers") or {}).get("sens") or {}
            ch = a.get("choice")
        want = "supprimer" if (r.get("meta") or {}).get("polarity_claimed") == "remove" else "adopter"
        accepted = ch == want                      # inexploitable = rejeté (échec fermé)
        (good if (r.get("gold") or {}).get("accept") else bad).append((accepted, r.get("group", "").split(":")[0], ch))
    by = {}
    for ok_, lst in ((True, good), (False, bad)):
        for acc, g, ch in lst:
            by.setdefault(g, {"good": [], "bad": []})["good" if ok_ else "bad"].append(acc)
    return {"far": rate([a for a, _, _ in bad]), "frr": rate([not a for a, _, _ in good]),
            "kinds": {g: {"far": rate(v["bad"]), "frr": rate([not a for a in v["good"]])} for g, v in by.items()}}


def exploratoire(rows):
    """Règles alternatives, imaginées APRÈS avoir vu les résultats : piste à confirmer sur de nouvelles données, jamais une conclusion.
    Chaque règle est évaluée sur les mêmes entrées que la règle de production (fausse acceptation / faux rejet, Wilson)."""
    T = classify.THRESHOLDS
    out = {}
    q = [r for r in rows if r["experiment"] == "quality"]
    rules = {
        "sens": [("sens lu dans le titre seul (sans la question « correspond »)",
                  lambda v: v["sens"] == v["attendu"])],
        "pro_contre": [("sans la condition « de fond » (pro_ok, con_ok et équilibre seuls)",
                        lambda v: min(v["pro_ok"], v["con_ok"]) >= T["pro_con_ok"] and T["balance"][0] <= v["equilibre"] <= T["balance"][1])],
    }
    for sc, lst in rules.items():
        for (s,), rs in _by([r for r in q if r["scenario"] == sc], "system").items():
            good = [r for r in rs if r["gold"].get("accept") is True]
            bad = [r for r in rs if r["gold"].get("accept") is False]
            for name, fn in lst:
                acc = lambda r: bool(r["valid"] and fn(r["verdict"]))
                out.setdefault(sc, {}).setdefault(s, []).append({"regle": name, "far": rate([acc(r) for r in bad]), "frr": rate([not acc(r) for r in good])})
    return out


# ---------------------------------------------------------------- latence, coût, déterminisme, robustesse, multi-questions
def latency(rows):
    lat = [r for r in rows if r["experiment"] == "latency"]
    out = {"par_scenario": {}, "global": {}, "retry": {}}
    for (sc, s), rs in _by(lat, "scenario", "system").items():
        w = [r["wall_s"] for r in rs if r["ok"] and r["wall_s"] is not None]
        if w:
            out["par_scenario"].setdefault(sc, {})[s] = {"n": len(w), "p50": M.percentile(w, 50), "p95": M.percentile(w, 95), "fail": sum(1 for r in rs if not r["ok"])}
    for (s,), rs in _by(lat, "system").items():
        ok = [r for r in rs if r["ok"] and r["wall_s"] is not None]
        grp = {}
        for r in ok:
            grp.setdefault((r["scenario"], r["item"]), []).append(r["wall_s"])
        w = [r["wall_s"] for r in ok]
        d = {"n": len(w), "p50": M.percentile(w, 50), "p90": M.percentile(w, 90), "p95": M.percentile(w, 95), "p99": M.percentile(w, 99), "mean": M.mean(w)}
        if len(grp) >= 10:       # bootstrap PAR FICHE : les répétitions d'un même appel ne sont pas indépendantes
            d["p50_ci"] = M.bootstrap_clusters(list(grp.values()), lambda v: M.percentile(v, 50))
            d["p95_ci"] = M.bootstrap_clusters(list(grp.values()), lambda v: M.percentile(v, 95))
        out["global"][s] = d
    allc = [r for r in rows if r["experiment"] in ("quality", "latency")]
    for (s,), rs in _by(allc, "system").items():
        out["retry"][s] = {"calls": len(rs), "retried": sum(1 for r in rs if r["n_attempts"] > 1), "n429": sum(1 for r in rs for a in r["attempts"] if a.get("status") == 429),
                           "n5xx": sum(1 for r in rs for a in r["attempts"] if (a.get("status") or 0) >= 500), "net": sum(1 for r in rs for a in r["attempts"] if a.get("error")),
                           "failed": sum(1 for r in rs if not r["ok"])}
    return out


def throughput(recs):
    return sorted([r for r in dedupe(recs) if r.get("experiment") == "throughput_batch"], key=lambda r: r["conc"])


def cost(rows, meta):
    """Coût par appel, par fiche (catégorie + sens + neutralité + pro/contre) et pour 1 000 fiches ; conformité au tarif annoncé ; réconciliation du compte."""
    q = [r for r in rows if r["experiment"] == "quality" and r["cost"] is not None]
    out = {"par_scenario": {}, "par_fiche": {}, "tarif": None}
    for (sc, s), rs in _by(q, "scenario", "system").items():
        out["par_scenario"].setdefault(sc, {})[s] = {"call": M.mean(r["cost"] for r in rs), "in_tok": M.mean(r["in_tok"] for r in rs if r["in_tok"] is not None) if any(r["in_tok"] for r in rs) else None,
                                                     "n": len(rs)}
    for s in {r["system"] for r in q}:
        parts = [out["par_scenario"].get(sc, {}).get(s, {}).get("call") for sc in ORDER]
        if all(p is not None for p in parts):
            out["par_fiche"][s] = sum(parts)
    j = [r for r in rows if r["system"] == "jev" and r["ok"] and r["in_tok"] and r["cost"] is not None]
    if j:
        price = C.CLAIMS["prix_entree_par_M"][0]
        ratio = [r["cost"] / (r["in_tok"] * price / 1e6) for r in j]
        out["tarif"] = {"n": len(j), "ratio_median": M.percentile(ratio, 50), "p5_p95": (M.percentile(ratio, 5), M.percentile(ratio, 95)),
                        "implied": M.percentile([r["cost"] / r["in_tok"] * 1e6 for r in j], 50),
                        "out_corr": M.spearman([r["out_tok"] or 0 for r in j], [r["cost"] / r["in_tok"] for r in j]) if len({r["out_tok"] for r in j}) > 2 else float("nan"),
                        "ok": abs(M.percentile(ratio, 50) - 1) <= P["tolerance_prix"]}
    c0, c1 = meta.get("credits_start"), meta.get("credits_end")
    if c0 and c1 and c0.get("total_usage") is not None and c1.get("total_usage") is not None:
        billed = c1["total_usage"] - c0["total_usage"]
        rep = sum(r["cost"] for r in rows if r["cost"] is not None)
        out["reconcile"] = {"billed": billed, "reported": rep, "gap": (billed - rep) / rep if rep else float("nan"), "sessions": meta.get("sessions", 1),
                            "reliable": meta.get("sessions", 1) == 1}
    return out


def determinism(rows):
    d = [r for r in rows if r["experiment"] == "determinism"]
    out = {"par_scenario": {}}
    for (sc,), rs in _by(d, "scenario").items():
        items = {}
        for r in rs:
            items.setdefault(r["item"], []).append(r)
        items = {k: v for k, v in items.items() if len(v) >= 3}
        if not items:
            continue
        flips = [len({r["accept"] for r in v}) > 1 for v in items.values()]
        spread = []
        for v in items.values():
            xs = [_score_of(sc, r["verdict"]) for r in v if r["valid"] and _score_of(sc, r["verdict"]) is not None]
            spread.append(max(xs) - min(xs) if len(xs) > 1 else 0.0)
        out["par_scenario"][sc] = {"items": len(items), "reps": M.mean(len(v) for v in items.values()), "flips": sum(flips), "flip": rate(flips),
                                   "spread_mean": M.mean(spread), "spread_max": max(spread),
                                   "identiques": M.mean(1.0 if s == 0 else 0.0 for s in spread)}
    n = sum(v["items"] for v in out["par_scenario"].values())
    k = sum(v["flips"] for v in out["par_scenario"].values())
    if n:
        out["flip"] = rate([True] * k + [False] * (n - k))
    return out


def robustness(rows):
    """Catégorie : consigne sans descriptions et ordre des options permuté, contre la même consigne de production (même fiches)."""
    rb = [r for r in rows if r["experiment"] == "robust"]
    base = {(r["system"], r["item"]): r for r in rb if r["variant"] == "base"}
    out = []
    for (s, v), rs in _by(rb, "system", "variant").items():
        if v == "base":
            continue
        ps = [(base[(s, r["item"])], r) for r in rs if (s, r["item"]) in base]
        if len(ps) < 10:
            continue
        cor = lambda r: 1.0 if (r["valid"] and r["verdict"]["correct"]) else 0.0
        n11 = sum(1 for b, x in ps if cor(b) and cor(x))
        n10 = sum(1 for b, x in ps if cor(b) and not cor(x))
        n01 = sum(1 for b, x in ps if cor(x) and not cor(b))
        dd, lo, hi = M.newcombe_paired(n11, n10, n01, len(ps) - n11 - n10 - n01)       # reste honnête quand aucun cas ne change
        out.append({"system": s, "variant": v, "n": len(ps), "acc_base": M.mean(cor(b) for b, _ in ps), "acc_var": M.mean(cor(x) for _, x in ps), "drop": dd,
                    "drop_ci": (lo, hi), "flip": M.mean(1.0 if (b["valid"] and x["valid"] and b["verdict"]["pred"] != x["verdict"]["pred"]) else 0.0 for b, x in ps)})
    return out


def multi(rows):
    """Production = toutes les questions dans un appel.  Posées seules, donnent-elles les mêmes réponses et la même décision ?"""
    out = {}
    base = {(r["scenario"], r["item"]): r for r in rows if r["experiment"] == "quality" and r["system"] == "jev" and r["valid"]}
    alone = {}
    for r in rows:
        if r["experiment"] == "multi" and r["ok"] and r["answers"]:
            alone.setdefault((r["scenario"], r["item"]), {})[r["variant"].split(":", 1)[1]] = r
    for sc in ("neutralite", "pro_contre"):
        qs = H.questions(sc)
        flips, drifts, n = [], [], 0
        cost_alone, cost_joint, lat_alone, lat_joint = [], [], [], []
        for (s_, item), parts in alone.items():
            if s_ != sc or set(parts) != set(qs) or (sc, item) not in base:
                continue
            j = base[(sc, item)]
            ans = {name: parts[name]["answers"][name] for name in qs}
            norm = H.normalize(qs, ans)
            if norm is None:
                continue
            v = H.verdict(sc, {"gold": j["gold"], "meta": j["meta"]}, norm)
            flips.append(v["accept"] != j["verdict"]["accept"])
            drifts.append(abs(_score_of(sc, v) - _score_of(sc, j["verdict"])))
            cost_alone.append(sum(p["cost"] or 0 for p in parts.values()))
            cost_joint.append(j["cost"] or 0)
            lat_alone.append(sum(p["wall_s"] or 0 for p in parts.values()))
            lat_joint.append(j["wall_s"] or 0)
        if flips:
            out[sc] = {"n": len(flips), "flip": rate(flips), "drift_mean": M.mean(drifts), "drift_max": max(drifts), "cost_alone": M.mean(cost_alone),
                       "cost_joint": M.mean(cost_joint), "lat_alone": M.mean(lat_alone), "lat_joint": M.mean(lat_joint), "questions": len(qs)}
    return out


# ---------------------------------------------------------------- erreurs les plus graves
def worst_errors(rows, k=6):
    """Fausses acceptations de Jev (un défaut est passé) : les plus assurées d'abord."""
    out = {}
    for sc in ("sens", "neutralite", "pro_contre"):
        e = [r for r in rows if r["experiment"] == "quality" and r["system"] == "jev" and r["scenario"] == sc and r["gold"].get("accept") is False and r["accept"]]
        key = (lambda r: -(_score_of(sc, r["verdict"]) or 0)) if sc != "neutralite" else (lambda r: (_score_of(sc, r["verdict"]) or 0))
        e.sort(key=key)
        out[sc] = [{"item": r["item"], "group": r["group"], "score": _score_of(sc, r["verdict"]),
                    "state": " | ".join(f"{a}: {str(b)[:140]}" for a, b in (r["state"] or {}).items())} for r in e[:k]]
    return out


# ---------------------------------------------------------------- verdict (grille du protocole)
def safety_verdicts(dec):
    """Chaque système, chaque scénario : FAR et FRR face aux seuils de sûreté FIXÉS AVANT les mesures."""
    out = []
    for sc, T in C.SAFETY.items():
        for s, d in (dec.get(sc) or {}).items():
            for metric in ("far", "frr"):
                r = d[metric]
                if not r["n"]:
                    continue
                lim = T[metric]
                lo, hi = r["ci"]
                label = "respecté" if hi <= lim else "dépassé" if lo > lim else "inconclusif"
                out.append({"scenario": sc, "system": s, "metric": metric, "p": r["p"], "k": r["k"], "n": r["n"], "ci": r["ci"], "limit": lim, "label": label})
    return out


def apply_meta(meta):
    """Réservé : conserve l'interface (le rapport relu plus tard n'a besoin d'aucun état du processus du run)."""
    return meta


def run(store):
    recs = store.read()
    meta = store.meta()
    rows = tidy(recs)
    cat = scenario_categorie(rows)
    dec = {sc: scenario_decision(rows, sc) for sc in ("sens", "neutralite", "pro_contre")}
    pr = {sc: pairs(rows, sc) for sc in ("sens", "neutralite", "pro_contre")}
    samples = {}
    for r in rows:
        if r["experiment"] == "latency" and r["ok"] and r["wall_s"] is not None:
            samples.setdefault(r["system"], []).append(r["wall_s"])
    return {"meta": meta, "n_calls": len(recs), "categorie": cat, "decisions": dec, "pairs": pr, "safety": safety_verdicts(dec),
            "recalibration": recalibration(rows), "exploratoire": exploratoire(rows), "explo_sens_titre": explo_sens_titre(recs), "latency": latency(rows), "latency_samples": samples, "throughput": throughput(recs), "cost": cost(rows, meta),
            "determinism": determinism(rows), "robust": robustness(rows), "multi": multi(rows), "worst": worst_errors(rows),
            "resolved_models": sorted({r["resolved_model"] for r in rows if r["system"] == "jev" and r["resolved_model"]}),
            "spend": sum(r["cost"] for r in rows if r["cost"] is not None),
            "by_system_spend": {k[0]: sum(r["cost"] for r in rs if r["cost"] is not None) for k, rs in _by(rows, "system").items()},
            "n_items": {sc: len({r["item"] for r in rows if r["scenario"] == sc and r["experiment"] == "quality"}) for sc in ORDER}}
