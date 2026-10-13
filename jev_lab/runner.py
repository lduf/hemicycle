"""Moteur d'expériences.  Chaque expérience produit une liste de « jobs » (un appel chacun) ; on peut donc :
  - estimer le coût AVANT de dépenser (`plan`) ;
  - exécuter dans un ordre mélangé qui entrelace les systèmes (pas de biais d'heure) ;
  - reprendre après interruption (un job réussi n'est jamais rejoué) ;
  - s'arrêter net au plafond de budget.

Expériences : quality (E1), latency (E3), throughput (E4), billing (E5), robust (E6), determinism (E7), limits (E8), multi (E9).
La calibration (E2) et la lecture des revendications sont calculées à l'analyse, sans appel supplémentaire."""
import json, random, threading, time, zlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable
from . import config as C, tasks as T, synth as SY, client as CL
from .budget import Budget, BudgetExceeded, tokens_estimate

SUITES = {
    # smoke : vérifie clé, schéma et chaîne complète pour quelques centimes
    "smoke": dict(tasks=["ag_news", "sst2"], n=20, n_base=20, latency=dict(tasks=["ag_news"], k=8, reps=1),
                  throughput=None, robust=None, determinism=None, limits=dict(n=10, probe=False), multi=None, billing=dict(k=4)),
    "standard": dict(tasks=T.ORDER_CORE, n=200, n_base=100, latency=dict(tasks=["ag_news", "boolq", "vitaminc"], k=30, reps=2),
                     throughput=dict(levels=[1, 2, 4, 8, 16], per=8), robust=dict(tasks=["ag_news", "sst2", "xnli_fr"], n=60),
                     determinism=dict(tasks=["ag_news", "sst2", "avis_fr"], k=40, reps=5), limits=dict(n=60, probe=True),
                     multi=dict(n=60), billing=dict(k=10)),
    "full": dict(tasks=T.ORDER_CORE, n=500, n_base=250, latency=dict(tasks=["ag_news", "boolq", "vitaminc", "banking77"], k=60, reps=3),
                 throughput=dict(levels=[1, 2, 4, 8, 16, 32, 64], per=10), robust=dict(tasks=["ag_news", "sst2", "xnli_fr", "vitaminc"], n=150),
                 determinism=dict(tasks=["ag_news", "sst2", "avis_fr", "vitaminc"], k=40, reps=5), limits=dict(n=150, probe=True),
                 multi=dict(n=150), billing=dict(k=20)),
}

NOISE_VARIANTS = [("noise:150:before", 150, "before"), ("noise:600:before", 600, "before"), ("noise:2400:before", 2400, "before"),
                  ("noise:600:after", 600, "after"), ("noise:2400:both", 2400, "both")]
PROBE_SIZES = [1000, 4000, 8000, 16000, 28000, 31000, 33000, 40000, 60000, 63000, 65000, 70000]


@dataclass
class Job:
    base: dict
    system: str
    est_in: int
    est_out: int
    run: Callable
    order: float = 0.0


