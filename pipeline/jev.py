"""Client Jev (TypeSafe) via OpenRouter : modèle de décision typé, pas un LLM.

POST https://openrouter.ai/api/alpha/decisions   (modèle `typesafe/jev-1.13`, ~0,042 $/M tokens d'entrée, sortie gratuite)
  state     : texte ou objet JSON à évaluer
  questions : {nom: {type: noul|choice|score, instructions, criteria}}
  -> answers: noul   {"noul": p}                                  (probabilité du « oui »)
              choice {"choice": option, "confidence", "probabilities": {option: p}}
              score  {"score": position pondérée, "confidence", "probabilities": {"0": p, ...}}
Pas de clé OPENROUTER_API_KEY -> `available()` est faux et tout appelant échoue fermé (jamais de résultat inventé).
"""
import json, os, time, threading, urllib.request, urllib.error

URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = os.environ.get("HEMI_JEV_MODEL", "typesafe/jev-1.13")   # figer la version : les seuils sont calibrés dessus
STATS = {"calls": 0, "input_tokens": 0, "cost": 0.0}
_lock = threading.Lock()


class JevError(RuntimeError):
    pass


def key():
    return os.environ.get("OPENROUTER_API_KEY")


def available():
    return bool(key())


def noul(instructions, criteria=None):
    q = {"type": "noul", "instructions": instructions}
    if criteria:
        q["criteria"] = criteria
    return q


def choice(instructions, criteria):
    if not 2 <= len(criteria) <= 255:
        raise ValueError("choice : 2 à 255 options")
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def score(instructions, levels):
    if not 2 <= len(levels) <= 10:
        raise ValueError("score : 2 à 10 niveaux")
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


def _post(body, timeout):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key()}", "Content-Type": "application/json",
        "X-OpenRouter-Title": "hemicycle", "HTTP-Referer": "https://github.com/lduf/hemicycle"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def decide(state, questions, model=None, timeout=60, attempts=4):
    """-> {"answers": {...}, "usage": {...}}. Réessaie 429/5xx/402 « in-flight budget » avec attente exponentielle."""
    if not available():
        raise JevError("OPENROUTER_API_KEY absente")
    body = {"model": model or MODEL, "state": state, "questions": questions}
    for i in range(attempts):
        try:
            d = _post(body, timeout)
            break
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")[:300]
            transient = e.code == 429 or e.code >= 500 or (e.code == 402 and "in_flight" in txt)
            if not transient or i == attempts - 1:
                raise JevError(f"Decisions {e.code}: {txt}")
            time.sleep(float(e.headers.get("Retry-After") or 0) or 2 ** (i + 1))
        except (urllib.error.URLError, TimeoutError) as e:
            if i == attempts - 1:
                raise JevError(f"Decisions injoignable : {e}")
            time.sleep(2 ** (i + 1))
    answers = d.get("answers") or {}
    missing = [k for k in questions if k not in answers]
    if missing:
        raise JevError(f"réponses manquantes : {missing}")
    u = d.get("usage") or {}
    with _lock:
        STATS["calls"] += 1; STATS["input_tokens"] += u.get("input_tokens", 0); STATS["cost"] += u.get("cost", 0.0)
    return {"answers": answers, "usage": u, "model": d.get("model")}
