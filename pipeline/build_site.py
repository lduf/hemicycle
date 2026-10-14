"""Étape 7 : site statique régénéré chaque nuit à partir de JSON. Page HTML autonome, sans compte, aucune donnée stockée.

Quelles fiches sont publiées ?
  published       -> oui, « relue »
  legacy          -> oui, balisée « non relue » (MVP)
  pending_review  -> oui, balisée « non relue » si include_pending (défaut), car les contrôles automatiques sont passés
  draft/blocked/rejected -> jamais

Pool du quiz : si content/curated.json existe (sélection transparente, voir pipeline/curate.py), seules les fiches dont le
numéro de vote figure dans `items[].vote` sont proposées ; les autres restent en base mais hors quiz. Sans ce fichier, repli
explicite : toutes les fiches publiables sont proposées, et la page Méthode le dit (`method.curated == False`).
"""
import json, os, re, datetime as dt, shutil
from . import config as C, store, seatmap, promises, direction


def _js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def curated_path():
    return os.path.join(C.CONTENT, "curated.json")


def jev_summary_path():
    return os.path.join(C.CONTENT, "jev_summary.json")


def load_curated(path=None):
    """content/curated.json -> dict, ou None s'il est absent ou inutilisable (repli explicite, jamais d'exception)."""
    try:
        cur = C.jload(path or curated_path())
        if not isinstance(cur, dict) or not isinstance(cur.get("items"), list):
            return None
        for it in cur["items"]:
            int(it["vote"])
    except (KeyError, TypeError, ValueError, OSError):
        print("[build] curated.json illisible : repli sur toutes les fiches publiables")
        return None
    return cur


def curated_items(cur):
    """{numéro de vote: item} de la sélection transparente."""
    return {int(it["vote"]): it for it in (cur or {}).get("items", [])}


def select_questions(include_pending=True, include_legacy=True, curated=None):
    """Fiches proposées dans le quiz. `curated` (dict de load_curated) restreint le pool ; None = repli, toutes les fiches publiables."""
    ok = {"published"} | ({"pending_review"} if include_pending else set()) | ({"legacy"} if include_legacy else set())
    qs = [q for q in store.all_questions() if q["status"] in ok]
    if curated:
        keep = curated_items(curated)
        qs = [q for q in qs if int(q["n"]) in keep]
    return qs


def make_data(questions, scrutins, seats, curated=None):
    items = curated_items(curated)
    qs = []
    for q in questions:
        s = scrutins[str(q["n"])]
        g = {k: v[:4] for k, v in s["g"].items() if k in C.SCORED or k == "NI"}
        # `bloc` (origine du texte) sert au tirage seulement : le template ne l'affiche jamais pendant le quiz.
        bloc = (items.get(int(q["n"])) or {}).get("bloc") or "autre"
        qs.append(dict(n=q["n"], kind=q.get("kind", "mesure"), cat=q["cat"], title=q["title"], sum=q["sum"], pro=q["pro"], con=q["con"],
                       date=s["date"], sort=s["sort"], tot=s["tot"], g=g, seats=seats[q["n"]][0], reviewed=q["status"] == "published",
                       bloc=bloc, pol=q.get("polarity") or "adopt"))
    cats = [c for c in C.CATS if any(x["cat"] == c for x in qs)]
    return dict(groups=C.GROUP_NAMES, cats=cats, q=qs)


# ---------- page Méthode : tout chiffre éditorial vient d'ici, jamais du template ----------
def load_jev_summary(path=None):
    """content/jev_summary.json (optionnel, rempli à la main) -> dict nettoyé, ou None (« Étude en cours »).

    Schéma : {titre: str, lede: str, chiffres: [{label: str, valeur: str|nombre, note?: str}], verdict: str, rapport_url: https://…}
    Toutes les clés sont facultatives ; une clé inconnue ou mal typée est ignorée, un fichier invalide donne None."""
    try:
        raw = C.jload(path or jev_summary_path())
    except (ValueError, OSError):
        print("[build] jev_summary.json illisible : ignoré (« Étude en cours »)")
        return None
    if not isinstance(raw, dict):
        return None
    out = {}
    for k in ("titre", "lede", "verdict"):
        if isinstance(raw.get(k), str) and raw[k].strip():
            out[k] = raw[k].strip()
    rows = []
    for c in raw.get("chiffres") if isinstance(raw.get("chiffres"), list) else []:
        if isinstance(c, dict) and isinstance(c.get("label"), str) and isinstance(c.get("valeur"), (str, int, float)) \
                and not isinstance(c.get("valeur"), bool):
            row = {"label": c["label"].strip(), "valeur": c["valeur"]}
            if isinstance(c.get("note"), str) and c["note"].strip():
                row["note"] = c["note"].strip()
            rows.append(row)
    if rows:
        out["chiffres"] = rows
    url = raw.get("rapport_url")
    if isinstance(url, str) and url.startswith("https://"):
        out["rapport_url"] = url
    return out or None


