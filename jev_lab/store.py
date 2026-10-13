"""Journal brut, en ajout seul : chaque appel est conservé tel que reçu (requête, réponse, temps, usage).

Aucune clé n'est jamais écrite (on ne garde que des en-têtes de réponse choisis)."""
import json, os, subprocess, threading, time, platform, sys

KEEP_HEADERS = ("x-request-id", "retry-after", "x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset", "date")


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def rec_key(rec):
    """Clé d'identité d'un appel (reprise, déduplication à l'analyse).  Le modèle en fait partie."""
    return "|".join(str(rec.get(k, "")) for k in ("experiment", "task", "item", "system", "model", "variant", "rep"))


class RunStore:
    def __init__(self, path):
        self.path = path
        os.makedirs(path, exist_ok=True)
        self.calls_path = os.path.join(path, "calls.jsonl")
        self._lock = threading.Lock()
        self._done = None

    def key(self, rec):
        return rec_key(rec)

    def done(self):
        if self._done is None:
            self._done = set()
            if os.path.exists(self.calls_path):
                with open(self.calls_path, encoding="utf-8") as f:
                    for line in f:
                        try:
                            r = json.loads(line)
                        except ValueError:
                            continue
                        if r.get("ok"):                 # un échec sera retenté à la reprise
                            self._done.add(self.key(r))
        return self._done

    def append(self, rec):
        with self._lock:
            with open(self.calls_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if rec.get("ok") and self._done is not None:
                self._done.add(self.key(rec))

    def read(self):
        out = []
        if os.path.exists(self.calls_path):
            with open(self.calls_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
        return out

    def write_meta(self, **kw):
        p = os.path.join(self.path, "meta.json")
        meta = {}
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                meta = json.load(f)
        meta.update(kw)
        meta.setdefault("started", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        meta.setdefault("git", git_sha())
        meta.setdefault("python", sys.version.split()[0])
        meta.setdefault("platform", platform.platform())
        with open(p, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)

    def meta(self):
        p = os.path.join(self.path, "meta.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        return {}
