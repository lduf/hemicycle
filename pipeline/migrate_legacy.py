"""Migration unique du MVP v5 (quiz_data.json + contenus écrits à la main) vers content/ ; statut `legacy` = « non relu »."""
import json, os
from . import config as C, direction as D, sources as S, store


def run(root=C.ROOT):
    qd = C.jload(os.path.join(root, "legacy", "quiz_data.json"))
    cj = lambda n: C.jload(os.path.join(root, "content", "legacy", n), {})
    labels = cj("labels.json")
    hook, surp = cj("hook.json"), cj("surp.json")
    scr = C.jload(os.path.join(C.DATA, "scrutins.json"), {})
    flagged = []
    for q in qd["q"]:
        n = q["n"]; s = scr.get(str(n), {})
        cl = D.classify(s.get("titre", ""))
        pol = cl["polarity"] or "adopt"
        if cl["polarity"] != "adopt":
            flagged.append((n, cl["polarity"], cl["reason"], s.get("titre", "")[:90]))
        rec = dict(n=n, date=q["date"], kind=q["kind"], subkind=cl["kind"], polarity=pol, polarity_verified=cl["polarity"] == "adopt",
                   cat=q["cat"], title=q["title"], label=labels.get(str(n)), hook=hook.get(str(n)), sum=q["sum"], pro=q["pro"], con=q["con"],
                   surp=surp.get(str(n)), sources=[dict(label="Scrutin officiel (Assemblée nationale)", url=S.scrutin_url(n))],
                   status="legacy", reviews=[], checks={}, legacy=True,
                   notes="Rédigé par IA dans le MVP, non relu. À revérifier à la source."
                   + (" Résumé en partie issu de connaissances générales." if n in (1308, 988, 1194, 606, 852, 2957, 7259) else ""))
        store.save(rec)
    # promesses héritées : déjà affichées dans le MVP, conservées telles quelles (statut legacy)
    prom = cj("prom.json")
    matches = {n: [dict(p, status="legacy") for p in L] for n, L in prom.items()}
    C.jdump(matches, os.path.join(C.CONTENT, "promise_matches.json"), indent=1)
    C.jdump(cj("src.json"), os.path.join(C.CONTENT, "sources.json"), indent=1)
    print(f"[migrate] {len(qd['q'])} questions ; polarité à contrôler à la main :")
    for f in flagged:
        print("   ", f)
    return flagged


if __name__ == "__main__":
    run()
