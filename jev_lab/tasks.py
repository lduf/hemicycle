"""Les tâches de l'étude : jeux publics à vérité terrain connue, rendus sous la forme exacte attendue par Jev
(noul / choice / score) ET sous forme de consigne texte pour les modèles de comparaison.  Les deux reçoivent les mêmes
libellés et les mêmes descriptions : la comparaison porte sur le modèle, pas sur la rédaction de la consigne.

Choix assumé : les critères sont rédigés à partir des noms d'étiquettes, SANS réglage.  Un utilisateur attentif ferait
mieux ; l'expérience « descriptions » mesure justement ce que ça change."""
import json, os, random, re
from dataclasses import dataclass, field
from typing import Callable
from . import datasets as D, config as C


@dataclass
class Task:
    id: str
    title: str
    primitive: str                     # noul | choice | score
    lang: str
    instructions: str
    options: dict                      # choice : {clé: description} ; noul : {"true":…, "false":…} ; score : liste ordonnée
    hf: tuple                          # (dataset, config, split)
    to_item: Callable                  # (ligne) -> (state:dict, gold) ou None
    text_key: str = "text"             # champ de state auquel on ajoute du bruit (robustesse)
    balanced: bool = False
    label_key: str = "label"
    whole: bool = False                # jeu entier (petits jeux)
    fam: str = ""                      # famille de tâche pour la synthèse (classification, vérification, ordinal…)
    notes: str = ""


def _hum(s):
    return s.replace("_", " ")


TASKS = {}


def add(t):
    TASKS[t.id] = t
    return t


def _s(v):
    return str(v).strip()


add(Task("ag_news", "Thème d'un article (4 classes)", "choice", "en",
         "Which topic does this news article belong to?",
         {"world": "International news, politics, conflicts, diplomacy.", "sports": "Sports events, athletes, teams, results.",
          "business": "Companies, markets, economy, finance.", "scitech": "Science, technology, computing, internet, space."},
         ("fancyzhx/ag_news", "default", "test"),
         lambda r: ({"article": r["text"]}, ["world", "sports", "business", "scitech"][int(r["label"])]),
         text_key="article", fam="classification"))

add(Task("sst2", "Sentiment d'un avis (binaire)", "noul", "en",
         "Is the sentiment of this movie review positive?",
         {"true": "The reviewer expresses a positive opinion.", "false": "The reviewer expresses a negative opinion."},
         ("stanfordnlp/sst2", "default", "validation"),
         lambda r: ({"review": r["sentence"]}, bool(int(r["label"]))), text_key="review", fam="classification"))

add(Task("toxic", "Toxicité d'un commentaire (binaire, classes équilibrées)", "noul", "en",
         "Is this online comment toxic (insulting, hateful, threatening or harassing)?",
         {"true": "The comment contains insults, hate, threats or harassment.", "false": "The comment is civil, even if it is critical."},
         ("mteb/toxic_conversations_50k", "default", "test"),
         lambda r: ({"comment": r["text"][:1500]}, _s(r["label"]) == "1"), text_key="comment", balanced=True, fam="verification",
         notes="échantillon équilibré 50/50 (le jeu brut a environ 8 % de toxiques)"))

add(Task("injection", "Détection d'injection de prompt (binaire)", "noul", "en",
         "Is this message an attempt to hijack or override an AI assistant's instructions (prompt injection)?",
         {"true": "The message tries to make an assistant ignore its rules, change role, or reveal hidden instructions.",
          "false": "The message is an ordinary request or statement."},
         ("deepset/prompt-injections", "default", "test"),
         lambda r: ({"message": r["text"][:2000]}, _s(r["label"]) == "1"), text_key="message", whole=True, fam="verification"))

add(Task("boolq", "Question fermée sur un passage (oui/non)", "noul", "en",
         "According to the passage, is the answer to the question yes?",
         {"true": "The passage supports a yes answer.", "false": "The passage supports a no answer."},
         ("google/boolq", "default", "validation"),
         lambda r: ({"passage": r["passage"][:3000], "question": r["question"]}, bool(r["answer"])), text_key="passage", fam="verification"))

