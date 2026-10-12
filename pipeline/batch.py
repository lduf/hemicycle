"""Lot de rédaction : choisit des candidats, trouve leurs sources officielles, rédige les fiches en parallèle.

  python -m pipeline.batch --n 40 [--workers 4] [--dry]
Ne publie rien : chaque fiche finit `pending_review` (affichée « non relue ») ou `blocked` (jamais affichée).
Seuls les votes sur l'ensemble d'un texte sont retenus (le sens est sûr et le texte officiel décrit la mesure).
"""
import argparse, collections, os, sys, concurrent.futures as cf
from . import config as C, classify, direction as D, select_votes as SV, sources as S, fiche, store


def pick(n, min_date=None):
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"))
    taken = {q["n"] for q in store.all_questions()}
    taken |= {int(k) for k, v in C.jload(os.path.join(C.CONTENT, "inbox.json"), {}).items() if not v}   # sans dossier : inutile de réessayer
    rej = set(C.jload(os.path.join(C.CONTENT, "rejected.json"), []))
    cands = [c for c in SV.candidates(sc, taken | rej, min_date=min_date) if c["kind"] == "ensemble"]
    return cands[:int(n * 1.6)], sc    # marge : certains n'auront pas de dossier officiel


def one(c, sc, inbox):
    n = str(c["n"])
    urls = inbox.get(n)
    if urls is None:
        urls = S.discover(c["n"])
        inbox[n] = urls
    if not urls:
        return c["n"], "sans dossier officiel", None
    texts = []
    for u in urls:
        if "/opendata/RAPP" in u:        # rapport : on saute la table des matières
            full = S.fetch_text(u, 10 ** 7)
            texts.append((u, full[S.body_start(full):][:24000]))
        elif "/opendata/" in u:          # texte initial : exposé des motifs
            texts.append((u, S.fetch_text(u, limit=6000, after="EXPOSÉ DES MOTIFS")))
        else:                            # page du dossier : chronologie
            texts.append((u, S.fetch_text(u, limit=2500)))
    if classify.backend() == "jev":                      # pré-contrôle ~gratuit : évite un appel de rédaction inutile
        try:
            pre = classify.sources_sufficient(sc[n]["titre"], [x for _, x in texts])
        except Exception:
            pre = None
        if pre is not None and not pre[0]:
            q = fiche._blocked(sc[n], D.classify(sc[n]["titre"]), f"sources insuffisantes (pré-contrôle Jev : {pre[1]})")
            return c["n"], "blocked", q
    q = fiche.draft(sc[n], urls, texts=texts)
    return c["n"], q["status"], q


def run(n=40, workers=4, dry=False):
    cands, sc = pick(n)
    inbox = C.jload(os.path.join(C.CONTENT, "inbox.json"), {})
    done = collections.Counter(); ok = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {}
        for c in cands:
            futs[ex.submit(one, c, sc, inbox)] = c
        for f in cf.as_completed(futs):
            c = futs[f]
            try:
                num, status, q = f.result()
            except Exception as e:
                print(f"  {c['n']} ERREUR {e}"); done["erreur"] += 1; continue
            done[status] += 1
            if q and not dry and ok < n:
                if q["status"] == "pending_review":
                    ok += 1
                fiche.save_and_report(q)
            elif q is None:
                print(f"  {num} : {status}")
            if ok >= n:
                for g in futs:
                    g.cancel()
    C.jdump(inbox, os.path.join(C.CONTENT, "inbox.json"), indent=1)
    print("[batch]", dict(done))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=40); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry", action="store_true"); a = ap.parse_args()
    run(a.n, a.workers, a.dry)
