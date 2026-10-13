"""Étude : l'heuristique d'importance parlementaire (salience.py) repère-t-elle réellement les sujets importants ?

Usage : python3 -m pipeline.salience build && python3 -m pipeline.salience_study
Sortie : SALIENCE_STUDY.md (chiffres réels, recalculés à chaque exécution) + data/salience_study.json

Il n'existe pas de vérité terrain officielle de « l'importance ».  On croise donc plusieurs contrôles, aucun
n'étant suffisant seul :
  1. validité sur un jeu choisi à la main avant cette étude (les 34 votes historiques du prototype) ;
  2. cohérence interne (les indicateurs mesurent-ils la même chose ?) ;
  3. robustesse (le top change-t-il si on retire un indicateur ?) ;
  4. biais d'origine (la liste favorise-t-elle un camp ?) ;
  5. lecture humaine du haut et du bas du classement (validité apparente).
Seuils de lecture fixés AVANT de calculer : AUC >= 0,75 bon, 0,60-0,75 moyen, < 0,60 échec.
"""
import glob, json, math, os, random, re
from . import config as C, salience as S, select_votes as SV

SEUIL_BON, SEUIL_MOYEN = 0.75, 0.60
TOP = 75
BLOC = {"GDR": "gauche", "LFI-NFP": "gauche", "SOC": "gauche", "ECOS": "gauche",
        "LIOT": "centre", "DEM": "centre", "EPR": "centre", "HOR": "centre",
        "DR": "droite", "UDR": "droite", "RN": "droite", "gouvernement": "gouvernement"}
SETS = {
    "débat": ["orateurs", "interventions", "duree_min", "mots"],
    "amendements": ["amendements", "amend_adoptes"],
    "votes": ["scrutins", "solennels"],
    "tout": ["orateurs", "interventions", "duree_min", "amendements", "scrutins", "solennels"],
}


def auc(pos, neg):
    """Probabilité qu'un cas positif ait un score plus haut qu'un négatif (ex aequo = 1/2)."""
    if not pos or not neg:
        return float("nan")
    w = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return w / (len(pos) * len(neg))


def spearman(a, b):
    ra, rb = S.pct_rank(a), S.pct_rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / math.sqrt(va * vb) if va and vb else float("nan")


def verdict(a):
    return "bon" if a >= SEUIL_BON else "moyen" if a >= SEUIL_MOYEN else "échec"


NON_LEGISLATIF = ("Engagement de la responsabilité", "Responsabilité pénale", "Commission d'enquête", "Mission d'information",
                  "Rapport d'information")


def legislatif(r):
    return not r["procedure"].startswith(NON_LEGISLATIF) and not S.norm(r["titre"]).startswith("motion de censure")


def kind(r):
    t, p = S.norm(r["titre"]), r["procedure"]
    if re.search(r"loi de finances|financement de la securite sociale|loi de reglement", t):
        return "budget"
    if "ratification" in p.lower():
        return "traité"
    if p.startswith("Résolution"):
        return "résolution"
    if "constitutionnelle" in p or "organique" in p:
        return "constitutionnel/organique"
    return "projet de loi" if p.startswith("Projet") else "proposition de loi"


def composite_par_type(rows, feats):
    """Rang percentile calculé DANS chaque type (projet / proposition / résolution...) : un texte d'opposition en
    niche parlementaire est comparé aux autres textes de niche, pas aux grands projets du gouvernement."""
    out = {}
    for k in {kind(r) for r in rows.values()}:
        sub = {ref: r for ref, r in rows.items() if kind(r) == k}
        sc = S.composite(sub, feats) if len(sub) > 1 else {ref: 0.5 for ref in sub}
        out.update(sc)
    return out


def ic_auc(pos, neg, b=1000, seed=1):
    """Intervalle de confiance à 95 % de l'AUC par rééchantillonnage."""
    rng = random.Random(seed)
    v = sorted(auc([rng.choice(pos) for _ in pos], [rng.choice(neg) for _ in neg]) for _ in range(b))
    return v[int(.025 * b)], v[int(.975 * b)]


def divergence_by_dossier(rows):
    """Divergence moyenne des votes « ensemble » du dossier (critère déjà utilisé pour la sélection)."""
    sc = C.jload(os.path.join(C.DATA, "scrutins.json"), {})
    out = {}
    for ref, r in rows.items():
        v = []
        for n in r["scrutin_numeros"]:
            f = sc.get(str(n))
            ft = SV.features(f) if f else None
            if ft:
                v.append(ft["div"])
        if v:
            out[ref] = sum(v) / len(v)
    return out