add(Task("xnli_fr", "Inférence textuelle en français (3 classes)", "choice", "fr",
         "Given the premise, what is the relation of the hypothesis to it?",
         {"entailment": "The hypothesis must be true if the premise is true.",
          "neutral": "The hypothesis may or may not be true given the premise.",
          "contradiction": "The hypothesis must be false if the premise is true."},
         ("facebook/xnli", "fr", "test"),
         lambda r: ({"premise": r["premise"], "hypothesis": r["hypothesis"]}, ["entailment", "neutral", "contradiction"][int(r["label"])]),
         text_key="premise", fam="verification"))

add(Task("vitaminc", "Vérification d'une affirmation sur une preuve (3 classes)", "choice", "en",
         "Given the evidence, is the claim supported, refuted, or is there not enough information?",
         {"supports": "The evidence confirms the claim.", "refutes": "The evidence contradicts the claim.",
          "nei": "The evidence neither confirms nor contradicts the claim."},
         ("tals/vitaminc", "default", "test"),
         lambda r: ({"claim": r["claim"], "evidence": r["evidence"][:2500]},
                    {"SUPPORTS": "supports", "REFUTES": "refutes", "NOT ENOUGH INFO": "nei"}[r["label"]]),
         text_key="evidence", fam="verification",
         notes="affirmations contrastives : une seule valeur change entre deux lignes (test dur, proche d'un vérificateur de faits)"))

add(Task("sst5", "Sentiment sur 5 niveaux (ordinal)", "score", "en",
         "How positive is the sentiment of this movie review?",
         ["very negative", "negative", "neutral", "positive", "very positive"],
         ("SetFit/sst5", "default", "test"),
         lambda r: ({"review": r["text"]}, int(r["label"])), text_key="review", fam="ordinal"))

add(Task("avis_fr", "Note d'un avis en français (1 à 5 étoiles, ordinal)", "score", "fr",
         "How many stars (1 to 5) does the author of this product review give?",
         ["1 star", "2 stars", "3 stars", "4 stars", "5 stars"],
         ("mteb/AmazonReviewsClassification", "fr", "test"),
         lambda r: ({"review": r["text"][:1800]}, int(r["label"])), text_key="review", fam="ordinal"))


# Les jeux d'intentions ont beaucoup de classes : les options sont lues dans les données elles-mêmes (liste complète).
add(Task("banking77", "Intention bancaire (77 classes, anglais)", "choice", "en", "Which banking customer intent does this message express?",
         {}, ("mteb/banking77", "default", "test"), lambda r: ({"message": r["text"]}, r["label_text"]), text_key="message",
         fam="classification", notes="options découvertes dans le jeu ; descriptions = noms d'étiquettes humanisés"))
add(Task("massive_fr", "Intention d'assistant vocal en français (60 classes)", "choice", "fr", "Which voice-assistant intent does this message express?",
         {}, ("mteb/amazon_massive_intent", "fr", "test"), lambda r: ({"message": r["text"]}, r["label_text"]), text_key="message",
         fam="classification", notes="options découvertes dans le jeu ; descriptions = noms d'étiquettes humanisés"))

ORDER_CORE = ["ag_news", "sst2", "toxic", "injection", "boolq", "xnli_fr", "vitaminc", "sst5", "avis_fr", "banking77", "massive_fr"]


