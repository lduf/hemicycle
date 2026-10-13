"""Clients HTTP instrumentés : Jev (Decisions API) et modèles de comparaison (chat completions), via OpenRouter.

Chaque appel renvoie un enregistrement `Call` (dict) complet : durée mesurée côté client, tentatives, usage, réponse brute.
Principes de mesure :
  - `wall_s` = durée de la tentative qui a abouti (ce que l'utilisateur attend, hors attentes de réessai) ;
  - `total_s` = durée totale, attentes de réessai comprises ;
  - on ne réessaie que 429 / 5xx / erreurs réseau, et chaque tentative est consignée : un taux d'erreur caché serait un biais.
"""
import http.client, json, os, random, re, threading, time, urllib.error, urllib.parse, urllib.request
from . import config as C
from .store import KEEP_HEADERS

RETRY_STATUS = (429, 500, 502, 503, 504)


def api_key():
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def _usage(u):
    """Tolère les deux graphies vues dans la doc (input_tokens / inputTokens)."""
    u = u or {}
    return {"input_tokens": u.get("input_tokens", u.get("inputTokens", u.get("prompt_tokens"))),
            "output_tokens": u.get("output_tokens", u.get("outputTokens", u.get("completion_tokens"))),
            "cost": u.get("cost")}


_tls = threading.local()


def _proxied(url):
    """Un proxy d'environnement s'applique-t-il ? (alors on retombe sur urllib, qui sait le gérer)."""
    u = urllib.parse.urlparse(url)
    if (u.hostname or "") in ("localhost", "127.0.0.1"):
        return False
    return bool(os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY") or os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY"))


def _attempt_keepalive(url, method, data, hdr, timeout):
    """Connexion persistante par thread : on ne paie ni DNS ni TLS à chaque appel (sinon la latence fixe écrase les écarts)."""
    u = urllib.parse.urlparse(url)
    key = (u.scheme, u.netloc)
    pool = getattr(_tls, "pool", None)
    if pool is None:
        pool = _tls.pool = {}
    path = u.path + (("?" + u.query) if u.query else "")
    for second_chance in (True, False):
        conn = pool.get(key)
        reused = conn is not None and conn.sock is not None
        if conn is None:
            cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
            conn = pool[key] = cls(u.netloc, timeout=timeout)
        try:
            conn.request(method, path, body=data, headers=hdr)
            r = conn.getresponse()
            text = r.read().decode("utf-8", "replace")
            return r.status, text, {k.lower(): v for k, v in r.getheaders() if k.lower() in KEEP_HEADERS}, None
        except (http.client.HTTPException, OSError) as e:
            try:
                conn.close()
            except OSError:
                pass
            pool.pop(key, None)
            stale = reused and isinstance(e, (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError))
            if stale and second_chance:
                continue                      # connexion fermée par le serveur entre deux appels : on se reconnecte sans compter d'échec
            return None, "", {}, f"{type(e).__name__}: {e}"
    return None, "", {}, "inatteignable"


def _attempt_urllib(url, method, data, hdr, timeout):
    status, text, headers, err = None, "", {}, None
    try:
        req = urllib.request.Request(url, data=data, method=method, headers=hdr)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, text = r.status, r.read().decode("utf-8", "replace")
            headers = {k.lower(): v for k, v in r.headers.items() if k.lower() in KEEP_HEADERS}
    except urllib.error.HTTPError as e:
        status, text = e.code, e.read().decode("utf-8", "replace")
        headers = {k.lower(): v for k, v in e.headers.items() if k.lower() in KEEP_HEADERS}
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, ConnectionError, OSError) as e:
        err = f"{type(e).__name__}: {e}"
    return status, text, headers, err


def http_json(url, body, timeout=90, method="POST", extra_headers=None, attempts=4, sleep=time.sleep):
    """-> dict(ok, status, wall_s, total_s, attempts[list], headers, body|text, error)."""
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    hdr = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json",
           "X-Title": "jev_lab", "HTTP-Referer": "https://github.com/lduf/hemicycle"}
    hdr.update(extra_headers or {})
    attempt = _attempt_urllib if _proxied(url) else _attempt_keepalive
    log, t_all = [], time.perf_counter()
    for i in range(attempts):
        t0 = time.perf_counter()
        status, text, headers, err = attempt(url, method, data, hdr, timeout)
        wall = time.perf_counter() - t0
        log.append({"status": status, "wall_s": round(wall, 4), "error": err})
        retriable = err is not None or status in RETRY_STATUS or (status == 402 and "in_flight" in text)
        if status is not None and 200 <= status < 300:
            try:
                return {"ok": True, "status": status, "wall_s": wall, "total_s": time.perf_counter() - t_all,
                        "attempts": log, "headers": headers, "body": json.loads(text)}
            except ValueError:
                err = "réponse non JSON"
                retriable = False
        if not retriable or i == attempts - 1:
            return {"ok": False, "status": status, "wall_s": wall, "total_s": time.perf_counter() - t_all,
                    "attempts": log, "headers": headers, "text": text[:2000], "error": err or f"HTTP {status}"}
        wait = float(headers.get("retry-after") or 0) or min(30, 2 ** (i + 1)) * (0.5 + random.random())
        sleep(wait)
    raise AssertionError("inatteignable")


