"""Importance parlementaire d'un dossier législatif, mesurée uniquement sur les données ouvertes de l'AN.

Aucune connaissance du modèle, aucun jugement : des comptages reproductibles, par dossier.

Sources (data.assemblee-nationale.fr, Licence Ouverte) :
  Dossiers_Legislatifs.json.zip  dossier -> textes, séances, réunions de commission, procédure
  Amendements.json.zip           un fichier par amendement, rangé sous son dossier
  syseron.xml.zip               comptes rendus intégraux des séances (orateur, horodatage)
  Scrutins.json.zip             scrutin -> dossier (objet.dossierLegislatif.dossierRef)

Indicateurs par dossier : voir FEATURES.  Ce module ne choisit rien : il mesure.
"""
import gzip, json, math, os, re, sys, unicodedata, zipfile
import xml.etree.ElementTree as ET
from . import config as C
from .ingest import download, _list

BASE = "https://data.assemblee-nationale.fr/static/openData/repository/17"
SOURCES = {
    "dossiers": (f"{BASE}/loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip", "Dossiers_Legislatifs.json.zip"),
    "amendements": (f"{BASE}/loi/amendements_div_legis/Amendements.json.zip", "Amendements.json.zip"),
    "debats": (f"{BASE}/vp/syceronbrut/syseron.xml.zip", "syseron.xml.zip"),
    "agenda": (f"{BASE}/vp/reunions/Agenda.json.zip", "Agenda.json.zip"),
}
OUT = os.path.join(C.DATA, "salience.json")

FEATURES = ["scrutins", "solennels", "amendements", "amend_adoptes", "orateurs", "groupes_orateurs",
            "interventions", "mots", "duree_min", "seances", "reunions_commission"]

