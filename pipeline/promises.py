"""Étape 6 : base de promesses par programme, appariement sémantique, confirmation humaine.

Fichiers :
  content/programmes/<id>.json  {"id","titre","bloc","groups":[..],"url","date","officiel":bool,"promesses":[{"id","text","theme"}]}
  content/promise_matches.json  {numero_question: [ {bloc,groups,exp,text,src:[ids],flag,status,score} ]}
        status : proposed (jamais affiché) | confirmed | legacy (héritage du MVP, à re-confirmer) | rejected
  content/sources.json          {id: [libellé, url]}

Appariement : similarité TF-IDF cosinus (stdlib) pour proposer ; le sens (`exp` : la promesse va dans le sens de
« pour » ou de « contre » ?) est proposé par un modèle si dispo, sinon laissé vide. RIEN n'est affiché sans `confirm`.
CLI : propose | confirm N INDEX --exp pour|contre|none | coverage
"""
import argparse, math, os, re, unicodedata, collections
from . import config as C, store

PROG_DIR = os.path.join(C.CONTENT, "programmes")
MATCHES = os.path.join(C.CONTENT, "promise_matches.json")
STOP = set("""le la les l un une des du de d et en à au aux pour par sur dans avec sans ce cet cette ces qui que quoi dont où
est sont être a ont avoir il elle ils elles on nous vous se sa son ses leur leurs plus moins très comme mais ou donc or ni car
ne pas y s qu si loi projet texte article proposition mesure nationale france français française""".split())


def toks(t):
    t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
    out = []
    for w in re.findall(r"[a-z0-9]{3,}", t):
        if w in STOP:
            continue
        for suf in ("ations", "ation", "ements", "ement", "ions", "ion", "eurs", "eur", "aux", "es", "s", "e"):
            if w.endswith(suf) and len(w) - len(suf) >= 4:
                w = w[:-len(suf)]; break
        out.append(w)
    return out


def tfidf(docs):
    df = collections.Counter(w for d in docs for w in set(d))
    N = len(docs)
    vecs = []
    for d in docs:
        tf = collections.Counter(d)
        v = {w: (1 + math.log(c)) * math.log((N + 1) / (df[w] + 0.5)) for w, c in tf.items()}
        nrm = math.sqrt(sum(x * x for x in v.values())) or 1
        vecs.append({w: x / nrm for w, x in v.items()})
    return vecs


def cos(a, b):
    return sum(x * b.get(w, 0) for w, x in a.items())


def load_programmes():
    out = []
    if os.path.isdir(PROG_DIR):
        for f in sorted(os.listdir(PROG_DIR)):
            if f.endswith(".json"):
                out.append(C.jload(os.path.join(PROG_DIR, f)))
    return out


def coverage(progs=None):
    """Groupes scorés sans aucune promesse sourcée dans la base (DR, UDR, LIOT manquaient dans le MVP)."""
    progs = progs if progs is not None else load_programmes()
    cov = collections.Counter()
    for p in progs:
        for g in p.get("groups", []):
            cov[g] += len(p.get("promesses", []))
    return {g: cov.get(g, 0) for g in C.SCORED}


def propose(threshold=0.18, per_q=3, questions=None, progs=None, call=None):
    qs = questions if questions is not None else [q for q in store.all_questions() if q["status"] in ("legacy", "published", "pending_review")]
    progs = progs if progs is not None else load_programmes()
    flat = [(p, pr) for p in progs for pr in p.get("promesses", [])]
    if not qs or not flat:
        return 0
    qdocs = [toks(" ".join(filter(None, [q.get("title"), q.get("label"), q.get("sum")]))) for q in qs]
    pdocs = [toks(pr["text"] + " " + (pr.get("theme") or "")) for _, pr in flat]
    vecs = tfidf(qdocs + pdocs); qv, pv = vecs[:len(qs)], vecs[len(qs):]
    m = C.jload(MATCHES, {}); added = 0
    for q, v in zip(qs, qv):
        have = {(x.get("text"), tuple(x.get("src", []))) for x in m.get(str(q["n"]), [])}
        ranked = sorted(((cos(v, w), i) for i, w in enumerate(pv)), reverse=True)[:per_q]
        for s, i in ranked:
            p, pr = flat[i]
            if s < threshold or (pr["text"], (p["id"],)) in have:
                continue
            exp = None
            if call:
                a = (call(f"Mesure votée : {q.get('label')}. Promesse : « {pr['text']} ». La promesse va-t-elle dans le sens de "
                          "adopter la mesure (pour), de s'y opposer (contre), ou sans rapport (none) ? Un seul mot.") or "").strip().lower()
                exp = a if a in ("pour", "contre") else None
            m.setdefault(str(q["n"]), []).append(dict(bloc=p["bloc"], groups=p["groups"], exp=exp, text=pr["text"], src=[p["id"]],
                                                      flag="appariement automatique, à confirmer", status="proposed", score=round(s, 3)))
            added += 1
    C.jdump(m, MATCHES, indent=1)
    return added


def confirm(n, idx, exp, flag=None):
    m = C.jload(MATCHES, {}); x = m[str(n)][idx]
    x["exp"] = None if exp == "none" else exp; x["status"] = "confirmed"
    if flag is not None: x["flag"] = flag
    elif x.get("flag", "").startswith("appariement automatique"): x["flag"] = ""
    C.jdump(m, MATCHES, indent=1)


def usable(m):
    """Promesses affichables : confirmées par un humain, ou héritées du MVP (affichées avec leur drapeau d'incertitude)."""
    return {n: [x for x in L if x.get("status") in ("confirmed", "legacy")] for n, L in m.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("propose"); sp.add_parser("coverage")
    c = sp.add_parser("confirm"); c.add_argument("n", type=int); c.add_argument("idx", type=int); c.add_argument("--exp", required=True)
    a = ap.parse_args()
    if a.cmd == "propose": print("[promises]", propose(), "proposition(s)")
    elif a.cmd == "coverage":
        for g, k in coverage().items(): print(f"{g:8} {k:3} promesse(s)" + ("   ← AUCUNE" if not k else ""))
    else: confirm(a.n, a.idx, a.exp)
