"""Sélection transparente des sujets du quiz : `python -m pipeline.curate [--n 80]` → content/curated.json

Entonnoir (chaque étape est comptée et publiée) :
  1. tous les dossiers législatifs de la 17e législature (data/salience.json) ;
  2. dossiers législatifs avec au moins un scrutin public (hors motions de censure, engagements de responsabilité, missions, rapports) ;
  3. dossiers dont on peut tirer UN vote lisible : sens du vote certain (direction.classify), au moins 150 votants, groupes qui ne
     votent pas tous pareil (sinon le quiz n'apprend rien), pas de motion de procédure ;
  4. classement par importance parlementaire (orateurs, interventions, durée du débat, mots) : moyenne du rang global et du rang à
     L'INTÉRIEUR de chaque type de texte (projet de loi, proposition de loi, résolution, …), pour ne pas favoriser les textes du
     gouvernement (rang par type) ni laisser un type rare écraser les autres (rang global) ; voir SALIENCE_STUDY.md. Les ratifications
     de traités sont écartées : ce ne sont pas des choix de société lisibles en une question ;
  5. plafond par origine politique du texte (gouvernement / gauche / centre / droite / autre) : aucun bloc ne dépasse CAP_BLOC ;
  6. un seul vote par dossier : le vote sur l'ensemble du texte s'il existe, sinon le vote le plus lisible.

Aucun jugement éditorial sur le fond : la liste est une fonction des données ouvertes et des règles ci-dessus, reproductible.
Les limites (ce que cette méthode ne mesure pas) sont écrites dans le fichier de sortie et affichées sur le site.
"""
import argparse, collections, json, os
from . import config as C, salience as S, salience_study as SS, select_votes as SV, direction as D

N_DEFAUT = 80
CAP_BLOC = 0.30            # part maximale d'un bloc d'origine dans la sélection
MIN_VOTANTS, MIN_DIV = 150, 0.2
FEATS = SS.SETS["débat"]
KINDS_OK = ("ensemble", "article", "amendement")
BLOC_LABEL = {"gouvernement": "gouvernement", "gauche": "gauche", "centre": "centre", "droite": "droite", "autre": "autre / non attribuée"}


def best_vote(r, sc):
    """Le vote le plus lisible du dossier : l'ensemble du texte d'abord, sinon l'article/amendement le plus clivant."""
    best = None
    for n in r["scrutin_numeros"]:
        f = sc.get(str(n))
        if not f:
            continue
        cl = D.classify(f["titre"])
        ft = SV.features(f)
        if cl["polarity"] is None or cl["kind"] not in KINDS_OK or not ft:
            continue
        if ft["votants"] < MIN_VOTANTS or ft["div"] < MIN_DIV:
            continue
        s = SV.score(f, ft, cl) + (1.0 if cl["kind"] == "ensemble" else 0.0)
        if not best or s > best[0]:
            best = (s, n, cl["kind"], round(ft["div"], 2), ft["votants"], f["date"], f["titre"], f["sort"])
    return best


