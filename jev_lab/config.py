"""Constantes de l'étude.  Les « revendications » sont celles du fournisseur : on les teste, on ne les croit pas."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(ROOT, "runs")
CACHE = os.path.join(ROOT, "cache")

BASE = os.environ.get("JEVLAB_BASE_URL", "https://openrouter.ai").rstrip("/")   # remplacé par le serveur factice en test
JEV_URL = BASE + "/api/alpha/decisions"
CHAT_URL = BASE + "/api/v1/chat/completions"
MODELS_URL = BASE + "/api/v1/models"
CREDITS_URL = BASE + "/api/v1/credits"


def set_base(base):
    """Redirige tous les appels (serveur factice pour les tests et la démonstration)."""
    global BASE, JEV_URL, CHAT_URL, MODELS_URL, CREDITS_URL
    BASE = base.rstrip("/")
    JEV_URL, CHAT_URL = BASE + "/api/alpha/decisions", BASE + "/api/v1/chat/completions"
    MODELS_URL, CREDITS_URL = BASE + "/api/v1/models", BASE + "/api/v1/credits"


JEV_MODEL = os.environ.get("JEVLAB_JEV_MODEL", "typesafe/jev-1.13")   # alias de la version 1.13 (la réponse donne le millésime)

# Familles de modèles de comparaison, résolues à l'exécution sur le catalogue OpenRouter (le plus récent qui correspond).
# On les fige ensuite dans meta.json du run : un résultat doit toujours dire contre QUEL modèle il a été obtenu.
BASELINE_PATTERNS = {
    "claude-petit": r"^anthropic/claude-[\w.\-]*haiku[\w.\-]*$",
    "claude-grand": r"^anthropic/claude-[\w.\-]*opus[\w.\-]*$",
    "gpt-petit": r"^openai/gpt-[\w.\-]*(mini|nano)[\w.\-]*$",
    "gemini-flash": r"^google/gemini-[\w.\-]*flash[\w.\-]*$",
}

# Revendications à tester (source : docs OpenRouter, lues le 2026-10-13).
CLAIMS = {
    "prix_entree_par_M": (0.042, "$ / million de tokens d'entrée", "blog OpenRouter « Jev vs LLM », 2026-09-19"),
    "prix_sortie_par_M": (0.0, "$ / million de tokens de sortie (gratuit)", "doc OpenRouter Jev"),
    "contexte_doc": (32000, "tokens (doc hub)", "openrouter.ai/docs/guides/community/jev"),
    "contexte_blog": (64000, "tokens par requête (blog ; 32k pour state + question la plus longue)", "blog « Jev vs LLM »"),
    "latence_p50_s": (0.194, "s, tickets courts, mesuré par l'auteur du blog", "blog « Jev vs LLM »"),
    "latence_p95_s": (0.633, "s, idem", "blog « Jev vs LLM »"),
    "calibration": ("≈ 80 % de réussite quand la probabilité est 0,8", "affirmé, non mesuré", "blog « Jev vs LLM »"),
    "determinisme": ("« légèrement différent d'une exécution à l'autre »", "affirmé", "tutoriel OpenRouter Jev"),
    "faiblesses": ("arithmétique, comptage, comparaison de dates, détails non pertinents", "annoncé par l'éditeur", "blog « Jev vs LLM »"),
}

# Seuils de lecture FIXÉS AVANT les mesures (voir PROTOCOL.md).  Les modifier après coup invalide l'étude.
PREREG = {
    "delta_non_inferiorite": 0.03,     # écart de précision toléré face à une référence (3 points)
    "ece_bon": 0.05, "ece_acceptable": 0.10,
    "gain_cout_significatif": 10.0,    # « nettement moins cher » = au moins 10 fois
    "gain_latence_significatif": 2.0,  # « nettement plus rapide » = au moins 2 fois (p50)
    "flip_max_determinisme": 0.02,     # au plus 2 % d'étiquettes qui changent à l'identique
    "tolerance_prix": 0.05,            # écart toléré entre coût facturé et tokens × tarif
    "utilisable": 0.90,                # une précision d'au moins 90 % est « utilisable » pour une décision automatique
    "chute_bruit_max": 0.03,           # perte de précision tolérée avec du texte non pertinent ajouté
    "flip_permutation_max": 0.03,      # étiquettes tolérées changées par une permutation de l'ordre des options
}

# Critères de sûreté de la PRODUCTION hémicycle, fixés avant les mesures (à valider avec le responsable du projet : voir PROTOCOL.md §5).
#   far = fausse acceptation (un défaut passe : bouton inversé, fiche orientée, arguments inversés) ; frr = faux rejet (une bonne entrée est refusée).
SAFETY = {
    "sens":       {"far": 0.02, "frr": 0.25},   # publier un bouton inversé est l'erreur la plus grave
    "neutralite": {"far": 0.10, "frr": 0.25},   # détecter au moins 90 % des fiches fortement orientées
    "pro_contre": {"far": 0.10, "frr": 0.25},
}
CATEGORIE = {"top1_min": 0.80, "precision_acceptees_min": 0.90}

SEED = 20261013
