"""Étape 1 : ingestion nocturne (incrémentale) des scrutins et des fiches acteurs/organes.

Sorties (dans DATA) :
  scrutins.json     {numero: fiche compacte}  (tous scrutins hors MOC, groupes fusionnés par alias)
  voters.jsonl.gz   une ligne par scrutin : votants nominatifs avec numPlace (pour l'hémicycle réel)
  groups.json       organeRef -> sigle (régénéré depuis AMO10 si dispo, sinon groups17.json)
  actors.json       acteur -> [nom, prénom]   (pour attribuer les amendements)
"""
import gzip, json, os, subprocess, sys, zipfile, re, shutil
from . import config as C


def download(url, dest):
    """Téléchargement reprenable (curl --retry ... -C -). Retourne True si le fichier a changé."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    before = (os.path.getsize(dest), os.path.getmtime(dest)) if os.path.exists(dest) else None
    tmp = dest + ".part"
    if os.path.exists(tmp):
        os.remove(tmp)
    # -z : ne retélécharge que si le serveur a une version plus récente
    cmd = ["curl", "-fsS", "--retry", "3", "--retry-all-errors", "-L", "-o", tmp, url]
    if before:
        cmd[1:1] = ["-z", dest]
    subprocess.run(cmd, check=True)
    if os.path.exists(tmp) and os.path.getsize(tmp) > 0:
        os.replace(tmp, dest)
    elif os.path.exists(tmp):
        os.remove(tmp)
    after = (os.path.getsize(dest), os.path.getmtime(dest))
    return before != after


def _list(x):
    if not x:
        return []
    return x if isinstance(x, list) else [x]


def load_groups():
    g = C.jload(os.path.join(C.DATA, "groups.json"))
    if g:
        return g
    legacy = C.jload(os.path.join(C.ROOT, "groups17.json"), {})
    return {k: v["sigle"] for k, v in legacy.items()}


def sig_of(ref, groups):
    return C.ALIAS.get(ref) or groups.get(ref) or "NI"


def parse_scrutin(s, groups):
    """-> (fiche compacte, liste de votants [acteur, place, sigle, état]) ou None pour un MOC."""
    typ = s["typeVote"]["codeTypeVote"]
    if typ == "MOC":
        return None
    d = s["syntheseVote"]["decompte"]
    g, voters = {}, []
    for grp in _list(s["ventilationVotes"]["organe"]["groupes"]["groupe"]):
        sg = sig_of(grp["organeRef"], groups)
        v = grp["vote"]["decompteVoix"]
        cur = g.setdefault(sg, [0, 0, 0, 0, 0])
        cur[0] += int(v["pour"]); cur[1] += int(v["contre"]); cur[2] += int(v["abstentions"])
        cur[3] += int(grp["nombreMembresGroupe"])
        dn = grp["vote"].get("decompteNominatif") or {}
        for key, st in (("pours", "p"), ("contres", "c"), ("abstentions", "a"), ("nonVotants", "x")):
            blk = dn.get(key)
            if not blk:
                continue
            for x in _list(blk.get("votant")):
                if x.get("parDelegation") == "true" and st in "pca":
                    cur[4] += 1
                if x.get("numPlace"):
                    voters.append([x["acteurRef"], int(x["numPlace"]), sg, st])
    fiche = dict(
        n=int(s["numero"]), date=s["dateScrutin"], titre=(s.get("titre") or "").replace("’", "'"), type=typ,
        sort=s["sort"]["code"], dem=(s.get("demandeur") or {}).get("texte") or "",
        tot=[int(d["pour"]), int(d["contre"]), int(d["abstentions"])], g=g,
    )
    return fiche, voters


def ingest_scrutins(zip_path=None, only_new=True):
    zip_path = zip_path or os.path.join(C.RAW, "Scrutins.json.zip")
    groups = load_groups()
    sp = os.path.join(C.DATA, "scrutins.json")
    vp = os.path.join(C.DATA, "voters.jsonl.gz")
    known = {int(k): v for k, v in (C.jload(sp, {}) or {}).items()}
    have_v = set()
    if os.path.exists(vp) and only_new:
        with gzip.open(vp, "rt", encoding="utf-8") as f:
            have_v = {json.loads(l)["n"] for l in f}
    new, newv = [], []
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            m = re.search(r"V(\d+)\.json$", name)
            if not m:
                continue
            n = int(m.group(1))
            if only_new and n in known and n in have_v:
                continue
            s = json.loads(z.read(name))["scrutin"]
            r = parse_scrutin(s, groups)
            if r is None:
                continue
            known[n] = r[0]; new.append(n)
            newv.append({"n": n, "d": r[0]["date"], "v": r[1]})
    if new:
        C.jdump({str(k): known[k] for k in sorted(known)}, sp)
        tmp = vp + ".tmp"
        new_set = set(new)
        with gzip.open(tmp, "wt", encoding="utf-8") as out:
            if os.path.exists(vp) and only_new:
                with gzip.open(vp, "rt", encoding="utf-8") as f:
                    for l in f:
                        if json.loads(l)["n"] not in new_set:
                            out.write(l)
            for x in newv:
                out.write(json.dumps(x, ensure_ascii=False) + "\n")
        os.replace(tmp, vp)
    return sorted(new)


def ingest_amo(zip_path=None):
    """Organes (groupes parlementaires de la 17e) et acteurs (noms) depuis AMO10."""
    zip_path = zip_path or os.path.join(C.RAW, "AMO10.json.zip")
    groups, actors = {}, {}
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            if "/organe/" in name and name.endswith(".json"):
                o = json.loads(z.read(name))["organe"]
                if o.get("codeType") == "GP" and str(o.get("legislature")) == "17":
                    groups[o["uid"]] = o.get("libelleAbrev") or o.get("libelle")
            elif "/acteur/" in name and name.endswith(".json"):
                a = json.loads(z.read(name))["acteur"]
                uid = a["uid"]["#text"] if isinstance(a["uid"], dict) else a["uid"]
                i = a["etatCivil"]["ident"]
                actors[uid] = [i["nom"], i["prenom"]]
    # Sécurité : on ne remplace pas une table existante par une table vide.
    if groups:
        merged = {**load_groups(), **groups}
        C.jdump(merged, os.path.join(C.DATA, "groups.json"))
    if actors:
        C.jdump(actors, os.path.join(C.DATA, "actors.json"))
    return len(groups), len(actors)


def run(refresh=True):
    if refresh:
        c1 = download(C.URL_SCRUTINS, os.path.join(C.RAW, "Scrutins.json.zip"))
        c2 = download(C.URL_AMO, os.path.join(C.RAW, "AMO10.json.zip"))
        print(f"[ingest] téléchargements : scrutins {'maj' if c1 else 'inchangé'}, AMO {'maj' if c2 else 'inchangé'}")
    if os.path.exists(os.path.join(C.RAW, "AMO10.json.zip")):
        print("[ingest] AMO10 : groupes/acteurs =", ingest_amo())
    new = ingest_scrutins()
    print(f"[ingest] {len(new)} nouveau(x) scrutin(s)")
    return new


if __name__ == "__main__":
    run(refresh="--no-download" not in sys.argv)