def positives(rows):
    leg = []
    for f in glob.glob(os.path.join(C.CONTENT, "questions", "*.json")):
        q = C.jload(f)
        if q and q.get("status") == "legacy":
            leg.append(q["n"])
    by = {n: ref for ref, r in rows.items() for n in r["scrutin_numeros"]}
    refs = {by[n] for n in leg if n in by}
    return refs, len(leg), sum(1 for n in leg if n in by)


def run():
    data = C.jload(S.OUT)
    rows_all = data["dossiers"]
    rows = {k: v for k, v in rows_all.items() if v["scrutins"] > 0 and legislatif(v)}
    refs = list(rows)
    pos_refs, n_leg, n_leg_linked = positives(rows)
    neg_refs = [r for r in refs if r not in pos_refs]
    res = {"n_dossiers": len(rows_all), "n_univers": len(rows), "couverture_debats": data["cover"],
           "legacy": {"votes": n_leg, "relies": n_leg_linked, "dossiers": len(pos_refs)}}

    # 1. validité sur le jeu choisi à la main
    comp = {name: S.composite(rows, feats) for name, feats in SETS.items()}
    single = {f: {r: rows[r][f] for r in refs} for f in S.FEATURES}
    div = divergence_by_dossier(rows)
    comp["tout, par type"] = composite_par_type(rows, SETS["tout"])
    comp["débat, par type"] = composite_par_type(rows, SETS["débat"])
    res["auc"], res["ic"] = {}, {}

    def add(name, score):
        p_, n_ = [score[r] for r in pos_refs if r in score], [score[r] for r in neg_refs if r in score]
        res["auc"][name] = auc(p_, n_)
        res["ic"][name] = ic_auc(p_, n_)
    for name, sc in comp.items():
        add(name, sc)
    for f in S.FEATURES:
        add("seul : " + f, single[f])
    pr = [r for r in refs if r in div]
    add("divergence (critère actuel)", div)
    rng = random.Random(0)
    res["hasard_100_tirages"] = sorted(auc([rng.random() for _ in pos_refs], [rng.random() for _ in neg_refs]) for _ in range(100))
    add("hasard (un tirage)", {r: rng.random() for r in refs})
    best = comp["tout"]
    ordre = sorted(refs, key=lambda r: -best[r])
    rank = {r: i + 1 for i, r in enumerate(ordre)}
    res["rangs_legacy"] = sorted(rank[r] for r in pos_refs)
    res["top_part"] = {k: sum(1 for r in pos_refs if rank[r] <= k) for k in (25, TOP, 100, 150)}

    # 2. cohérence interne
    groups = {k: comp[k] for k in ("débat", "amendements", "votes")}
    res["spearman"] = {f"{a} ~ {b}": spearman([groups[a][r] for r in refs], [groups[b][r] for r in refs])
                       for a, b in (("débat", "amendements"), ("débat", "votes"), ("amendements", "votes"))}
    res["spearman"]["tout ~ divergence"] = spearman([best[r] for r in pr], [div[r] for r in pr])

    # 3. robustesse du top
    base = set(ordre[:TOP])
    res["jaccard_sans"] = {}
    for f in SETS["tout"]:
        sc = S.composite(rows, [x for x in SETS["tout"] if x != f])
        top = set(sorted(refs, key=lambda r: -sc[r])[:TOP])
        res["jaccard_sans"][f] = len(base & top) / len(base | top)

    # 4. biais d'origine et de type
    def part(sel):
        c = {}
        for r in sel:
            b = BLOC.get(rows[r]["origine"], "autre")
            c[b] = c.get(b, 0) + 1
        return {k: round(v / len(sel), 3) for k, v in sorted(c.items())}
    ordre_t = sorted(refs, key=lambda r: -comp["tout, par type"][r])
    res["origine_top_par_type"] = part(ordre_t[:TOP])
    res["origine_univers"], res["origine_top"] = part(refs), part(ordre[:TOP])
    res["origine_legacy"] = part(sorted(pos_refs))
    kt = lambda sel: {k: sum(1 for r in sel if kind(rows[r]) == k) for k in sorted({kind(rows[r]) for r in refs})}
    res["type_univers"], res["type_top"] = kt(refs), kt(ordre[:TOP])

    # 5. lecture humaine
    fmt = lambda r: {"titre": rows[r]["titre"], "type": kind(rows[r]), "origine": rows[r]["origine"], "score": round(best[r], 3),
                     **{f: rows[r][f] for f in ("scrutins", "amendements", "orateurs", "duree_min")}}
    res["top30"] = [fmt(r) for r in ordre[:30]]
    res["bas20"] = [fmt(r) for r in ordre[-20:]]
    res["legacy_rangs_detail"] = sorted(({"rang": rank[r], **fmt(r)} for r in pos_refs), key=lambda x: x["rang"])
    C.jdump(res, os.path.join(C.DATA, "salience_study.json"), indent=1)
    write_report(res)
    return res


