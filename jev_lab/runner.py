"""Moteur d'expériences, centré sur les appels RÉELS du pipeline hémicycle (voir hemicycle.py).

Un « job » = un appel (une fiche, un système).  On peut donc estimer le coût AVANT de dépenser (`plan`), entrelacer les
systèmes dans un ordre aléatoire (pas de biais d'heure), reprendre après interruption et s'arrêter net au plafond de budget.

Expériences : quality (E1, aussi base des décisions, seuils et calibration), latency (E3), throughput (E4),
robust (E6, catégorie), determinism (E7), multi (E9 : questions seules ou ensemble, comme en production)."""
import json, random, threading, time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable
from pipeline import classify
from . import config as C, client as CL, hemicycle as H
from .budget import Budget, BudgetExceeded, tokens_estimate

SUITES = {
    # smoke : vérifie clé, schéma et chaîne complète pour quelques centimes
    "smoke": dict(scenarios=["categorie", "sens"], cap=20, latency=dict(k=6, reps=1), throughput=None, robust=None, determinism=None, multi=None),
    # standard : tout le jeu d'essai du dépôt (≈ 800 appels par système), toutes les expériences
    "standard": dict(scenarios=H.ORDER, cap=None, latency=dict(k=15, reps=2), throughput=dict(levels=[1, 2, 4, 8], per=8),
                     robust=dict(n=34), determinism=dict(k=20, reps=5), multi=dict(n=30), explo=True),
}


@dataclass
class Job:
    base: dict
    system: str
    est_in: int
    est_out: int
    run: Callable


