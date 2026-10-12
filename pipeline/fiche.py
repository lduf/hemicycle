"""Étape 4a : génération d'une fiche neutre à partir du texte officiel et de sources citées.

Le modèle n'a le droit de s'appuyer QUE sur les extraits fournis (jamais sur sa mémoire, surtout pour les chiffres).
Chaque fiche créée est enregistrée dans content/questions/<n>.json avec status=draft, puis passe par :
  direction.llm_check  ->  neutrality.evaluate  ->  status=pending_review (relecture humaine) ou blocked.
"""
import json, os, datetime as dt
from . import config as C, direction as D, llm, neutrality as N, sources as S, store

SYSTEM = (
    "Tu rédiges des fiches de vote pour un quiz civique destiné aux jeunes, en français simple. Règles absolues : "
    "(1) aucun nom de parti, de groupe parlementaire ni de personne ; (2) aucun adjectif orienté ; "
    "(3) résumé de 3 à 5 phrases ; (4) arguments des partisans et des opposants de poids égal (même longueur, même "
    "niveau de détail) ; (5) tu n'utilises QUE les extraits de sources fournis : aucun chiffre ni fait qui n'y figure pas, "
    "et si une information manque tu l'omets ; (6) tu vérifies le sens du vote : un amendement de suppression ou de rejet "
    "inverse le sens de « pour »."
    " (7) Les arguments portent sur le FOND de la mesure, jamais sur la procédure (« conclure la procédure », « version commune »)."
    " (8) Les arguments des opposants se tirent des réserves et critiques DOCUMENTÉES dans les extraits (avis du Conseil d'État, "
    "objections ou limites évoquées dans le rapport, points de vigilance, amendements de suppression) ; reformule-les sans nommer "
    "qui les porte. Si les extraits ne permettent pas de décrire ce que la mesure change concrètement, ou ne contiennent AUCUNE "
    "réserve ni critique, réponds uniquement {\"insuffisant\": true} plutôt que d'inventer."
)


def build_prompt(scr, cl, texts):
    srcs = "\n\n".join(f"[SOURCE {i + 1}] {u}\n{t}" for i, (u, t) in enumerate(texts))
    sens = ("Voter POUR = adopter la mesure." if cl["polarity"] == "adopt"
            else "ATTENTION : voter POUR = SUPPRIMER / REJETER la mesure ; « label » doit désigner la mesure supprimée.")
    return (
        f"Scrutin n° {scr['n']} du {scr['date']}. Titre officiel : « {scr['titre']} ». Résultat : {scr['sort']}.\n{sens}\n\n"
        f"{srcs}\n\n"
        "Produis un objet JSON avec les clés : title (titre court et neutre), label (groupe nominal pour le bouton, ex. "
        "« l'interdiction de X » ; le site affichera « Pour <label> » / « Contre <label> »), cat (une de : "
        f"{', '.join(C.CATS)}), hook (une phrase « Ça change quoi pour moi ? »), sum (3 à 5 phrases), pro (arguments des "
        "partisans, 1-2 phrases), con (arguments des opposants, même longueur), surp (1-2 phrases neutres sur ce qu'un "
        "pour/contre ne dit pas), source_ids (liste des numéros de SOURCE utilisés).")


