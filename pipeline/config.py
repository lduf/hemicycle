"""Configuration commune. Tout est surchargeable par variable d'environnement."""
import os, json

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA = os.environ.get("HEMI_DATA", os.path.join(ROOT, "data"))          # données dérivées (régénérables)
RAW = os.environ.get("HEMI_RAW", os.path.join(ROOT, "an_data"))          # téléchargements bruts AN
CONTENT = os.environ.get("HEMI_CONTENT", os.path.join(ROOT, "content"))  # contenu éditorial (versionné)
SITE = os.environ.get("HEMI_SITE", os.path.join(ROOT, "docs"))           # site statique généré
TEMPLATE = os.path.join(ROOT, "pipeline", "templates", "template.html")

URL_SCRUTINS = "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip"
URL_AMO = ("https://data.assemblee-nationale.fr/static/openData/repository/17/amo/"
           "deputes_actifs_mandats_actifs_organes/AMO10_deputes_actifs_mandats_actifs_organes.json.zip")
URL_SCRUTIN_PAGE = "https://www.assemblee-nationale.fr/dyn/17/scrutins/{n}"
LICENCE = "Licence Ouverte / Open Licence v2.0 (Etalab) : https://www.etalab.gouv.fr/licence-ouverte-open-licence/"

# Alias de groupes : identifiants successifs d'un même groupe -> sigle. NI = non-inscrits.
ALIAS = {"PO847173": "UDR", "PO872880": "UDR", "PO840056": "NI"}
SCORED = ["RN", "EPR", "LFI-NFP", "SOC", "DR", "ECOS", "DEM", "HOR", "LIOT", "GDR", "UDR"]
ORDER = ["GDR", "LFI-NFP", "ECOS", "SOC", "LIOT", "DEM", "EPR", "HOR", "DR", "UDR", "RN", "NI"]  # gauche -> droite
GROUP_NAMES = {
    "RN": "Rassemblement National", "EPR": "Ensemble pour la République", "LFI-NFP": "La France insoumise",
    "SOC": "Socialistes et apparentés", "DR": "Droite Républicaine", "ECOS": "Écologiste et Social",
    "DEM": "Les Démocrates", "HOR": "Horizons & Indépendants",
    "LIOT": "Libertés, Indépendants, Outre-mer et Territoires", "GDR": "Gauche Démocrate et Républicaine",
    "UDR": "Union des droites pour la République",
}
CATS = ["Éducation", "Sport", "Écologie & énergie", "Économie & fiscalité", "Famille & social", "Santé & fin de vie",
        "Justice & sécurité", "Immigration", "Numérique", "Défense", "Agriculture", "Droits & société",
        "Institutions", "Logement", "Transports", "Culture & médias"]

# Modèles (API Anthropic). Sans ANTHROPIC_API_KEY, les étapes « modèle » sont ignorées et la fiche reste bloquée.
MODEL_WRITER = os.environ.get("HEMI_MODEL_WRITER", "claude-sonnet-5-5")
MODEL_JUDGE = os.environ.get("HEMI_MODEL_JUDGE", "claude-opus-5-5")  # second modèle, distinct de l'auteur

# Règles éditoriales
MIN_REVIEWERS = 2
SENSIBILITIES = ("gauche", "droite")  # il faut au moins une relecture de chaque bord (ou « centre » en renfort)
NEUTRALITY_MAX = 2                    # note d'orientation du second modèle : 0 neutre ... 5 très orienté
SUM_MIN_LINES, SUM_MAX_LINES = 3, 5


def p(*parts):
    path = os.path.join(*parts)
    os.makedirs(os.path.dirname(path) if os.path.splitext(path)[1] else path, exist_ok=True)
    return path


def jload(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def jdump(obj, path, indent=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, sort_keys=indent is not None)
    os.replace(tmp, path)
