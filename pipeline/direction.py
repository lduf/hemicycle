"""Étape 3a : sens du vote par règles déterministes, à partir du titre officiel du scrutin.

On répond à une seule question : « voter POUR, est-ce adopter la mesure décrite, ou la supprimer/rejeter ? »
  polarity = "adopt"   : pour = adopter la mesure   (texte entier, article, amendement d'ajout, rétablissement)
  polarity = "remove"  : pour = supprimer / rejeter (amendement de suppression, rejet, question préalable)
  polarity = None      : douteux -> NE PAS PUBLIER

Toute ambiguïté renvoie None. Le modèle (llm_check) ne peut que confirmer ou faire échouer ; il ne remplace pas la règle.
"""
import re

REMOVE = [
    r"amendements? (?:de )?suppression", r"amendements? tendant à supprimer", r"amendements? visant à supprimer",
    r"amendements? de rejet", r"motion de rejet", r"question préalable", r"exception d'irrecevabilité",
    r"\bsuppression de l'article", r"amendements? n°\s*\d+\s*\(?suppression",
]
RESTORE = [r"rétablissement", r"rétablir", r"réintroduction", r"réintroduire"]
WHOLE = [r"^l'ensemble (?:du|de la|des|de l')", r"^la proposition de loi", r"^le projet de loi", r"^l'article unique",
         r"^la première partie", r"^la deuxième partie", r"^la proposition de résolution"]
ARTICLE = [r"^l'article \d+", r"^l'article premier", r"^les articles?"]
PROCEDURE = [  # scrutins de pure procédure : jamais publiés
    r"motion de renvoi", r"demande de renvoi", r"rappel au règlement", r"suspension de séance", r"ordre du jour",
    r"demande de seconde délibération", r"motion de censure", r"déclaration de politique générale", r"demande de réserve",
    r"vote solennel sur les conclusions de la commission", r"accord de procédure",
]
TWO_WAY = [r"sous-amendement"]  # un sous-amendement modifie un amendement : sens trop dépendant du texte


def _any(pats, t):
    return any(re.search(p, t, re.I) for p in pats)


def classify(titre):
    """-> dict(kind, polarity, reason). kind : ensemble|article|amendement|motion|procedure|autre"""
    t = (titre or "").replace("’", "'").strip().lower()
    if _any(PROCEDURE, t):
        return dict(kind="procedure", polarity=None, reason="scrutin de procédure")
    if _any(TWO_WAY, t):
        return dict(kind="amendement", polarity=None, reason="sous-amendement : sens dépendant du texte")
    rem, res = _any(REMOVE, t), _any(RESTORE, t)
    if rem and res:
        return dict(kind="amendement", polarity=None, reason="suppression ET rétablissement dans le titre")
    if rem:
        kind = "motion" if re.search(r"motion|question préalable|irrecevabilité", t) else "amendement"
        return dict(kind=kind, polarity="remove", reason="titre : suppression/rejet")
    if res:
        return dict(kind="amendement", polarity="adopt", reason="titre : rétablissement")
    if _any(WHOLE, t):
        return dict(kind="ensemble", polarity="adopt", reason="vote sur l'ensemble du texte")
    if _any(ARTICLE, t) and not re.search(r"amendement", t):
        return dict(kind="article", polarity="adopt", reason="vote sur un article")
    if re.search(r"l'amendement", t):
        return dict(kind="amendement", polarity="adopt", reason="amendement ordinaire (le contenu doit être décrit à la main)")
    return dict(kind="autre", polarity=None, reason="titre non reconnu")


def button_labels(subject, polarity):
    """Libellés explicites. `subject` = groupe nominal décrivant ce qui est ADOPTÉ (adopt) ou SUPPRIMÉ (remove)."""
    s = subject.strip()
    if polarity == "remove":
        s = "la suppression " + _de(s)
    return f"Pour {s}", f"Contre {s}"


def _de(s):
    s = s.strip()
    return ("d'" + s[0:]) if s[:1].lower() in "aeiouyhéèêàâîôû" and not s.lower().startswith(("le ", "la ", "les ", "l'", "l’")) else \
        ("de " + s if not s.lower().startswith(("le ", "la ", "les ", "l'", "l’")) else _de_article(s))


def _de_article(s):
    low = s.lower()
    if low.startswith("le "):
        return "du " + s[3:]
    if low.startswith("les "):
        return "des " + s[4:]
    if low.startswith("la "):
        return "de la " + s[3:]
    return "de " + s[0:].replace("l’", "l'", 1) if low.startswith(("l'", "l’")) else "de " + s


def llm_check(client_call, titre, subject, polarity):
    """Vérification par un modèle. client_call(prompt)->str. Renvoie (ok:bool, raison:str).
    Échec fermé : toute réponse autre que 'OK' bloque la publication."""
    pour, _ = button_labels(subject, polarity)
    pr = (f"Titre officiel du scrutin : « {titre} »\nIntitulé du bouton : « {pour} ».\n"
          "Voter « pour » au scrutin correspond-il bien exactement à ce que dit ce bouton ? "
          "Attention aux amendements de suppression, de rejet, de rétablissement. "
          "Réponds par un seul mot : OK, INVERSE ou DOUTE.")
    ans = (client_call(pr) or "").strip().upper()
    word = re.sub(r"[^A-Z]", "", ans.split()[0]) if ans.split() else ""   # tolère « **OK** », « OK. »
    return word == "OK", ans[:80]
