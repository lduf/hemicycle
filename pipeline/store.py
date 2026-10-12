"""Stockage éditorial : un fichier JSON par question dans content/questions/<n>.json (versionné dans git)."""
import hashlib, json, os, datetime as dt
from . import config as C

QDIR = os.path.join(C.CONTENT, "questions")
VISIBLE_TEXT = ("title", "label", "hook", "sum", "pro", "con", "surp")
STATUSES = ("draft", "blocked", "pending_review", "legacy", "published", "rejected")


def path(n):
    return os.path.join(QDIR, f"{int(n)}.json")


def load(n):
    return C.jload(path(n))


def save(q):
    q["updated"] = dt.date.today().isoformat()
    C.jdump(q, path(q["n"]), indent=1)


def all_questions():
    if not os.path.isdir(QDIR):
        return []
    out = []
    for f in sorted(os.listdir(QDIR), key=lambda x: int(os.path.splitext(x)[0]) if x[:-5].isdigit() else 0):
        if f.endswith(".json"):
            out.append(C.jload(os.path.join(QDIR, f)))
    return out


def text_hash(q):
    """Empreinte du texte affiché : toute modification invalide les relectures déjà données."""
    blob = json.dumps({k: q.get(k) for k in VISIBLE_TEXT} | {"polarity": q.get("polarity")}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def sources_ok(q):
    srcs = q.get("sources") or []
    return len(srcs) >= 1 and all(s.get("url", "").startswith("https://") for s in srcs)
