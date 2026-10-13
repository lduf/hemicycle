# Étude : l'heuristique d'importance parlementaire fonctionne-t-elle ?

*Généré par `python3 -m pipeline.salience_study`. Tous les chiffres sont recalculés sur les données ouvertes de l'Assemblée nationale (17e législature).*

**Données** : 3252 dossiers législatifs, dont 251 ont au moins un scrutin public et sont de nature législative (hors motions de censure, engagements de responsabilité, missions et rapports ; c'est l'univers étudié). Débats rattachés à un dossier : 742 points sur 1116 avec prise de parole (le reste : questions au gouvernement, déclarations, débats sans texte).

## 1. Validité sur un jeu choisi avant l'étude

Jeu de référence : les 34 votes historiques du prototype, choisis à la main comme sujets de société ; 30 sont reliés à un dossier (30 dossiers distincts). On mesure l'AUC : la probabilité qu'un dossier de ce jeu ait un meilleur score qu'un dossier de l'univers (0,5 = hasard, 1 = parfait). Seuils fixés avant le calcul : ≥ 0.75 bon, 0.6–0.75 moyen, < 0.6 échec.

| Score | AUC | IC 95 % | Lecture (sur la borne basse de l'IC) |
|---|---|---|---|
| débat | 0.83 | 0.76 – 0.89 | bon |
| amendements | 0.72 | 0.61 – 0.81 | moyen |
| votes | 0.74 | 0.63 – 0.83 | moyen |
| tout | 0.82 | 0.74 – 0.88 | moyen |
| tout, par type | 0.84 | 0.78 – 0.90 | bon |
| débat, par type | 0.85 | 0.79 – 0.91 | bon |
| seul : scrutins | 0.73 | 0.62 – 0.83 | moyen |
| seul : solennels | 0.68 | 0.59 – 0.78 | échec |
| seul : amendements | 0.74 | 0.63 – 0.83 | moyen |
| seul : amend_adoptes | 0.69 | 0.59 – 0.79 | échec |
| seul : orateurs | 0.85 | 0.78 – 0.90 | bon |
| seul : groupes_orateurs | 0.63 | 0.59 – 0.67 | échec |
| seul : interventions | 0.84 | 0.78 – 0.90 | bon |
| seul : mots | 0.81 | 0.74 – 0.87 | moyen |
| seul : duree_min | 0.80 | 0.72 – 0.86 | moyen |
| seul : seances | 0.75 | 0.66 – 0.83 | moyen |
| seul : reunions_commission | 0.61 | 0.49 – 0.72 | échec |
| divergence (critère actuel) | 0.70 | 0.62 – 0.78 | moyen |
| hasard (un tirage) | 0.53 | 0.41 – 0.66 | contrôle |

Contrôle : sur 100 tirages aléatoires, l'AUC varie de 0.35 à 0.67 (médiane 0.51). Avec seulement 30 cas positifs, un écart de moins de 0,10 avec 0,5 ne prouve rien.

Rang du jeu de référence dans le classement « tout » (sur 251, global) : médiane 37. Dans le top 25 : 13 / 30 ; top 75 : 18 ; top 100 : 25 ; top 150 : 29.

**Limite** : ce jeu a été choisi à la main, en partie selon la divergence entre groupes, pas selon la notoriété. Un bon AUC est un indice, pas une preuve ; un mauvais AUC serait une réfutation.

## 2. Cohérence interne

Corrélation de rang (Spearman) entre familles d'indicateurs : si elles mesurent la même chose (l'importance), elles doivent être corrélées sans être identiques.

| Paire | Spearman |
|---|---|
| débat ~ amendements | 0.61 |
| débat ~ votes | 0.73 |
| amendements ~ votes | 0.59 |
| tout ~ divergence | 0.33 |

## 3. Robustesse du top 75

Part du top commune (Jaccard) quand on retire un indicateur : proche de 1 = stable.

| Indicateur retiré | Jaccard |
|---|---|
| orateurs | 0.95 |
| interventions | 0.92 |
| duree_min | 0.97 |
| amendements | 0.92 |
| scrutins | 0.95 |
| solennels | 0.85 |

## 4. Biais d'origine et de type

