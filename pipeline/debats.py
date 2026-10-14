"""Extraits des débats en séance publique (comptes rendus officiels, open data AN) pour un ensemble de dossiers.

Pourquoi : pour décrire fidèlement les arguments des opposants à une mesure, le texte déposé et le rapport ne suffisent pas toujours ;
les interventions en séance les contiennent, dites par ceux qui les portent. Le rédacteur reçoit ces extraits SANS les noms des orateurs
(seul le texte parlé est conservé) et reformule sans nommer personne, comme pour toute source.

Rattachement point de séance → dossier : celui de salience.py (recouvrement du titre, agenda officiel).
`python -m pipeline.debats DLR5L17N… …` ou `extraits(refs)` → {dossier: texte}. Mis en cache dans data/debats_text.json.
"""
import json, os, re, sys, zipfile
import xml.etree.ElementTree as ET
from . import config as C, salience as S

CACHE = os.path.join(C.DATA, "debats_text.json")
MAX_CHARS = 80000


def _paras(el):
    """Texte des interventions (hors président de séance), sans identité d'orateur."""
    out = []
    for p in el.iter():
        if S._ns(p.tag) != "paragraphe" or p.get("roledebat") == "president" or not p.get("id_acteur"):
            continue
        tx = next((c for c in p if S._ns(c.tag) == "texte"), None)
        if tx is not None:
            t = re.sub(r"\s+", " ", "".join(tx.itertext())).strip()
            if len(t) > 40:
                out.append(t)
    return out


def _points(xml_bytes):
    root = ET.fromstring(xml_bytes)
    ref = next((e.text for e in root.iter() if S._ns(e.tag) == "seanceRef"), None)
    contenu = next((e for e in root.iter() if S._ns(e.tag) == "contenu"), None)
    pts, cur = [], None
    if contenu is None:
        return ref, pts
    for el in contenu:
        if S._ns(el.tag) == "point" and el.get("nivpoint") == "1":
            tx = next((c for c in el if S._ns(c.tag) == "texte"), None)
            cur = {"titre": "".join(tx.itertext()).strip() if tx is not None else "", "orateurs": set(), "interventions": 0, "mots": 0,
                   "t0": None, "t1": None, "textes": []}
            pts.append(cur)
        if cur is not None:
            cur["interventions"] += 1
            cur["textes"] += _paras(el)
    return ref, pts


def extraits(refs, force=False):
    refs = set(refs)
    cache = C.jload(CACHE, {}) if not force else {}
    todo = refs - set(cache)
    if not todo:
        return {r: cache[r] for r in refs}
    dos = S.load_dossiers(os.path.join(C.RAW, S.SOURCES["dossiers"][1]))
    odj = S.load_ordre_du_jour(os.path.join(C.RAW, S.SOURCES["agenda"][1]))
    by_seance = {}
    for ref, d in dos.items():
        for s in d["seances"]:
            by_seance.setdefault(s, []).append((d["titre"], ref))
    for s, lst in odj.items():
        for objet, ref in lst:
            by_seance.setdefault(s, []).append((objet, ref))
    got = {r: [] for r in todo}
    with zipfile.ZipFile(os.path.join(C.RAW, S.SOURCES["debats"][1])) as z:
        for n in sorted(z.namelist()):
            if not n.endswith(".xml"):
                continue
            seance, pts = _points(z.read(n))
            for p, ref in S.attribute(pts, by_seance.get(seance, [])):
                if ref in got and p["textes"]:
                    got[ref] += p["textes"]
    for r, lst in got.items():
        cache[r] = " ".join(lst)[:MAX_CHARS]
    C.jdump(cache, CACHE)
    return {r: cache[r] for r in refs}


if __name__ == "__main__":
    res = extraits(sys.argv[1:])
    for r, t in res.items():
        print(r, len(t), t[:150])
