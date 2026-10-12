import json, glob, os

BASE = os.path.dirname(os.path.abspath(__file__))
G = json.load(open(os.path.join(BASE, "groups17.json")))

# Identifiants de groupe -> sigle affiché. UDR apparaît sous deux identifiants (avant / après sept. 2025) : fusionnés.
ALIAS = {"PO847173": "UDR", "PO872880": "UDR"}
KEEP = {"RN", "EPR", "LFI-NFP", "SOC", "DR", "ECOS", "DEM", "HOR", "LIOT", "GDR", "UDR"}

GROUP_NAMES = {
    "RN": "Rassemblement National",
    "EPR": "Ensemble pour la République",
    "LFI-NFP": "La France insoumise",
    "SOC": "Socialistes et apparentés",
    "DR": "Droite Républicaine",
    "ECOS": "Écologiste et Social",
    "DEM": "Les Démocrates",
    "HOR": "Horizons & Indépendants",
    "LIOT": "Libertés, Indépendants, Outre-mer et Territoires",
    "GDR": "Gauche Démocrate et Républicaine",
    "UDR": "Union des droites pour la République",
}

CATS = [
    "Éducation", "Sport", "Écologie & énergie", "Économie & fiscalité", "Famille & social",
    "Santé & fin de vie", "Justice & sécurité", "Immigration", "Numérique", "Défense",
    "Agriculture", "Droits & société",
]

