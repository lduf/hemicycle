"""Étape 7 : site statique régénéré chaque nuit à partir de JSON. Page HTML autonome, sans compte, aucune donnée stockée.

Quelles fiches sont publiées ?
  published       -> oui, « relue »
  legacy          -> oui, balisée « non relue » (MVP)
  pending_review  -> oui, balisée « non relue » si include_pending (défaut), car les contrôles automatiques sont passés
  draft/blocked/rejected -> jamais
"""
import json, os, re, datetime as dt, shutil
from . import config as C, store, seatmap, promises, direction


def _js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace(" ", "\\u2028")


def select_questions(include_pending=True, include_legacy=True):
    ok = {"published"} | ({"pending_review"} if include_pending else set()) | ({"legacy"} if include_legacy else set())
    return [q for q in store.all_questions() if q["status"] in ok]


def make_data(questions, scrutins, seats):
    qs = []
    for q in questions:
        s = scrutins[str(q["n"])]
        g = {k: v[:4] for k, v in s["g"].items() if k in C.SCORED or k == "NI"}
        qs.append(dict(n=q["n"], kind=q.get("kind", "mesure"), cat=q["cat"], title=q["title"], sum=q["sum"], pro=q["pro"], con=q["con"],
                       date=s["date"], sort=s["sort"], tot=s["tot"], g=g, seats=seats[q["n"]][0], reviewed=q["status"] == "published"))
    cats = [c for c in C.CATS if any(x["cat"] == c for x in qs)]
    return dict(groups=C.GROUP_NAMES, cats=cats, q=qs)


def build(out_dir=None, include_pending=True, include_legacy=True, today=None):
    out_dir = out_dir or C.SITE
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"))
    qs = select_questions(include_pending, include_legacy)
    problems = []
    for q in qs:                                   # garde-fous à la publication
        if str(q["n"]) not in sc: problems.append(f"{q['n']}: scrutin absent des données")
        if not q.get("label") or not q.get("cat"): problems.append(f"{q['n']}: label/catégorie manquants")
        if q["status"] != "legacy" and not store.sources_ok(q): problems.append(f"{q['n']}: sans source")
        if q["status"] == "published":
            from . import review
            ok, why = review.can_publish(q)
            if not ok: problems.append(f"{q['n']}: publiée mais relecture invalide ({why})")
    if problems:
        raise SystemExit("[build] ARRÊT :\n  " + "\n  ".join(problems))
    seats = seatmap.build({q["n"]: sc[str(q["n"])]["date"] for q in qs})
    data = make_data(qs, sc, seats)
    prom = promises.usable(C.jload(promises.MATCHES, {}))
    prom = {n: L for n, L in prom.items() if int(n) in {q["n"] for q in qs}}
    prom = {n: [{k: v for k, v in x.items() if k in ("bloc", "groups", "exp", "text", "src", "flag")} for x in L] for n, L in prom.items() if L}
    html = open(C.TEMPLATE, encoding="utf-8").read()
    rep = {"__DATA__": data, "__SRC__": C.jload(os.path.join(C.CONTENT, "sources.json"), {}), "__PROM__": prom,
           "__STATS__": C.jload(os.path.join(C.DATA, "stats.json"), {"n_scrutins": 0, "groups": {}, "agree": {}}),
           "__HOOK__": {str(q["n"]): q["hook"] for q in qs if q.get("hook")}, "__SURP__": {str(q["n"]): q["surp"] for q in qs if q.get("surp")},
           "__LABELS__": {str(q["n"]): q["label"] for q in qs}}
    for k, v in rep.items():
        assert k in html, f"placeholder {k} absent du template"
        html = html.replace(k, _js(v))
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    # données ouvertes réutilisables + attribution (Licence Ouverte)
    pub = dict(generated=(today or dt.date.today()).isoformat(), licence=C.LICENCE, source="data.assemblee-nationale.fr",
               questions=[dict(n=q["n"], date=q["date"], title=q["title"], label=q["label"], status=q["status"], polarity=q.get("polarity"),
                               url=C.URL_SCRUTIN_PAGE.format(n=q["n"]), sources=q.get("sources")) for q in qs])
    C.jdump(pub, os.path.join(out_dir, "data.json"))
    C.jdump(dict(builds=dt.date.today().isoformat(), n_questions=len(qs), n_reviewed=sum(q["status"] == "published" for q in qs)),
            os.path.join(out_dir, "status.json"))
    print(f"[build] {len(qs)} questions ({sum(q['status'] == 'published' for q in qs)} relues) -> {out_dir}/index.html "
          f"({os.path.getsize(os.path.join(out_dir, 'index.html')) // 1024} Ko)")
    return data


if __name__ == "__main__":
    import sys
    build(include_pending="--no-pending" not in sys.argv, include_legacy="--no-legacy" not in sys.argv)
