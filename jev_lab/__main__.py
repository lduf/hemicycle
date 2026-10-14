"""Ligne de commande : python -m jev_lab <commande>      (étude de Jev sur les usages réels du pipeline hémicycle)

  ping                 un appel à Jev (et aux références) : vérifie clé, schéma de réponse, usage, coût.  À lancer en premier.
  models               catalogue OpenRouter et modèles de comparaison résolus.
  gen-variants         réécrit les fiches (orientées pour / contre / cadrage léger) pour tester la détection de biais ; à relire, à committer.
  items                décrit le jeu d'essai tiré du dépôt (aucun appel).
  show-variants        affiche quelques réécritures générées, pour les relire (la vérité terrain de la neutralité en dépend).
  label-sheet          écrit la liste des fiches à étiqueter à la main (catégories) : c'est ce qui donnera du poids à la mesure de la catégorie.
  plan   --suite S     nombre d'appels et coût estimé, sans rien dépenser.
  run    --suite S     lance (ou reprend) l'étude.
  report RUN           (re)génère REPORT.md depuis le journal brut.
  inspect RUN          parcourt les appels (échecs, fausses acceptations...).
  demo                 chaîne complète contre un serveur factice (DONNÉES SIMULÉES, gratuit).
"""
import argparse, json, os, sys, time
from . import config as C, client as CL, runner as R, store as ST, budget as B, analysis as A, report as RP, hemicycle as H


def need_key():
    if not CL.api_key():
        sys.exit("OPENROUTER_API_KEY absente (export OPENROUTER_API_KEY=... ou secret GitHub). Jamais dans un fichier du dépôt.")


def build_lab(a, store, mock=False, variants_path=None):
    wanted = [x for x in (a.baselines or "").split(",") if x]
    cat = CL.catalog() if any(not w.startswith("cli:") for w in wanted) else []
    prices = {m["id"]: (m["prompt"], m["completion"]) for m in cat}
    baselines, resolved = [], {}
    fams = CL.resolve_patterns(cat) if cat else {}
    for w in [x for x in (a.baselines or "").split(",") if x]:
        if w.startswith("cli:"):                # Claude via `claude -p` (abonnement), jamais via OpenRouter
            c = CL.CliClient(w[4:])
            resolved[c.name] = c.model
            baselines.append(c)
            continue
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
    lab = R.Lab(store, B.Budget(a.budget, spent0), CL.JevClient(a.jev_model, mock_gold=mock), baselines, workers=a.workers, mock=mock, prices=prices,
                variants_path=variants_path, claude_only=getattr(a, "claude_only", False))
    return lab, resolved


def cmd_ping(a):
    need_key()
    j = CL.JevClient(a.jev_model)
    it = H.items_pro_contre()[0]
    qs = H.questions("pro_contre")
    rec = j.call({"experiment": "ping", "task": "pro_contre", "item": "ping", "rep": 0, "variant": "base", "gold": None}, it["state"], qs)
    print(json.dumps({k: rec.get(k) for k in ("ok", "status", "wall_s", "n_attempts", "usage", "resolved_model", "headers", "error", "error_text")}, ensure_ascii=False, indent=1))
    print(json.dumps(rec.get("response"), ensure_ascii=False, indent=1))
    ok = rec["ok"]
    if ok:
        ans = rec["response"].get("answers", {})
        norm = H.normalize(qs, ans)
        if norm is None:
            ok = False
            print("⚠ la réponse ne respecte pas le format attendu par le pipeline (answers/type/noul/score) : le pipeline refuserait toutes les fiches")
        else:
            pk = set((ans.get("equilibre") or {}).get("probabilities") or {})
            if pk and pk != {"0", "1", "2"}:
                ok = False
                print(f"⚠ indexation des niveaux de score inattendue : clés {sorted(pk)} (attendu 0, 1, 2) — les notes seraient décalées")
        print("→ format conforme à ce que lit le pipeline" if ok else "→ ÉCART : à examiner avant de lancer l'étude (le pipeline échoue fermé dans ce cas)")
    for b in [x for x in (a.baselines or "").split(",") if x]:
        lab, _ = build_lab(a, ST.RunStore(os.path.join(C.RUNS, "_ping")))
        c = lab.baselines[0]
        from pipeline import classify
        r = c.call({"experiment": "ping", "task": "pro_contre", "item": "ping", "rep": 0, "variant": "base", "gold": None}, classify.claude_prompt(it["state"], qs))
        print(c.name, r.get("ok"), r.get("wall_s"), r.get("usage"), "finish_reason=", r.get("finish_reason"),
              "lisible par le pipeline :", H.chat_answers(qs, r.get("text")) is not None, (r.get("error") or "")[:100])
        break
    sys.exit(0 if ok else 1)


