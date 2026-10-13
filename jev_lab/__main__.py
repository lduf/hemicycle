"""Ligne de commande : python -m jev_lab <commande>

  ping                 un appel à Jev (et aux références) : vérifie clé, schéma de réponse, usage, coût.  À lancer en premier.
  models               catalogue OpenRouter et familles de modèles de comparaison résolues.
  plan   --suite S     nombre d'appels et coût estimé, sans rien dépenser.
  run    --suite S     lance (ou reprend) une étude.
  report RUN           (re)génère REPORT.md depuis le journal brut.
  inspect RUN          parcourt les réponses (erreurs, appels échoués).
  demo                 chaîne complète contre un serveur factice (DONNÉES SIMULÉES, gratuit).
"""
import argparse, json, os, sys, time
from . import datasets as D, config as C, client as CL, runner as R, store as ST, budget as B, analysis as A, report as RP, tasks as T


def need_key():
    if not CL.api_key():
        sys.exit("OPENROUTER_API_KEY absente (export OPENROUTER_API_KEY=... ou secret GitHub). Jamais dans un fichier du dépôt.")


def build_lab(a, store, mock=False):
    cat = CL.catalog()
    prices = {m["id"]: (m["prompt"], m["completion"]) for m in cat}
    baselines, resolved = [], {}
    wanted = [x for x in (a.baselines or "").split(",") if x]
    fams = CL.resolve_patterns(cat)
    for w in wanted:
        if "/" in w:
            mid, label = w, w
        elif w in fams:
            mid, label = fams[w]["id"], f"{w} ({fams[w]['id']})"
        else:
            sys.exit(f"famille inconnue ou introuvable au catalogue : {w}.  Familles : {', '.join(C.BASELINE_PATTERNS)} ; ou un identifiant exact « fournisseur/modèle ».")
        if mid not in prices:
            sys.exit(f"modèle absent du catalogue OpenRouter : {mid}")
        resolved[label] = mid
        baselines.append(CL.ChatClient(mid, label=label, mock_gold=mock))
    # le plafond vaut pour le RUN ENTIER : ce qui a déjà été dépensé dans les sessions précédentes est déduit
    spent0 = sum((r.get("usage") or {}).get("cost") or 0.0 for r in store.read())
    lab = R.Lab(store, B.Budget(a.budget, spent0), CL.JevClient(a.jev_model, mock_gold=mock), baselines, workers=a.workers, mock=mock, prices=prices)
    for path in (getattr(a, "custom", None) or []):
        lab.custom.append(T.load_custom(path).id)
    return lab, resolved


def cmd_ping(a):
    need_key()
    j = CL.JevClient(a.jev_model)
    state = {"ticket": "Ma page de paiement reste blanche après le clic sur Payer."}
    qs = {"is_bug": {"type": "noul", "instructions": "Is the customer reporting a software defect?",
                     "criteria": {"true": "The customer describes broken product behavior.", "false": "The customer asks a question or requests a feature."}},
          "team": {"type": "choice", "instructions": "Which team should own this ticket?",
                   "criteria": {"payments": "Checkout and payment issues.", "frontend": "Rendering and browser issues.", "account": "Login and profile issues."}},
          "urgency": {"type": "score", "instructions": "How urgent is this ticket?", "criteria": ["Can wait", "This week", "Blocking revenue now"]}}
    rec = j.call({"experiment": "ping", "task": "ping", "item": "ping", "rep": 0, "variant": "base", "gold": None}, state, qs)
    print(json.dumps({k: rec.get(k) for k in ("ok", "status", "wall_s", "n_attempts", "usage", "resolved_model", "headers", "error", "error_text")}, ensure_ascii=False, indent=1))
    print(json.dumps(rec.get("response"), ensure_ascii=False, indent=1))
    ok = rec["ok"]
    if ok:
        ans = rec["response"].get("answers", {})
        exp = {"is_bug": ("noul",), "team": ("choice", "confidence", "probabilities"), "urgency": ("score", "confidence", "probabilities")}
        for k, fields in exp.items():
            miss = [f for f in fields if f not in (ans.get(k) or {})]
            if miss:
                ok = False
                print(f"⚠ schéma inattendu pour {k} : champs absents {miss}")
        pk = set((ans.get("urgency") or {}).get("probabilities") or {})
        if pk != {"0", "1", "2"}:
            ok = False
            print(f"⚠ indexation des niveaux de score inattendue : clés {sorted(pk)} (attendu 0, 1, 2) — l'étude lirait des niveaux décalés")
        print("→ schéma conforme à la documentation" if ok else "→ ÉCART avec la documentation : à examiner avant de lancer l'étude")
    for b in (a.baselines or "").split(","):
        if b:
            lab, res = build_lab(a, ST.RunStore(os.path.join(C.RUNS, "_ping")))
            c = lab.baselines[0]
            r = c.call({"experiment": "ping", "task": "ping", "item": "ping", "rep": 0, "variant": "base", "gold": None}, 'Réponds {"ok": true}')
            print(c.name, r.get("ok"), r.get("wall_s"), r.get("usage"), "finish_reason=", r.get("finish_reason"), (r.get("text") or r.get("error_text") or r.get("error") or "")[:120])
            break
    sys.exit(0 if ok else 1)