def blocked_stage(reason):
    """Étape de la chaîne de contrôles où une fiche a été bloquée, d'après blocked_reason (première cause citée)."""
    first = (reason or "").lower().split(";")[0].strip()
    if first.startswith("sources insuffisantes") or first.startswith("aucune source"):
        return "sources"
    if first.startswith("sens du vote"):
        return "sens"
    if first.startswith("nom de parti") or first.startswith("nom de personne"):
        return "noms"
    if first.startswith("arguments pour/contre"):
        return "pro_con"
    if first.startswith("catégorie") or first.startswith("champs manquants"):
        return "format"
    return "neutralite" if first else "autre"      # orientation, termes orientés, longueur, asymétrie, second modèle indisponible


def fiche_stats(fiches, n_sujets):
    """Chiffres de la chaîne de fabrication, lus des fiches (status, checks). `fiches` = fiches du pool de sujets."""
    st = {k: 0 for k in store.STATUSES}
    stage = {}
    checks = dict(avec_controles=0, sens_ok=0, neutralite_ok=0, pro_con_ok=0, pro_con_non_evalue=0)
    notes, models = [], set()
    legacy_sans_controles = 0
    for q in fiches:
        st[q["status"]] = st.get(q["status"], 0) + 1
        if q["status"] == "blocked":
            k = blocked_stage(q.get("blocked_reason"))
            stage[k] = stage.get(k, 0) + 1
        ck = q.get("checks") or {}
        if ck:
            checks["avec_controles"] += 1
            checks["sens_ok"] += bool((ck.get("direction") or {}).get("ok"))
            checks["neutralite_ok"] += bool((ck.get("neutrality") or {}).get("ok"))
            pc = ck.get("pro_con")
            if pc is None:
                checks["pro_con_non_evalue"] += 1
            else:
                checks["pro_con_ok"] += bool(pc.get("ok"))
            sc = ((ck.get("neutrality") or {}).get("judge") or {}).get("score")
            if isinstance(sc, (int, float)):
                notes.append(sc)
        elif q["status"] == "legacy":
            legacy_sans_controles += 1
        m = (q.get("generator") or {}).get("model")
        if m:
            models.add(m)
    return dict(sujets=n_sujets, fiches=len(fiches), sans_fiche=max(0, n_sujets - len(fiches)), par_statut=st, bloquees_par_etape=stage,
                controles=checks, legacy_sans_controles=legacy_sans_controles, relues=st.get("published", 0),
                note_neutralite_moyenne=round(sum(notes) / len(notes), 2) if notes else None, note_neutralite_n=len(notes),
                modeles=sorted(models), seuil_neutralite=C.NEUTRALITY_MAX, relecteurs_min=C.MIN_REVIEWERS)


def bloc_definition():
    """{bloc: [sigles des groupes]} : le classement des groupes en blocs d'origine, tel qu'utilisé par curate.py (affiché sur la page Méthode)."""
    from . import salience_study as SS
    out = {}
    for g, b in SS.BLOC.items():
        if g in C.GROUP_NAMES:
            out.setdefault(b, []).append(g)
    return out


def make_method(curated, pool, all_fiches, jev, today=None):
    """Bloc de données de la page Méthode (injecté en __METHOD__). `curated` None = repli, signalé à l'écran."""
    by_n = {q["n"]: q for q in all_fiches}
    pool_n = {q["n"] for q in pool}
    m = dict(generated=(today or dt.date.today()).isoformat(), curated=bool(curated), licence=C.LICENCE, jev=jev,
             pool=dict(n=len(pool), n_cats=len({q["cat"] for q in pool}),
                       pol={p: sum((q.get("polarity") or "adopt") == p for q in pool) for p in ("adopt", "remove")}))
    if not curated:
        m["fiches"] = fiche_stats(all_fiches, len(all_fiches))
        return m
    items = curated["items"]
    cit = curated_items(curated)
    scope = [by_n[int(it["vote"])] for it in items if int(it["vote"]) in by_n]
    m["fiches"] = fiche_stats(scope, len(items))
    m["pool"]["n_blocs"] = len({cit[q["n"]].get("bloc") for q in pool if q["n"] in cit})
    m["curated_info"] = {k: curated.get(k) for k in ("entonnoir", "repartition", "limites", "indicateurs", "cap_bloc", "min_votants", "min_div", "n", "n_cible", "refuses_par_plafond")}
    m["bloc_def"] = bloc_definition()
    m["items"] = [dict(rang=it.get("rang"), vote=int(it["vote"]), titre=it.get("titre_dossier"), type=it.get("type"), bloc=it.get("bloc"),
                       date=it.get("vote_date"), signaux=it.get("signaux") or {}, votants=it.get("votants"), kind=it.get("vote_kind"),
                       fiche=(by_n[int(it["vote"])]["status"] if int(it["vote"]) in by_n else None), in_quiz=int(it["vote"]) in pool_n)
                  for it in items]
    return m