def _record(base, res, parse_usage=True):
    rec = dict(base)
    rec.update({"ok": res["ok"], "status": res["status"], "wall_s": round(res["wall_s"], 4), "total_s": round(res["total_s"], 4),
                "n_attempts": len(res["attempts"]), "attempts": res["attempts"], "headers": res["headers"],
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    if res["ok"]:
        b = res["body"]
        rec["response"] = b
        rec["usage"] = _usage(b.get("usage"))
        rec["resolved_model"] = b.get("model")
    else:
        rec["error"] = res.get("error")
        rec["error_text"] = res.get("text")
        rec["usage"] = _usage(None)
    return rec


def _mock_headers(base, gold):
    """Uniquement pour le serveur factice : vérité terrain et identité de l'exemple (jamais envoyés à l'API réelle)."""
    h = {"X-Mock-Meta": json.dumps({"task": base.get("task"), "item": base.get("item"), "variant": base.get("variant"), "rep": base.get("rep")})}
    if gold is not None:
        h["X-Mock-Gold"] = json.dumps(gold)
    return h


class JevClient:
    kind = "jev"

    def __init__(self, model=None, timeout=90, mock_gold=False):
        self.model = model or C.JEV_MODEL
        self.name = "jev"
        self.timeout = timeout
        self.mock_gold = mock_gold

    def call(self, base, state, questions, gold=None):
        body = {"model": self.model, "state": state, "questions": questions}
        extra = _mock_headers(base, gold) if self.mock_gold else None
        res = http_json(C.JEV_URL, body, self.timeout, extra_headers=extra)
        rec = _record({**base, "system": self.name, "request": body}, res)
        return rec


SYS_PROMPT = ("Tu es un système de décision. Réponds UNIQUEMENT par un objet JSON valide, sans texte autour, sans explication.")


class ChatClient:
    kind = "chat"

    def __init__(self, model, label=None, timeout=120, max_tokens=1000, mock_gold=False):
        self.model = model
        self.name = label or model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.mock_gold = mock_gold

    def call(self, base, prompt, gold=None):
        # usage.include : demande à OpenRouter de renvoyer le coût réel (sinon le garde-fou de budget serait aveugle)
        body = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens, "usage": {"include": True},
                "messages": [{"role": "system", "content": SYS_PROMPT}, {"role": "user", "content": prompt}]}
        extra = _mock_headers(base, gold) if self.mock_gold else None
        res = http_json(C.CHAT_URL, body, self.timeout, extra_headers=extra)
        rec = _record({**base, "system": self.name, "request": body}, res)
        if res["ok"]:
            if isinstance(res["body"], dict) and res["body"].get("error"):          # erreur du fournisseur renvoyée avec un statut 200
                rec["ok"], rec["error"], rec["error_text"] = False, "erreur fournisseur", json.dumps(res["body"]["error"])[:500]
                return rec
            try:
                ch = res["body"]["choices"][0]
                rec["text"] = ch["message"]["content"]
                rec["finish_reason"] = ch.get("finish_reason")
            except (KeyError, IndexError, TypeError):
                rec["ok"], rec["error"] = False, "réponse sans contenu"
                return rec
            # contenu vide ou tronqué (budget de sortie consommé par un raisonnement caché, par exemple) : c'est un artefact de
            # paramétrage, pas une erreur du modèle ; on le compte comme échec d'appel (rejoué à la reprise) et on le publie
            if not (rec["text"] or "").strip() or rec.get("finish_reason") == "length":
                rec["ok"], rec["error"] = False, f"contenu vide ou tronqué (finish_reason={rec.get('finish_reason')})"
        return rec


# ---------- catalogue ----------
def catalog():
    """Liste des modèles OpenRouter (id, prix, date de création)."""
    res = http_json(C.MODELS_URL, None, 60, method="GET")
    if not res["ok"]:
        raise RuntimeError(f"catalogue indisponible : {res.get('error')} {res.get('text', '')[:200]}")
    out = []
    for m in res["body"].get("data", []):
        p = m.get("pricing") or {}
        try:
            out.append({"id": m["id"], "created": m.get("created", 0), "context": m.get("context_length"),
                        "prompt": float(p.get("prompt") or 0), "completion": float(p.get("completion") or 0)})
        except (KeyError, ValueError, TypeError):
            continue
    return out


def resolve_patterns(cat, patterns=None):
    """Pour chaque famille, le modèle le plus récent du catalogue qui correspond au motif."""
    out = {}
    for fam, rx in (patterns or C.BASELINE_PATTERNS).items():
        ms = [m for m in cat if re.match(rx, m["id"]) and not m["id"].endswith(":free")]
        if ms:
            out[fam] = max(ms, key=lambda m: m["created"])
    return out


def credits():
    """Crédits OpenRouter (total acheté, total consommé) : sert à réconcilier le coût rapporté et le coût facturé."""
    res = http_json(C.CREDITS_URL, None, 30, method="GET")
    if not res["ok"]:
        return None
    d = (res["body"] or {}).get("data") or {}
    return {"total_credits": d.get("total_credits"), "total_usage": d.get("total_usage"), "ts": time.time()}
