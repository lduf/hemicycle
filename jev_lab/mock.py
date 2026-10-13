"""Serveur factice (Jev + modèles de chat + catalogue + crédits) pour tester toute la chaîne SANS dépenser un centime.

Les résultats obtenus contre ce serveur sont SIMULÉS : le rapport porte alors un bandeau explicite et ne doit jamais
être lu comme une mesure de Jev.  Le serveur reçoit la vérité terrain dans l'en-tête X-Mock-Gold (réservé à cet usage)."""
import json, random, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PRICES = {"claude-opus": (5.0, 25.0), "claude-haiku": (1.0, 5.0), "gpt-mini": (0.25, 2.0), "default": (0.5, 2.0)}


class MockState:
    def __init__(self, jev_acc=0.9, chat_acc=None, max_inflight=64, ctx=64000, latency=(0.002, 0.02), seed=7, billing_bias=0.0):
        self.jev_acc, self.max_inflight, self.ctx, self.latency = jev_acc, max_inflight, ctx, latency
        self.chat_acc = chat_acc or {"default": 0.92}
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

        def _gold(self):
            h = self.headers.get("X-Mock-Gold")
            return json.loads(h) if h else None

        def do_GET(self):
            if self.path.endswith("/models"):
                self._send(200, {"data": [
                    {"id": "anthropic/claude-opus-5", "created": 1790000000, "context_length": 200000, "pricing": {"prompt": "0.000005", "completion": "0.000025"}},
                    {"id": "anthropic/claude-haiku-5", "created": 1790000100, "context_length": 200000, "pricing": {"prompt": "0.000001", "completion": "0.000005"}},
                    {"id": "openai/gpt-5-mini", "created": 1790000200, "context_length": 128000, "pricing": {"prompt": "0.00000025", "completion": "0.000002"}},
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
                time.sleep(S.rnd.uniform(*S.latency))
                body = self._body()
                gold = self._gold()
                if self.path.endswith("/decisions"):
                    self._decisions(body, gold)
                elif self.path.endswith("/chat/completions"):
                    self._chat(body, gold)
                else:
                    self._send(404, {"error": "?"})
            finally:
                with S.lock:
                    S.inflight -= 1

        def _decisions(self, body, gold):
            nt = _tok({"s": body["state"], "q": body["questions"]})
            if nt > S.ctx:
                self._send(400, {"error": {"message": f"context length exceeded ({nt} > {S.ctx})"}})
                return
            ans = {}
            for name, q in body["questions"].items():
                g = (gold or {}).get(name) if isinstance(gold, dict) else None
                ok = S.rnd.random() < S.jev_acc
                conf = min(0.999, max(0.34, S.rnd.gauss(S.jev_acc, 0.12)))
                if q["type"] == "noul":
                    truth = bool(g) if g is not None else S.rnd.random() < .5
                    yes = truth if ok else not truth
                    p = conf if yes else 1 - conf
                    ans[name] = {"type": "noul", "noul": round(p, 3)}
                elif q["type"] == "choice":
                    opts = list(q["criteria"])
                    pick = g if (ok and g in opts) else S.rnd.choice(opts)
                    rest = [o for o in opts if o != pick]
                    pr = {o: round((1 - conf) / max(1, len(rest)), 3) for o in rest}
                    pr[pick] = round(conf, 3)
                    ans[name] = {"type": "choice", "choice": pick, "confidence": round(conf, 3), "probabilities": pr}
                else:
                    k = len(q["criteria"])
                    pick = g if (ok and isinstance(g, int)) else S.rnd.randrange(k)
                    pr = {str(i): round((1 - conf) / max(1, k - 1), 3) for i in range(k)}
                    pr[str(pick)] = round(conf, 3)
                    ans[name] = {"type": "score", "score": float(pick), "confidence": round(conf, 3), "probabilities": pr}
            cost = nt * 0.042e-6 * (1 + S.billing_bias)
            with S.lock:
                S.usage += cost
                S.calls += 1
            self._send(200, {"id": "gen-dec-mock", "model": "typesafe/jev-1.13-mock", "provider": "TypeSafe", "answers": ans,
                             "usage": {"input_tokens": nt, "output_tokens": 40, "cost": cost}})

        def _chat(self, body, gold):
            model = body["model"]
            fam = next((k for k in PRICES if k.replace("-", "") in model.replace("-", "")), "default")
            pin, pout = PRICES[fam]
            nin = _tok(body["messages"])
            acc = S.chat_acc.get(fam, S.chat_acc.get("default", .9))
            g = gold.get("q") if isinstance(gold, dict) else None
            txt = body["messages"][-1]["content"]
            ok = S.rnd.random() < acc
            if '"p_yes"' in txt:
                truth = bool(g) if g is not None else S.rnd.random() < .5
                yes = truth if ok else not truth
                out = {"p_yes": round(.9 if yes else .1, 2)}
            elif '"level"' in txt:
                out = {"level": g if (ok and isinstance(g, int)) else S.rnd.randrange(5), "confidence": 0.8}
            else:
                out = {"choice": g if (ok and g is not None) else "?", "confidence": 0.8}
            content = json.dumps(out)
            cost = (nin * pin + 30 * pout) / 1e6
            with S.lock:
                S.usage += cost
                S.calls += 1
            self._send(200, {"id": "chat-mock", "model": model, "choices": [{"message": {"role": "assistant", "content": content}}],
                             "usage": {"prompt_tokens": nin, "completion_tokens": 30, "cost": cost}})
    return H


def start(**kw):
    S = MockState(**kw)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(S))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, S, f"http://127.0.0.1:{srv.server_address[1]}"