def draft(scr, urls, call=None, texts=None):
    """Crée/écrase un brouillon. `urls` = sources officielles (https) choisies par un humain ou le pipeline."""
    cl = D.classify(scr["titre"])
    if cl["polarity"] is None:
        return _blocked(scr, cl, f"sens du vote douteux : {cl['reason']}")
    texts = texts if texts is not None else [(u, S.fetch_text(u)) for u in urls if S.allowed(u)]
    if not texts:
        return _blocked(scr, cl, "aucun texte officiel exploitable")
    ask = call or (lambda p: llm.ask_json(C.MODEL_WRITER, p, system=SYSTEM, max_tokens=1500))
    r = ask(build_prompt(scr, cl, texts))
    if not isinstance(r, dict):
        return _blocked(scr, cl, "génération indisponible (modèle absent ou réponse illisible)")
    if r.get("insuffisant") or "sources fournies" in json.dumps(r, ensure_ascii=False).lower():
        return _blocked(scr, cl, "sources insuffisantes pour décrire la mesure et ses critiques")
    issues = N.deterministic(dict(r, sources=[dict(url="https://x")]), None)       # une seule passe de réparation, sur les défauts de forme
    if issues and call is None:
        fixed = ask(build_prompt(scr, cl, texts) + "\n\nTa réponse précédente :\n" + json.dumps(r, ensure_ascii=False) +
                    "\n\nElle présente ces défauts : " + " ; ".join(issues) + ". Renvoie le JSON complet corrigé (mêmes clés).")
        if isinstance(fixed, dict) and not fixed.get("insuffisant"):
            r = fixed
    srcs = [dict(label=f"Source {i + 1}", url=texts[i - 1][0]) for i in r.get("source_ids", []) if 1 <= i <= len(texts)]
    srcs.insert(0, dict(label="Scrutin officiel (Assemblée nationale)", url=S.scrutin_url(scr["n"])))
    q = dict(n=scr["n"], date=scr["date"], kind="texte" if cl["kind"] == "ensemble" else "mesure", subkind=cl["kind"],
             polarity=cl["polarity"], cat=r.get("cat") if r.get("cat") in C.CATS else None,
             title=r.get("title"), label=r.get("label"), hook=r.get("hook"), sum=r.get("sum"), pro=r.get("pro"),
             con=r.get("con"), surp=r.get("surp"), sources=srcs,
             generator=dict(model=C.MODEL_WRITER, date=dt.date.today().isoformat()), status="draft", reviews=[], checks={})
    return check(q, call_judge=None)


def _blocked(scr, cl, why):
    return dict(n=scr["n"], date=scr["date"], status="blocked", polarity=cl["polarity"], blocked_reason=why, reviews=[],
                title=scr["titre"], sources=[dict(label="Scrutin officiel (Assemblée nationale)", url=S.scrutin_url(scr["n"]))])


def check(q, call_judge=None, call_dir=None):
    """Enchaîne sens du vote (modèle) puis neutralité. Met à jour q['status'] et q['checks']."""
    if q.get("cat") not in C.CATS:
        q["status"] = "blocked"; q["blocked_reason"] = f"catégorie invalide : {q.get('cat')!r}"; return q
    if not q.get("label") or not q.get("title"):
        q["status"] = "blocked"; q["blocked_reason"] = "champs manquants"; return q
    scr_title = (C.jload(os.path.join(C.DATA, "scrutins.json"), {}).get(str(q["n"])) or {}).get("titre", q.get("title"))
    ok, ans = (True, "non vérifié (hors ligne)")
    fn = call_dir or ((lambda p: llm.ask(C.MODEL_JUDGE, p, max_tokens=10, temperature=0)) if llm.available() else None)
    if fn:
        ok, ans = D.llm_check(fn, scr_title, q["label"], q["polarity"])
    elif os.environ.get("HEMI_ALLOW_NO_JUDGE") != "1":
        ok, ans = False, "vérification du sens par modèle indisponible (échec fermé)"
    ev = N.evaluate(q, call_judge)
    q["checks"] = dict(direction=dict(ok=ok, answer=ans), neutrality=ev, date=dt.date.today().isoformat())
    if ok and ev["ok"]:
        q["status"] = "pending_review"; q.pop("blocked_reason", None)
    else:
        q["status"] = "blocked"
        q["blocked_reason"] = "; ".join(([] if ok else [f"sens du vote : {ans}"]) + ev["issues"])
    q["reviewed_hash"] = None
    return q


def save_and_report(q):
    store.save(q)
    print(f"[fiche] {q['n']} -> {q['status']}" + (f" ({q.get('blocked_reason')})" if q["status"] == "blocked" else ""))
    return q