# Aucun nom de parti, de groupe ni de personne dans les textes affichés pendant le vote.
# kind = "mesure" (scrutin sur une mesure précise) ou "texte" (scrutin sur l'ensemble d'un texte).
Q = [
    dict(n=7397, kind="texte", cat="Éducation", title="Bourses étudiantes : indexation et versement sur 12 mois",
         sum="Proposition de loi sur les bourses sur critères sociaux. Elle indexe chaque année les montants et les barèmes au moins sur l'inflation, et verse la bourse sur douze mois au lieu de dix. Coût estimé à un peu plus de 540 millions d'euros par an ; un chiffre proche de 400 millions a aussi été avancé.",
         pro="Le système actuel ne remplit plus son rôle de démocratisation de l'enseignement supérieur, et les mesures sont simples à appliquer.",
         con="Le coût pour les finances publiques. Certains préfèrent une réforme d'ensemble, qui inclurait aussi une partie des classes moyennes aujourd'hui exclues."),
    dict(n=7893, kind="texte", cat="Sport", title="Organisation et financement du sport professionnel",
         sum="Proposition de loi déposée après une mission d'information sur le financement du football. Selon la version négociée avec le Sénat, elle renforce le rôle des fédérations, plafonne certaines rémunérations de dirigeants, encadre les agents sportifs (formation, déclaration des sommes perçues), crée des comités de dialogue avec les supporters et donne un pouvoir de contrôle à la DNCG sur les ventes de clubs. Elle contient aussi des mesures contre le piratage et sur les paris sportifs.",
         pro="Un encadrement plus strict des clubs, des agents et des rémunérations, avec un contrôle financier renforcé.",
         con="Certains jugent que le texte vise surtout le football et peut affecter le rugby et d'autres sports. Le niveau du plafond des salaires et la multipropriété des clubs font débat."),
    dict(n=2521, kind="mesure", cat="Écologie & énergie", title="Relancer la construction de réacteurs nucléaires",
         sum="Article d'un texte sur la programmation de l'énergie. Il vise environ 27 GW de nouvelles capacités nucléaires d'ici 2050, avec au moins 10 GW de constructions lancées dès 2026, et le maintien du parc existant à au moins 63 GW. Six réacteurs EPR2 sont déjà engagés, et la décision d'en construire huit de plus doit être prise d'ici fin 2026. Un coût de 67 milliards d'euros est évoqué pour le nouveau nucléaire.",
         pro="Les partisans jugent cette relance nécessaire et contestent les craintes sur la sûreté et la durabilité des installations.",
         con="Les opposants dénoncent un manque de transparence sur les données et les coûts, et un engagement sur des durées très longues. D'autres défendent une place plus mesurée du nucléaire dans le mix électrique."),
    dict(n=2580, kind="mesure", cat="Écologie & énergie", title="Suspendre tout nouveau projet éolien et photovoltaïque (moratoire)",
         sum="Amendement ajouté à un texte sur la programmation de l'énergie. Il suspend le développement de toute nouvelle installation éolienne et photovoltaïque, dès la promulgation de la loi. La durée et les exceptions ne sont pas précisées dans les sources consultées. Il a été adopté de justesse (65 voix contre 62), dans un hémicycle très peu rempli.",
         pro="Les partisans jugent l'éolien et le solaire coûteux et intermittents.",
         con="Les opposants jugent la mesure dévastatrice pour les industriels du secteur, estiment qu'elle détruirait des dizaines de milliers d'emplois (80 000 selon une organisation professionnelle) et y voient une menace pour le climat."),
    dict(n=881, kind="texte", cat="Économie & fiscalité", title="Impôt plancher de 2 % sur les très gros patrimoines",
         sum="Proposition de loi. Elle crée un impôt minimum de 2 % par an sur les patrimoines supérieurs à 100 millions d'euros, soit environ 1 800 personnes. Les biens professionnels sont inclus. L'objectif affiché est de limiter les contournements, notamment par les holdings patrimoniales.",
         pro="Corriger une injustice fiscale. Selon les partisans, le texte ne toucherait pas les petits entrepreneurs ou artisans.",
         con="Les opposants jugent la mesure inefficace, confiscatoire, et contraire à la jurisprudence constitutionnelle pour un taux de 2 %. Ils craignent une fiscalité punitive qui nuirait à l'attractivité du pays."),
    dict(n=4438, kind="texte", cat="Économie & fiscalité", title="Nationalisation d'ArcelorMittal France",
         sum="Proposition de loi. Elle transfère à l'État la totalité du capital d'ArcelorMittal France. Le coût est estimé entre 3 et 4 milliards d'euros selon les députés qui l'ont chiffré.",
         pro="Faire de la France un leader de l'acier décarboné plutôt que de laisser décliner son industrie.",
         con="Les opposants estiment que la nationalisation ne répond pas à la nature du problème, la protection de l'acier se jouant à Bruxelles. Ils craignent de donner de faux espoirs aux salariés."),
    dict(n=2272, kind="texte", cat="Famille & social", title="Allocations familiales dès le premier enfant",
         sum="Proposition de loi. Les allocations familiales sont aujourd'hui versées à partir du deuxième enfant, sauf en outre-mer où elles le sont dès le premier. Le texte étend le versement dès le premier enfant à tout le territoire. Coût estimé entre 3 et 4 milliards d'euros par an.",
         pro="Un peu plus d'un tiers des familles n'ont qu'un enfant, donc le seuil actuel ne correspond plus à leur réalité. Défense de l'universalité de la prestation.",
         con="Le manque de marges budgétaires. Selon certains, la mesure n'aurait pas d'effet redistributif pour les familles modestes, car le RSA et la prime d'activité baisseraient mécaniquement."),
    dict(n=5729, kind="texte", cat="Santé & fin de vie", title="Aide à mourir (deuxième lecture)",
         sum="Texte créant un droit à l'aide à mourir pour certaines personnes en fin de vie, sous conditions. Dans la version votée, la personne prend elle-même la substance létale. Un soignant ne peut l'administrer que si la personne est dans l'incapacité physique de le faire. Une souffrance psychologique seule ne donne pas accès à l'aide à mourir. Vote de conscience : les députés d'un même groupe sont souvent partagés.",
         pro="Reconnaître un droit encadré à choisir sa fin de vie. Une partie des élus voulait laisser le choix entre auto-administration et administration par un soignant.",
         con="Une partie des députés s'oppose au principe même d'une aide active à mourir. D'autres critiquent la précision sur la souffrance psychologique, qui crée selon eux une hiérarchie des souffrances."),
    dict(n=805, kind="texte", cat="Justice & sécurité", title="Justice des mineurs : excuse de minorité et comparution immédiate",
         sum="Proposition de loi. Elle atténue l'excuse de minorité pour les mineurs de plus de 16 ans en récidive pour des faits graves. Elle crée une comparution immédiate pour les mineurs. Elle rend les parents civilement responsables, solidairement et de plein droit, des dommages causés par leur enfant.",
         pro="Les partisans estiment que les mineurs sont davantage impliqués dans certaines infractions, comme les violences et les trafics, et que des réseaux les recrutent parce que la justice les traite plus légèrement.",
         con="Les opposants rappellent que les juges pour enfants peuvent déjà écarter l'excuse de minorité, et jugent ces mesures trop répressives."),
    dict(n=7987, kind="texte", cat="Justice & sécurité", title="Présomption d'usage légitime de l'arme pour policiers et gendarmes",
         sum="Proposition de loi. Elle instaure une présomption de légitime défense pour les policiers et gendarmes face à une menace réelle, immédiate et grave. En commission, cette formule a été remplacée par une « présomption d'usage légitime de l'arme ».",
         pro="Répondre à une évolution inquiétante des violences contre les policiers et les gendarmes.",
         con="Des opposants parlent d'un « permis de tuer » et citent la hausse des tirs mortels liés aux refus d'obtempérer. Une pétition de près de 85 000 signatures s'oppose au texte."),
    dict(n=4754, kind="texte", cat="Immigration", title="Renouvellement automatique des titres de séjour de longue durée",
         sum="Proposition de loi. L'administration renouvellerait automatiquement les titres de séjour de longue durée, sauf si elle a des motifs juridiques de s'y opposer, qu'elle devrait alors démontrer.",
         pro="Les délais de renouvellement plongent dans la précarité des personnes installées depuis longtemps en France. Selon une élue, 99,5 % des titres sont renouvelés.",
         con="Certains jugent le texte juridiquement fragile et inefficace. D'autres y voient un renversement de la charge de la preuve et une réduction du pouvoir d'appréciation de l'administration."),
    dict(n=5192, kind="texte", cat="Numérique", title="Interdiction des réseaux sociaux avant 15 ans",
         sum="Proposition de loi. L'accès aux réseaux sociaux serait interdit aux moins de 15 ans et les comptes existants seraient suspendus. Les messageries privées sont exclues. L'usage du téléphone portable serait aussi interdit dans les lycées. Pour l'âge, le texte s'appuie sur la possibilité, ouverte par le droit européen, de fixer une limite nationale.",
         pro="Protéger la santé mentale des adolescents face aux algorithmes, et agir au niveau national en attendant une action européenne.",
         con="Il n'existe pas d'outil fiable de vérification de l'âge, et il est difficile de contraindre les plateformes à le mettre en œuvre."),
    dict(n=6736, kind="texte", cat="Défense", title="Actualisation de la loi de programmation militaire",
         sum="Projet de loi qui ajoute 36 milliards d'euros sur 2026-2030 à la programmation militaire 2024-2030, pour porter l'effort de défense à plus de 2,5 % du PIB dès 2030 selon ses auteurs. Priorités : munitions, lutte anti-drones, dissuasion nucléaire. Il crée un service national volontaire pour les 18-25 ans et un « état d'alerte de sécurité nationale » qui permet des dérogations temporaires à certaines normes.",
         pro="Permettre à la France de faire face à toute situation dans un contexte de menace russe, et accélérer le réarmement.",
         con="Certains dénoncent une logique d'escalade et un alignement sur les États-Unis. D'autres jugent que les dépenses nouvelles ne sont qu'un simple rattrapage de la loi de 2023."),
    dict(n=7259, kind="texte", cat="Agriculture", title="Loi d'urgence pour la protection et la souveraineté agricoles",
         sum="Projet de loi en plusieurs volets : facilitation des ouvrages de stockage d'eau, procédure allégée pour les bâtiments d'élevage, tirs de défense facilités contre le loup, peines aggravées pour les vols et dégradations sur les exploitations, et mesures sur les prix et les importations de produits traités avec des pesticides interdits dans l'UE.",
         pro="Les partisans parlent de mesures pragmatiques : faciliter le stockage d'eau et l'élevage, lutter contre la concurrence déloyale, protéger les biens agricoles.",
         con="Les opposants dénoncent des atteintes à la démocratie locale de l'eau, une disposition favorable à l'élevage intensif et la suppression d'un article sur les « tunnels de prix » (une expérimentation sur les prix agricoles)."),
    dict(n=1202, kind="texte", cat="Droits & société", title="Consentement dans la définition pénale du viol",
         sum="Proposition de loi transpartisane. Elle inscrit le non-consentement dans la définition pénale du viol et des agressions sexuelles, en plus des critères actuels (violence, contrainte, menace, surprise). Le consentement doit être libre, éclairé, spécifique, préalable et révocable.",
         pro="Dire plus clairement qu'un rapport non consenti est illégal, et sanctionner des situations de sidération ou d'emprise.",
         con="La crainte que le juge examine davantage le comportement de la victime que celui de l'auteur, et d'une inversion de la charge de la preuve."),
]

