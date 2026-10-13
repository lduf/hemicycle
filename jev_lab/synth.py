"""Tâches synthétiques à réponse exacte (génération déterministe) et bruit de contexte.

Servent à tester ce que l'éditeur annonce comme faiblesses : arithmétique, comptage, comparaison de dates, détails
non pertinents.  La vérité est calculée par le programme, jamais estimée."""
import datetime, random
from . import config as C
from .tasks import Task, TASKS, add

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _fr(d):
    return f"{d.day} {MOIS[d.month - 1]} {d.year}"


def gen_dates(n, seed):
    """Quelle date est la plus ancienne ?  (formats mélangés : français littéral ou ISO)"""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        a = datetime.date(2015, 1, 1) + datetime.timedelta(days=rnd.randrange(3650))
        b = a + datetime.timedelta(days=rnd.choice([1, 3, 20, 90, 400]) * rnd.choice([1, -1]))
        f = (lambda d: d.isoformat()) if rnd.random() < .5 else _fr
        out.append({"id": f"dates-{i}", "state": {"date_a": f(a), "date_b": f(b)}, "gold": "a" if a < b else "b"})
    return out


def gen_counting(n, seed):
    """Combien de fois le mot « chat » apparaît-il ?  (0 à 8)"""
    rnd = random.Random(seed)
    filler = ["le", "jardin", "est", "calme", "ce", "matin", "un", "chien", "dort", "près", "de", "la", "porte", "et", "les", "oiseaux", "chantent"]
    out = []
    for i in range(n):
        k = rnd.randrange(0, 9)
        words = [rnd.choice(filler) for _ in range(rnd.randrange(20, 60))]
        for _ in range(k):
            words.insert(rnd.randrange(len(words) + 1), "chat")
        out.append({"id": f"comptage-{i}", "state": {"texte": " ".join(words)}, "gold": str(k)})
    return out


def gen_arith(n, seed):
    """La somme est-elle supérieure au seuil ?  (oui/non, écart faible pour forcer le calcul)"""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        a, b = rnd.randrange(100, 999), rnd.randrange(100, 999)
        s = a + b
        t = s + rnd.choice([-40, -7, -1, 1, 7, 40])
        out.append({"id": f"arith-{i}", "state": {"a": a, "b": b, "seuil": t}, "gold": s > t})
    return out


def gen_max(n, seed):
    """Quel nombre est le plus grand parmi quatre ?  (nombres proches, longueurs variées)"""
    rnd = random.Random(seed)
    out = []
    for i in range(n):
        base = rnd.randrange(1000, 90000)
        vals = [base + rnd.randrange(-300, 300) for _ in range(4)]
        if len(set(vals)) < 4:
            vals = [base, base + 1, base + 2, base + 3]
        rnd.shuffle(vals)
        out.append({"id": f"max-{i}", "state": {"nombres": vals}, "gold": "abcd"[vals.index(max(vals))]})
    return out


SYNTH = {
    "dates": (Task("dates", "Quelle date est la plus ancienne ?", "choice", "fr", "Which of the two dates is earlier?",
                   {"a": "date_a is earlier than date_b", "b": "date_b is earlier than date_a"}, ("", "", ""), None,
                   text_key="date_a", fam="limite-annoncee"), gen_dates),
    "comptage": (Task("comptage", "Combien de fois « chat » apparaît ?", "choice", "fr", "How many times does the word 'chat' appear in the text?",
                      {str(k): f"{k} times" for k in range(9)}, ("", "", ""), None, text_key="texte", fam="limite-annoncee"), gen_counting),
    "arith": (Task("arith", "La somme dépasse-t-elle le seuil ?", "noul", "fr", "Is a + b strictly greater than seuil?",
                   {"true": "a + b > seuil", "false": "a + b <= seuil"}, ("", "", ""), None, text_key="a", fam="limite-annoncee"), gen_arith),
    "max": (Task("max", "Quel nombre est le plus grand ?", "choice", "fr", "Which of the four numbers is the largest? (a = first, b = second, c = third, d = fourth)",
                 {"a": "the first number is largest", "b": "the second number is largest", "c": "the third number is largest",
                  "d": "the fourth number is largest"}, ("", "", ""), None, text_key="nombres", fam="limite-annoncee"), gen_max),
}
for _t, _ in SYNTH.values():
    TASKS[_t.id] = _t

SYNTH_IDS = list(SYNTH)


def load_synth(tid, n, seed=C.SEED):
    return SYNTH[tid][1](n, seed)


# ---------- bruit de contexte ----------
_BOILER = ["Les présentes conditions générales s'appliquent à l'ensemble des services proposés sur ce site.",
           "Conformément à la réglementation en vigueur, vous disposez d'un droit d'accès et de rectification.",
           "Cet email et ses pièces jointes sont confidentiels et destinés exclusivement à leur destinataire.",
           "Pour vous désinscrire de cette liste de diffusion, cliquez sur le lien en bas de page.",
           "Ce site utilise des cookies afin d'améliorer votre expérience de navigation.",
           "Copyright tous droits réservés. Toute reproduction est interdite sans autorisation préalable.",
           "Veuillez ne pas répondre à ce message automatique ; il est envoyé depuis une adresse non surveillée.",
           "Les informations figurant dans ce document sont données à titre indicatif et peuvent être modifiées."]


def noise(n_tokens, seed):
    """≈ n_tokens de texte administratif sans rapport avec la tâche (3,6 car./token)."""
    rnd = random.Random(seed)
    out, size = [], 0
    while size < n_tokens * 3.6:
        s = rnd.choice(_BOILER)
        out.append(s)
        size += len(s) + 1
    return " ".join(out)


def add_noise(task, state, n_tokens, where, seed):
    """Ajoute du bruit au champ principal : where = before | after | both."""
    st = dict(state)
    k = task.text_key if task.text_key in st else next(iter(st))
    t = str(st[k])
    if where == "before":
        st[k] = noise(n_tokens, seed) + "\n\n" + t
    elif where == "after":
        st[k] = t + "\n\n" + noise(n_tokens, seed)
    else:
        st[k] = noise(n_tokens // 2, seed) + "\n\n" + t + "\n\n" + noise(n_tokens // 2, seed + 1)
    return st