def run(n_target=N_DEFAUT):
    data = C.jload(S.OUT)
    allrows = data["dossiers"]
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"))
    leg = {k: v for k, v in allrows.items() if SS.legislatif(v)}
    avec_vote = {k: v for k, v in leg.items() if v["scrutins"] > 0}
    avec_vote = {k: v for k, v in avec_vote.items() if SS.kind(v) != "traité"}
    par_type, global_ = SS.composite_par_type(avec_vote, FEATS), S.composite(avec_vote, FEATS)
    score = {k: (par_type[k] + global_[k]) / 2 for k in avec_vote}
    elig = {}
    for ref, r in avec_vote.items():
        b = best_vote(r, sc)
        if b:
            elig[ref] = b
    ordre = sorted(elig, key=lambda ref: (-score[ref], ref))
    cap = max(1, round(CAP_BLOC * n_target))
    prises, par_bloc, refuses = [], collections.Counter(), []
    for ref in ordre:
        bloc = SS.BLOC.get(avec_vote[ref]["origine"], "autre")
        if len(prises) >= n_target:
            break
        if par_bloc[bloc] >= cap:
            refuses.append((ref, f"plafond du bloc « {BLOC_LABEL[bloc]} » atteint ({cap})"))
            continue
        par_bloc[bloc] += 1
        prises.append(ref)
    out_items = []
    for rang, ref in enumerate(prises, 1):
        r, b = avec_vote[ref], elig[ref]
        out_items.append({
            "rang": rang, "dossier": ref, "titre_dossier": r["titre"], "type": SS.kind(r), "bloc": SS.BLOC.get(r["origine"], "autre"),
            "origine": r["origine"], "score": round(score[ref], 3), "vote": b[1], "vote_kind": b[2], "vote_date": b[5],
            "vote_titre": b[6], "vote_sort": b[7], "div": b[3], "votants": b[4],
            "signaux": {k: r[k] for k in ("orateurs", "interventions", "duree_min", "amendements", "scrutins")},
        })
    univers_bloc = collections.Counter(SS.BLOC.get(r["origine"], "autre") for r in avec_vote.values())
    elig_bloc = collections.Counter(SS.BLOC.get(avec_vote[r]["origine"], "autre") for r in elig)
    type_univers = collections.Counter(SS.kind(r) for r in avec_vote.values())
    type_sel = collections.Counter(i["type"] for i in out_items)
    res = {
        "n_cible": n_target, "n": len(out_items), "cap_bloc": cap, "min_votants": MIN_VOTANTS, "min_div": MIN_DIV, "indicateurs": FEATS,
        "entonnoir": [
            ["Dossiers de la 17e législature", len(allrows)],
            ["Dossiers législatifs avec au moins un scrutin public (hors ratifications de traités)", len(avec_vote)],
            [f"…dont un vote lisible (sens certain, ≥ {MIN_VOTANTS} votants, groupes divisés)", len(elig)],
            [f"…retenus (importance parlementaire, plafond par origine)", len(out_items)],
        ],
        "repartition": {"bloc": {"univers": dict(univers_bloc), "eligibles": dict(elig_bloc), "selection": dict(par_bloc)},
                        "type": {"univers": dict(type_univers), "selection": dict(type_sel)}},
        "refuses_par_plafond": [{"dossier": ref, "titre": avec_vote[ref]["titre"], "raison": why} for ref, why in refuses],
        "limites": [
            "L'importance est mesurée au Parlement (prises de parole, durée du débat), pas dans le public ni dans la presse.",
            "Exiger des groupes divisés écarte les textes consensuels : le quiz montre les désaccords, pas l'ensemble du travail parlementaire.",
            "Un texte déposé par un groupe peut être peu débattu faute de temps de séance (niches parlementaires) : le tri par type limite ce biais sans le supprimer.",
            "Le choix du vote (ensemble du texte, sinon le plus clivant) est lui-même une décision de méthode.",
            "La sélection ne juge ni le fond ni la neutralité ; la neutralité est contrôlée fiche par fiche (voir la page Méthode).",
        ],
        "items": out_items,
    }
    C.jdump(res, os.path.join(C.CONTENT, "curated.json"), indent=1)
    print(f"[curate] {len(avec_vote)} dossiers avec scrutin → {len(elig)} éligibles → {len(out_items)} retenus ; blocs {dict(par_bloc)}")
    return res

def draft_missing(workers=4, limit=None, only=None):
    """Rédige les fiches des votes retenus qui n'en ont pas (sources officielles découvertes depuis la page du scrutin)."""
    from concurrent.futures import ThreadPoolExecutor
    from . import fiche, sources as SR, store
    cur = C.jload(os.path.join(C.CONTENT, "curated.json"))
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"))
    ref = {i["vote"]: i["dossier"] for i in cur["items"]}
    todo = [i["vote"] for i in cur["items"] if not store.load(i["vote"]) and (only is None or i["vote"] in only)]
    if limit:
        todo = todo[:limit]
    print(f"[curate] {len(todo)} fiches à rédiger")

    def one(n):
        try:
            urls = SR.discover(n, ref[n])
        except Exception as e:
            urls = []
            print(f"[curate] {n} : sources introuvables ({str(e)[:80]})")
        try:
            fiche.save_and_report(fiche.draft(sc[str(n)], urls))
        except Exception as e:
            print(f"[curate] {n} : ÉCHEC {type(e).__name__} {str(e)[:120]}")

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, todo))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=N_DEFAUT)
    ap.add_argument("--draft", action="store_true", help="rédiger les fiches manquantes (claude -p)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    run(a.n)
    if a.draft:
        draft_missing(a.workers, a.limit)
