"""Chargement des jeux publics (Hugging Face « datasets-server », sans dépendance) avec cache disque.

Échantillonnage : on tire au hasard (graine fixe) de nombreux petits blocs de lignes consécutives, ce qui évite de
télécharger tout le jeu tout en limitant le biais des fichiers triés.  Le cache garantit que deux exécutions
comparent exactement les mêmes exemples."""
import json, os, random, time, urllib.parse, urllib.request, urllib.error
from . import config as C

API = "https://datasets-server.huggingface.co/rows"
BLOCK = 25          # lignes consécutives par requête : peu de requêtes, donc pas de limitation de débit
MIN_BLOCKS = 12     # au moins 12 blocs répartis au hasard, même pour un petit échantillon


TRIES = 6


def _get(url, tries=None):
    tries = tries or TRIES
    for i in range(tries):
        try:
            time.sleep(0.25)
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "jev_lab"}), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if i == tries - 1 or e.code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"jeu indisponible ({url}) : {e}")
            time.sleep(float(e.headers.get("Retry-After") or 0) or min(60, 4 * 2 ** i))
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            if i == tries - 1:
                raise RuntimeError(f"jeu indisponible ({url}) : {e}")
            time.sleep(2 ** i)


def rows(dataset, config, split, offset, length):
    q = urllib.parse.urlencode({"dataset": dataset, "config": config, "split": split, "offset": offset, "length": length})
    d = _get(f"{API}?{q}")
    return d.get("num_rows_total"), [r["row"] for r in d.get("rows", [])]


def pool(dataset, config, split, seed, nblocks):
    """Réservoir de nblocks × BLOCK lignes, blocs tirés au hasard (graine fixe) et mis en cache.
    L'ordre est entrelacé entre les blocs : les k premières lignes sont donc toujours les mêmes quel que soit le
    nombre d'exemples demandé ensuite (les échantillons de tailles différentes s'emboîtent, l'appariement tient)."""
    tag = f"v2__{dataset.replace('/', '__')}__{config}__{split}__{seed}__{nblocks}.jsonl"
    path = os.path.join(C.CACHE, tag)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [json.loads(x) for x in f]
    total, _ = rows(dataset, config, split, 0, 1)
    nstarts = max(1, (total or BLOCK) - BLOCK + 1)
    perm = random.Random(seed).sample(range(nstarts), min(nblocks, nstarts))     # permutation : les premiers blocs ne dépendent pas de nblocks
    blocks = [rows(dataset, config, split, s, BLOCK)[1] for s in perm]
    got = [b[j] for j in range(BLOCK) for b in blocks if j < len(b)]
    os.makedirs(C.CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in got:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return got


def sample(dataset, config, split, n, seed, label_key=None, balanced=False, nblocks=40):
    """n lignes (préfixe stable).  balanced : autant par classe, en alternant les classes ; erreur si une classe manque."""
    if not balanced:
        return pool(dataset, config, split, seed, nblocks)[:n]
    got = pool(dataset, config, split, seed, max(nblocks, 150))
    by = {}
    for r in got:
        by.setdefault(r[label_key], []).append(r)
    k = len(by)
    per = -(-n // max(1, k))
    short = {c: len(v) for c, v in by.items() if len(v) < per}
    if k < 2 or short:
        raise RuntimeError(f"échantillon équilibré impossible : classes sous-représentées {short or by.keys()} (besoin de {per} par classe)")
    cls = sorted(by)
    out = [by[c][i] for i in range(per) for c in cls]
    return out[:n]


def all_rows(dataset, config, split):
    """Jeu entier (petits jeux seulement)."""
    path = os.path.join(C.CACHE, f"{dataset.replace('/', '__')}__{config}__{split}__all.jsonl")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [json.loads(x) for x in f]
    out, off = [], 0
    while True:
        total, rs = rows(dataset, config, split, off, 100)
        out += rs
        off += 100
        if not rs or off >= (total or 0):
            break
    os.makedirs(C.CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out
