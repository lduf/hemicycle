"""Appel minimal à l'API Anthropic (stdlib seulement). Sans ANTHROPIC_API_KEY : retourne None (étape bloquée, jamais devinée)."""
import json, os, urllib.request, urllib.error

API = "https://api.anthropic.com/v1/messages"


def available():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def ask(model, prompt, system="", max_tokens=1500, temperature=0.2, timeout=120):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API {e.code}: {e.read()[:300]!r}")
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def ask_json(model, prompt, system="", **kw):
    """Demande une réponse JSON ; extrait le premier objet {...}. Retourne None si indisponible/illisible."""
    t = ask(model, prompt, system, **kw)
    if t is None:
        return None
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < a:
        return None
    try:
        return json.loads(t[a:b + 1])
    except ValueError:
        return None
