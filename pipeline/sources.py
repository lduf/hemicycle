"""Récupération des textes officiels qui nourrissent les fiches. Domaines autorisés uniquement."""
import re, subprocess, html, time
from urllib.parse import urlparse
from . import config as C

ALLOWED = ("assemblee-nationale.fr", "senat.fr", "legifrance.gouv.fr", "vie-publique.fr", "conseil-constitutionnel.fr",
           "gouv.fr", "data.gouv.fr", "europa.eu", "elysee.fr", "conseil-etat.fr")


def allowed(url):
    h = (urlparse(url).hostname or "").lower()
    return urlparse(url).scheme == "https" and any(h == d or h.endswith("." + d) for d in ALLOWED)


def fetch_html(url, attempts=3):
    if not allowed(url):
        raise ValueError(f"domaine non autorisé : {url}")
    for i in range(attempts):
        r = subprocess.run(["curl", "-fsSL", "--max-time", "40", "--retry", "2", url], capture_output=True, timeout=90)
        if not r.returncode:
            return r.stdout.decode("utf-8", "replace")
        time.sleep(2 ** (i + 1))
    raise RuntimeError(f"téléchargement impossible : {url}")


def fetch_text(url, limit=12000, after=None):
    t = fetch_html(url)
    t = re.sub(r"(?is)<(script|style|nav|header|footer)[^>]*>.*?</\1>", " ", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t).strip()
    if after:                      # ex. « EXPOSÉ DES MOTIFS » : on saute la liste des signataires
        i = t.find(after)
        if i >= 0:
            t = t[i:]
    return t[:limit]


def scrutin_url(n):
    return C.URL_SCRUTIN_PAGE.format(n=n)


def discover(n, dossier_ref=None):
    """Sources officielles d'un scrutin : page du dossier législatif + texte initial (exposé des motifs),
    trouvés depuis la page officielle du scrutin, ou directement depuis la référence du dossier (`dossier_ref`, connue de la
    sélection) quand la page du scrutin n'y renvoie pas. Liste vide si le scrutin n'a pas de dossier."""
    if dossier_ref:
        dossier = "https://www.assemblee-nationale.fr/dyn/17/dossiers/" + dossier_ref
    else:
        page = fetch_html(scrutin_url(n))
        m = re.search(r'href="(?:https://www\.assemblee-nationale\.fr)?(/dyn/17/dossiers/[A-Za-z0-9_\\-]+)"', page)
        if not m:
            return []
        dossier = "https://www.assemblee-nationale.fr" + m.group(1)
    d = fetch_html(dossier)
    # texte initial = exposé des motifs (première version déposée) ; à défaut, tout texte déposé
    pats = [r"l17b\d+_(?:projet-loi|proposition-loi|projet-loi-organique|proposition-loi-organique|proposition-resolution)",
            r"l17b\d+_(?:projet|proposition)[a-z\-]*"]
    for pat in pats:
        t = re.search(r'href="(https://www\.assemblee-nationale\.fr/dyn/17/textes/' + pat + r')"', d)
        if t:
            # la page « texte » n'est qu'une coquille : le texte intégral est la version HTML open data
            h = re.search(r'href="(/dyn/opendata/[A-Z0-9]+\.html)"', fetch_html(t.group(1)))
            out = [("https://www.assemblee-nationale.fr" + h.group(1)) if h else t.group(1)]  # texte d'abord
            r = rapport_url(d)
            if r:
                out.append(r)     # rapport de commission : analyse et critiques documentées
            return out + [dossier]
    return [dossier]


def body_start(t):
    """Début du corps d'un rapport, après la table des matières : « Mesdames, Messieurs, » sinon 2e « INTRODUCTION »."""
    m = re.search(r"(?i)M\s*esdames\s*,\s*M\s*essieurs", t)
    if m:
        return m.start()
    ms = [x.start() for x in re.finditer(r"INTRODUCTION", t)]
    return ms[1] if len(ms) > 1 else 0


def rapport_url(dossier_html):
    m = re.search(r'href="(https://www\.assemblee-nationale\.fr/dyn/17/rapports/[A-Za-z0-9_/]+_rapport-fond)"', dossier_html)
    if not m:
        return None
    h = re.search(r'href="(/dyn/opendata/RAPPANR5L17B\d+\.html)"', fetch_html(m.group(1)))
    return "https://www.assemblee-nationale.fr" + h.group(1) if h else None