def cmd_models(a):
    cat = CL.catalog()
    print(f"{len(cat)} modèles au catalogue")
    print("Jev :", [(m["id"], m["prompt"], m["context"]) for m in cat if "jev" in m["id"].lower()] or "absent du catalogue (l'API Decisions n'est pas forcément listée)")
    for fam, m in CL.resolve_patterns(cat).items():
        print(f"{fam:14} -> {m['id']}   entrée {m['prompt'] * 1e6:.2f} $/M  sortie {m['completion'] * 1e6:.2f} $/M")


def cmd_items(a):
    var = H.load_variants()
    for sc in H.ORDER:
        its = H.items_neutralite(var) if sc == "neutralite" else H.items(sc)
        groups = {}
        for i in its:
            groups[i["group"]] = groups.get(i["group"], 0) + 1
        print(f"{sc:11} {len(its):4} items  {groups}")
        print(f"            {H.SCENARIOS[sc]}")
    print(f"\nvariantes de neutralité en cache : {len(var)} fiches ({H.VARIANTS_PATH})" if var else
          "\nvariantes de neutralité : AUCUNE (lancer `gen-variants` ; sans elles, le scénario neutralité n'a pas de cas orientés)")


def cmd_show_variants(a):
    var = H.load_variants()
    fs = {str(q["n"]): q for q in H.fiches_pro_con()}
    if not var:
        sys.exit("aucune variante : lancer `gen-variants`")
    for n in list(var)[: a.limit]:
        q = fs.get(n)
        if not q:
            continue
        print(f"=== fiche {n} : {q['title']}\n  ORIGINE : {q['sum'][:220]}")
        for k in H.SLANTS:
            v = (var[n] or {}).get(k)
            if v:
                print(f"  {k.upper():7}: {str(v.get('sum'))[:220]}")


def cmd_label_sheet(a):
    from pipeline import store as HS
    os.makedirs(H.GOLD_DIR, exist_ok=True)
    path = os.path.join(H.GOLD_DIR, "categories_a_etiqueter.jsonl")
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for q in HS.all_questions():
            if q.get("status") in ("pending_review", "published") and q.get("sum") and q.get("label"):
                fh.write(json.dumps({"n": q["n"], "title": q["title"], "label": q["label"], "sum": q["sum"], "cat_actuelle": q.get("cat"), "cat": ""}, ensure_ascii=False) + "\n")
                n += 1
    print(f"{n} fiches à étiqueter → {path}\nRemplir le champ \"cat\" (une des {len(__import__('pipeline.config', fromlist=['CATS']).CATS)} catégories), "
          f"supprimer les lignes vides, puis renommer en categories.jsonl : elles entrent dans le jeu d'essai de la catégorie (groupe « humain »).")