def cmd_models(a):
    cat = CL.catalog()
    print(f"{len(cat)} modèles au catalogue")
    jev = [m for m in cat if "jev" in m["id"].lower()]
    print("Jev :", [(m["id"], m["prompt"], m["context"]) for m in jev] or "absent du catalogue (l'API Decisions n'est pas forcément listée)")
    for fam, m in CL.resolve_patterns(cat).items():
        print(f"{fam:14} -> {m['id']}   entrée {m['prompt'] * 1e6:.2f} $/M  sortie {m['completion'] * 1e6:.2f} $/M")


def cmd_plan(a):
    st = ST.RunStore(os.path.join(C.RUNS, "_plan"))
    lab, _ = build_lab(a, st)
    lab.offline_estimate = True
    D.TRIES = 2
    rows, total = lab.plan(a.suite, a.robust_baselines)
    if lab.estimated_tasks:
        print(f"⚠ jeux injoignables, taille moyenne supposée pour : {', '.join(sorted(lab.estimated_tasks))} (estimation hors ligne, ±30 %)")
    print(f"Suite {a.suite} — estimation (jetons estimés à 3,6 caractères ; sortie des modèles de chat estimée à 25 tokens)\n")
    for exp, by in rows:
        print(f"  {exp:16}" + "   ".join(f"{s}: {n} appels ≈ {c:.4f} $" for s, (n, c) in by.items()))
    print(f"\nTOTAL estimé ≈ {total:.2f} $   (plafond demandé : {a.budget} $)")


def cmd_run(a, mock=False):
    if not mock:
        need_key()
    run_dir = os.path.join(C.RUNS, a.run or time.strftime("%Y%m%d-%H%M%S"))
    st = ST.RunStore(run_dir)
    lab, resolved = build_lab(a, st, mock=mock)
    rows, total = lab.plan(a.suite, a.robust_baselines)
    print(f"Dossier du run : {run_dir}\nCoût estimé ≈ {total:.2f} $ (plafond {a.budget} $)")
    if total > a.budget * 1.2 and not a.yes:
        sys.exit("L'estimation dépasse sensiblement le plafond : réduire la suite/les références, relever --budget, ou --yes pour s'arrêter au plafond.")
    prev = st.meta()
    kw = {}
    if "credits_start" not in prev:           # le point de départ des crédits n'est fixé qu'une fois : une reprise ne le réécrit pas
        kw["credits_start"] = None if mock else CL.credits()
    used = [t for t in list(R.SUITES[a.suite]["tasks"]) + lab.custom]
    st.write_meta(suite=a.suite, jev_model=lab.jev.model, baselines=resolved, budget=a.budget, mock=mock, seed=lab.seed, sessions=prev.get("sessions", 0) + 1,
                  robust_baselines=a.robust_baselines, **kw,
                  task_options={t: T.TASKS[t].options for t in used if t in T.TASKS and T.TASKS[t].primitive == "choice" and T.TASKS[t].options},
                  custom_tasks={t: {"title": T.TASKS[t].title, "primitive": T.TASKS[t].primitive, "instructions": T.TASKS[t].instructions,
                                    "options": T.TASKS[t].options, "text_key": T.TASKS[t].text_key, "lang": T.TASKS[t].lang} for t in lab.custom},
                  dropped=dict(T.DROPPED))
    res = lab.run(a.suite, a.robust_baselines)
    if not mock:
        st.write_meta(credits_end=CL.credits(), dropped=dict(T.DROPPED))
    print(json.dumps({k: v for k, v in res.items() if k != "throughput"}, ensure_ascii=False))
    cmd_report(argparse.Namespace(run=run_dir))