class Lab:
    def __init__(self, store, budget, jev, baselines, seed=C.SEED, workers=4, mock=False, jev_price=C.CLAIMS["prix_entree_par_M"][0], prices=None):
        self.store, self.budget, self.jev, self.baselines = store, budget, jev, baselines
        self.seed, self.workers, self.mock, self.jev_price = seed, workers, mock, jev_price
        self.prices = prices or {}            # modèle -> (prompt $/token, completion $/token), lu au catalogue
        self.systems = {"jev": jev, **{b.name: b for b in baselines}}
        self._items = {}
        self.custom = []                      # identifiants de tâches personnalisées (--custom)
        self.offline_estimate = False         # vrai pour `plan` : si un jeu est injoignable, taille moyenne connue à la place
        self.estimated_tasks = set()
        self.stop = threading.Event()
        self.skipped_budget = 0

    # ----- items -----
    def items(self, task_id, n):
        k = (task_id, n)
        if k not in self._items:
            if task_id in T.CUSTOM_ITEMS:
                self._items[k] = T.CUSTOM_ITEMS[task_id][:n]
            elif task_id in SY.SYNTH:
                self._items[k] = SY.load_synth(task_id, n, self.seed)
            else:
                try:
                    self._items[k] = T.load(task_id, n, self.seed)
                except RuntimeError:
                    if not self.offline_estimate:
                        raise
                    self.estimated_tasks.add(task_id)
                    self._items[k] = T.load(task_id, n, self.seed, fixtures=True)
        return self._items[k]

    def task(self, tid):
        t = T.TASKS[tid]
        if t.primitive == "choice" and not t.options and tid not in SY.SYNTH:
            if self.mock:
                t.options = {f"classe_{i}": f"classe {i}" for i in range(12)}
            else:
                try:
                    T.discover_options(t, self.seed)
                except RuntimeError:
                    if not self.offline_estimate:
                        raise
                    self.estimated_tasks.add(tid)       # estimation seulement : nombre de classes connu, libellés factices
                    t.options = {f"classe_{i}": f"classe {i}" for i in range(77 if tid == "banking77" else 60)}
        return t

    # ----- fabrique de jobs -----
    def est_cost(self, system, est_in, est_out):
        if system == "jev":
            return est_in * self.jev_price / 1e6
        pin, pout = self.prices.get(self.systems[system].model, (1e-6, 4e-6))
        return est_in * pin + est_out * pout

    def job(self, system, base, state, task, variant="base", spec_override=None, gold=None, questions=None):
        """Un appel : Jev (state + questions) ou modèle de chat (consigne texte équivalente)."""
        c = self.systems[system]
        sv = variant if (variant == "nodesc" or variant.startswith("shuffle")) else "base"   # les autres variantes ne changent pas la consigne
        base = {**base, "task": task.id, "primitive": task.primitive, "variant": variant, "gold": base.get("gold", gold), "model": c.model}
        if c.kind == "jev":
            qs = questions or {"q": spec_override or T.spec(task, sv, self.seed)}
            gold_hdr = base["gold"] if questions else {"q": base["gold"]}
            est_in = tokens_estimate(json.dumps({"s": state, "q": qs}, ensure_ascii=False))
            return Job(base, system, est_in, 0, lambda: c.call(base, state, qs, gold=gold_hdr))
        prompt = T.chat_prompt(task, state, sv, self.seed)
        return Job(base, system, tokens_estimate(prompt) + 40, 25, lambda: c.call(base, prompt, gold={"q": base["gold"]}))

    # ----- exécution -----
    def execute(self, jobs, workers=None, shuffle=True, label=""):
        done = self.store.done()
        todo = [j for j in jobs if self.store.key(j.base | {"system": j.system}) not in done]
        rnd = random.Random(f"{self.seed}-{label}")
        if shuffle:
            rnd.shuffle(todo)
        stats = {"jobs": len(jobs), "already_done": len(jobs) - len(todo), "run": 0, "failed": 0, "budget_stop": False}
        lock = threading.Lock()

        def go(j):
            if self.stop.is_set():
                return
            est = self.est_cost(j.system, j.est_in, j.est_out)
            try:
                self.budget.acquire(est)
            except BudgetExceeded:
                self.stop.set()
                with lock:
                    stats["budget_stop"] = True
                return
            try:
                rec = j.run()
                u = rec.get("usage") or {}
                if u.get("cost") is None and rec.get("ok") and u.get("input_tokens") is not None:
                    # coût non rapporté : estimé au tarif (catalogue pour les modèles de chat, tarif annoncé pour Jev), et signalé
                    if j.system == "jev":
                        u["cost"] = u["input_tokens"] * self.jev_price / 1e6
                    else:
                        pin, pout = self.prices.get(self.systems[j.system].model, (0, 0))
                        u["cost"] = u["input_tokens"] * pin + (u.get("output_tokens") or 0) * pout
                    rec["cost_estimated"] = True
                self.store.append(rec)
                self.budget.add(j.system, u.get("cost"))
            finally:
                self.budget.release(est)
            with lock:
                stats["run" if rec.get("ok") else "failed"] += 1

        w = workers or self.workers
        if w <= 1:
            for j in todo:
                go(j)
        else:
            with ThreadPoolExecutor(max_workers=w) as ex:
                list(ex.map(go, todo))
        return stats

    # ----- E1 : qualité -----
    def jobs_quality(self, tasks, n, n_base):
        jobs = []
        for tid in tasks:
            t = self.task(tid)
            for i, it in enumerate(self.items(tid, n)):
                for s in self.systems:
                    if s != "jev" and i >= n_base:
                        continue
                    jobs.append(self.job(s, {"experiment": "quality", "item": it["id"], "rep": 0, "gold": it["gold"]}, it["state"], t))
        return jobs

    # ----- E3 : latence (série, entrelacée) -----
    def jobs_latency(self, tasks, k, reps):
        jobs, rnd = [], random.Random(self.seed + 3)
        for tid in tasks:
            t = self.task(tid)
            its = sorted(self.items(tid, max(k * 3, k)), key=lambda it: len(json.dumps(it["state"], ensure_ascii=False)))
            step = max(1, len(its) // k)
            sel = its[::step][:k]                      # k exemples répartis du plus court au plus long
            for it in sel:
                names = list(self.systems)
                for r in range(reps):
                    rnd.shuffle(names)
                    for s in names:
                        jobs.append(self.job(s, {"experiment": "latency", "item": it["id"], "rep": r, "gold": it["gold"]}, it["state"], t))
        # échauffement : 3 appels par système, exclus de l'analyse
        warm = []
        t0 = self.task(tasks[0])
        it0 = self.items(tasks[0], 3)
        for s in self.systems:
            for i, it in enumerate(it0):
                warm.append(self.job(s, {"experiment": "latency_warmup", "item": it["id"], "rep": i, "gold": it["gold"]}, it["state"], t0))
        # taille d'entrée : un même exemple, de plus en plus de contexte ; tailles et systèmes mélangés à chaque répétition
        size = []
        t1 = self.task("ag_news" if "ag_news" in T.TASKS else tasks[0])
        base_it = self.items(t1.id, 3)[0]
        sizes = (0, 400, 1600, 6400)
        for r in range(max(4, reps)):
            order = [(tok, s) for tok in sizes for s in self.systems]
            rnd.shuffle(order)
            for tok, s in order:
                st = SY.add_noise(t1, base_it["state"], tok, "before", self.seed) if tok else base_it["state"]
                size.append(self.job(s, {"experiment": "latency_size", "item": f"{base_it['id']}@{tok}", "rep": r, "gold": base_it["gold"],
                                         "size_tokens": tok}, st, t1, variant=f"size:{tok}"))
        return warm, jobs, size

    # ----- E4 : débit et limites de cadence -----
    def run_throughput(self, levels, per):
        t = self.task("ag_news")
        it = self.items("ag_news", 5)
        out = []
        for conc in levels:
            n = max(16, conc * per)
            jobs = [self.job("jev", {"experiment": "throughput", "item": f"{it[i % 5]['id']}#c{conc}-{i}", "rep": conc, "gold": it[i % 5]["gold"]},
                             it[i % 5]["state"], t, variant=f"conc:{conc}") for i in range(n)]
            t0 = time.perf_counter()
            stats = self.execute(jobs, workers=conc, shuffle=False, label=f"thr{conc}")
            wall = time.perf_counter() - t0
            recs = [r for r in self.store.read() if r.get("experiment") == "throughput" and r.get("rep") == conc]
            n429 = sum(1 for r in recs for a in r.get("attempts", []) if a.get("status") == 429)
            row = {"experiment": "throughput_batch", "conc": conc, "n": n, "wall_total_s": round(wall, 3), "ok": stats["run"] + stats["already_done"],
                   "failed": stats["failed"], "n_429": n429, "rps": round(n / wall, 2) if wall else None, "ok_flag": True,
                   "task": "ag_news", "item": f"batch-{conc}", "system": "jev", "variant": f"conc:{conc}", "rep": conc}
            if stats["run"] > 0:                # reprise : un palier déjà mesuré n'est pas re-chronométré
                self.store.append(row)
            out.append(row)
            if n and stats["failed"] / n > 0.2:
                break
        return out

    # ----- E5 : facturation -----
    def jobs_billing(self, k):
        """Mêmes questions répétées 1, 2, 4, 8 fois dans une requête : le jeton d'entrée est-il facturé une fois ou N fois ?"""
        t = self.task("ag_news")
        jobs = []
        for it in self.items("ag_news", k):
            for q in (1, 2, 4, 8):
                qs = {f"q{j}": T.spec(t, "base", self.seed) for j in range(q)}
                jobs.append(self.job("jev", {"experiment": "billing", "item": it["id"], "rep": q, "gold": {f"q{j}": it["gold"] for j in range(q)}},
                                     it["state"], t, variant=f"nq:{q}", questions=qs))
        return jobs

    # ----- E6 : robustesse -----
    def jobs_robust(self, tasks, n, with_baselines):
        jobs = []
        for tid in tasks:
            t = self.task(tid)
            for it in self.items(tid, n):
                vs = [("base", it["state"], "base"), ("nodesc", it["state"], "nodesc")]
                if t.primitive == "choice":
                    vs += [(f"shuffle{k}", it["state"], f"shuffle{k}") for k in (1, 2)]
                for name, tokens, where in NOISE_VARIANTS:
                    vs.append((name, SY.add_noise(t, it["state"], tokens, where, self.seed + zlib.crc32(it["id"].encode()) % 1000), "base"))
                for name, st, sv in vs:
                    for s in self.systems:
                        if s != "jev" and not with_baselines:
                            continue
                        jobs.append(self.job(s, {"experiment": "robust", "item": it["id"], "rep": 0, "gold": it["gold"]}, st, t,
                                             variant=name if name.startswith("noise") else sv))
        return jobs

    # ----- E7 : déterminisme -----
    def jobs_determinism(self, tasks, k, reps):
        jobs = []
        for tid in tasks:
            t = self.task(tid)
            for it in self.items(tid, k):
                for r in range(reps):
                    jobs.append(self.job("jev", {"experiment": "determinism", "item": it["id"], "rep": r, "gold": it["gold"]}, it["state"], t))
        return jobs

    # ----- E8 : limites annoncées + sonde de contexte -----
    def jobs_limits(self, n):
        jobs = []
        for tid in SY.SYNTH_IDS:
            t = self.task(tid)
            for it in self.items(tid, n):
                for s in self.systems:
                    jobs.append(self.job(s, {"experiment": "limits", "item": it["id"], "rep": 0, "gold": it["gold"]}, it["state"], t))
        return jobs

    def jobs_probe(self):
        t = self.task("ag_news")
        it = self.items("ag_news", 2)[0]
        return [self.job("jev", {"experiment": "ctx_probe", "item": f"{it['id']}@{tok}", "rep": 0, "gold": it["gold"], "size_tokens": tok},
                         SY.add_noise(t, it["state"], tok, "before", self.seed), t, variant=f"ctx:{tok}") for tok in PROBE_SIZES]

    # ----- E9 : plusieurs questions dans un appel -----
    def jobs_multi(self, n):
        t_s = self.task("sst2")
        t_a = self.task("ag_news")
        jobs = []
        for it in self.items("sst2", n):
            pos = T.spec(t_s, "base", self.seed)
            neg = {"type": "noul", "instructions": "Is the sentiment of this movie review negative?",
                   "criteria": {"true": "The reviewer expresses a negative opinion.", "false": "The reviewer expresses a positive opinion."}}
            ch = {"type": "choice", "instructions": "Is this movie review positive or negative?",
                  "criteria": {"positive": "The reviewer expresses a positive opinion.", "negative": "The reviewer expresses a negative opinion."}}
            g = it["gold"]
            jobs.append(self.job("jev", {"experiment": "multi", "item": it["id"], "rep": 0, "gold": {"pos": g, "neg": not g}}, it["state"], t_s,
                                 variant="pair_noul", questions={"pos": pos, "neg": neg}))
            jobs.append(self.job("jev", {"experiment": "multi", "item": it["id"], "rep": 0, "gold": {"c": "positive" if g else "negative"}}, it["state"], t_s,
                                 variant="one_choice", questions={"c": ch}))
        for it in self.items("ag_news", n):
            a = T.spec(t_a, "base", self.seed)
            b = {"type": "noul", "instructions": "Is this article about sports?", "criteria": {"true": "Sports news.", "false": "Not sports news."}}
            c = {"type": "score", "instructions": "How formal is the language of this article?", "criteria": ["very informal", "informal", "neutral", "formal", "very formal"]}
            jobs.append(self.job("jev", {"experiment": "multi", "item": it["id"], "rep": 0, "gold": {"a": it["gold"]}}, it["state"], t_a,
                                 variant="alone", questions={"a": a}))
            jobs.append(self.job("jev", {"experiment": "multi", "item": it["id"], "rep": 0, "gold": {"a": it["gold"], "b": it["gold"] == "sports", "c": 3}},
                                 it["state"], t_a, variant="joint", questions={"a": a, "b": b, "c": c}))
        return jobs

    # ----- orchestration -----
    def all_jobs(self, suite, with_baselines_robust=False):
        s = SUITES[suite]
        out = {"quality": self.jobs_quality(list(s["tasks"]) + self.custom, s["n"], s["n_base"])}
        if s["latency"]:
            warm, lat, size = self.jobs_latency(**s["latency"])
            out["latency_warmup"], out["latency"], out["latency_size"] = warm, lat, size
        if s["billing"]:
            out["billing"] = self.jobs_billing(**s["billing"])
        if s["robust"]:
            out["robust"] = self.jobs_robust(s["robust"]["tasks"], s["robust"]["n"], with_baselines_robust)
        if s["determinism"]:
            out["determinism"] = self.jobs_determinism(**s["determinism"])
        if s["limits"]:
            out["limits"] = self.jobs_limits(s["limits"]["n"])
            if s["limits"].get("probe"):
                out["ctx_probe"] = self.jobs_probe()
        if s["multi"]:
            out["multi"] = self.jobs_multi(s["multi"]["n"])
        return out

    def plan(self, suite, with_baselines_robust=False):
        """Estimation sans appel : nombre d'appels et coût attendu par expérience et par système."""
        jobs = self.all_jobs(suite, with_baselines_robust)
        rows, total = [], 0.0
        for exp, js in jobs.items():
            by = {}
            for j in js:
                c = by.setdefault(j.system, [0, 0.0])
                c[0] += 1
                c[1] += self.est_cost(j.system, j.est_in, j.est_out)
            rows.append((exp, by))
            total += sum(v[1] for v in by.values())
        if SUITES[suite]["throughput"]:
            n = sum(max(16, c * SUITES[suite]["throughput"]["per"]) for c in SUITES[suite]["throughput"]["levels"])
            rows.append(("throughput", {"jev": [n, n * 300 * self.jev_price / 1e6]}))
            total += n * 300 * self.jev_price / 1e6
        return rows, total

    def run(self, suite, with_baselines_robust=False, log=print):
        s = SUITES[suite]
        all_ = self.all_jobs(suite, with_baselines_robust)
        res = {}
        order = ["latency_warmup", "latency", "latency_size", "quality", "billing", "limits", "ctx_probe", "multi", "determinism", "robust"]
        for exp in order:
            if exp not in all_:
                continue
            w = 1 if exp.startswith("latency") or exp == "ctx_probe" else self.workers
            res[exp] = self.execute(all_[exp], workers=w, shuffle=not exp.startswith("latency") and exp != "ctx_probe", label=exp)
            log(f"[{exp}] {res[exp]}  dépensé {self.budget.spent:.4f} $")
            if res[exp]["budget_stop"]:
                log("plafond de budget atteint : arrêt propre (reprise possible avec le même dossier de run)")
                break
        if s["throughput"] and not self.stop.is_set():
            res["throughput"] = self.run_throughput(**s["throughput"])
            log(f"[throughput] {len(res['throughput'])} paliers  dépensé {self.budget.spent:.4f} $")
        return res
