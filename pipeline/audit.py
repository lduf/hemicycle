"""Audit permanent des fiches existantes : neutralité déterministe, sources, sens du vote. Écrit data/audit.json."""
import os
from . import config as C, store, neutrality as N, review


def run(verbose=True):
    rows = []
    for q in store.all_questions():
        issues = N.deterministic(q)
        if q.get("status") in ("legacy", "pending_review", "published") and not q.get("polarity_verified", True) and q.get("legacy"):
            issues.append("sens du vote non vérifié par règle")
        if q.get("status") == "published":
            ok, why = review.can_publish(q)
            if not ok: issues.append(f"relecture invalide : {why}")
        rows.append(dict(n=q["n"], status=q["status"], issues=issues))
    C.jdump(rows, os.path.join(C.DATA, "audit.json"), indent=1)
    bad = [r for r in rows if r["issues"]]
    if verbose:
        print(f"[audit] {len(rows)} fiches, {len(bad)} avec remarques")
        for r in bad:
            print(f"  {r['n']:>5} {r['status']:<14}", " | ".join(r["issues"]))
    return rows


if __name__ == "__main__":
    run()
