"""Orchestrateur nocturne : python -m pipeline.nightly [--no-download] [--steps ingest,select,drafts,stats,build,card,report]

Aucune publication « automatique » d'une fiche : le pipeline prépare, filtre et construit ; les humains valident (review.py).
Une étape qui échoue interrompt la chaîne SANS toucher au site déjà publié (le build écrit dans docs/ seulement à la fin).
"""
import argparse, datetime as dt, os, sys, traceback
from . import config as C, ingest, select_votes, fiche, store, stats_build, build_site, weekly_card, audit, review, promises

STEPS = ["ingest", "select", "drafts", "audit", "stats", "build", "card", "report"]


def drafts(max_new=5):
    """Fiches à rédiger : numéros listés dans content/inbox.json {"N": ["https://…officiel", …]} (sources choisies par un humain)."""
    inbox = C.jload(os.path.join(C.CONTENT, "inbox.json"), {})
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"))
    done = 0
    for n, urls in inbox.items():
        if done >= max_new or store.load(n) or n not in sc:
            continue
        fiche.save_and_report(fiche.draft(sc[n], urls)); done += 1
    return done


def report():
    """REVIEW_QUEUE.md : ce qu'un humain doit faire."""
    qs = store.all_questions()
    cands = C.jload(os.path.join(C.DATA, "candidates.json"), [])[:15]
    L = [f"# File de travail — {dt.date.today().isoformat()}", "", "## À relire (2 relecteurs, gauche + droite)"]
    for q in qs:
        if q["status"] in ("pending_review", "legacy"):
            ok, why = review.can_publish(dict(q, status="pending_review"))
            L.append(f"- {q['n']} · {q['title']} — {q['status']} · {why}")
    L += ["", "## Bloquées (à corriger ou abandonner)"]
    L += [f"- {q['n']} · {q.get('blocked_reason')}" for q in qs if q["status"] == "blocked"]
    L += ["", "## Candidats du jour (ajouter des sources officielles dans content/inbox.json pour lancer la rédaction)"]
    L += [f"- {c['n']} · {c['date']} · score {c['score']} · {c['titre'][:100]}" for c in cands]
    L += ["", "## Couverture des promesses"] + [f"- {g}: {k}" for g, k in promises.coverage().items()]
    os.makedirs(C.DATA, exist_ok=True)
    open(os.path.join(C.DATA, "REVIEW_QUEUE.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8").write("\n".join(L) + "\n")
    print("[report] data/REVIEW_QUEUE.md écrit")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true"); ap.add_argument("--steps", default=",".join(STEPS))
    a = ap.parse_args(argv); steps = a.steps.split(",")
    for s in steps:
        print(f"== {s}")
        try:
            if s == "ingest": ingest.run(refresh=not a.no_download)
            elif s == "select": select_votes.run(limit=10, min_date=(dt.date.today() - dt.timedelta(days=120)).isoformat())
            elif s == "drafts": drafts()
            elif s == "audit": audit.run()
            elif s == "stats": C.jdump(stats_build.run(), os.path.join(C.DATA, "stats.json"))
            elif s == "build": build_site.build()
            elif s == "card": weekly_card.run()
            elif s == "report": report()
        except SystemExit as e:
            print(f"ARRÊT à l'étape {s}: {e}"); return 2
        except Exception:
            traceback.print_exc(); print(f"ÉCHEC à l'étape {s} : le site publié n'est pas modifié."); return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
