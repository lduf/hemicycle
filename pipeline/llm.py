"""Accès aux modèles. Deux backends :

  cli (défaut si `claude` est installé) : `claude -p`, qui utilise l'abonnement Claude de l'utilisateur.
       Sans outils, sans session, hors du dépôt (pas de CLAUDE.md chargé). ANTHROPIC_API_KEY est retirée de
       l'environnement du processus fils pour ne jamais facturer l'API par accident.
       En CI : `claude setup-token` puis secret CLAUDE_CODE_OAUTH_TOKEN.
  api : API Anthropic (stdlib), si ANTHROPIC_API_KEY est définie et HEMI_LLM=api.
HEMI_LLM=none désactive tout (tests, mode hors ligne) : les étapes « modèle » échouent fermé.
Jamais de réponse devinée : indisponible -> None.
"""
import json, os, shutil, subprocess, tempfile, urllib.request, urllib.error

API = "https://api.anthropic.com/v1/messages"


def backend():
    want = os.environ.get("HEMI_LLM", "").lower()
    if want == "none":
        return None
    if want == "api" or (not want and not shutil.which("claude") and os.environ.get("ANTHROPIC_API_KEY")):
        return "api" if os.environ.get("ANTHROPIC_API_KEY") else None
    return "cli" if shutil.which("claude") else None


def available():
    return backend() is not None


def _ask_cli(model, prompt, system, timeout):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):      # un jeton collé sur 2 lignes dans un secret est rejeté (« line break ») : on retire les blancs
        env["CLAUDE_CODE_OAUTH_TOKEN"] = "".join(env["CLAUDE_CODE_OAUTH_TOKEN"].split())
    cmd = ["claude", "-p", "--model", model, "--tools", "", "--no-session-persistence", "--disable-slash-commands",
           "--output-format", "text"]
    if system:
        cmd += ["--system-prompt", system]
    with tempfile.TemporaryDirectory() as cwd:   # hors dépôt : aucun CLAUDE.md ni réglage projet
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
    if r.returncode:
        # `claude -p` écrit souvent ses erreurs (jeton invalide, quota…) sur stdout : on garde les deux
        raise RuntimeError(f"claude -p a échoué ({r.returncode}) : {(r.stderr.strip() + ' | ' + r.stdout.strip())[:400]}")
    return r.stdout


def _ask_api(model, prompt, system, max_tokens, temperature, timeout):
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": [{"role": "user", "content": prompt}]}
    if system:
        body["system"] = system
    req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API {e.code}: {e.read()[:300]!r}")
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def ask(model, prompt, system="", max_tokens=1500, temperature=0.2, timeout=180):
    """max_tokens/temperature ne s'appliquent qu'au backend api (`claude -p` ne les expose pas)."""
    b = backend()
    if b is None:
        return None
    return _ask_cli(model, prompt, system, timeout) if b == "cli" else _ask_api(model, prompt, system, max_tokens, temperature, timeout)


def ask_json(model, prompt, system="", **kw):
    """Réponse JSON : premier objet {...}. None si indisponible ou illisible."""
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