def cmd_gen_variants(a, mock=False, path=None):
    """Réécriture des fiches par un modèle de langage.  Le résultat est un jeu d'essai : à relire par un humain (voir `show`) avant de s'y fier.
    `--gen-model cli:claude-sonnet-5-5` : par `claude -p` (abonnement, rien de facturé) ; sinon un modèle OpenRouter (clé requise)."""
    from concurrent.futures import ThreadPoolExecutor
    gm = a.gen_model or ("" if mock else None)
    if not gm and not mock:
        sys.exit("--gen-model requis : « cli:claude-sonnet-5-5 » (claude -p) ou un identifiant OpenRouter (voir `models`)")
    if mock:
        client, mid = CL.ChatClient(gm or "anthropic/claude-opus-5", mock_gold=False, max_tokens=2000), gm or "mock"
    elif gm.startswith("cli:"):
        client = CL.CliClient(gm[4:])
        mid = f"{gm[4:]} (claude -p)"
    else:
        need_key()
        cat = CL.catalog()
        fams = CL.resolve_patterns(cat)
        mid = fams[gm]["id"] if gm in fams else gm
        if mid not in {m["id"] for m in cat}:
            sys.exit(f"modèle de réécriture absent du catalogue : {mid}")
        client = CL.ChatClient(mid, mock_gold=False, max_tokens=4000)
    path = path or H.VARIANTS_PATH
    out = H.load_variants(path)
    jobs = [(q, k) for q in H.fiches_pro_con() for k in H.SLANTS if k not in (out.get(str(q["n"])) or {})]
    n = 0

    def one(job):
        q, k = job
        rec = client.call({"experiment": "gen", "task": "neutralite", "item": f"{q['n']}-{k}", "rep": 0, "variant": k, "gold": None}, H.variant_prompt(q, k))
        r = H.json_in(rec.get("text")) if rec.get("ok") else None
        return q, k, r

    with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
        for q, k, r in ex.map(one, jobs):
            if isinstance(r, dict) and all(f in r for f in ("sum", "pro", "con")):
                out.setdefault(str(q["n"]), {})[k] = {f: r.get(f) or q.get(f) for f in H.FIELDS}
                n += 1
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(f"{n}/{len(jobs)} variantes écrites dans {path} (générées par {mid}) — à relire avant de s'y fier ; `git add` pour le rendre reproductible")


def cmd_artifact(a):
    from . import artifact
    print(artifact.build(a.run, a.out))
    if a.site:
        with open(a.site, "w", encoding="utf-8") as fh:
            json.dump(artifact.site_summary(a.run, a.rapport_url) or {}, fh, ensure_ascii=False, indent=1)
        print(a.site)


def cmd_plan(a):
    st = ST.RunStore(os.path.join(C.RUNS, "_plan"))
    lab, _ = build_lab(a, st)
    rows, total = lab.plan(a.suite, a.robust_baselines)
    print(f"Suite {a.suite} — estimation (jetons estimés à 3,6 caractères ; sortie des modèles de chat estimée à 600 tokens par appel)\n")
    for exp, by in rows:
        print(f"  {exp:16}" + "   ".join(f"{s}: {n} appels ≈ {c:.4f} $" for s, (n, c) in by.items()))
    print(f"\nTOTAL estimé ≈ {total:.2f} $   (plafond demandé : {a.budget} $)")


def cmd_run(a, mock=False, variants_path=None):
    if not mock and not a.claude_only:
        need_key()
    run_dir = os.path.join(C.RUNS, a.run or time.strftime("%Y%m%d-%H%M%S"))
    st = ST.RunStore(run_dir)
    lab, resolved = build_lab(a, st, mock=mock, variants_path=variants_path)
    rows, total = lab.plan(a.suite, a.robust_baselines)
    print(f"Dossier du run : {run_dir}\nCoût estimé ≈ {total:.2f} $ (plafond {a.budget} $)")
    if total > a.budget * 1.2 and not a.yes:
        sys.exit("L'estimation dépasse sensiblement le plafond : réduire la suite/les références, relever --budget, ou --yes pour s'arrêter au plafond.")
    prev = st.meta()
    kw = {}
    if "credits_start" not in prev and not a.claude_only:           # le point de départ des crédits n'est fixé qu'une fois : une reprise ne le réécrit pas
        kw["credits_start"] = None if mock else CL.credits()
    from pipeline import classify, config as HC
    resolved = {**(prev.get("baselines") or {}), **resolved}        # la passe Claude (locale) s'ajoute à celle de Jev (Actions)
    if a.claude_only:
        kw["claude_pass"] = True
    st.write_meta(suite=a.suite, jev_model=lab.jev.model, baselines=resolved, budget=a.budget, mock=mock, seed=lab.seed, sessions=prev.get("sessions", 0) + 1,
                  robust_baselines=a.robust_baselines, **kw, thresholds=dict(classify.THRESHOLDS, neutralite_max=HC.NEUTRALITY_MAX),
                  n_items={sc: len(lab.items(sc)) for sc in R.SUITES[a.suite]["scenarios"]})
    res = lab.run(a.suite, a.robust_baselines)
    if not mock and not a.claude_only:
        st.write_meta(credits_end=CL.credits())
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
    rows = A.tidy(ST.RunStore(path).read())
    sel = [r for r in rows if (not a.scenario or r["scenario"] == a.scenario) and (not a.system or r["system"] == a.system)]
    if a.failed:
        sel = [r for r in sel if not r["ok"]]
    elif a.errors:
        sel = [r for r in sel if r["valid"] and r["gold"].get("accept") is not None and r["accept"] != r["gold"]["accept"]]
    for r in sel[: a.limit]:
        print(json.dumps({k: r[k] for k in ("experiment", "scenario", "item", "group", "system", "variant", "accept", "valid", "verdict", "wall_s", "status", "error")}, ensure_ascii=False))