INLINE = (("/*__DRAW__*/", "draw.js"), ("/*__METHOD_JS__*/", "method.js"), ("/*__METHOD_CSS__*/", "method.css"))
PLACEHOLDERS = ("__DATA__", "__SRC__", "__PROM__", "__STATS__", "__HOOK__", "__SURP__", "__LABELS__", "__METHOD__")


def assemble_template(path=None):
    """Template + fichiers inclus (tirage, page Méthode : JS et CSS), prêt à recevoir les données."""
    path = path or C.TEMPLATE
    html = open(path, encoding="utf-8").read()
    for marker, fname in INLINE:
        assert marker in html, f"marqueur {marker} absent du template"
        html = html.replace(marker, open(os.path.join(os.path.dirname(path), fname), encoding="utf-8").read().replace("</", "<\\/"))
    return html


def inject(html, rep):
    """Remplace chaque placeholder par son JSON. Échoue si un placeholder manque dans le template ou reste non remplacé."""
    for k, v in rep.items():
        assert k in html, f"placeholder {k} absent du template"
        html = html.replace(k, _js(v))
    left = [k for k in PLACEHOLDERS if k in html]
    assert not left, f"placeholders non remplacés : {left}"
    return html


def build(out_dir=None, include_pending=True, include_legacy=True, today=None, use_curated=True):
    out_dir = out_dir or C.SITE
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"))
    curated = load_curated() if use_curated else None
    if use_curated and curated is None:
        print("[build] AVERTISSEMENT : content/curated.json absent -> repli : toutes les fiches publiables sont proposées")
    qs = select_questions(include_pending, include_legacy, curated)
    if not qs:
        raise SystemExit("[build] ARRÊT : aucune fiche publiable dans le pool du quiz")
    problems = []
    for q in qs:                                   # garde-fous à la publication
        if str(q["n"]) not in sc: problems.append(f"{q['n']}: scrutin absent des données")
        if not q.get("label") or not q.get("cat"): problems.append(f"{q['n']}: label/catégorie manquants")
        if q["status"] != "legacy" and not store.sources_ok(q): problems.append(f"{q['n']}: sans source")
        if q["status"] == "published":
            from . import review
            ok, why = review.can_publish(q)
            if not ok: problems.append(f"{q['n']}: publiée mais relecture invalide ({why})")
    if problems:
        raise SystemExit("[build] ARRÊT :\n  " + "\n  ".join(problems))
    seats = seatmap.build({q["n"]: sc[str(q["n"])]["date"] for q in qs})
    data = make_data(qs, sc, seats, curated)
    method = make_method(curated, qs, store.all_questions(), load_jev_summary(), today)
    prom = promises.usable(C.jload(promises.MATCHES, {}))
    prom = {n: L for n, L in prom.items() if int(n) in {q["n"] for q in qs}}
    prom = {n: [{k: v for k, v in x.items() if k in ("bloc", "groups", "exp", "text", "src", "flag")} for x in L] for n, L in prom.items() if L}
    html = assemble_template()
    rep = {"__DATA__": data, "__SRC__": C.jload(os.path.join(C.CONTENT, "sources.json"), {}), "__PROM__": prom,
           "__STATS__": C.jload(os.path.join(C.DATA, "stats.json"), {"n_scrutins": 0, "groups": {}, "agree": {}}),
           "__HOOK__": {str(q["n"]): q["hook"] for q in qs if q.get("hook")}, "__SURP__": {str(q["n"]): q["surp"] for q in qs if q.get("surp")},
           "__LABELS__": {str(q["n"]): q["label"] for q in qs}, "__METHOD__": method}
    html = inject(html, rep)
    os.makedirs(out_dir, exist_ok=True)
    open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(out_dir, ".nojekyll"), "w").close()
    # données ouvertes réutilisables + attribution (Licence Ouverte)
    pub = dict(generated=(today or dt.date.today()).isoformat(), licence=C.LICENCE, source="data.assemblee-nationale.fr", selection="curated.json" if curated else "toutes les fiches publiables (repli)",
               questions=[dict(n=q["n"], date=q["date"], title=q["title"], label=q["label"], status=q["status"], polarity=q.get("polarity"),
                               url=C.URL_SCRUTIN_PAGE.format(n=q["n"]), sources=q.get("sources")) for q in qs])
    C.jdump(pub, os.path.join(out_dir, "data.json"))
    C.jdump(dict(builds=dt.date.today().isoformat(), n_questions=len(qs), n_reviewed=sum(q["status"] == "published" for q in qs), curated=bool(curated)),
            os.path.join(out_dir, "status.json"))
    print(f"[build] {len(qs)} questions ({sum(q['status'] == 'published' for q in qs)} relues) -> {out_dir}/index.html "
          f"({os.path.getsize(os.path.join(out_dir, 'index.html')) // 1024} Ko)")
    return data


if __name__ == "__main__":
    import sys
    build(include_pending="--no-pending" not in sys.argv, include_legacy="--no-legacy" not in sys.argv, use_curated="--no-curated" not in sys.argv)