class Lab:
    def __init__(self, store, budget, jev, baselines, seed=C.SEED, workers=4, mock=False, jev_price=C.CLAIMS["prix_entree_par_M"][0],
                 prices=None, variants_path=None, claude_only=False):
        self.store, self.budget, self.jev, self.baselines = store, budget, jev, baselines
        self.seed, self.workers, self.mock, self.jev_price = seed, workers, mock, jev_price
        self.prices = prices or {}                  # modèle -> (prompt $/token, completion $/token), lu au catalogue
        self.claude_only = claude_only
        self.systems = {**({} if claude_only else {"jev": jev}), **{b.name: b for b in baselines}}
        self.variants_path = variants_path
        self._items = {}
        self.stop = threading.Event()

    # ----- items -----
    def items(self, scenario):
        if scenario not in self._items:
            self._items[scenario] = (H.items_neutralite(H.load_variants(self.variants_path)) if scenario == "neutralite" else H.items(scenario))
        return self._items[scenario]

    def sample(self, scenario, k):
        """k items répartis sur tous les groupes (entrelacés), toujours les mêmes."""
        its = self.items(scenario)
        step = max(1, len(its) // k)
        return its[::step][:k]

    # ----- fabrique de jobs -----
    def est_cost(self, system, est_in, est_out):
        if system == "jev":
            return est_in * self.jev_price / 1e6
        if getattr(self.systems[system], "free", False):
            return 0.0                              # `claude -p` : abonnement, rien de facturé
        pin, pout = self.prices.get(self.systems[system].model, (1e-6, 4e-6))
        return est_in * pin + est_out * pout

    def job(self, system, experiment, scenario, item, qs, variant="base", rep=0, extra=None):
        c = self.systems[system]
        base = {"experiment": experiment, "task": scenario, "scenario": scenario, "item": item["id"], "group": item["group"], "variant": variant,
                "rep": rep, "gold": item["gold"], "meta": item.get("meta"), "model": c.model, **(extra or {})}
        gq = item["gold"].get("q") or {}
        if c.kind == "jev":
            return Job(base, system, tokens_estimate(json.dumps({"s": item["state"], "q": qs}, ensure_ascii=False)), 0,
                       lambda: c.call(base, item["state"], qs, gold=gq))
        prompt = classify.claude_prompt(item["state"], qs)
        return Job(base, system, tokens_estimate(prompt), 600, lambda: c.call(base, prompt, gold=gq))

    # ----- exécution -----
    def execute(self, jobs, workers=None, shuffle=True, label=""):
        done = self.store.done()
        todo = [j for j in jobs if self.store.key(j.base | {"system": j.system}) not in done]
        if shuffle:
            random.Random(f"{self.seed}-{label}").shuffle(todo)       # entrelace les systèmes : pas de biais d'heure
        stats = {"jobs": len(jobs), "already_done": len(jobs) - len(todo), "run": 0, "failed": 0, "budget_stop": False}
        lock = threading.Lock()

        def go(j):
            if self.stop.is_set():
                return
            est = self.est_cost(j.system, j.est_in, j.est_out)
            try:
                self.budget.acquire(est)          # réserve AVANT d'envoyer : plusieurs appels simultanés ne peuvent pas dépasser le plafond
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

    # ----- E1 : qualité (et décisions, seuils, calibration) -----
    def jobs_quality(self, scenarios, cap=None):
        jobs = []
        for sc in scenarios:
            qs = H.questions(sc)
            its = self.items(sc) if cap is None else self.sample(sc, cap)
            for it in its:
                for s in self.systems:
                    jobs.append(self.job(s, "quality", sc, it, qs))
        return jobs

    # ----- E3 : latence (série, entrelacée) -----
    def jobs_latency(self, scenarios, k, reps):
        rnd, jobs, warm = random.Random(self.seed + 3), [], []
        for sc in scenarios:
            qs = H.questions(sc)
            for i, it in enumerate(self.sample(sc, k)):
                for r in range(reps):
                    names = list(self.systems)
                    rnd.shuffle(names)
                    for s in names:
                        jobs.append(self.job(s, "latency", sc, it, qs, rep=r))
            for s in self.systems:        # échauffement exclu de l'analyse
                warm += [self.job(s, "latency_warmup", sc, it, qs, rep=i) for i, it in enumerate(self.sample(sc, 2))]
        return warm, jobs

    # ----- E4 : débit et limites de cadence (Jev seul, appel de production le plus lourd) -----
    def run_throughput(self, levels, per):
        sc = "pro_contre"
        qs = H.questions(sc)
        its = self.sample(sc, 5)
        out = []
        for conc in levels:
            n = max(16, conc * per)
            jobs = [self.job("jev", "throughput", sc, dict(its[i % 5], id=f"{its[i % 5]['id']}#c{conc}-{i}"), qs, variant=f"conc:{conc}", rep=conc) for i in range(n)]
            t0 = time.perf_counter()
            stats = self.execute(jobs, workers=conc, shuffle=False, label=f"thr{conc}")
            wall = time.perf_counter() - t0
            recs = [r for r in self.store.read() if r.get("experiment") == "throughput" and r.get("rep") == conc]
            n429 = sum(1 for r in recs for a in r.get("attempts", []) if a.get("status") == 429)
            row = {"experiment": "throughput_batch", "conc": conc, "n": n, "wall_total_s": round(wall, 3), "ok": stats["run"] + stats["already_done"],
                   "failed": stats["failed"], "n_429": n429, "rps": round(n / wall, 2) if wall else None, "task": sc, "item": f"batch-{conc}",
                   "system": "jev", "variant": f"conc:{conc}", "rep": conc, "ok_flag": True}
            if stats["run"] > 0:                # reprise : un palier déjà mesuré n'est pas re-chronométré
                self.store.append(row)
            out.append(row)
            if n and stats["failed"] / n > 0.2:
                break
        return out

    # ----- E6 : robustesse de la catégorie (consigne sans descriptions, ordre des options permuté) -----
    def jobs_robust(self, n, with_baselines=False):
        jobs = []
        for it in self.sample("categorie", n):
            for variant in ("base", "nodesc", "shuffle1", "shuffle2"):
                qs = H.questions("categorie", variant)
                for s in self.systems:
                    if s != "jev" and not with_baselines:
                        continue
                    jobs.append(self.job(s, "robust", "categorie", it, qs, variant=variant))
        return jobs

    # ----- E7 : déterminisme (même appel répété ; ce qui compte : la DÉCISION change-t-elle ?) -----
    def jobs_determinism(self, k, reps):
        jobs = []
        for sc in H.ORDER:
            qs = H.questions(sc)
            for it in self.sample(sc, k):
                jobs += [self.job("jev", "determinism", sc, it, qs, rep=r) for r in range(reps)]
        return jobs

    # ----- E9 : les questions d'un appel de production, posées seules ou ensemble -----
    def jobs_multi(self, n):
        jobs = []
        for sc in ("neutralite", "pro_contre"):
            qs = H.questions(sc)
            for it in self.sample(sc, n):
                for name in qs:
                    jobs.append(self.job("jev", "multi", sc, it, {name: qs[name]}, variant=f"alone:{name}"))
        return jobs

    # ----- piste exploratoire : le sens du vote lu dans le TITRE SEUL (sans le libellé des boutons) -----
    def jobs_explo_sens(self, n=None):
        """Imaginée après le premier run : Jev semble suivre le libellé du bouton plus que le titre. On lui pose la seule question de sens,
        sur le titre, puis on compare au sens annoncé. Même jeu d'essai que le scénario « sens » ; Jev seul (rien à comparer côté Claude)."""
        qs = {"sens": H.questions("sens")["sens"]}
        jobs = []
        for it in (self.items("sens") if n is None else self.sample("sens", n)):
            titre = it["state"].get("titre_officiel_du_scrutin")
            jobs.append(self.job("jev", "explo_sens", "sens", dict(it, state={"titre_officiel_du_scrutin": titre}), qs, variant="titre_seul"))
        return jobs

    # ----- orchestration -----
    def all_jobs(self, suite, with_baselines_robust=False):
        s = SUITES[suite]
        out = {"quality": self.jobs_quality(s["scenarios"], s["cap"])}
        if self.claude_only:        # latence, débit, déterminisme, robustesse, « seules ou ensemble » : propres à Jev, faits dans le workflow
            return out
        if s["latency"]:
            out["latency_warmup"], out["latency"] = self.jobs_latency(s["scenarios"], **s["latency"])
        if s["robust"] and "categorie" in s["scenarios"]:
            out["robust"] = self.jobs_robust(s["robust"]["n"], with_baselines_robust)
        if "sens" in s["scenarios"] and s.get("explo"):
            out["explo_sens"] = self.jobs_explo_sens()
        if s["determinism"]:
            out["determinism"] = self.jobs_determinism(**s["determinism"])
        if s["multi"]:
            out["multi"] = self.jobs_multi(**s["multi"])
        return out

    def plan(self, suite, with_baselines_robust=False):
        """Estimation sans appel : nombre d'appels et coût attendu par expérience et par système."""
        rows, total = [], 0.0
        for exp, js in self.all_jobs(suite, with_baselines_robust).items():
            by = {}
            for j in js:
                c = by.setdefault(j.system, [0, 0.0])
                c[0] += 1
                c[1] += self.est_cost(j.system, j.est_in, j.est_out)
            rows.append((exp, by))
            total += sum(v[1] for v in by.values())
        if SUITES[suite]["throughput"] and not self.claude_only:
            n = sum(max(16, c * SUITES[suite]["throughput"]["per"]) for c in SUITES[suite]["throughput"]["levels"])
            est = n * 1100 * self.jev_price / 1e6
            rows.append(("throughput", {"jev": [n, est]}))
            total += est
        return rows, total

    def run(self, suite, with_baselines_robust=False, log=print):
        s = SUITES[suite]
        all_ = self.all_jobs(suite, with_baselines_robust)
        res = {}
        for exp in ["latency_warmup", "latency", "quality", "multi", "determinism", "robust", "explo_sens"]:
            if exp not in all_:
                continue
            w = 1 if exp.startswith("latency") else self.workers
            res[exp] = self.execute(all_[exp], workers=w, shuffle=not exp.startswith("latency"), label=exp)
            log(f"[{exp}] {res[exp]}  dépensé {self.budget.spent:.4f} $")
            if res[exp]["budget_stop"]:
                log("plafond de budget atteint : arrêt propre (reprise possible avec le même dossier de run)")
                break
        if s["throughput"] and not self.stop.is_set() and not self.claude_only:
            res["throughput"] = self.run_throughput(**s["throughput"])
            log(f"[throughput] {len(res['throughput'])} paliers  dépensé {self.budget.spent:.4f} $")
        return res
