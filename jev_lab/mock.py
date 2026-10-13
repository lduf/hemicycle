"""Serveur factice (Jev + modèles de chat + catalogue + crédits) pour tester toute la chaîne SANS dépenser un centime.

⚠️ Les résultats obtenus contre ce serveur sont SIMULÉS : le rapport porte un bandeau explicite et ne dit RIEN de Jev.
Le scénario ci-dessous est un « Jev imaginaire » écrit à la main pour illustrer la forme d'un rapport : forte précision sur la
classification simple, faible sur l'arithmétique, sensible au bruit, etc.  Ces valeurs n'ont aucune valeur de mesure.
Le serveur reçoit la vérité terrain et l'identité de l'exemple dans des en-têtes réservés (X-Mock-*)."""
import hashlib, json, math, random, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# précision de base par tâche et par famille de système (SCÉNARIO FICTIF)
ACC = {
    "jev":    {"ag_news": .90, "sst2": .91, "toxic": .88, "injection": .93, "boolq": .78, "xnli_fr": .72, "vitaminc": .55, "sst5": .48, "avis_fr": .50,
               "banking77": .90, "massive_fr": .88, "dates": .62, "comptage": .30, "arith": .55, "max": .55},
    "haiku":  {"ag_news": .88, "sst2": .93, "toxic": .86, "injection": .90, "boolq": .85, "xnli_fr": .80, "vitaminc": .60, "sst5": .50, "avis_fr": .52,
               "banking77": .75, "massive_fr": .78, "dates": .90, "comptage": .70, "arith": .95, "max": .95},
    "opus":   {"ag_news": .91, "sst2": .95, "toxic": .90, "injection": .94, "boolq": .90, "xnli_fr": .88, "vitaminc": .72, "sst5": .56, "avis_fr": .58,
               "banking77": .88, "massive_fr": .85, "dates": .97, "comptage": .90, "arith": .99, "max": .99},
}
NOISE_SENS = {"jev": 0.05, "haiku": 0.012, "opus": 0.006}        # perte de précision par doublement du bruit (SCÉNARIO)
LAT = {"jev": (0.012, 0.35), "haiku": (0.06, 0.4), "opus": (0.15, 0.4)}   # médiane (s, DIVISÉE PAR 10 vs une vraie latence), dispersion log-normale
PRICES = {"claude-opus": (4.0, 20.0), "claude-haiku": (0.10, 0.5), "gpt-nano": (0.2, 1.25), "default": (0.5, 2.0)}


def fam_of(model):
    m = model.replace("-", "")
    return "opus" if "opus" in m else "haiku" if ("haiku" in m or "nano" in m or "mini" in m) else "jev" if "jev" in m else "haiku"