Origine du texte (groupe de l'auteur, ou gouvernement), en part de l'ensemble.

| Origine | Univers | Top 75 (global) | Top 75 (rang par type) | Jeu de référence |
|---|---|---|---|---|
| autre | 19% | 13% | 15% | 10% |
| centre | 30% | 33% | 36% | 13% |
| droite | 8% | 11% | 11% | 17% |
| gauche | 22% | 9% | 17% | 40% |
| gouvernement | 20% | 33% | 21% | 20% |

| Type de dossier | Univers | Top 75 |
|---|---|---|
| budget | 6 | 6 |
| constitutionnel/organique | 12 | 4 |
| projet de loi | 25 | 15 |
| proposition de loi | 165 | 47 |
| résolution | 36 | 3 |
| traité | 7 | 0 |

## 5. Lecture humaine

### Les 30 premiers

| # | Dossier | Type | Origine | Scrutins | Amend. | Orateurs | Débat (min) |
|---|---|---|---|---|---|---|---|
| 1 | Fin de vie | proposition de loi | DEM | 382 | 9270 | 278 | 7970.8 |
| 2 | Projet de loi d’urgence pour la protection et la souveraineté agricoles | projet de loi | gouvernement | 422 | 4038 | 240 | 3675.5 |
| 3 | Projet de loi de financement de la sécurité sociale pour 2026 | budget | gouvernement | 49 | 6208 | 361 | 6496.7 |
| 4 | Projet de loi relatif à la lutte contre les fraudes sociales et fiscales | projet de loi | gouvernement | 188 | 1931 | 175 | 2794.3 |
| 5 | Projet de loi de finances pour 2026 | budget | gouvernement | 52 | 19510 | 436 | 8690.5 |
| 6 | Projet de loi visant à offrir des réponses immédiates aux phénomènes troublant l’ordre pub | projet de loi | gouvernement | 290 | 1831 | 169 | 1851.8 |
| 7 | Projet de loi actualisant la programmation militaire pour les années 2024 à 2030 et portan | projet de loi | gouvernement | 292 | 1364 | 131 | 2256.5 |
| 8 | Proposition de loi visant à sortir la France du piège du narcotrafic | proposition de loi | autre | 31 | 1676 | 189 | 2511.6 |
| 9 | Renforcer la sécurité, la rétention administrative et la prévention des risques d’attentat | proposition de loi | EPR | 105 | 369 | 156 | 1348.9 |
| 10 | Projet de loi de programmation pour la refondation de Mayotte | projet de loi | gouvernement | 39 | 1315 | 123 | 1692.5 |
| 11 | Soins palliatifs et d’accompagnement | proposition de loi | EPR | 17 | 1889 | 170 | 2481.3 |
| 12 | Projet de loi relatif à l’organisation des jeux Olympiques et Paralympiques de 2030 | projet de loi | gouvernement | 65 | 674 | 123 | 1132.4 |
| 13 | Projet de loi relatif à la protection des enfants | projet de loi | gouvernement | 140 | 2458 | 126 | 1307.0 |
| 14 | Projet de loi de finances pour 2025 | budget | gouvernement | 13 | 14522 | 361 | 4666.6 |
| 15 | Projet de loi sur la justice criminelle et le respect des victimes | projet de loi | gouvernement | 80 | 824 | 111 | 875.6 |
| 16 | Reconnaître une présomption de légitime défense pour les forces de l'ordre, dans l'exercic | proposition de loi | DR | 50 | 604 | 126 | 485.4 |
| 17 | Projet de loi d'urgence pour Mayotte | projet de loi | gouvernement | 24 | 635 | 99 | 831.1 |
| 18 | Renforcer les conditions d'accès à la nationalité française à Mayotte | proposition de loi | DR | 32 | 470 | 124 | 621.6 |
| 19 | Apporter une réponse intégrale au phénomène des violences sexuelles et sexistes contre les | proposition de loi | SOC | 221 | 2370 | 183 | 2751.6 |
| 20 | Protéger les mineurs des risques auxquels les expose l’utilisation des réseaux sociaux | proposition de loi | EPR | 30 | 265 | 88 | 424.8 |
| 21 | Pour une montagne vivante et souveraine | proposition de loi | DR | 75 | 426 | 59 | 436.4 |
| 22 | Proposition de loi relative à l'organisation, à la gestion et au financement du sport prof | proposition de loi | autre | 76 | 685 | 46 | 605.5 |
| 23 | Projet de loi constitutionnelle pour une Corse autonome au sein de la République | constitutionnel/organique | gouvernement | 25 | 164 | 75 | 933.2 |
| 24 | Projet de loi de finances de fin de gestion pour 2025 | budget | gouvernement | 14 | 210 | 108 | 595.0 |
| 25 | Nationalisation d'ArcelorMittal France | proposition de loi | LFI-NFP | 102 | 492 | 131 | 660.4 |
| 26 | Proposition de loi visant à faciliter le maintien en rétention des personnes condamnées po | proposition de loi | autre | 20 | 115 | 92 | 408.4 |
| 27 | Relancer les investissements dans le secteur de l’hydroélectricité pour contribuer à la tr | proposition de loi | SOC | 31 | 321 | 52 | 420.5 |
| 28 | Projet de loi de financement de la sécurité sociale pour 2025 | budget | gouvernement | 9 | 5892 | 265 | 2093.8 |
| 29 | Restaurer l'autorité de la justice à l'égard des mineurs délinquants et de leurs parents | proposition de loi | EPR | 8 | 177 | 119 | 426.6 |
| 30 | Renforcement du soutien à l'Ukraine | résolution | LIOT | 25 | 85 | 93 | 393.9 |

### Les 20 derniers

| Dossier | Type | Scrutins | Amend. | Orateurs | Débat (min) |
|---|---|---|---|---|---|
| Lutter contre la pédocriminalité | proposition de loi | 1 | 6 | 10 | 15.5 |
| Libération des prisonniers arméniens détenus par l’Azerbaïdjan | résolution | 1 | 0 | 15 | 65.3 |
| Projet de loi autorisant l’approbation de la convention de coopération judiciaire internat | traité | 1 | 0 | 13 | 65.4 |
| Supprimer le vote par assis et levé | résolution | 1 | 0 | 15 | 38.7 |
| Prévenir les ingérences étrangères en France | proposition de loi | 2 | 0 | 0 | 0.0 |
| Renforcer la prévention en santé au travail | proposition de loi | 2 | 0 | 0 | 0.0 |
| Démocratiser le sport en France | proposition de loi | 2 | 0 | 0 | 0.0 |
| Projet de loi autorisant l’approbation de l’accord entre le Gouvernement de la République  | traité | 1 | 0 | 12 | 56.3 |
| Évaluer précisément le coût réel et sociétal de l’insécurité routière et son impact sur le | résolution | 1 | 0 | 10 | 45.8 |
| Améliorer l'accès aux soins par la territorialisation et la formation | proposition de loi | 1 | 0 | 0 | 0.0 |
| Généralisation du contrat à durée indéterminée à des fins d’employabilité | proposition de loi | 1 | 0 | 0 | 0.0 |
| Proposition de loi visant à améliorer le repérage et l’accompagnement des personnes présen | proposition de loi | 1 | 0 | 0 | 0.0 |
| Régime juridique des actions de groupe | proposition de loi | 1 | 0 | 0 | 0.0 |
| Lutte contre les discriminations par la pratique de tests individuels et statistiques | proposition de loi | 1 | 0 | 0 | 0.0 |
| Proposition de loi encadrant l'intervention des cabinets de conseil privés dans les politi | proposition de loi | 1 | 0 | 0 | 0.0 |
| Ouvrir le dispositif de réduction d’activité progressive aux moniteurs de ski stagiaires | proposition de loi | 1 | 0 | 0 | 0.0 |
| Mieux indemniser les dégâts sur les biens immobiliers causés par le retrait-gonflement de  | proposition de loi | 1 | 0 | 0 | 0.0 |
| Programmation militaire pour les années 2024 à 2030 et diverses dispositions intéressant l | projet de loi | 1 | 0 | 0 | 0.0 |
| Confidentialité des consultations des juristes d’entreprise | proposition de loi | 1 | 0 | 0 | 0.0 |
| Convention des Nations unies sur la mer et conservation et utilisation durable de la diver | traité | 1 | 0 | 0 | 0.0 |

### Où se classent les votes du jeu de référence

| Rang | Dossier | Type |
|---|---|---|
| 1 | Fin de vie | proposition de loi |
| 2 | Projet de loi d’urgence pour la protection et la souveraineté agricoles | projet de loi |
| 4 | Projet de loi relatif à la lutte contre les fraudes sociales et fiscales | projet de loi |
| 6 | Projet de loi visant à offrir des réponses immédiates aux phénomènes troublant l’ordre pub | projet de loi |
| 7 | Projet de loi actualisant la programmation militaire pour les années 2024 à 2030 et portan | projet de loi |
| 8 | Proposition de loi visant à sortir la France du piège du narcotrafic | proposition de loi |
| 12 | Projet de loi relatif à l’organisation des jeux Olympiques et Paralympiques de 2030 | projet de loi |
| 16 | Reconnaître une présomption de légitime défense pour les forces de l'ordre, dans l'exercic | proposition de loi |
| 18 | Renforcer les conditions d'accès à la nationalité française à Mayotte | proposition de loi |
| 20 | Protéger les mineurs des risques auxquels les expose l’utilisation des réseaux sociaux | proposition de loi |
| 22 | Proposition de loi relative à l'organisation, à la gestion et au financement du sport prof | proposition de loi |
| 23 | Projet de loi constitutionnelle pour une Corse autonome au sein de la République | constitutionnel/organique |
| 25 | Nationalisation d'ArcelorMittal France | proposition de loi |
| 29 | Restaurer l'autorité de la justice à l'égard des mineurs délinquants et de leurs parents | proposition de loi |
| 30 | Renforcement du soutien à l'Ukraine | résolution |
| 37 | Impôt plancher de 2 % sur le patrimoine des ultra riches | proposition de loi |
| 44 | Proposition de loi visant à lever les contraintes à l’exercice du métier d’agriculteur | proposition de loi |
| 73 | Retrouver la confiance et l’équilibre dans les rapports locatifs | proposition de loi |
| 76 | Modifier la définition pénale du viol et des agressions sexuelles | proposition de loi |
| 79 | Accorder le versement des allocations familiales dès le premier enfant | proposition de loi |
| 82 | Empêcher la constitution de monopoles économiques dans les secteurs des médias | proposition de loi |
| 85 | Protéger les mineurs isolés et à lutter contre le sans-abrisme | proposition de loi |
| 88 | Protéger la population des risques liés aux substances per- et polyfluoroalkylées (PFAS) | proposition de loi |
| 92 | Rendre accessible à tous les étudiants le repas à 1 euro | proposition de loi |
| 94 | Garantir un renouvellement automatique des titres de séjour de longue durée | proposition de loi |
| 116 | Réformer les bourses sur critères sociaux et lutter contre la précarité étudiante | proposition de loi |
| 137 | Dénoncer les accords franco-algériens du 27 décembre 1968 | résolution |
| 144 | Proroger le dispositif d’expérimentation favorisant l’égalité des chances pour l’accès à c | proposition de loi |
| 145 | Refonder l'espace Schengen en instaurant une double frontière nationale et européenne | résolution |
| 162 | Mobiliser la commande publique au service de l’emploi, de la production et de l’innovation | résolution |

## Conclusion (calculée à partir des chiffres ci-dessus)

- **Le signal existe.** Le score de débat (orateurs, interventions, durée, mots), classé au sein de chaque type de texte, atteint une AUC de 0.85 (IC 95 % : 0.79–0.91) contre 0.67 au plus pour 100 tirages aléatoires. Il fait mieux que le critère de divergence actuel (0.70) pour repérer ces sujets.
- **Les amendements et le nombre de scrutins seuls sont plus faibles** (AUC 0.72 et 0.74, bornes basses 0.61 et 0.63) : utiles en complément, pas en critère principal.
- **Biais d'origine réel si on classe sans précaution** : textes du gouvernement 20% de l'univers mais 33% du top 75 ; textes de la gauche 22% de l'univers mais 9% du top. Classer au sein de chaque type ramène ces parts à 21% et 17%. L'importance parlementaire mesure aussi le poids institutionnel : il faut donc corriger et plafonner par origine, pas seulement trier.
- **Le jeu de départ n'était pas équilibré** : 40% de textes d'origine « gauche », 13% « centre », 17% « droite ». Cela vient de la sélection à la main du prototype, pas de la méthode ; c'est une raison de plus pour automatiser et publier les critères.
- **Limites** : (1) la validation repose sur 30 dossiers choisis à la main, donc un indice plutôt qu'une preuve ; (2) les textes courts adoptés sans véritable débat (niches parlementaires) sont sous-classés même quand le sujet intéresse le public ; (3) aucune mesure de l'attention du public ou de la presse n'a été utilisée, donc « important pour le Parlement » n'est pas « important pour les gens » ; (4) l'importance n'est pas la neutralité : le tri ne dit rien de l'orientation.
