"""Étape 4b : filtre de neutralité.

1. Contrôles déterministes (toujours exécutés) :
   - aucun nom de parti, de groupe ni de personne dans les textes affichés pendant le quiz
   - résumé de 3 à 5 phrases ; arguments pour/contre de poids comparable (symétrie)
   - lexique d'adjectifs/expressions orientés
   - au moins une source https
2. Second modèle, distinct de l'auteur, qui NOTE l'orientation de 0 à 5. Toute fiche notée > NEUTRALITY_MAX est rejetée.
   Sans clé API la note est absente : la fiche ne peut pas passer en relecture (échec fermé), sauf HEMI_ALLOW_NO_JUDGE=1 (dev).
"""
import os, re, unicodedata
from . import config as C, llm

PARTY_TERMS = [
    "rassemblement national", "front national", "la france insoumise", "france insoumise", "insoumis", "lfi", "nupes",
    "nouveau front populaire", "parti socialiste", "socialistes", "écologistes", "les écologistes", "europe écologie",
    "ensemble pour la république", "renaissance", "horizons", "modem", "mouvement démocrate", "les démocrates",
    "les républicains", "droite républicaine", "union des droites", "ciotti", "reconquête", "parti communiste",
    "communistes", "gauche démocrate", "liot", "udr", "epr", "gdr", "ecos", "rn ", " ps ", " pcf", "lr ",
    "macronistes", "macronie", "lepénistes",
]
PERSON_TITLES = re.compile(r"\b(?:M\.|Mme|Monsieur|Madame|Mmes|MM\.)\s+[A-ZÉÈÀ][\wÉÈÀéèêàç'’-]+")
LOADED = [  # radicaux (préfixes) : « scandal » attrape scandale, scandaleux, scandaleuse…
    "scandal", "honteu", "courageu", "indigne", "laxiste", "liberticide", "fascis", "extrémis", "d'extrême", "ultra-",
    "démagog", "populis", "idéologi", "catastroph", "dangereu", "irresponsab", "évidemment", "heureusement", "malheureusement",
    "hélas", "bien sûr", "sans surprise", "cache-sexe", "nauséabond", "sécuritaire", "ultralibéra", "gauchis", "woke",
    "cadeau aux riches", "inacceptable", "salutaire", "mensonge", "honte", "tyranni", "autoritaire", "liberticide",
]
SHOWN = ("title", "label", "hook", "sum", "pro", "con", "surp")


def _norm(t):
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def _has(low, term):
    term = term.strip()
    return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9]" + ("" if not term.endswith("-") else "|$") + ")", low) is not None


META = re.compile(r"(?i)\b(?:extraits?|sources?|documents?)\s+(?:fournis?e?s?|disponibles?|consultés?)|décrits? ici|dans les extraits")


def strip_meta(text):
    """Retire les phrases qui parlent du processus de rédaction (« les extraits fournis ne détaillent pas… »)."""
    return " ".join(s for s in sentences(text or "") if not META.search(s)).strip()


def sentences(t):
    return [s for s in re.split(r"(?<=[.!?…])\s+", (t or "").strip()) if len(s.strip()) > 2]


def forbidden_names(extra_actors=None):
    """Noms complets de députés (Prénom Nom) + liste éditée à la main content/forbidden_names.json."""
    names = set(C.jload(os.path.join(C.CONTENT, "forbidden_names.json"), []))
    actors = extra_actors if extra_actors is not None else C.jload(os.path.join(C.DATA, "actors.json"), {})
    for nom, prenom in actors.values():
        if len(nom) > 3 and len(prenom) > 2:
            names.add(f"{prenom} {nom}")
    return names


def deterministic(q, actors=None):
    issues = []
    text_all = " ".join((q.get(k) or "") for k in SHOWN)
    low = " " + _norm(text_all) + " "
    for term in PARTY_TERMS:
        t = _norm(term)
        if _has(low, t):
            issues.append(f"nom de parti/groupe : « {term.strip()} »")
    if PERSON_TITLES.search(text_all):
        issues.append("nom de personne (M./Mme + nom)")
    for full in forbidden_names(actors):
        if _norm(full) in low:
            issues.append(f"nom de personne : « {full} »")
            break
    for w in LOADED:
        if re.search(r"(?<![a-z0-9])" + re.escape(_norm(w)), low):
            issues.append(f"terme orienté : « {w.strip()} »")
    if META.search(text_all):
        issues.append("mention du processus de rédaction (extraits/sources fournis)")
    n = len(sentences(q.get("sum")))
    if not C.SUM_MIN_LINES <= n <= C.SUM_MAX_LINES:
        issues.append(f"résumé de {n} phrases (attendu {C.SUM_MIN_LINES}-{C.SUM_MAX_LINES})")
    lp, lc = len((q.get("pro") or "").split()), len((q.get("con") or "").split())
    if not lp or not lc:
        issues.append("argument pour ou contre manquant")
    elif not 0.6 <= lp / lc <= 1.0 / 0.6:
        issues.append(f"asymétrie pour/contre ({lp} mots vs {lc} mots)")
    if not (q.get("sources") or []):
        issues.append("aucune source")
    for s in q.get("sources") or []:
        if not str(s.get("url", "")).startswith("https://"):
            issues.append("source sans URL https")
    return issues


def judge(q, call=None):
    """Note d'orientation 0-5 par un second modèle. -> dict(score, reasons) ou None si indisponible."""
    prompt = (
        "Tu es un relecteur de neutralité politique. Voici une fiche destinée à un quiz grand public sur un vote "
        "de l'Assemblée nationale. Note l'ORIENTATION du texte de 0 (strictement neutre, arguments symétriques, "
        "aucun adjectif orienté) à 5 (clairement partisan). Considère : choix des mots, ordre et poids des arguments, "
        "cadrage du titre, ce qui est omis. Réponds uniquement en JSON : "
        '{"score": <0-5>, "biais": "gauche|droite|aucun|autre", "raisons": ["..."]}.\n\n'
        f"Titre : {q.get('title')}\nBouton : Pour {q.get('label')}\nRésumé : {q.get('sum')}\n"
        f"Argument des partisans : {q.get('pro')}\nArgument des opposants : {q.get('con')}\n"
        f"Accroche : {q.get('hook')}\nPourquoi ça peut surprendre : {q.get('surp')}")
    r = (call or (lambda p: llm.ask_json(C.MODEL_JUDGE, p, max_tokens=500, temperature=0)))(prompt)
    if not isinstance(r, dict) or "score" not in r:
        return None
    return dict(score=float(r["score"]), bias=r.get("biais"), reasons=r.get("raisons", []), model=C.MODEL_JUDGE)


def evaluate(q, call=None, actors=None):
    """-> dict(ok, issues, judge). ok=False bloque la fiche."""
    issues = deterministic(q, actors)
    j = judge(q, call)
    if j is None:
        if os.environ.get("HEMI_ALLOW_NO_JUDGE") == "1":
            j = dict(score=None, note="juge absent (mode dev)")
        else:
            issues.append("second modèle indisponible : note d'orientation absente (échec fermé)")
    elif j["score"] > C.NEUTRALITY_MAX:
        issues.append(f"orientation jugée trop forte ({j['score']}/5, biais {j.get('bias')})")
    return dict(ok=not issues, issues=issues, judge=j)