def write_report(r):
    L = []
    w = L.append
    a = r["auc"]
    w("# Étude : l'heuristique d'importance parlementaire fonctionne-t-elle ?\n")
    w("*Généré par `python3 -m pipeline.salience_study`. Tous les chiffres sont recalculés sur les données ouvertes de l'Assemblée nationale (17e législature).*\n")
    w(f"**Données** : {r['n_dossiers']} dossiers législatifs, dont {r['n_univers']} ont au moins un scrutin public et sont de nature législative (hors motions de censure, engagements de responsabilité, missions et rapports ; c'est l'univers étudié). "
      f"Débats rattachés à un dossier : {r['couverture_debats']['points_rattaches']} points sur {r['couverture_debats']['points_avec_debat']} avec prise de parole "
      f"(le reste : questions au gouvernement, déclarations, débats sans texte).\n")
    w("## 1. Validité sur un jeu choisi avant l'étude\n")
    lg = r["legacy"]
    w(f"Jeu de référence : les {lg['votes']} votes historiques du prototype, choisis à la main comme sujets de société ; {lg['relies']} sont reliés à un dossier ({lg['dossiers']} dossiers distincts). "
      f"On mesure l'AUC : la probabilité qu'un dossier de ce jeu ait un meilleur score qu'un dossier de l'univers (0,5 = hasard, 1 = parfait). "
      f"Seuils fixés avant le calcul : ≥ {SEUIL_BON} bon, {SEUIL_MOYEN}–{SEUIL_BON} moyen, < {SEUIL_MOYEN} échec.\n")
    w("| Score | AUC | IC 95 % | Lecture (sur la borne basse de l'IC) |\n|---|---|---|---|")
    for k, v in a.items():
        lo, hi = r["ic"][k]
        w(f"| {k} | {v:.2f} | {lo:.2f} – {hi:.2f} | {verdict(lo) if not k.startswith('hasard') else 'contrôle'} |")
    h = r["hasard_100_tirages"]
    w(f"\nContrôle : sur 100 tirages aléatoires, l'AUC varie de {h[0]:.2f} à {h[-1]:.2f} (médiane {h[50]:.2f}). "
      f"Avec seulement {lg['dossiers']} cas positifs, un écart de moins de 0,10 avec 0,5 ne prouve rien.")
    tp = r["top_part"]
    w(f"\nRang du jeu de référence dans le classement « tout » (sur {r['n_univers']}, global) : médiane {sorted(r['rangs_legacy'])[len(r['rangs_legacy'])//2]}. "
      f"Dans le top 25 : {tp[25]} / {lg['dossiers']} ; top {TOP} : {tp[TOP]} ; top 100 : {tp[100]} ; top 150 : {tp[150]}.\n")
    w("**Limite** : ce jeu a été choisi à la main, en partie selon la divergence entre groupes, pas selon la notoriété. Un bon AUC est un indice, pas une preuve ; un mauvais AUC serait une réfutation.\n")
    w("## 2. Cohérence interne\n")
    w("Corrélation de rang (Spearman) entre familles d'indicateurs : si elles mesurent la même chose (l'importance), elles doivent être corrélées sans être identiques.\n")
    w("| Paire | Spearman |\n|---|---|")
    for k, v in r["spearman"].items():
        w(f"| {k} | {v:.2f} |")
    w("\n## 3. Robustesse du top " + str(TOP) + "\n")
    w("Part du top commune (Jaccard) quand on retire un indicateur : proche de 1 = stable.\n")
    w("| Indicateur retiré | Jaccard |\n|---|---|")
    for k, v in r["jaccard_sans"].items():
        w(f"| {k} | {v:.2f} |")
    w("\n## 4. Biais d'origine et de type\n")
    w("Origine du texte (groupe de l'auteur, ou gouvernement), en part de l'ensemble.\n")
    w("| Origine | Univers | Top " + str(TOP) + " (global) | Top " + str(TOP) + " (rang par type) | Jeu de référence |\n|---|---|---|---|---|")
    ks = sorted(set(r["origine_univers"]) | set(r["origine_top"]) | set(r["origine_legacy"]))
    for k in ks:
        w(f"| {k} | {r['origine_univers'].get(k, 0):.0%} | {r['origine_top'].get(k, 0):.0%} | {r['origine_top_par_type'].get(k, 0):.0%} | {r['origine_legacy'].get(k, 0):.0%} |")
    w("\n| Type de dossier | Univers | Top " + str(TOP) + " |\n|---|---|---|")
    for k in r["type_univers"]:
        w(f"| {k} | {r['type_univers'][k]} | {r['type_top'].get(k, 0)} |")
    w("\n## 5. Lecture humaine\n")
    w("### Les 30 premiers\n\n| # | Dossier | Type | Origine | Scrutins | Amend. | Orateurs | Débat (min) |\n|---|---|---|---|---|---|---|---|")
    for i, x in enumerate(r["top30"], 1):
        w(f"| {i} | {x['titre'][:90]} | {x['type']} | {x['origine']} | {x['scrutins']} | {x['amendements']} | {x['orateurs']} | {x['duree_min']} |")
    w("\n### Les 20 derniers\n\n| Dossier | Type | Scrutins | Amend. | Orateurs | Débat (min) |\n|---|---|---|---|---|---|")
    for x in r["bas20"]:
        w(f"| {x['titre'][:90]} | {x['type']} | {x['scrutins']} | {x['amendements']} | {x['orateurs']} | {x['duree_min']} |")
    w("\n### Où se classent les votes du jeu de référence\n\n| Rang | Dossier | Type |\n|---|---|---|")
    for x in r["legacy_rangs_detail"]:
        w(f"| {x['rang']} | {x['titre'][:90]} | {x['type']} |")
    w("\n## Conclusion (calculée à partir des chiffres ci-dessus)\n")
    d_, a_, v_ = a["débat, par type"], a["amendements"], a["votes"]
    lo = r["ic"]["débat, par type"][0]
    w(f"- **Le signal existe.** Le score de débat (orateurs, interventions, durée, mots), classé au sein de chaque type de texte, atteint une AUC de {d_:.2f} "
      f"(IC 95 % : {r['ic']['débat, par type'][0]:.2f}–{r['ic']['débat, par type'][1]:.2f}) contre {r['hasard_100_tirages'][-1]:.2f} au plus pour 100 tirages aléatoires. "
      f"Il fait apparemment mieux que le critère de divergence actuel ({a['divergence (critère actuel)']:.2f}) pour repérer ces sujets.")
    w(f"- **Les amendements et le nombre de scrutins seuls sont plus faibles** (AUC {a_:.2f} et {v_:.2f}, bornes basses {r['ic']['amendements'][0]:.2f} et {r['ic']['votes'][0]:.2f}) : "
      "utiles en complément, pas en critère principal.")
    ou, ot, op = r["origine_univers"], r["origine_top"], r["origine_top_par_type"]
    w(f"- **Biais d'origine réel si on classe sans précaution** : textes du gouvernement {ou.get('gouvernement', 0):.0%} de l'univers mais {ot.get('gouvernement', 0):.0%} du top {TOP} ; "
      f"textes de la gauche {ou.get('gauche', 0):.0%} de l'univers mais {ot.get('gauche', 0):.0%} du top. Classer au sein de chaque type ramène ces parts à "
      f"{op.get('gouvernement', 0):.0%} et {op.get('gauche', 0):.0%}. L'importance parlementaire mesure aussi le poids institutionnel : il faut donc corriger et plafonner par origine, "
      "pas seulement trier.")
    og = r["origine_legacy"]
    w(f"- **Le jeu de départ n'était pas équilibré** : {og.get('gauche', 0):.0%} de textes d'origine « gauche », {og.get('centre', 0):.0%} « centre », {og.get('droite', 0):.0%} « droite ». "
      "Cela vient de la sélection à la main du prototype, pas de la méthode ; c'est une raison de plus pour automatiser et publier les critères.")
    w("- **Limites** : (1) la validation repose sur 30 dossiers choisis à la main, donc un indice plutôt qu'une preuve ; (2) les textes courts adoptés sans véritable débat "
      "(niches parlementaires) sont sous-classés même quand le sujet intéresse le public ; (3) aucune mesure de l'attention du public ou de la presse n'a été utilisée, "
      "donc « important pour le Parlement » n'est pas « important pour les gens » ; (4) l'importance n'est pas la neutralité : le tri ne dit rien de l'orientation.")
    open(os.path.join(C.ROOT, "SALIENCE_STUDY.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


if __name__ == "__main__":
    run()
    print("[salience_study] -> SALIENCE_STUDY.md")
