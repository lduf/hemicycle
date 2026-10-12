"""Récupération des textes officiels qui nourrissent les fiches. Domaines autorisés uniquement."""
import re, subprocess, html
from urllib.parse import urlparse
from . import config as C

ALLOWED = ("assemblee-nationale.fr", "senat.fr", "legifrance.gouv.fr", "vie-publique.fr", "conseil-constitutionnel.fr",
           "gouv.fr", "data.gouv.fr", "europa.eu", "elysee.fr", "conseil-etat.fr")


def allowed(url):
    h = (urlparse(url).hostname or "").lower()
    return urlparse(url).scheme == "https" and any(h == d or h.endswith("." + d) for d in ALLOWED)


def fetch_text(url, limit=12000):
    if not allowed(url):
        raise ValueError(f"domaine non autorisé : {url}")
    r = subprocess.run(["curl", "-fsSL", "--max-time", "40", "--retry", "2", url], capture_output=True, timeout=90)
    if r.returncode:
        raise RuntimeError(f"téléchargement impossible : {url}")
    t = r.stdout.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t).strip()[:limit]


def scrutin_url(n):
    return C.URL_SCRUTIN_PAGE.format(n=n)
