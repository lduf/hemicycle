"""Étape 5 : validation humaine par deux relecteurs de sensibilités opposées.

Règle : une fiche passe à `published` quand elle a >= MIN_REVIEWERS approbations de personnes DISTINCTES,
dont au moins une « gauche » et une « droite », toutes portant sur la version actuelle du texte (empreinte).
Un refus l'envoie en `rejected`. Toute modification du texte efface les approbations (voir store.text_hash).
CLI :  python -m pipeline.review list | show N | sign N --by NOM --side gauche|droite|centre --verdict approve|reject [--note ..]
"""
import argparse, datetime as dt
from . import config as C, store

SIDES = ("gauche", "centre", "droite")


def valid_reviews(q):
    h = store.text_hash(q)
    return [r for r in q.get("reviews", []) if r.get("hash") == h]


def can_publish(q):
    if q.get("status") not in ("pending_review", "published"):
        return False, f"statut {q.get('status')}"
    rs = [r for r in valid_reviews(q) if r["verdict"] == "approve"]
    people = {r["by"].strip().lower() for r in rs}
    sides = {r["side"] for r in rs}
    if len(people) < C.MIN_REVIEWERS:
        return False, f"{len(people)}/{C.MIN_REVIEWERS} relecteurs"
    if not {"gauche", "droite"} <= sides:
        return False, "il faut au moins un relecteur de gauche et un de droite"
    if not store.sources_ok(q):
        return False, "sources manquantes"
    return True, "ok"


def sign(n, by, side, verdict, note=""):
    q = store.load(n)
    if not q:
        raise SystemExit(f"question {n} introuvable")
    if side not in SIDES or verdict not in ("approve", "reject"):
        raise SystemExit("side ∈ gauche|centre|droite ; verdict ∈ approve|reject")
    if q["status"] not in ("pending_review", "published", "legacy"):
        raise SystemExit(f"statut {q['status']} : relecture impossible")
    q["reviews"] = [r for r in q.get("reviews", []) if r["by"].lower() != by.lower() or r.get("hash") != store.text_hash(q)]
    q["reviews"].append(dict(by=by, side=side, verdict=verdict, note=note, hash=store.text_hash(q), date=dt.date.today().isoformat()))
    if verdict == "reject":
        q["status"] = "rejected"
        rej = set(C.jload(f"{C.CONTENT}/rejected.json", []))
        rej.add(int(n)); C.jdump(sorted(rej), f"{C.CONTENT}/rejected.json")
    else:
        ok, why = can_publish(dict(q, status="pending_review") if q["status"] == "legacy" else q)
        if ok:
            q["status"] = "published"
    store.save(q)
    print(f"[review] {n} : {q['status']}" + ("" if q["status"] == "published" else f" ({can_publish(dict(q, status='pending_review'))[1]})"))
    return q


def listing():
    for q in store.all_questions():
        ok, why = can_publish(dict(q, status="pending_review")) if q["status"] in ("pending_review", "legacy") else (False, "")
        print(f"{q['n']:>5} {q['status']:<15} {len(valid_reviews(q))} relecture(s) valide(s)  {why:<45} {str(q.get('title'))[:50]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("list")
    s = sp.add_parser("show"); s.add_argument("n", type=int)
    g = sp.add_parser("sign"); g.add_argument("n", type=int); g.add_argument("--by", required=True)
    g.add_argument("--side", required=True); g.add_argument("--verdict", required=True); g.add_argument("--note", default="")
    a = ap.parse_args()
    if a.cmd == "list":
        listing()
    elif a.cmd == "show":
        import json; print(json.dumps(store.load(a.n), ensure_ascii=False, indent=1))
    else:
        sign(a.n, a.by, a.side, a.verdict, a.note)