from extra_q import EXTRA, EXTRA_CATS
Q = Q + EXTRA
CATS = CATS + EXTRA_CATS
files = {int(json.load(open(f))["scrutin"]["numero"]): f for f in glob.glob(os.path.join(BASE, "an_data/out/json/*.json"))}

out = []
for q in Q:
    s = json.load(open(files[q["n"]]))["scrutin"]
    d = s["syntheseVote"]["decompte"]
    g = {}
    for grp in s["ventilationVotes"]["organe"]["groupes"]["groupe"]:
        ref = grp["organeRef"]
        sig = ALIAS.get(ref) or G.get(ref, {}).get("sigle")
        if ref == "PO840056":
            sig = "NI"
        if sig not in KEEP and sig != "NI":
            continue
        v = grp["vote"]["decompteVoix"]
        cur = g.setdefault(sig, [0, 0, 0, 0])
        cur[0] += int(v["pour"]); cur[1] += int(v["contre"]); cur[2] += int(v["abstentions"]); cur[3] += int(grp["nombreMembresGroupe"])
    out.append(dict(
        n=q["n"], kind=q["kind"], cat=q["cat"], title=q["title"], sum=q["sum"], pro=q["pro"], con=q["con"],
        date=s["dateScrutin"], sort=s["sort"]["code"],
        tot=[int(d["pour"]), int(d["contre"]), int(d["abstentions"])], g=g,
    ))

blob = dict(groups=GROUP_NAMES, cats=CATS, q=out)
json.dump(blob, open(os.path.join(BASE, "quiz_data.json"), "w"), ensure_ascii=False)
print(len(out), "questions;", sum(len(x["g"]) for x in out), "group-votes")
for x in out:
    print(x["n"], x["kind"], x["date"], x["sort"], x["tot"], len(x["g"]), "groups")
