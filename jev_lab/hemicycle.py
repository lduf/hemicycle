"""Scénarios d'étude de Jev = les appels RÉELS du pipeline hémicycle.

Rien n'est réinventé : les questions envoyées à Jev et les règles de décision (seuils inclus) sont celles de
`pipeline/classify.py` (fonctions `*_call` et `*_verdict`).  Si la production change, l'étude change avec elle.

Scénarios (un par appel de production) :
  categorie   fiche.py    : Jev propose la catégorie ; acceptée si confiance >= THRESHOLDS['cat_min'].
  sens        fiche.py    : le bouton « Pour … » correspond-il au sens du vote ?  (fausse acceptation = bouton inversé publié)
  neutralite  neutrality  : note d'orientation 0-5 ; fiche rejetée si > NEUTRALITY_MAX.
  pro_contre  fiche.py    : les arguments pour/contre défendent-ils bien la mesure, sur le fond, à poids égal ?
Non couvert : `sources_sufficient` (pré-contrôle du lot) : il faudrait des extraits de sources étiquetés par un humain.

Vérité terrain : connue PAR CONSTRUCTION (bouton exact / inversé, arguments permutés / tronqués, fiche réécrite orientée)
ou posée à la main (34 catégories du MVP).  Jamais devinée par un modèle, sauf les variantes réécrites (voir gen_variants).
"""
import json, os, random, re
from pipeline import classify, config as HC, direction as D, store as HS
from . import config as C

VARIANTS_PATH = os.path.join(HC.CONTENT, "bench", "variantes_neutralite.json")
GOLD_DIR = os.path.join(HC.CONTENT, "gold")
FIELDS = ("title", "label", "hook", "sum", "pro", "con", "surp")
STRONG = ("pour", "contre")

# Décisions « acceptées » attendues (None = on ne tranche pas)
SCENARIOS = {
    "categorie": "Catégorie proposée par Jev (acceptée si confiance ≥ seuil, sinon la catégorie du rédacteur est conservée)",
    "sens": "Le bouton « Pour … » correspond-il au sens réel du vote ? (échec fermé)",
    "neutralite": "Note d'orientation 0–5 ; la fiche est rejetée si la note dépasse NEUTRALITY_MAX",
    "pro_contre": "Les arguments pour / contre sont-ils pertinents, sur le fond et de poids comparable ?",
}
ORDER = list(SCENARIOS)


# ---------------------------------------------------------------- données du dépôt
def _fiches(statuses):
    return [q for q in HS.all_questions() if q.get("status") in statuses]


def fiches_pro_con():
    """Fiches avec pour/contre rédigés (MVP validées + lot automatique non relu)."""
    return [q for q in _fiches({"legacy", "pending_review", "published"}) if q.get("pro") and q.get("con") and q.get("sum")]


def scrutins():
    p = os.path.join(HC.DATA, "scrutins.json")
    d = HC.jload(p)
    if not d:
        raise RuntimeError("data/scrutins.json absent : lancer `python -m pipeline.ingest` (titres officiels des scrutins)")
    return d


def _fields(q):
    return {f: q.get(f) for f in FIELDS}


