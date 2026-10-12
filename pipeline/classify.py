"""Classifications du pipeline : catégorie, orientation (neutralité), pertinence pour/contre, sens du vote, suffisance des sources.

Répartition des rôles : les LLM (Claude via `claude -p`) RÉDIGENT ; Jev (OpenRouter) CLASSE et NOTE.
Même interface quel que soit le moteur (`decide`) : Jev natif, ou Claude répondant au même format typé (secours et
comparaison équitable dans bench_jev). HEMI_CLASSIFIER = auto (défaut : Jev si clé, sinon Claude) | jev | claude | none.
Chaque fonction renvoie None si aucun moteur n'est disponible : l'appelant échoue fermé.
Les SEUILS ci-dessous sont des valeurs de départ prudentes, à recalibrer avec `python -m pipeline.bench_jev`.
"""
import json, os
from . import config as C, jev, llm

THRESHOLDS = dict(
    cat_min=0.5,            # confiance minimale pour écraser la catégorie proposée par le rédacteur
    dir_ok=0.85,            # P(« pour » = ce que dit le bouton)
    pro_con_ok=0.8,         # P(le texte « pour » défend bien / le texte « contre » s'oppose bien)
    substance_ok=0.6,       # P(l'argument porte sur le fond)
    balance=(0.5, 1.5),     # position pondérée sur [0,2] ; 1 = arguments de poids comparable
    source_ok=0.5,          # P(les extraits décrivent la mesure) et P(ils documentent des critiques)
)

CAT_DESC = {
    "Éducation": "École, université, bourses, examens, formation initiale, vie étudiante.",
    "Sport": "Sport professionnel ou amateur, compétitions, Jeux olympiques, clubs, fédérations.",
    "Écologie & énergie": "Climat, environnement, énergie, nucléaire, renouvelables, eau, biodiversité, pollution.",
    "Économie & fiscalité": "Budget de l'État, impôts, taxes, dette, entreprises, finances publiques, commerce.",
    "Famille & social": "Allocations, aides sociales, famille, handicap, pauvreté, protection de l'enfance.",
    "Santé & fin de vie": "Santé publique, hôpital, médicaments, fin de vie, bioéthique, assurance maladie.",
    "Justice & sécurité": "Police, justice, peines, prisons, mineurs délinquants, terrorisme, violences.",
    "Immigration": "Titres de séjour, nationalité, asile, frontières, étrangers.",
    "Numérique": "Internet, réseaux sociaux, données personnelles, IA, télécoms, cybersécurité.",
    "Défense": "Armées, budget militaire, guerre, Ukraine, OTAN, relations internationales de sécurité.",
    "Agriculture": "Agriculteurs, élevage, pesticides, alimentation, pêche, ruralité agricole.",
    "Droits & société": "Libertés publiques, discriminations, égalité, mœurs, droits individuels, consentement.",
    "Travail & retraites": "Emploi, chômage, salaires, retraites, syndicats, conditions de travail.",
    "Institutions": "Élections, mode de scrutin, collectivités, outre-mer, organisation de l'État, Constitution.",
    "Logement": "Logement social, loyers, urbanisme, construction, propriétaires et locataires.",
    "Transports": "Routes, trains, aviation, mobilités, infrastructures de transport.",
    "Culture & médias": "Culture, audiovisuel public, presse, patrimoine, création artistique.",
}
ORIENT_LEVELS = [
    "Strictement neutre : faits et arguments présentés sans jugement, avec un poids égal.",
    "Quasi neutre : une nuance de cadrage mineure.",
    "Léger cadrage : choix de mots ou ordre des arguments favorisant un peu un camp.",
    "Cadrage net : un camp est mieux présenté ou son vocabulaire est repris.",
    "Orienté : jugements de valeur ou arguments nettement déséquilibrés.",
    "Partisan : plaidoyer pour ou contre la mesure.",
]


def backend():
    want = os.environ.get("HEMI_CLASSIFIER", "auto").lower()
    if want == "none":
        return None
    if want in ("auto", "jev") and jev.available():
        return "jev"
    if want in ("auto", "claude") and llm.available():
        return "claude"
    return None


def _claude_decide(state, questions):
    """Même contrat que Jev, assuré par Claude : il estime des probabilités. Sert de secours et de point de comparaison."""
    spec = json.dumps({k: {"type": v["type"], "instructions": v["instructions"], "criteria": v.get("criteria")} for k, v in questions.items()},
                      ensure_ascii=False)
    prompt = ("Réponds à chaque question sur l'objet `state`. Format JSON strict, une clé par question : "
              'noul -> {"noul": p} (probabilité du oui, 0-1) ; choice -> {"choice": "<option>", "probabilities": {"<option>": p, ...}} ; '
              'score -> {"score": x} (position pondérée, index 0 = premier niveau). Aucun autre texte.\n\n'
              f"state = {json.dumps(state, ensure_ascii=False)}\n\nquestions = {spec}")
    r = llm.ask_json(C.MODEL_JUDGE, prompt, max_tokens=900, temperature=0)
    if not isinstance(r, dict) or any(k not in r for k in questions):
        raise jev.JevError("réponse Claude illisible")
    return {"answers": {k: dict(type=questions[k]["type"], **r[k]) for k in questions}, "usage": {}, "model": C.MODEL_JUDGE}


def decide(state, questions, engine=None):
    engine = engine or backend()
    if engine is None:
        return None
    return (jev.decide if engine == "jev" else _claude_decide)(state, questions)


# ---------------------------------------------------------------- tâches