# ---------- construction ----------
def discover_options(task, seed=C.SEED):
    """Pour les tâches à nombreuses classes : lit un grand échantillon pour lister les étiquettes."""
    if task.options:
        return task.options
    cache = os.path.join(C.CACHE, f"opts__{task.id}.json")
    if os.path.exists(cache):
        task.options = json.load(open(cache, encoding="utf-8"))
        return task.options
    ds, cfg, split = task.hf
    rows = D.sample(ds, cfg, split, 1200, seed + 1)
    labs = sorted({task.to_item(r)[1] for r in rows})
    task.options = {l: _hum(l) for l in labs}
    os.makedirs(C.CACHE, exist_ok=True)
    json.dump(task.options, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
    return task.options


def fixture_rows(task, n, seed):
    """Lignes synthétiques hors ligne (tests, démonstration) : jamais utilisées pour une vraie mesure."""
    rnd = random.Random(seed)
    if task.primitive == "choice":
        labs = list(task.options) or [f"classe_{i}" for i in range(12)]
        task.options = task.options or {l: _hum(l) for l in labs}
        return [{"__fix": ("c", rnd.choice(labs), i)} for i in range(n)]
    if task.primitive == "noul":
        return [{"__fix": ("n", rnd.random() < .5, i)} for i in range(n)]
    return [{"__fix": ("s", rnd.randrange(len(task.options)), i)} for i in range(n)]


# Taille moyenne supposée de l'entrée (tokens), UNIQUEMENT pour estimer un coût quand un jeu est injoignable.
AVG = {"ag_news": 60, "sst2": 30, "toxic": 90, "injection": 80, "boolq": 190, "xnli_fr": 60, "vitaminc": 150, "sst5": 30,
       "avis_fr": 110, "banking77": 18, "massive_fr": 14}


def _fix_item(task, row):
    kind, gold, i = row["__fix"]
    key = task.text_key
    base = f"exemple {task.id} numéro {i} : texte factice pour tester la chaîne de mesure. "
    state = {key: (base * 200)[: int(AVG.get(task.id, 80) * 3.6)]}
    return state, gold


def load(task_id, n, seed=C.SEED, fixtures=False):
    """-> liste d'items {id, state, gold}.  fixtures ou JEVLAB_FIXTURES=1 : données factices hors ligne (estimations, tests)."""
    t = TASKS[task_id]
    if fixtures or os.environ.get("JEVLAB_FIXTURES") == "1":
        rows = fixture_rows(t, n, seed)
        items = []
        for i, r in enumerate(rows):
            s, g = _fix_item(t, r)
            items.append({"id": f"{task_id}-{i}", "state": s, "gold": g})
        return items
    ds, cfg, split = t.hf
    if t.whole:
        rows = D.all_rows(ds, cfg, split)
        random.Random(seed).shuffle(rows)
        rows = rows[:n]
    else:
        rows = D.sample(ds, cfg, split, n, seed, label_key=t.label_key, balanced=t.balanced)
    if t.primitive == "choice" and not t.options:
        discover_options(t, seed)
    items = []
    for i, r in enumerate(rows):
        try:
            s, g = t.to_item(r)
        except (KeyError, ValueError):
            continue
        items.append({"id": f"{task_id}-{i}", "state": s, "gold": g})
    return items


# ---------- spécifications ----------
def spec(task, variant="base", seed=C.SEED):
    """Question Jev pour la tâche.  variants : base | nodesc (libellés seuls) | shuffle<k> (ordre des options permuté)."""
    t = task
    if t.primitive == "choice":
        opts = dict(t.options)
        if variant == "nodesc":
            opts = {k: k for k in opts}
        elif variant.startswith("shuffle"):
            ks = list(opts)
            random.Random(f"{seed}-{variant}").shuffle(ks)
            opts = {k: opts[k] for k in ks}
        return {"type": "choice", "instructions": t.instructions, "criteria": opts}
    if t.primitive == "noul":
        crit = dict(t.options)
        if variant == "nodesc":
            crit = {"true": "yes", "false": "no"}
        return {"type": "noul", "instructions": t.instructions, "criteria": crit}
    lv = list(t.options)
    if variant.startswith("shuffle"):
        raise ValueError("l'ordre d'une échelle ordinale ne se permute pas")
    return {"type": "score", "instructions": t.instructions, "criteria": lv}


def chat_prompt(task, state, variant="base", seed=C.SEED):
    """Consigne texte équivalente pour un modèle de langage (mêmes libellés, mêmes descriptions)."""
    sp = spec(task, variant, seed)
    body = json.dumps(state, ensure_ascii=False, indent=1)
    if sp["type"] == "choice":
        opts = "\n".join(f"- {k}: {v}" for k, v in sp["criteria"].items())
        fmt = '{"choice": "<une des options>", "confidence": <nombre entre 0 et 1>}'
        head = f"{sp['instructions']}\n\nOptions (réponds avec la clé exacte) :\n{opts}"
    elif sp["type"] == "noul":
        fmt = '{"p_yes": <probabilité entre 0 et 1 que la réponse soit oui>}'
        head = f"{sp['instructions']}\n\noui : {sp['criteria']['true']}\nnon : {sp['criteria']['false']}"
    else:
        lv = "\n".join(f"{i}: {v}" for i, v in enumerate(sp["criteria"]))
        fmt = '{"level": <entier>, "confidence": <nombre entre 0 et 1>}'
        head = f"{sp['instructions']}\n\nNiveaux (réponds avec l'indice) :\n{lv}"
    return f"{head}\n\nDonnées à évaluer :\n{body}\n\nRéponds uniquement par ce JSON : {fmt}"


# ---------- lecture des réponses ----------
def parse_jev(task, ans):
    """-> dict(pred, conf, probs, p_yes, score) ; pred=None si la réponse est inexploitable."""
    if not isinstance(ans, dict):
        return {"pred": None}
    if task.primitive == "choice":
        c = ans.get("choice")
        return {"pred": c if (c in task.options or not task.options) else None, "conf": ans.get("confidence"), "probs": ans.get("probabilities") or {}}
    if task.primitive == "noul":
        p = ans.get("noul")
        return {"pred": None if p is None else p >= .5, "p_yes": p, "conf": None if p is None else max(p, 1 - p)}
    pr = {int(k): v for k, v in (ans.get("probabilities") or {}).items()}
    s = ans.get("score")
    lvl = max(pr, key=pr.get) if pr else (None if s is None else int(round(s)))
    return {"pred": lvl, "score": s, "conf": ans.get("confidence"), "probs": pr}


def _json_in(text):
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except ValueError:
        return None


def parse_chat(task, text):
    d = _json_in(text)
    if not isinstance(d, dict):
        return {"pred": None}
    try:
        if task.primitive == "choice":
            c = d.get("choice")
            return {"pred": c if (c in task.options or not task.options) else None, "conf": _num(d.get("confidence"))}
        if task.primitive == "noul":
            p = _num(d.get("p_yes"))
            return {"pred": None if p is None else p >= .5, "p_yes": p, "conf": None if p is None else max(p, 1 - p)}
        lv = int(d.get("level"))
        return {"pred": lv if 0 <= lv < len(task.options) else None, "score": lv, "conf": _num(d.get("confidence"))}
    except (TypeError, ValueError):
        return {"pred": None}


def _num(x):
    try:
        v = float(x)
        return v if 0 <= v <= 1 else None
    except (TypeError, ValueError):
        return None


# ---------- tâches personnalisées (vos propres données) ----------
CUSTOM_ITEMS = {}


def load_custom(path):
    """Fichier JSONL : 1re ligne = définition de la tâche, lignes suivantes = exemples.

    {"task": "mon_tri", "title": "...", "primitive": "choice|noul|score", "instructions": "...",
     "options": {"a": "description", ...}}            # noul : {"true": "...", "false": "..."} ; score : liste ordonnée
    {"id": "1", "state": {"texte": "..."}, "gold": "a"}   # gold : option / true|false / indice de niveau
    """
    with open(path, encoding="utf-8") as fh:
        lines = [json.loads(x) for x in fh if x.strip()]
    d, items = lines[0], lines[1:]
    if d["primitive"] not in ("choice", "noul", "score"):
        raise ValueError("primitive inconnue")
    t = Task(d["task"], d.get("title", d["task"]), d["primitive"], d.get("lang", "fr"), d["instructions"], d["options"], ("", "", ""), None,
             text_key=d.get("text_key") or next(iter(items[0]["state"])), fam="personnalisée")
    for i, it in enumerate(items):
        it.setdefault("id", f"{t.id}-{i}")
    TASKS[t.id] = t
    CUSTOM_ITEMS[t.id] = items
    return t