def cmd_demo(a):
    from . import mock
    import shutil, tempfile
    os.environ.setdefault("OPENROUTER_API_KEY", "demo-key-not-real")
    srv, S, url = mock.start(max_inflight=12)
    C.set_base(url)
    a.baselines, a.budget, a.run, a.yes, a.robust_baselines = "claude-petit,claude-grand", 50.0, "demo", True, True
    shutil.rmtree(os.path.join(C.RUNS, "demo"), ignore_errors=True)
    tmp = tempfile.mkdtemp()
    vp = os.path.join(tmp, "variantes.json")                 # les variantes de la démonstration ne touchent pas au dépôt
    a.gen_model = "anthropic/claude-opus-5"
    cmd_gen_variants(a, mock=True, path=vp)
    cmd_run(a, mock=True, variants_path=vp)
    srv.shutdown()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jev_lab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--baselines", default="", help="références : « cli:claude-sonnet-5-5 » (Claude via `claude -p`, abonnement) ou familles OpenRouter (claude-petit,claude-grand,gpt-petit,gemini-flash) ou identifiants exacts, séparés par des virgules")
        p.add_argument("--budget", type=float, default=5.0, help="plafond de dépense en $ pour le run entier (arrêt net)")
        p.add_argument("--workers", type=int, default=4)
        p.add_argument("--jev-model", default=C.JEV_MODEL)
        p.add_argument("--robust-baselines", action="store_true", help="rejouer aussi les références sur les tests de robustesse (coûteux)")
    for name in ("ping", "models", "items", "show-variants", "label-sheet", "gen-variants", "plan", "run", "demo"):
        p = sub.add_parser(name)
        common(p)
        if name in ("plan", "run", "demo"):
            p.add_argument("--suite", choices=list(R.SUITES), default="standard" if name == "demo" else "smoke")
        if name == "show-variants":
            p.add_argument("--limit", type=int, default=3)
        if name == "gen-variants":
            p.add_argument("--gen-model", default=None, help="modèle de réécriture : famille (claude-grand) ou identifiant exact")
        if name == "run":
            p.add_argument("--run", default=None, help="nom du dossier de run (le réutiliser pour reprendre)")
            p.add_argument("--yes", action="store_true")
            p.add_argument("--claude-only", action="store_true", help="ne rejouer que les références (`cli:...`) sur un dossier de run déjà rempli par Jev : aucune clé OpenRouter, aucun appel Jev")
    p = sub.add_parser("report"); p.add_argument("run")
    p = sub.add_parser("artifact"); p.add_argument("run"); p.add_argument("--out")
    p.add_argument("--site", help="écrit aussi le résumé pour la page Méthode du site (ex. content/jev_summary.json)"); p.add_argument("--rapport-url")
    p = sub.add_parser("inspect"); p.add_argument("run"); p.add_argument("--scenario"); p.add_argument("--system"); p.add_argument("--errors", action="store_true")
    p.add_argument("--failed", action="store_true"); p.add_argument("--limit", type=int, default=30)
    a = ap.parse_args(argv)
    {"ping": cmd_ping, "models": cmd_models, "items": cmd_items, "show-variants": cmd_show_variants, "label-sheet": cmd_label_sheet, "gen-variants": cmd_gen_variants, "plan": cmd_plan, "run": cmd_run, "report": cmd_report, "artifact": cmd_artifact,
     "inspect": cmd_inspect, "demo": cmd_demo}[a.cmd](a)


if __name__ == "__main__":
    main()