STOP = set("""le la les l un une des du de d et en au aux a à pour par sur sous dans ce cette ces son sa ses leur leurs qui que quoi dont
projet proposition loi lecture nouvelle premiere deuxieme definitive visant relative relatif relatifs relatives portant tendant
discussion suite generale articles article presentation vote ensemble explications texte adoptee adopte senat engagement procedure acceleree""".split())


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower().replace("’", "'"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def tokens(s):
    return {w for w in re.findall(r"[a-z0-9]+", norm(s)) if len(w) > 2 and w not in STOP}


NON_LEGIS = re.compile(r"question|ordre du jour|declaration|motions? de censure|hommage|rappel|remplacement|communication|nomination|election")


def overlap(point_title, dossier_title):
    """Part des mots du titre de point retrouvés dans le titre du dossier (0..1)."""
    p, d = tokens(point_title), tokens(dossier_title)
    return len(p & d) / len(p) if p else 0.0


# ---------- dossiers ----------
def _walk_acts(o, out):
    if isinstance(o, dict):
        for v in _list((o.get("voteRefs") or {}).get("voteRef") if isinstance(o.get("voteRefs"), dict) else None):
            if isinstance(v, str) and re.search(r"V(\d+)$", v):
                out["votes"].add(int(re.search(r"V(\d+)$", v).group(1)))
        t = o.get("@xsi:type", "")
        if t == "DiscussionSeancePublique_Type":
            out["seances"].append(o.get("reunionRef"))
        elif t == "DiscussionCommission_Type":
            out["commission"].append(o.get("reunionRef"))
        for v in o.values():
            _walk_acts(v, out)
    elif isinstance(o, list):
        for i in o:
            _walk_acts(i, out)


def load_dossiers(path):
    res = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if "/dossierParlementaire/" not in n or not n.endswith(".json"):
                continue
            d = json.loads(z.read(n))["dossierParlementaire"]
            acts = {"seances": [], "commission": [], "votes": set()}
            _walk_acts(d.get("actesLegislatifs"), acts)
            proc = d.get("procedureParlementaire") or {}
            res[d["uid"]] = {
                "titre": (d.get("titreDossier") or {}).get("titre", ""),
                "slug": (d.get("titreDossier") or {}).get("titreChemin", ""),
                "procedure": proc.get("libelle", "") if isinstance(proc, dict) else "",
                "seances": sorted({s for s in acts["seances"] if s}),
                "commission": sorted({s for s in acts["commission"] if s}),
                "votes": sorted(acts["votes"]),
                "initiateurs": [x.get("acteurRef") for x in _list(((d.get("initiateur") or {}).get("acteurs") or {}).get("acteur"))
                                if isinstance(x, dict)],
            }
    return res


# ---------- scrutins ----------
def load_scrutin_dossiers(path):
    """{numéro de scrutin: (dossierRef, type de vote, titre, séance)}."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if not n.endswith(".json"):
                continue
            s = json.loads(z.read(n))["scrutin"]
            ref = ((s.get("objet") or {}).get("dossierLegislatif") or {}).get("dossierRef")
            out[int(s["numero"])] = (ref, s["typeVote"]["codeTypeVote"], s.get("titre", ""), s.get("seanceRef"))
    return out


def link_scrutins(scr, odj, dossiers, min_cover=0.6):
    """Trois voies, de la plus sûre à la moins sûre : dossierRef du scrutin, voteRefs du dossier, puis titre du scrutin
    rapproché de l'ordre du jour de sa séance.  -> {numéro: (dossierRef, voie)}"""
    out = {}
    for n, (ref, _t, _ti, _s) in scr.items():
        if ref:
            out[n] = (ref, "scrutin")
    for ref, d in dossiers.items():
        for n in d["votes"]:
            if n in scr and n not in out:
                out[n] = (ref, "dossier")
    for n, (_r, _t, titre, seance) in scr.items():
        if n in out:
            continue
        best, score = None, 0.0
        for objet, ref in odj.get(seance, []):
            if not ref:
                continue
            sc = overlap(titre, objet)
            if sc > score:
                best, score = ref, sc
        if best and score >= min_cover:
            out[n] = (best, "ordre du jour")
    return out


# ---------- amendements ----------
def load_amendements(path, groups):
    """{dossierRef: {total, adoptes, groupes:set, auteurs:set}} ; le dossier est dans le chemin du fichier."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            m = re.match(r"json/(DLR5L17N\d+)/", n)
            if not m or not n.endswith(".json"):
                continue
            a = json.loads(z.read(n))["amendement"]
            r = out.setdefault(m.group(1), {"total": 0, "adoptes": 0, "groupes": set(), "auteurs": set()})
            r["total"] += 1
            sort = (a.get("cycleDeVie") or {}).get("sort")
            if isinstance(sort, str) and sort.lower().startswith("adopt"):
                r["adoptes"] += 1
            au = (a.get("signataires") or {}).get("auteur") or {}
            who, gref = au.get("acteurRef"), au.get("groupePolitiqueRef")
            if isinstance(who, str):  # les champs vides (xsi:nil) arrivent sous forme de dict
                r["auteurs"].add(who)
            if isinstance(gref, str) and (C.ALIAS.get(gref) or groups.get(gref)):
                r["groupes"].add(C.ALIAS.get(gref) or groups[gref])
    return out


# ---------- débats ----------
def _ns(tag):
    return tag.rsplit("}", 1)[-1]


def parse_compte_rendu(xml_bytes):
    """-> (seanceRef, [ {titre, orateurs:set, interventions, mots, t0, t1} par point de niveau 1 ])."""
    root = ET.fromstring(xml_bytes)
    ref = next((e.text for e in root.iter() if _ns(e.tag) == "seanceRef"), None)
    contenu = next((e for e in root.iter() if _ns(e.tag) == "contenu"), None)
    pts, cur = [], None
    if contenu is None:
        return ref, pts
    for el in contenu:
        tag = _ns(el.tag)
        if tag == "point" and el.get("nivpoint") == "1":
            tx = next((c for c in el if _ns(c.tag) == "texte"), None)
            cur = {"titre": "".join(tx.itertext()).strip() if tx is not None else "", "orateurs": set(),
                   "interventions": 0, "mots": 0, "t0": None, "t1": None}
            pts.append(cur)
        if cur is None:
            continue
        for p in el.iter():
            if _ns(p.tag) != "paragraphe":
                continue
            who = p.get("id_acteur")
            tx = next((c for c in p if _ns(c.tag) == "texte"), None)
            if tx is None:
                continue
            if who and p.get("roledebat") != "president":
                cur["orateurs"].add(who)
                cur["interventions"] += 1
                cur["mots"] += len("".join(tx.itertext()).split())
            st = tx.get("stime")
            if st:
                try:
                    v = float(st)
                except ValueError:
                    continue
                cur["t0"] = v if cur["t0"] is None else min(cur["t0"], v)
                cur["t1"] = v if cur["t1"] is None else max(cur["t1"], v)
    return ref, pts


def load_ordre_du_jour(path):
    """{séance: [(objet, dossierRef|None), ...]} depuis l'agenda officiel (points de séance publique)."""
    out = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if "IDS" not in n or not n.endswith(".json"):
                continue
            r = json.loads(z.read(n))["reunion"]
            pts = ((r.get("ODJ") or {}).get("pointsODJ") or {}).get("pointODJ")
            lst = []
            for p in _list(pts):
                refs = p.get("dossiersLegislatifsRefs")
                ref = next((x for x in _list(refs.get("dossierRef") if isinstance(refs, dict) else None) if isinstance(x, str)), None)
                lst.append((p.get("objet") or "", ref))
            out[r["uid"]] = lst
    return out


def attribute(points, candidates, min_cover=0.5):
    """Associe chaque point de niveau 1 au dossier (parmi ceux discutés ce jour-là) dont le titre recouvre le mieux.
    candidates : [(texte, dossierRef|None)] — titres du dossier et libellés de l'ordre du jour ; ref None = point
    sans dossier (questions au gouvernement, déclarations...).  -> [(point, dossierRef|None)]
    Repli : s'il n'y a qu'un seul dossier ce jour-là et que le point ne ressemble à aucun point sans dossier,
    on lui attribue le point (le titre court d'un débat, « Droit à l'aide à mourir », ne recoupe pas toujours
    le titre officiel, « Fin de vie »)."""
    out = []
    refs = {r for _, r in candidates if r}
    for p in points:
        best, score = None, 0.0
        for texte, ref in candidates:
            s = overlap(p["titre"], texte)
            if s > score:
                best, score = ref, s
        if score >= min_cover and len(tokens(p["titre"])) >= 1:
            out.append((p, best))
        elif len(refs) == 1 and score < min_cover and not NON_LEGIS.search(norm(p["titre"])):
            out.append((p, next(iter(refs))))
        else:
            out.append((p, None))
    return out


def load_debats(path, dossiers, odj):
    by_seance = {}
    for ref, d in dossiers.items():
        for s in d["seances"]:
            by_seance.setdefault(s, []).append((d["titre"], ref))
    for s, lst in odj.items():
        for objet, ref in lst:
            by_seance.setdefault(s, []).append((objet, ref))
    out, total, matched = {}, 0, 0
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            if not n.endswith(".xml"):
                continue
            seance, pts = parse_compte_rendu(z.read(n))
            cands = by_seance.get(seance, [])
            for p, ref in attribute(pts, cands):
                if p["interventions"] == 0:
                    continue
                total += 1
                if not ref:
                    continue
                matched += 1
                r = out.setdefault(ref, {"orateurs": set(), "interventions": 0, "mots": 0, "duree": 0.0, "seances": set()})
                r["orateurs"] |= p["orateurs"]
                r["interventions"] += p["interventions"]
                r["mots"] += p["mots"]
                if p["t0"] is not None:
                    r["duree"] += p["t1"] - p["t0"]
                r["seances"].add(seance)
    return out, {"points_avec_debat": total, "points_rattaches": matched}


# ---------- assemblage ----------
def actor_groups():
    """acteur -> sigle du groupe (dernier connu), depuis les votes nominatifs déjà ingérés."""
    out = {}
    p = os.path.join(C.DATA, "voters.jsonl.gz")
    if not os.path.exists(p):
        return out
    with gzip.open(p, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            for v in r.get("v", r.get("voters", [])):
                out[str(v[0]).replace("PA", "")] = v[2]
    return out


def origine(d, ag):
    """Groupe du ou des députés auteurs (le plus fréquent), « gouvernement » pour un projet de loi, sinon « autre »."""
    if d["procedure"].startswith(("Projet", "Engagement")):
        return "gouvernement"
    gs = [ag.get(str(a).replace("PA", "")) for a in d["initiateurs"] if a]
    gs = [g for g in gs if g]
    return max(set(gs), key=gs.count) if gs else "autre"


def fetch():
    for key, (url, name) in SOURCES.items():
        dest = os.path.join(C.RAW, name)
        if not os.path.exists(dest):
            print(f"[salience] téléchargement {name}", flush=True)
            download(url, dest)


def build():
    groups = C.jload(os.path.join(C.DATA, "groups.json"), {})
    dos = load_dossiers(os.path.join(C.RAW, SOURCES["dossiers"][1]))
    scr = load_scrutin_dossiers(os.path.join(C.RAW, "Scrutins.json.zip"))
    am = load_amendements(os.path.join(C.RAW, SOURCES["amendements"][1]), groups)
    odj = load_ordre_du_jour(os.path.join(C.RAW, SOURCES["agenda"][1]))
    deb, cover = load_debats(os.path.join(C.RAW, SOURCES["debats"][1]), dos, odj)
    ag = actor_groups()
    links = link_scrutins(scr, odj, dos)
    rows = {}
    for ref, d in dos.items():
        a, b = am.get(ref, {}), deb.get(ref, {})
        sc = [(n, scr[n][1]) for n, (r, _) in links.items() if r == ref]
        deputes = {x for x in b.get("orateurs", set()) if x.replace("PA", "") in ag}
        rows[ref] = {
            "titre": d["titre"], "slug": d["slug"], "procedure": d["procedure"],
            "scrutins": len(sc), "solennels": sum(1 for _, t in sc if t == "SPS"),
            "scrutin_numeros": sorted(n for n, _ in sc),
            "amendements": a.get("total", 0), "amend_adoptes": a.get("adoptes", 0),
            "groupes_amendeurs": len(a.get("groupes", ())),
            "orateurs": len(deputes), "groupes_orateurs": len({ag[x.replace("PA", "")] for x in deputes} - {"NI"}),
            "interventions": b.get("interventions", 0), "mots": b.get("mots", 0),
            "duree_min": round(b.get("duree", 0.0) / 60, 1), "seances": len(b.get("seances", ())),
            "reunions_commission": len(d["commission"]),
            "origine": origine(d, ag),
        }
    C.jdump({"cover": cover, "dossiers": rows}, OUT)
    print(f"[salience] {len(rows)} dossiers -> {OUT}  (débats rattachés : {cover})")
    return rows


# ---------- score ----------
def pct_rank(values):
    """Rang percentile (0..1) de chaque valeur, ex aequo au rang moyen."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    r = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 / max(1, n - 1)
        i = j + 1
    return r


def composite(rows, feats):
    """Moyenne des rangs percentiles sur feats : insensible aux unités et aux valeurs extrêmes."""
    refs = list(rows)
    cols = [pct_rank([rows[r][f] for r in refs]) for f in feats]
    return {r: sum(c[i] for c in cols) / len(cols) for i, r in enumerate(refs)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "fetch":
        fetch()
    else:
        fetch()
        build()
