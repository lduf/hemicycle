"""Page stats : participation, auteurs d'amendements, discipline (indice de Rice), taux de victoire, délégations,
présence individuelle, jour de la semaine, mois, accord entre groupes. Mesure la participation aux scrutins PUBLICS,
pas la charge de travail réelle (commissions, circonscription) — à dire dans l'interface.
"""
import gzip, json, os, re, collections, datetime as dt, statistics as st, unicodedata
from . import config as C

GROUPS = ["GDR", "LFI-NFP", "ECOS", "SOC", "LIOT", "DEM", "EPR", "HOR", "DR", "UDR", "RN"]
AUTH = re.compile(r"amendement[^,]*? de (?:M\.|Mme) (.+?)(?= et | à | après | avant | au | aux |,| \(|$)")
DEM = re.compile(r'groupe "([^"]+)"')


def norm(x):
    return unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower().replace("’", "'").strip()


def run(scrutins=None, voters_path=None, actors=None):
    sc = scrutins or C.jload(os.path.join(C.DATA, "scrutins.json"))
    actors = actors if actors is not None else C.jload(os.path.join(C.DATA, "actors.json"), {})
    names = collections.defaultdict(set)
    for uid, (nom, prenom) in actors.items():
        names[norm(nom)].add(uid); names[norm(prenom + " " + nom)].add(uid)
    # passage unique sur les votants : plage de dates par (acteur, groupe) + nb de votes exprimés
    span = collections.defaultdict(dict); nvotes = collections.Counter(); alldates = set()
    vp = voters_path or os.path.join(C.DATA, "voters.jsonl.gz")
    with gzip.open(vp, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line); d = r["d"]; alldates.add(d)
            for a, place, g, s in r["v"]:
                sp = span[a].get(g)
                span[a][g] = [min(sp[0], d), max(sp[1], d)] if sp else [d, d]
                if s in "pca":
                    nvotes[a] += 1

    def grp_at(a, d):
        sp = span.get(a)
        if not sp:
            return None
        for g, (lo, hi) in sp.items():
            if lo <= d <= hi:
                return g
        return min(sp.items(), key=lambda kv: min(abs((dt.date.fromisoformat(d) - dt.date.fromisoformat(x)).days) for x in kv[1]))[0]

    gname = {norm(v): k for k, v in C.GROUP_NAMES.items()}
    gname[norm("La France insoumise - Nouveau Front Populaire")] = "LFI-NFP"
    S = collections.defaultdict(lambda: collections.defaultdict(float))
    WD = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    MON = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    agree = collections.defaultdict(lambda: [0, 0]); unknown_auth = 0; n_scr = 0; cnt_date = collections.Counter()
    for k, s in sc.items():
        if s["type"] == "MOC":
            continue
        n_scr += 1; d = s["date"]; t = s["titre"]; typ = s["type"]; cnt_date[d] += 1
        kind = ("ensemble" if re.match(r"l'ensemble|la première partie|la deuxième partie|l'article unique", t) else
                "amendement" if re.match(r"l'amendement|le sous-amendement", t) else "article" if t.startswith("l'article") else "autre")
        adopt = s["sort"] == "adopté"
        auth = None
        if kind == "amendement":
            m = AUTH.search(t)
            if m:
                u = names.get(norm(m.group(1)))
                if u and len(u) == 1:
                    auth = grp_at(next(iter(u)), d)
            if auth is None:
                unknown_auth += 1
        dem = {gname[norm(x)] for x in DEM.findall(s["dem"]) if norm(x) in gname}
        stance = {}
        for sg, (p, c, a, m, deleg) in s["g"].items():
            if sg == "NI":
                continue
            vot = p + c + a
            X = S[sg]; X["mem"] += m; X["vot"] += vot; X["p"] += p; X["c"] += c; X["a"] += a; X["deleg"] += deleg; X["n"] += 1
            for key in ("mem_" + kind, "mem_" + typ): X[key] += m
            for key in ("vot_" + kind, "vot_" + typ): X[key] += vot
            if p + c: X["rice"] += abs(p - c) / (p + c); X["rice_n"] += 1
            if auth:
                k2 = "own" if auth == sg else "oth"; X["mem_am_" + k2] += m; X["vot_am_" + k2] += vot
            if dem:
                k3 = "dem_own" if sg in dem else "dem_oth"; X["mem_" + k3] += m; X["vot_" + k3] += vot
            if vot:
                ms = (p - c) / vot
                if abs(ms) >= .5:
                    X["pos"] += 1; X["win"] += (ms > 0) == adopt
                stance[sg] = ms
            wd = dt.date.fromisoformat(d).weekday(); WD[sg][wd][0] += vot; WD[sg][wd][1] += m
            MON[sg][d[:7]][0] += vot; MON[sg][d[:7]][1] += m
        if auth in GROUPS:
            S[auth]["am_tot"] += 1; S[auth]["am_ok"] += adopt
        for g in dem:
            if g in GROUPS: S[g]["dem_n"] += 1
        ks = [k2 for k2 in stance if abs(stance[k2]) >= .5]
        for i in ks:
            for j in ks:
                if i < j:
                    agree[(i, j)][0] += (stance[i] > 0) == (stance[j] > 0); agree[(i, j)][1] += 1
    dates = sorted(alldates); didx = {d: i for i, d in enumerate(dates)}
    cum = [0]
    for d in dates: cum.append(cum[-1] + cnt_date[d])
    indiv = collections.defaultdict(list)
    for a, sp in span.items():
        first = min(v[0] for v in sp.values()); last = max(v[1] for v in sp.values())
        den = cum[didx[last] + 1] - cum[didx[first]]
        if den < 300: continue
        # groupe principal = celui de la plage la plus longue
        g = max(sp.items(), key=lambda kv: (dt.date.fromisoformat(kv[1][1]) - dt.date.fromisoformat(kv[1][0])).days)[0]
        if g in GROUPS: indiv[g].append(min(1, nvotes[a] / den))
    out = {"n_scrutins": n_scr, "unknown_auth": unknown_auth, "groups": {}}
    for g in GROUPS:
        X = S[g]; r = lambda a, b: round(X[a] / X[b], 4) if X[b] else None
        v = indiv[g] or [0.0]
        q = st.quantiles(v, n=4) if len(v) > 1 else [v[0]] * 3
        out["groups"][g] = dict(
            members_avg=round(X["mem"] / X["n"], 1), part=r("vot", "mem"), part_ensemble=r("vot_ensemble", "mem_ensemble"),
            part_amend=r("vot_amendement", "mem_amendement"), part_article=r("vot_article", "mem_article"), part_sps=r("vot_SPS", "mem_SPS"),
            part_am_own=r("vot_am_own", "mem_am_own"), part_am_oth=r("vot_am_oth", "mem_am_oth"),
            part_dem_own=r("vot_dem_own", "mem_dem_own"), part_dem_oth=r("vot_dem_oth", "mem_dem_oth"),
            abst=round(X["a"] / X["vot"], 4), deleg=round(X["deleg"] / X["vot"], 4), rice=round(X["rice"] / X["rice_n"], 4),
            win=round(X["win"] / X["pos"], 4), am_tot=int(X["am_tot"]), am_ok=int(X["am_ok"]), dem_n=int(X["dem_n"]),
            indiv=dict(n=len(indiv[g]), median=round(st.median(v), 4), q1=round(q[0], 4), q3=round(q[2], 4), mn=round(min(v), 4),
                       mx=round(max(v), 4), lt10=sum(x < .10 for x in v), gt50=sum(x > .5 for x in v)),
            weekday={k: round(a[0] / a[1], 4) for k, a in sorted(WD[g].items()) if a[1]},
            monthly={k: round(a[0] / a[1], 4) for k, a in sorted(MON[g].items()) if a[1]},
        )
    out["agree"] = {f"{i}|{j}": round(a / b, 4) for (i, j), (a, b) in agree.items() if b > 50}
    out["generated"] = dt.date.today().isoformat()
    return out


if __name__ == "__main__":
    o = run(); C.jdump(o, os.path.join(C.DATA, "stats.json")); print("[stats]", o["n_scrutins"], "scrutins, auteurs inconnus", o["unknown_auth"])
