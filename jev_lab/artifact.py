"""Page de présentation (HTML autonome) générée depuis summary.json : `python -m jev_lab artifact <dossier_de_run> [sortie.html]`.
Aucun chiffre n'est saisi à la main : le gabarit (artifact_template.html) lit les données incorporées."""
import json, os, statistics

TEMPLATE = os.path.join(os.path.dirname(__file__), "artifact_template.html")


def payload(run_dir, luna_dir=None):
    with open(os.path.join(run_dir, "summary.json"), encoding="utf-8") as f:
        s = json.load(f)
    s.pop("latency_samples", None)
    out = {"summary": s}
    # durée d'un appel de la référence Claude (claude -p), quand elle a tourné : démarrage du programme inclus
    walls = []
    p = os.path.join(run_dir, "calls.jsonl")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("system") not in (None, "jev") and r.get("ok") and r.get("wall_s") is not None and r.get("experiment") == "quality":
                    walls.append(r["wall_s"])
    if luna_dir:                                      # second système de l'API Decisions (GPT-6 Luna), même jeu d'essai : sa clé « jev » désigne Luna
        with open(os.path.join(luna_dir, "summary.json"), encoding="utf-8") as f:
            ls = json.load(f)
        ls.pop("latency_samples", None)
        out["luna"] = ls
    if walls:
        out["claude_wall"] = {"p50": statistics.median(walls), "n": len(walls)}
    return out


def build(run_dir, out_path=None, luna_dir=None):
    data = json.dumps(payload(run_dir, luna_dir), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = open(TEMPLATE, encoding="utf-8").read().replace("__DATA__", data)
    out_path = out_path or os.path.join(run_dir, "presentation.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    import sys
    print(build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))


def site_summary(run_dir, rapport_url=None):
    """content/jev_summary.json pour la page Méthode du site : mêmes chiffres que la présentation, en peu de mots."""
    s = payload(run_dir)["summary"]
    if not all(k in s["decisions"] and "jev" in s["decisions"][k] for k in ("sens", "neutralite", "pro_contre")):
        return None                                  # run partiel (smoke) : pas de résumé pour le site
    J, c = s["decisions"], s["categorie"]["jev"]
    pct = lambda x: (f"{100 * x:.1f}" if x < 0.1 else f"{100 * x:.0f}").replace(".", ",") + " %"
    rate = lambda r: f"{pct(r['p'])} ({r['k']}/{r['n']})"
    ex = s.get("explo_sens_titre")
    out = {
        "titre": "Jev à l'essai : ce qu'il sait contrôler",
        "lede": "Jev est un modèle qui répond par des probabilités. Le pipeline lui confie quatre contrôles sur les fiches. "
                "On a rejoué ces contrôles " + f"{s['n_calls']:,}".replace(",", "\u202f") + " fois sur de vraies fiches et des défauts fabriqués, puis compté ce qui passe et ce qui est refusé à tort.",
        "chiffres": [
            {"label": "Neutralité : textes orientés qui passent", "valeur": rate(J["neutralite"]["jev"]["far"]), "note": "limite fixée à 10 %"},
            {"label": "Neutralité : bonnes fiches refusées", "valeur": rate(J["neutralite"]["jev"]["frr"]), "note": "limite fixée à 25 %"},
            {"label": "Catégorie : bonne réponse", "valeur": rate(c["top1"]), "note": "34 fiches classées à la main : jeu trop petit pour mieux"},
            {"label": "Pour / contre : défauts qui passent", "valeur": rate(J["pro_contre"]["jev"]["far"]), "note": "mais " + rate(J["pro_contre"]["jev"]["frr"]) + " des bonnes fiches sont refusées"},
            {"label": "Sens du vote : boutons inversés qui passent", "valeur": rate(J["sens"]["jev"]["far"]), "note": "limite fixée à 2 % : ce contrôle ne peut pas être confié à Jev tel quel"},
        ],
    }
    # conclusion déduite des intervalles, avec les limites du protocole (sens 2 %, neutralité et pour/contre 10 %, faux rejets 25 %)
    ok = lambda sc, fl: J[sc]["jev"]["far"]["ci"][1] <= fl and J[sc]["jev"]["frr"]["ci"][1] <= 0.25
    parts = []
    parts.append("Jev tient le contrôle de neutralité" if ok("neutralite", 0.10) else "Le contrôle de neutralité de Jev est à revoir")
    parts.append("et classe bien les fiches" if c["top1"]["p"] >= 0.8 else "et classe mal les fiches")
    pc = J["pro_contre"]["jev"]
    if pc["far"]["ci"][1] <= 0.10 and pc["frr"]["ci"][0] > 0.25:
        parts.append("; il refuse trop de bonnes fiches sur les arguments pour/contre")
    sn = J["sens"]["jev"]
    if sn["far"]["ci"][0] > 0.02:
        parts.append(", et il ne sait pas vérifier seul le sens d'un vote tel que le pipeline le lui demande")
    out["verdict"] = " ".join(parts).replace(" ;", ";").replace(" ,", ",") + "."
    if ex:
        out["chiffres"].append({"label": "Sens du vote lu sur le titre seul (piste)", "valeur": rate(ex["far"]), "note": "boutons inversés qui passent ; à confirmer sur de nouveaux votes"})
    if rapport_url:
        out["rapport_url"] = rapport_url
    return out