def _gold_file(name):
    p = os.path.join(GOLD_DIR, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


# ---------------------------------------------------------------- questions (identiques à la production)
def questions(scenario, variant="base", seed=C.SEED):
    """Questions envoyées à Jev pour ce scénario.  variantes (catégorie seulement) : nodesc | shuffle<k>."""
    qs = {"categorie": lambda: classify.category_call({})[1], "sens": lambda: classify.direction_call("", "x", "adopt")[1],
          "neutralite": lambda: classify.orientation_call({})[1], "pro_contre": lambda: classify.pro_con_call({})[1]}[scenario]()
    if scenario == "categorie" and variant != "base":
        cq = qs["cat"]
        crit = dict(cq["criteria"])
        if variant == "nodesc":
            crit = {k: k for k in crit}
        elif variant.startswith("shuffle"):
            ks = list(crit)
            random.Random(f"{seed}-{variant}").shuffle(ks)
            crit = {k: crit[k] for k in ks}
        qs = {"cat": dict(cq, criteria=crit)}
    return qs


# ---------------------------------------------------------------- items
def items_categorie():
    out = []
    for q in _fiches({"legacy"}):
        state, _ = classify.category_call(q)
        out.append({"id": f"cat-{q['n']}", "scenario": "categorie", "group": "mvp", "state": state,
                    "gold": {"q": {"cat": q["cat"]}, "cat": q["cat"], "accept": None}, "meta": {"n": q["n"]}})
    for i, g in enumerate(x for x in _gold_file("categories.jsonl") if x.get("cat") in HC.CATS):              # extension : étiquettes posées par des humains (voir README)
        state, _ = classify.category_call(g)
        out.append({"id": f"cat-h{i}", "scenario": "categorie", "group": "humain", "state": state,
                    "gold": {"q": {"cat": g["cat"]}, "cat": g["cat"], "accept": None}, "meta": {"n": g.get("n")}})
    return out


def _sens_items(titre, label, polarity, key, group, extra=None):
    """Deux items par vote : le bouton exact (doit être accepté) et le bouton inversé (doit être rejeté)."""
    inv = "remove" if polarity == "adopt" else "adopt"
    true_sens = "supprimer" if polarity == "remove" else "adopter"
    res = []
    for kind, pol in (("exact", polarity), ("inverse", inv)):
        state, _ = classify.direction_call(titre, label, pol)
        res.append({"id": f"sens-{key}-{kind}", "scenario": "sens", "group": f"{group}:{kind}", "state": state,
                    "gold": {"q": {"correspond": kind == "exact", "sens": true_sens}, "accept": kind == "exact"},
                    "meta": {"polarity_claimed": pol, "polarity_true": polarity, "kind": group, **(extra or {})}})
    return res


def items_sens(n_extra=90, seed=C.SEED):
    sc = scrutins()
    out = []
    for q in _fiches({"legacy", "pending_review", "published", "blocked"}):
        titre = (sc.get(str(q["n"])) or {}).get("titre")
        if titre and q.get("label") and q.get("polarity") in ("adopt", "remove"):
            out += _sens_items(titre, q["label"], q["polarity"], q["n"], "fiche")
    # titres officiels supplémentaires dont le sens est certain par construction (ensemble / suppression / amendement), libellé générique
    rng, buckets = random.Random(seed), {"ensemble": [], "suppression": [], "amendement": []}
    for k, s in sorted(sc.items()):
        c = D.classify(s["titre"])
        if c["polarity"] is None:
            continue
        if c["kind"] == "ensemble":
            buckets["ensemble"].append((k, s["titre"], "adopt"))
        elif c["polarity"] == "remove" and c["kind"] == "amendement":
            buckets["suppression"].append((k, s["titre"], "remove"))
        elif c["kind"] == "amendement":
            buckets["amendement"].append((k, s["titre"], "adopt"))
    taken = {q["n"] for q in _fiches({"legacy", "pending_review", "published", "blocked"})}
    for b, L in buckets.items():
        L = [x for x in L if str(x[0]) not in {str(t) for t in taken}]
        for k, titre, pol in rng.sample(L, min(len(L), n_extra // 3)):
            out += _sens_items(titre, "la mesure examinée", pol, k, f"titre_{b}")
    return out


def load_variants(path=None):
    p = path or VARIANTS_PATH
    return HC.jload(p, {})


def items_neutralite(variants=None):
    var = variants if variants is not None else load_variants()
    out = []
    for q in fiches_pro_con():
        state, _ = classify.orientation_call(q)
        out.append({"id": f"neu-{q['n']}-orig", "scenario": "neutralite", "group": "orig", "state": state,
                    "gold": {"q": {"charge": None}, "accept": True}, "meta": {"n": q["n"]}})
        for k in ("pour", "contre", "subtil"):
            v = (var.get(str(q["n"])) or {}).get(k)
            if not v:
                continue
            st, _ = classify.orientation_call(dict(_fields(q), **{f: v.get(f) or q.get(f) for f in FIELDS}))
            out.append({"id": f"neu-{q['n']}-{k}", "scenario": "neutralite", "group": k, "state": st,
                        "gold": {"q": {"charge": True if k in STRONG else None}, "accept": False if k in STRONG else None},
                        "meta": {"n": q["n"]}})
    return out


def items_pro_contre():
    fs = fiches_pro_con()
    out = []
    for i, q in enumerate(fs):
        other = fs[(i + 7) % len(fs)]
        variants = {
            "orig": (q["pro"], q["con"]),
            "permutes": (q["con"], q["pro"]),
            "contre_tronque": (q["pro"], " ".join(q["con"].split()[:6]) + "."),
            "contre_d_une_autre_mesure": (q["pro"], other["con"]),
        }
        for k, (pro, con) in variants.items():
            state, _ = classify.pro_con_call(dict(q, pro=pro, con=con))
            gq = {"pro_ok": k != "permutes", "con_ok": k not in ("permutes", "contre_d_une_autre_mesure")} if k != "orig" else {"pro_ok": True, "con_ok": True}
            out.append({"id": f"pc-{q['n']}-{k}", "scenario": "pro_contre", "group": k, "state": state,
                        "gold": {"q": gq, "accept": k == "orig"}, "meta": {"n": q["n"]}})
    return out


def items(scenario, **kw):
    return {"categorie": items_categorie, "sens": items_sens, "neutralite": items_neutralite, "pro_contre": items_pro_contre}[scenario](**kw)


# ---------------------------------------------------------------- lecture des réponses et décisions de production
def _num(x, lo=0.0, hi=1.0):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def _match(value, options):
    if value in options:
        return value
    v = str(value).strip().lower()
    for k in options:
        if str(k).strip().lower() == v:
            return k
    return None


def normalize(qs, answers):
    """Réponses -> forme canonique, ou None si UNE question est inexploitable (la fiche serait refusée : échec fermé)."""
    if not isinstance(answers, dict):
        return None
    out = {}
    for name, q in qs.items():
        a = answers.get(name)
        if not isinstance(a, dict):
            return None
        if q["type"] == "noul":
            p = _num(a.get("noul"))
            if p is None:
                return None
            out[name] = {"type": "noul", "noul": p}
        elif q["type"] == "choice":
            c = _match(a.get("choice"), q["criteria"])
            if c is None:
                return None
            pr = a.get("probabilities") if isinstance(a.get("probabilities"), dict) else {}
            out[name] = {"type": "choice", "choice": c, "confidence": _num(a.get("confidence")),
                         "probabilities": {k: v for k, v in ((k, _num(v)) for k, v in pr.items()) if v is not None}}
        else:
            s = _num(a.get("score"), -0.5, len(q["criteria"]) - 0.5)
            if s is None:
                return None
            out[name] = {"type": "score", "score": s, "confidence": _num(a.get("confidence")),
                         "probabilities": {k: v for k, v in ((k, _num(v)) for k, v in (a.get("probabilities") or {}).items()) if v is not None}
                         if isinstance(a.get("probabilities"), dict) else {}}
    return out


def json_in(text):
    """Premier objet JSON valide d'un texte (tolère le markdown et les phrases autour)."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", text or ""):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def chat_answers(qs, text):
    """Réponse texte d'un modèle de langage -> réponses normalisées (même contrat que Jev, via la consigne de production)."""
    try:
        return normalize(qs, classify.claude_answers(json_in(text), qs))
    except Exception:
        return None


def verdict(scenario, item, answers, thresholds=None):
    """Décision de PRODUCTION à partir des réponses normalisées -> dict(accept: bool, ...détails)."""
    T = thresholds or classify.THRESHOLDS
    if scenario == "categorie":
        v = classify.category_verdict(answers)
        gold = item["gold"]["cat"]
        accepted = (v["confidence"] is None or v["confidence"] >= T["cat_min"]) and v["cat"] in HC.CATS
        pr = v.get("probs") or {}
        top3 = sorted(pr, key=pr.get, reverse=True)[:3] or [v["cat"]]
        return {"accept": accepted, "pred": v["cat"], "conf": v["confidence"], "correct": v["cat"] == gold, "top3": gold in top3}
    if scenario == "sens":
        ok, det = classify.direction_verdict(answers, item["meta"]["polarity_claimed"], T)
        return {"accept": ok, "p_correspond": det["correspond"], "sens": det["sens"], "attendu": det["attendu"], "conf": det["correspond"]}
    if scenario == "neutralite":
        v = classify.orientation_verdict(answers)
        return {"accept": v["score"] <= HC.NEUTRALITY_MAX, "score": v["score"], "charge": v["loaded"], "bord": v["bias"]}
    v = classify.pro_con_verdict(answers, T)
    return {"accept": bool(v["ok"]), "pro_ok": v["pro_ok"], "con_ok": v["con_ok"], "pro_fond": v["pro_fond"], "con_fond": v["con_fond"],
            "equilibre": v["equilibre"], "min_ok": min(v["pro_ok"], v["con_ok"])}


# ---------------------------------------------------------------- variantes de neutralité (réécritures par un modèle de langage)
SLANTS = {"pour": "clairement orientée EN FAVEUR de la mesure : adjectifs de valeur, formules engagées, arguments des opposants minimisés",
          "contre": "clairement orientée CONTRE la mesure : adjectifs de valeur, formules engagées, arguments des partisans minimisés",
          "subtil": "très légèrement cadrée : change seulement quelques mots (verbes ou adjectifs légèrement connotés) et l'ordre des phrases, sans rien dire de faux"}


def variant_prompt(q, slant):
    return (f"Réécris cette fiche pour qu'elle soit {SLANTS[slant]}. Garde les mêmes faits et les mêmes clés JSON ({', '.join(FIELDS)}). "
            f"Réponds uniquement par l'objet JSON. Fiche : {json.dumps(_fields(q), ensure_ascii=False)}")
