"""Hémicycle fidèle : place réelle (numPlace) de chaque député, absents inclus.

Chaîne par question : 2 caractères par siège, du plus grand numPlace (gauche) au plus petit (droite) :
  1er = lettre du groupe (index dans ORDER, 'A'=GDR ...), 2e = état (p pour, c contre, a abstention, x absent/non votant).
Un absent est placé à sa dernière place connue (fenêtre de 45 jours avant/après, 150 en repli).
Une seule lecture du fichier des votants, quel que soit le nombre de questions.
"""
import gzip, json, os, datetime as dt, collections
from . import config as C

GI = {g: i for i, g in enumerate(C.ORDER)}


def build(targets, voters_path=None, w_near=45, w_far=150, min_seats=570):
    """targets : {n: 'YYYY-MM-DD'} -> {n: (chaîne, nb_sièges, comptes_par_groupe)}"""
    vp = voters_path or os.path.join(C.DATA, "voters.jsonl.gz")
    D = {n: dt.date.fromisoformat(d) for n, d in targets.items()}
    best = {n: {} for n in targets}       # n -> acteur -> (dist, place, groupe, état)
    with gzip.open(vp, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            d = dt.date.fromisoformat(rec["d"])
            for n, Dn in D.items():
                dist = abs((d - Dn).days)
                if dist > w_far and rec["n"] != n:
                    continue
                exact = rec["n"] == n
                dist = 0 if exact else max(1, dist)  # un autre scrutin du même jour n'est pas « ce vote »
                bn = best[n]
                for a, place, g, st in rec["v"]:
                    cur = bn.get(a)
                    if cur is None or dist < cur[0]:
                        bn[a] = (dist, place, g, st if exact else "x")
    out = {}
    for n, bn in best.items():
        for W in (w_near, w_far):
            seat = {}
            for a, (dist, place, g, st) in bn.items():
                if dist > W:
                    continue
                cur = seat.get(place)
                if cur is None or dist < cur[0]:
                    seat[place] = (dist, g, st)
            if len(seat) >= min_seats:
                break
        places = sorted(seat, reverse=True)
        s = "".join(chr(65 + GI.get(seat[p][1], len(C.ORDER) - 1)) + seat[p][2] for p in places)
        out[n] = (s, len(places), dict(collections.Counter(seat[p][1] for p in places)))
    return out


def check(n, counts, g):
    """Écarts entre le nombre de sièges par groupe sur la carte et les effectifs officiels du scrutin."""
    return {k: counts.get(k, 0) - v[3] for k, v in g.items() if counts.get(k, 0) != v[3]}