def category(fields, engine=None):
    """fields : dict(title, label, sum). -> dict(cat, confidence, probs, engine) ou None."""
    q = {"cat": jev.choice("Dans quel domaine politique se range le mieux ce texte de loi ?", CAT_DESC)}
    r = decide({k: fields.get(k) for k in ("title", "label", "sum")}, q, engine)
    if r is None:
        return None
    a = r["answers"]["cat"]
    return dict(cat=a["choice"], confidence=a.get("confidence"), probs=a.get("probabilities"), engine=engine or backend())


def orientation(fields, engine=None):
    """Neutralité : note 0-5 (même échelle que NEUTRALITY_MAX) + bord éventuel. -> dict(score, bias, loaded, ...) ou None."""
    state = {k: fields.get(k) for k in ("title", "label", "hook", "sum", "pro", "con", "surp")}
    q = {
        "orientation": jev.score("À quel point ce texte destiné au grand public est-il orienté politiquement ?", ORIENT_LEVELS),
        "bord": jev.choice("Ce texte favorise-t-il un bord politique ?", {
            "aucun": "Aucun bord n'est favorisé : le texte reste symétrique.",
            "gauche": "Le cadrage ou le vocabulaire favorise plutôt les positions classées à gauche.",
            "droite": "Le cadrage ou le vocabulaire favorise plutôt les positions classées à droite."}),
        "charge": jev.noul("Le texte contient-il des jugements de valeur, des adjectifs ou des formules connotées ?"),
    }
    r = decide(state, q, engine)
    if r is None:
        return None
    a = r["answers"]
    return dict(score=float(a["orientation"]["score"]), bias=a["bord"]["choice"], bias_p=(a["bord"].get("probabilities") or {}),
                loaded=a["charge"]["noul"], engine=engine or backend(), model=r.get("model"))


def pro_con(fields, engine=None):
    """Les arguments « pour » défendent-ils vraiment la mesure, les « contre » s'y opposent-ils, sur le fond, à poids égal ?"""
    state = {"mesure": fields.get("label"), "arguments_des_partisans": fields.get("pro"), "arguments_des_opposants": fields.get("con")}
    q = {
        "pro_ok": jev.noul("Le texte « arguments des partisans » défend-il bien l'adoption de la mesure ?"),
        "con_ok": jev.noul("Le texte « arguments des opposants » s'oppose-t-il bien à l'adoption de la mesure ?"),
        "pro_fond": jev.noul("Les arguments des partisans portent-ils sur le fond (effets, coûts, droits, valeurs) et non sur la procédure ?"),
        "con_fond": jev.noul("Les arguments des opposants portent-ils sur le fond (effets, coûts, droits, valeurs) et non sur la procédure ?"),
        "equilibre": jev.score("Comparer le développement des deux argumentaires.", [
            "Les arguments des opposants sont nettement moins développés.", "Les deux argumentaires sont de poids comparable.",
            "Les arguments des partisans sont nettement moins développés."]),
    }
    r = decide(state, q, engine)
    if r is None:
        return None
    a = r["answers"]; T = THRESHOLDS
    res = dict(pro_ok=a["pro_ok"]["noul"], con_ok=a["con_ok"]["noul"], pro_fond=a["pro_fond"]["noul"], con_fond=a["con_fond"]["noul"],
               equilibre=float(a["equilibre"]["score"]), engine=engine or backend())
    res["ok"] = (min(res["pro_ok"], res["con_ok"]) >= T["pro_con_ok"] and min(res["pro_fond"], res["con_fond"]) >= T["substance_ok"]
                 and T["balance"][0] <= res["equilibre"] <= T["balance"][1])
    return res


def direction(titre, label, polarity, engine=None):
    """Le bouton « Pour … » correspond-il au sens réel du vote ? -> (ok, détail) ou None. Échec fermé."""
    from . import direction as D
    pour, contre = D.button_labels(label, polarity)
    q = {
        "correspond": jev.noul("Voter « pour » à ce scrutin signifie-t-il exactement ce que dit le bouton « pour » ?"),
        "sens": jev.choice("Que signifie voter « pour » à ce scrutin ?", {
            "adopter": "Adopter ou maintenir la mesure, le texte, l'article ou l'amendement.",
            "supprimer": "Supprimer, rejeter ou abroger la mesure (amendement de suppression, motion de rejet).",
            "douteux": "On ne peut pas le déterminer avec certitude à partir du titre."}),
    }
    r = decide({"titre_officiel_du_scrutin": titre, "bouton_pour": pour, "bouton_contre": contre}, q, engine)
    if r is None:
        return None
    a = r["answers"]; want = "supprimer" if polarity == "remove" else "adopter"
    ok = a["correspond"]["noul"] >= THRESHOLDS["dir_ok"] and a["sens"]["choice"] == want
    return ok, dict(correspond=a["correspond"]["noul"], sens=a["sens"]["choice"], attendu=want, engine=engine or backend())


def sources_sufficient(titre, extraits, engine=None):
    """Pré-contrôle bon marché AVANT d'appeler le rédacteur : les extraits décrivent-ils la mesure et documentent-ils des critiques ?"""
    q = {
        "decrit": jev.noul("Les extraits décrivent-ils concrètement ce que la mesure change ?"),
        "critiques": jev.noul("Les extraits documentent-ils des réserves, objections ou critiques adressées à la mesure ?"),
    }
    r = decide({"scrutin": titre, "extraits": extraits}, q, engine)
    if r is None:
        return None
    a = r["answers"]; ok = min(a["decrit"]["noul"], a["critiques"]["noul"]) >= THRESHOLDS["source_ok"]
    return ok, dict(decrit=a["decrit"]["noul"], critiques=a["critiques"]["noul"], engine=engine or backend())
