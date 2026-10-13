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


def sample(dataset, config, split, n, seed, label_key=None, balanced=False):
    """n lignes tirées au hasard (ou n/k par classe si balanced) ; mises en cache."""
    tag = f"{dataset.replace('/', '__')}__{config}__{split}__{n}__{seed}__{'bal' if balanced else 'uni'}.jsonl"
    path = os.path.join(C.CACHE, tag)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [json.loads(x) for x in f]
    total, first = rows(dataset, config, split, 0, BLOCK)
    rnd = random.Random(seed)
    want = n * (4 if balanced else 1)
    nblocks = max(MIN_BLOCKS, -(-want // BLOCK))
    starts = sorted(rnd.sample(range(0, max(1, (total or BLOCK) - BLOCK + 1)), min(nblocks, max(1, (total or BLOCK) - BLOCK + 1))))
    got = []
    for s in starts:
        got += rows(dataset, config, split, s, BLOCK)[1]
    rnd.shuffle(got)
    if balanced and label_key:
        by = {}
        for r in got:
            by.setdefault(r[label_key], []).append(r)
        per = max(1, n // max(1, len(by)))
        got = [r for rs in by.values() for r in rs[:per]]
        rnd.shuffle(got)
    got = got[:n]
    os.makedirs(C.CACHE, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in got:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return got


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
