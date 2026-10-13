"""Serveur factice (Jev + modèles de chat + catalogue + crédits) pour tester toute la chaîne SANS dépenser un centime.

⚠️ Les résultats obtenus contre ce serveur sont SIMULÉS : le rapport porte un bandeau explicite et ne dit RIEN de Jev.
Le comportement ci-dessous est un « Jev imaginaire » écrit à la main (taux d'erreur par scénario, bruit sur les notes, quelques faiblesses
choisies pour que le rapport en montre) : il illustre la FORME d'un rapport, jamais un résultat.
Le serveur reçoit la vérité terrain et l'identité de l'exemple dans des en-têtes réservés (X-Mock-*)."""
import hashlib, json, math, random, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# probabilité d'erreur sur une réponse oui/non ou à choix, par famille de système et par scénario (SCÉNARIO FICTIF)
ERR = {
    "jev":   {"categorie": .14, "correspond": .03, "sens": .04, "charge": .10, "pro_ok": .06, "con_ok": .07},
    "haiku": {"categorie": .15, "correspond": .07, "sens": .09, "charge": .14, "pro_ok": .10, "con_ok": .11},
    "opus":  {"categorie": .07, "correspond": .02, "sens": .03, "charge": .08, "pro_ok": .04, "con_ok": .05},
}
SD = {"jev": .75, "haiku": 1.05, "opus": .65}          # bruit sur les notes (échelle 0-5 ou 0-2)
BIAS_JEV_ORIENT = -0.35                                  # faiblesse fictive : Jev sous-estime légèrement l'orientation
LAT = {"jev": (0.012, 0.35), "haiku": (0.06, 0.4), "opus": (0.15, 0.4)}   # médiane en secondes, DIVISÉE PAR 10 vs un service réel
PRICES = {"claude-opus": (4.0, 20.0), "claude-haiku": (0.10, 0.5), "gpt-nano": (0.2, 1.25), "default": (0.5, 2.0)}
LEVEL = {"orig": 0.8, "pour": 4.0, "contre": 4.0, "subtil": 2.0}


def fam_of(model):
    m = model.replace("-", "")
    return "opus" if "opus" in m else "haiku" if ("haiku" in m or "nano" in m or "mini" in m) else "jev" if "jev" in m else "haiku"


