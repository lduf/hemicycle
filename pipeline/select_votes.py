"""Étape 2 : sélection des scrutins intéressants.

Critères (tous déterministes et reproductibles) :
  - divergence entre groupes (les groupes ne votent pas tous pareil)
  - participation suffisante (assez de votants)
  - mesure isolée de préférence (article / amendement précis / ensemble d'un texte court)
  - pas de procédure obscure, pas de sens douteux (direction.classify)
"""
import os
from . import config as C, direction as D


def group_margin(g):
    p, c, a = g[0], g[1], g[2]
    den = p + c + a
    return (p - c) / den if den else None


def features(f):
    ms = {s: group_margin(v) for s, v in f["g"].items() if s in C.SCORED}
    ms = {s: m for s, m in ms.items() if m is not None}
    if len(ms) < 8:
        return None
    pos = sum(1 for m in ms.values() if m >= .5)
    neg = sum(1 for m in ms.values() if m <= -.5)
    # divergence : 0 si tout le monde du même côté, 1 si 50/50
    firm = pos + neg
    div = (2 * min(pos, neg) / firm) if firm else 0
    spread = max(ms.values()) - min(ms.values())
    votants = f["tot"][0] + f["tot"][1] + f["tot"][2]
    return dict(div=div, spread=spread, votants=votants, pos=pos, neg=neg, ms=ms)


def score(f, ft, cl):
    s = 0.5 * ft["div"] + 0.3 * min(ft["spread"] / 2, 1) + 0.2 * min(ft["votants"] / 400, 1)
    if cl["kind"] in ("ensemble", "article"):
        s += 0.15        # mesure isolée / texte complet : plus lisible
    if cl["kind"] == "amendement":
        s += 0.05
    if f["type"] == "SPS":
        s += 0.05        # scrutin solennel
    return round(s, 4)


def law_key(titre):
    """Même loi, lectures différentes : on ne propose qu'un scrutin par texte (« (nouvelle lecture) », « (texte de la commission) »…)."""
    import re
    t = re.sub(r"\([^)]*\)", "", titre.lower().replace("’", "'"))
    t = re.sub(r"^l'ensemble (du|de la|des|de l')\s*", "", t.strip())
    return re.sub(r"\s+", " ", t).strip(" .")


def candidates(scrutins, taken=(), min_votants=150, min_div=0.2, min_date=None):
    """Retourne la liste triée des candidats non encore traités (`taken` = numéros déjà en base)."""
    seen = {law_key(scrutins[str(n)]["titre"]) for n in taken if str(n) in scrutins}
    out = []
    for k, f in scrutins.items():
        n = int(k)
        if n in taken or f["type"] == "MOC":
            continue
        if min_date and f["date"] < min_date:
            continue
        cl = D.classify(f["titre"])
        if cl["polarity"] is None or cl["kind"] in ("procedure", "autre"):
            continue
        ft = features(f)
        if not ft or ft["votants"] < min_votants or ft["div"] < min_div:
            continue
        out.append(dict(n=n, date=f["date"], titre=f["titre"], kind=cl["kind"], polarity=cl["polarity"],
                        why=cl["reason"], score=score(f, ft, cl), div=round(ft["div"], 3), votants=ft["votants"],
                        sort=f["sort"]))
    out.sort(key=lambda x: (-x["score"], x["n"]))
    uniq = []
    for c in out:
        k = law_key(c["titre"])
        if k in seen:
            continue
        seen.add(k); uniq.append(c)
    return uniq


def run(limit=20, min_date=None):
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"), {})
    taken = {int(os.path.splitext(f)[0]) for f in os.listdir(os.path.join(C.CONTENT, "questions"))} \
        if os.path.isdir(os.path.join(C.CONTENT, "questions")) else set()
    rejected = set(C.jload(os.path.join(C.CONTENT, "rejected.json"), []))
    cands = candidates(sc, taken | rejected, min_date=min_date)
    C.jdump(cands[:200], os.path.join(C.DATA, "candidates.json"), indent=1)
    print(f"[select] {len(cands)} candidats ; top {min(limit, len(cands))} :")
    for c in cands[:limit]:
        print(f"  {c['n']:>5} {c['date']} {c['score']:.2f} div={c['div']:.2f} {c['polarity']:<6} {c['titre'][:90]}")
    return cands


if __name__ == "__main__":
    run()