def u_item(task, item):
    """Difficulté propre à l'exemple, stable : un même exemple est « difficile » pour tous les appels qui le concernent."""
    return int(hashlib.md5(f"{task}|{item}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def acc_eff(fam, task, variant):
    a = ACC[fam].get(task, .8)
    m = re.match(r"noise:(\d+):", variant or "")
    if m:
        a -= NOISE_SENS[fam] * math.log2(1 + int(m.group(1)) / 150)
    if variant == "nodesc":
        a -= 0.02 if fam == "jev" else 0.01
    return max(0.05, a)


class MockState:
    def __init__(self, scenario=True, jev_acc=0.9, chat_acc=None, max_inflight=64, ctx=64000, latency=(0.002, 0.02), seed=7, billing_bias=0.0):
        self.scenario, self.jev_acc, self.chat_acc = scenario, jev_acc, chat_acc or {"default": 0.92}
        self.max_inflight, self.ctx, self.latency = max_inflight, ctx, latency
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
            with S.lock:
                S.inflight += 1
                over = S.inflight > S.max_inflight
            try:
                if over:
                    self._send(429, {"error": {"message": "rate limited"}}, {"Retry-After": "0"})
                    return
                body = self._body()
                gold, meta = self._hdr("X-Mock-Gold"), self._hdr("X-Mock-Meta") or {}
                fam = "jev" if self.path.endswith("/decisions") else fam_of(body.get("model", ""))
                if S.scenario:
                    med, sig = LAT[fam]
                    time.sleep(min(2.0, S.rnd.lognormvariate(math.log(med), sig) + _tok(body) / 1e6))
                else:
                    time.sleep(S.rnd.uniform(*S.latency))
                if self.path.endswith("/decisions"):
                    self._decisions(body, gold, meta)
                elif self.path.endswith("/chat/completions"):
                    self._chat(body, gold, meta, fam)
                else:
                    self._send(404, {"error": "?"})
            finally:
                with S.lock:
                    S.inflight -= 1

        # ---- décisions du Jev imaginaire ----
        def _correct_and_conf(self, fam, task, item, variant, qname="q"):
            if not S.scenario:
                ok = S.rnd.random() < S.jev_acc
                return ok, min(0.999, max(0.34, S.rnd.gauss(S.jev_acc, 0.12)))
            u = (u_item(task, item) + (0 if qname in ("q", "a") else u_item("q", qname))) % 1.0
            ok = u < acc_eff(fam, task, variant)
            # confiance décroissante avec la difficulté (+ bruit) : plutôt bien calibrée, légèrement optimiste
            conf = 0.985 - 0.62 * u ** 1.4 + S.rnd.gauss(0, 0.035)
            return ok, min(0.999, max(0.34, conf))

        def _decisions(self, body, gold, meta):
            nt = _tok({"s": body["state"], "q": body["questions"]})
            if nt > S.ctx:
                self._send(400, {"error": {"message": f"context length exceeded ({nt} > {S.ctx})"}})
                return
            task, item, variant = meta.get("task") or "ag_news", meta.get("item") or "?", meta.get("variant") or "base"
            ans = {}
            for name, q in body["questions"].items():
                g = gold.get(name) if isinstance(gold, dict) else None
                ok, conf = self._correct_and_conf("jev", task, item, variant, name)
                jitter = S.rnd.gauss(0, 0.006)                      # « légèrement différent d'une exécution à l'autre » : bruit simulé
                conf = min(0.999, max(0.34, conf + jitter))
                if q["type"] == "noul":
                    truth = bool(g) if g is not None else S.rnd.random() < .5
                    yes = truth if ok else not truth
                    ans[name] = {"type": "noul", "noul": round(conf if yes else 1 - conf, 3)}
                elif q["type"] == "choice":
                    opts = list(q["criteria"])
                    wrong = [o for o in opts if o != g] or opts
                    pick = g if (ok and g in opts) else wrong[int(u_item(task, item) * 997) % len(wrong)]
                    rest = [o for o in opts if o != pick]
                    pr = {o: round((1 - conf) / max(1, len(rest)), 3) for o in rest}
                    pr[pick] = round(conf, 3)
                    ans[name] = {"type": "choice", "choice": pick, "confidence": round(conf, 3), "probabilities": pr}
                else:
                    k = len(q["criteria"])
                    pick = g if (ok and isinstance(g, int)) else (((g if isinstance(g, int) else 2) + (1 if u_item(task, item) < .5 else -1)) % k)
                    pr = {str(i): round((1 - conf) / max(1, k - 1), 3) for i in range(k)}
                    pr[str(pick)] = round(conf, 3)
                    ans[name] = {"type": "score", "score": float(pick), "confidence": round(conf, 3), "probabilities": pr}
            cost = nt * 0.042e-6 * (1 + S.billing_bias)
            with S.lock:
                S.usage += cost
                S.calls += 1
            self._send(200, {"id": "gen-dec-mock", "model": "typesafe/jev-1.13-SIMULE", "provider": "TypeSafe", "answers": ans,
                             "usage": {"input_tokens": nt, "output_tokens": 40, "cost": cost}})

        # ---- modèles de comparaison ----
        def _chat(self, body, gold, meta, fam):
            model = body["model"]
            key = next((k for k in PRICES if k.replace("-", "") in model.replace("-", "")), "default")
            pin, pout = PRICES[key]
            nin = _tok(body["messages"])
            g = gold.get("q") if isinstance(gold, dict) else None
            txt = body["messages"][-1]["content"]
            task, item, variant = meta.get("task") or "ag_news", meta.get("item") or "?", meta.get("variant") or "base"
            if S.scenario:
                u = u_item(task + "#" + fam, item)
                ok = u < acc_eff(fam, task, variant)
                conf = min(0.95, max(0.5, 0.92 - 0.4 * u))
            else:
                ok = S.rnd.random() < S.chat_acc.get(key, S.chat_acc.get("default", .9))
                conf = 0.8
            if '"p_yes"' in txt:
                truth = bool(g) if g is not None else S.rnd.random() < .5
                yes = truth if ok else not truth
                out = {"p_yes": round(conf if yes else 1 - conf, 2)}
            elif '"level"' in txt:
                lv = g if (ok and isinstance(g, int)) else (((g if isinstance(g, int) else 2) + 1) % 5)
                out = {"level": lv, "confidence": round(conf, 2)}
            else:
                opts = re.findall(r"^- ([^:\n]+):", txt, re.M)
                wrong = [o for o in opts if o != g] or ["?"]
                out = {"choice": g if (ok and g is not None) else wrong[int(u_item(task, item) * 997) % len(wrong)], "confidence": round(conf, 2)}
            content = json.dumps(out)
            cost = (nin * pin + 30 * pout) / 1e6
            with S.lock:
                S.usage += cost
                S.calls += 1
            self._send(200, {"id": "chat-mock", "model": model, "choices": [{"message": {"role": "assistant", "content": content}}],
                             "usage": {"prompt_tokens": nin, "completion_tokens": 30, "cost": cost}})
    return H


def start(**kw):
    kw.setdefault("scenario", False)       # les tests utilisent le comportement simple ; la démonstration active le scénario
    S = MockState(**kw)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(S))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, S, f"http://127.0.0.1:{srv.server_address[1]}"