def h01(*parts):
    """Nombre stable dans [0, 1) pour un tuple de chaînes : un même exemple est « difficile » pour tous les appels qui le concernent."""
    return int(hashlib.md5("|".join(map(str, parts)).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def noise(sd, *parts):
    return random.Random("|".join(map(str, parts))).gauss(0, sd)


def answer(fam, scenario, group, name, q, g, item, rnd):
    """Réponse simulée à UNE question, d'après la vérité terrain `g` (None = inconnue) et le niveau de difficulté de l'exemple."""
    u, v = h01(scenario, name, item, "u"), h01(scenario, name, item, "v")
    err = ERR[fam].get(name, ERR[fam].get(scenario, .08))
    if name == "con_ok" and group == "contre_d_une_autre_mesure" and fam == "jev":
        err = .40                                   # faiblesse fictive : Jev peine à voir qu'un « contre » parle d'une autre mesure
    p_err = min(.95, err * 2 * u)                   # difficulté de l'exemple : la moyenne des p_err vaut `err`
    wrong = v < p_err
    conf = min(.999, max(.5, 1 - p_err + .03 + rnd.gauss(0, .03)))           # calibrée par construction, +3 points d'excès de confiance
    if q["type"] == "noul":
        truth = bool(g) if g is not None else (h01(scenario, name, item, "t") < .85 if name.endswith("fond") else h01(scenario, name, item, "t") < .30)
        yes = (not truth) if wrong else truth
        return {"noul": round(conf if yes else 1 - conf, 3)}
    if q["type"] == "choice":
        opts = list(q["criteria"])
        if g is None or g not in opts:
            g = "aucun" if "aucun" in opts else opts[int(h01(scenario, item) * 997) % len(opts)]
        others = sorted(o for o in opts if o != g)
        pick = others[int(h01(scenario, name, item, "w") * 997) % len(others)] if wrong else g
        pr = {o: round((1 - conf) / max(1, len(others)), 3) for o in others}
        pr[pick] = round(conf, 3)
        return {"choice": pick, "confidence": round(conf, 3), "probabilities": pr}
    k = len(q["criteria"])
    level = float(g) if g is not None else (k - 1) / 2
    if scenario == "neutralite":
        level += BIAS_JEV_ORIENT if fam == "jev" else 0
    x = level + noise(SD[fam] * (0.5 + u), scenario, name, item, fam)
    return {"score": round(max(0.0, min(k - 1.0, x)), 2)}


def gold_levels(scenario, group, g):
    """Vérité terrain des questions pour lesquelles le scénario ne pose pas de réponse unique (notes d'orientation, équilibre)."""
    out = dict(g or {})
    if scenario == "neutralite":
        out["orientation"] = LEVEL.get(group, 1.0)
        out["bord"] = "aucun" if group == "orig" else ("gauche" if h01(group) < .5 else "droite")
        out["charge"] = True if group in ("pour", "contre") else out.get("charge")
    elif scenario == "pro_contre":
        out["equilibre"] = {"orig": 1.0, "contre_tronque": 0.0}.get(group, 1.0)
    return out


class MockState:
    def __init__(self, max_inflight=64, ctx=64000, seed=7, billing_bias=0.0):
        self.max_inflight, self.ctx = max_inflight, ctx
        self.rnd = random.Random(seed)
        self.lock = threading.Lock()
        self.inflight = 0
        self.usage = 0.0
        self.calls = 0
        self.billing_bias = billing_bias


def _tok(obj):
    return max(1, int(len(json.dumps(obj, ensure_ascii=False)) / 3.6))


def make_handler(S):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"         # connexions persistantes, comme le vrai service

        def log_message(self, *a):
            pass

        def _send(self, code, obj, headers=None):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(b)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def _hdr(self, name):
            h = self.headers.get(name)
            return json.loads(h) if h else None

        def do_GET(self):
            if self.path.endswith("/models"):
                self._send(200, {"data": [
                    {"id": "anthropic/claude-opus-5", "created": 1790000000, "context_length": 200000, "pricing": {"prompt": "0.000004", "completion": "0.00002"}},
                    {"id": "anthropic/claude-haiku-5", "created": 1790000100, "context_length": 200000, "pricing": {"prompt": "0.0000001", "completion": "0.0000005"}},
                    {"id": "openai/gpt-5-nano", "created": 1790000200, "context_length": 128000, "pricing": {"prompt": "0.0000002", "completion": "0.00000125"}},
                    {"id": "typesafe/jev-1.13", "created": 1789000000, "context_length": 32000, "pricing": {"prompt": "0.000000042", "completion": "0"}}]})
            elif self.path.endswith("/credits"):
                self._send(200, {"data": {"total_credits": 100.0, "total_usage": S.usage}})
            else:
                self._send(404, {"error": "?"})

        def do_POST(self):
            body = self._body()                 # toujours lire le corps (connexion persistante)
            with S.lock:
                S.inflight += 1
                over = S.inflight > S.max_inflight
            try:
                if over:
                    self._send(429, {"error": {"message": "rate limited"}}, {"Retry-After": "0"})
                    return
                gold, meta = self._hdr("X-Mock-Gold") or {}, self._hdr("X-Mock-Meta") or {}
                fam = "jev" if self.path.endswith("/decisions") else fam_of(body.get("model", ""))
                med, sig = LAT[fam]
                time.sleep(min(2.0, S.rnd.lognormvariate(math.log(med), sig) + _tok(body) / 1e6))
                if self.path.endswith("/decisions"):
                    self._decisions(body, gold, meta)
                elif self.path.endswith("/chat/completions"):
                    self._chat(body, gold, meta, fam)
                else:
                    self._send(404, {"error": "?"})
            finally:
                with S.lock:
                    S.inflight -= 1

        def _answers(self, fam, qs, gold, meta):
            sc, group, item = meta.get("task") or "?", meta.get("group") or "?", meta.get("item") or "?"
            g = gold_levels(sc, group, gold if isinstance(gold, dict) else {})
            return {name: dict(type=q["type"], **answer(fam, sc, group, name, q, g.get(name), item, S.rnd)) for name, q in qs.items()}

        def _decisions(self, body, gold, meta):
            nt = _tok({"s": body["state"], "q": body["questions"]})
            if nt > S.ctx:
                self._send(400, {"error": {"message": f"context length exceeded ({nt} > {S.ctx})"}})
                return
            ans = self._answers("jev", body["questions"], gold, meta)
            for name, q in body["questions"].items():            # forme exacte documentée : probabilités par niveau pour un score
                if q["type"] == "score":
                    k, x = len(q["criteria"]), ans[name]["score"]
                    pr = {str(i): max(0.0, 1 - abs(i - x)) for i in range(k)}
                    tot = sum(pr.values()) or 1
                    ans[name]["probabilities"] = {a: round(b / tot, 3) for a, b in pr.items()}
                    ans[name]["confidence"] = round(max(ans[name]["probabilities"].values()), 3)
            cost = nt * 0.042e-6 * (1 + S.billing_bias)
            with S.lock:
                S.usage += cost
                S.calls += 1
            self._send(200, {"id": "gen-dec-mock", "model": "typesafe/jev-1.13-SIMULE", "provider": "TypeSafe", "answers": ans,
                             "usage": {"input_tokens": nt, "output_tokens": 40, "cost": cost}})

        def _chat(self, body, gold, meta, fam):
            model = body["model"]
            key = next((k for k in PRICES if k.replace("-", "") in model.replace("-", "")), "default")
            pin, pout = PRICES[key]
            nin = _tok(body["messages"])
            txt = body["messages"][-1]["content"]
            if "Réécris cette fiche" in txt:                                    # génération des variantes de neutralité
                m = re.search(r"Fiche : (\{.*\})\s*$", txt, re.S)
                fiche = json.loads(m.group(1)) if m else {}
                tag = "[EN FAVEUR] " if "EN FAVEUR" in txt else "[CONTRE] " if "CONTRE la mesure" in txt else "[CADRAGE LÉGER] "
                content = json.dumps({k: (tag + v if isinstance(v, str) and k in ("sum", "pro", "con", "hook") else v) for k, v in fiche.items()}, ensure_ascii=False)
            else:
                m = re.search(r"questions = (\{.*\})\s*$", txt, re.S)
                qs = json.loads(m.group(1)) if m else {}
                qs = {k: {"type": v["type"], "criteria": v.get("criteria")} for k, v in qs.items()}
                out = self._answers(fam, qs, gold, meta)
                content = json.dumps({k: {a: b for a, b in v.items() if a != "type"} for k, v in out.items()}, ensure_ascii=False)
            cost = (nin * pin + 120 * pout) / 1e6
            with S.lock:
                S.usage += cost
                S.calls += 1
            self._send(200, {"id": "chat-mock", "model": model, "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                             "usage": {"prompt_tokens": nin, "completion_tokens": 120, "cost": cost}})
    return H


def start(**kw):
    S = MockState(**kw)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(S))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, S, f"http://127.0.0.1:{srv.server_address[1]}"