def cmd_report(a):
    path = a.run if os.path.isdir(a.run) else os.path.join(C.RUNS, a.run)
    st = ST.RunStore(path)
    Rr = A.run(st)
    RP.build(Rr, path)
    print(f"→ {os.path.join(path, 'REPORT.md')}")


def cmd_inspect(a):
    path = a.run if os.path.isdir(a.run) else os.path.join(C.RUNS, a.run)
    store = ST.RunStore(path)
    A.apply_meta(store.meta())
    rows = A.tidy(store.read())
    sel = [r for r in rows if (not a.task or r["task"] == a.task) and (not a.system or r["system"] == a.system)]
    if a.failed:
        sel = [r for r in sel if not r["ok"]]
    elif a.errors:
        sel = [r for r in sel if r["valid"] and not r["correct"]]
    for r in sel[: a.limit]:
        print(json.dumps({k: r[k] for k in ("experiment", "task", "item", "system", "variant", "gold", "pred", "conf", "p_yes", "wall_s", "status", "error")}, ensure_ascii=False))


def cmd_demo(a):
    from . import mock
    os.environ["JEVLAB_FIXTURES"] = "1"
    os.environ.setdefault("OPENROUTER_API_KEY", "demo-key-not-real")
    srv, S, url = mock.start(scenario=True, max_inflight=12)
    C.set_base(url)
    a.baselines, a.budget, a.run, a.yes, a.robust_baselines = "claude-petit,claude-grand", 50.0, "demo", True, True
    import shutil
    shutil.rmtree(os.path.join(C.RUNS, "demo"), ignore_errors=True)
    cmd_run(a, mock=True)
    srv.shutdown()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jev_lab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def common(p):
        p.add_argument("--baselines", default="", help="familles (claude-petit,claude-grand,gpt-petit,gemini-flash) ou identifiants exacts, séparés par des virgules")
        p.add_argument("--budget", type=float, default=5.0, help="plafond de dépense en $ (arrêt net)")
        p.add_argument("--workers", type=int, default=4)
        p.add_argument("--jev-model", default=C.JEV_MODEL)
        p.add_argument("--custom", action="append", help="fichier JSONL d'une tâche à vous (voir README) ; répétable")
        p.add_argument("--robust-baselines", action="store_true", help="rejouer aussi les références sur les tests de robustesse (coûteux)")
    for name in ("ping", "models", "plan", "run", "demo"):
        p = sub.add_parser(name)
        common(p)
        if name == "demo":
            p.add_argument("--suite", choices=list(R.SUITES), default="standard")
        if name in ("plan", "run"):
            p.add_argument("--suite", choices=list(R.SUITES), default="smoke")
        if name == "run":
            p.add_argument("--run", default=None, help="nom du dossier de run (le réutiliser pour reprendre)")
            p.add_argument("--yes", action="store_true")
    p = sub.add_parser("report"); p.add_argument("run")
    p = sub.add_parser("inspect"); p.add_argument("run"); p.add_argument("--task"); p.add_argument("--system"); p.add_argument("--errors", action="store_true")
    p.add_argument("--failed", action="store_true"); p.add_argument("--limit", type=int, default=30)
    a = ap.parse_args(argv)
    {"ping": cmd_ping, "models": cmd_models, "plan": cmd_plan, "run": cmd_run, "report": cmd_report, "inspect": cmd_inspect, "demo": cmd_demo}[a.cmd](a)


if __name__ == "__main__":
    main()
