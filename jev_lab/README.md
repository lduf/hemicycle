# jev_lab — comment se comporte Jev dans le pipeline hémicycle

Banc d'essai qui mesure **Jev (TypeSafe, via OpenRouter) sur les appels réels du pipeline hémicycle**, pour décider à froid s'il peut tenir ses rôles, avec quels seuils, à quel coût et à quelle vitesse.

> ⚠️ **État : rien n'a encore été mesuré sur le vrai Jev** (aucune clé n'était disponible quand l'outil a été construit). La chaîne est testée contre un serveur factice
> (`python -m jev_lab demo`, 28 tests) ; ces rapports portent un bandeau « DONNÉES SIMULÉES ». Hypothèses et seuils : [`PROTOCOL.md`](PROTOCOL.md), figés avant les mesures.

## Ce qui est étudié : les 4 appels réels du pipeline

| Scénario | Ce que Jev fait en production | Erreur grave | Jeu d'essai (tiré du dépôt) |
|---|---|---|---|
| **categorie** | propose la catégorie de la fiche (acceptée si confiance ≥ 0,5) | mauvaise catégorie | 34 fiches du MVP (catégorie posée à la main) |
| **sens** | vérifie que le bouton « Pour … » correspond au sens du vote | **bouton inversé publié** | chaque vote avec son bouton exact et son bouton inversé (≈ 150 votes) |
| **neutralite** | note l'orientation 0-5 ; fiche rejetée si > `NEUTRALITY_MAX` | fiche orientée publiée | fiches actuelles + réécritures orientées POUR / CONTRE / cadrage léger |
| **pro_contre** | juge si les arguments pour/contre sont pertinents, de fond, de poids égal | arguments inversés ou bâclés publiés | chaque fiche + 3 défauts fabriqués (permutés, « contre » tronqué, « contre » d'une autre mesure) |

Les questions et les règles de décision sont **celles de `pipeline/classify.py`** (fonctions `*_call` et `*_verdict`) : si la production change, l'étude change. Les références sont **Claude** via OpenRouter,
avec la consigne de secours de production : c'est l'alternative réelle d'aujourd'hui (`claude -p`).

Deux erreurs sont mesurées partout : la **fausse acceptation** (un défaut passe) et le **faux rejet** (une bonne entrée est refusée). Une réponse inexploitable ou un appel échoué = **rejet**, comme en production (échec fermé).

## Voir à quoi ressemble un rapport avant de dépenser quoi que ce soit

[`exemple_simule/REPORT.md`](exemple_simule/REPORT.md) : rapport complet produit contre un **serveur factice** qui joue un « Jev imaginaire » (écrit à la main dans `mock.py`).
Les chiffres ne disent **rien** de Jev ; ils montrent la forme du rapport, les verdicts, et ce que « inconclusif » veut dire. Régénérer : `python -m jev_lab demo` (gratuit, ≈ 7 minutes).

## Démarrage

```bash
export OPENROUTER_API_KEY=...                          # jamais dans un fichier du dépôt
python -m pipeline.ingest                              # titres officiels des scrutins (jeu d'essai du sens du vote)
python -m jev_lab items                                # le jeu d'essai tiré du dépôt, sans appel
python -m jev_lab ping                                 # 1 appel : clé, format de réponse lu par le pipeline. À lancer en premier.
python -m jev_lab models                               # catalogue OpenRouter, modèles de comparaison résolus
python -m jev_lab gen-variants --gen-model claude-grand --budget 2    # réécrit les fiches pour tester la détection de biais (une fois)
python -m jev_lab show-variants                        # À RELIRE : la vérité terrain de la neutralité en dépend ; puis git add content/bench
python -m jev_lab plan --suite standard                # coût estimé, rien n'est dépensé
python -m jev_lab run  --suite smoke    --budget 1                # quelques centimes : vérifie toute la chaîne
python -m jev_lab run  --suite standard --budget 6 --run etude1       # Jev seul (OpenRouter)
# puis la référence Claude, par `claude -p` (abonnement, rien de facturé), sur le MÊME dossier de run (journal du workflow téléchargé dans jev_lab/runs/etude1/) :
python -m jev_lab run  --suite standard --baselines cli:claude-sonnet-5-5 --claude-only --run etude1 --yes
python -m jev_lab report etude1                        # (re)génère jev_lab/runs/etude1/REPORT.md depuis le journal brut
```

Une exécution interrompue (réseau, plafond) **se reprend** : même commande, même `--run` (un appel réussi n'est jamais rejoué). Le plafond vaut pour le run **entier**.
Dans GitHub (Jev seul) : *Actions → jev-lab → Run workflow* (secret `OPENROUTER_API_KEY` requis ; rapport en résumé de job, journal brut en artefact). La latence mesurée dépend alors du runner : lancer aussi en local.

## Rendre la mesure plus puissante : étiquettes humaines

Le jeu est petit (34 catégories, 60 fiches) : beaucoup de lignes sortiront « inconclusif », c'est normal. Le levier le plus efficace est humain :

```bash
python -m jev_lab label-sheet     # écrit content/gold/categories_a_etiqueter.jsonl (fiches du lot automatique)
# remplir "cat" pour chaque fiche, renommer en categories.jsonl : elles entrent dans le jeu (groupe « humain »)
```

À chaque lot nocturne, de nouvelles fiches s'ajoutent au jeu de neutralité et de pour/contre : relancer l'étude pour resserrer les intervalles.

## Contenu du rapport

Synthèse « Jev peut-il tenir ces rôles ? » (fausses acceptations / faux rejets face aux limites du protocole, comparaison appariée à Claude) · détail par scénario ·
**les seuils actuels sont-ils bien placés ?** (seuil actuel vs suggéré, validation croisée) · temps (par appel, par fiche, lot de 50) et débit · coût (par appel, par fiche, pour 1 000 fiches, tarif vérifié, crédits réconciliés) ·
stabilité (la **décision** change-t-elle si on répète ?) · robustesse (consigne, ordre des options, questions seules vs ensemble) · **les fausses acceptations de Jev** (ce qui passerait en production) · limites de l'étude.

## Lire les résultats sans se tromper

- **Lire les intervalles.** 0 erreur sur 60 cas laisse une borne haute d'environ 6 % ; sur 150, 2,5 %.
- « Inconclusif » = l'échantillon ne permet pas de trancher ; ce n'est pas « Jev est mauvais ».
- Les comparaisons à Claude sont nombreuses : ≈ 1 sur 20 sort « significative » par hasard ; lire la colonne p (Holm).
- Les seuils de sûreté du protocole sont des **propositions** à valider avant le run.
- Le modèle servi est un millésime : refaire l'étude avant de changer un seuil de production, et à chaque nouvelle version de Jev.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `ping` : le pipeline « refuserait toutes les fiches » | le format de réponse de Jev diffère de la doc : l'étude refuse de continuer (échec fermé) |
| `data/scrutins.json absent` | lancer `python -m pipeline.ingest` |
| neutralité : « aucune variante » | lancer `gen-variants` (puis relire et committer) |
| beaucoup de 429 Jev | baisser `--workers` ; voir le palier de débit du rapport |
| dépassement du plafond | normal : arrêt propre ; relever `--budget` et relancer le même `--run` |

## Organisation du code

`hemicycle.py` (scénarios, jeu d'essai, décisions de production) · `runner.py` (expériences, plan, reprise, budget) · `analysis.py` / `metrics.py` (statistiques) · `report.py` (REPORT.md + SVG) ·
`client.py` (HTTP instrumenté) · `store.py` / `budget.py` · `mock.py` (serveur factice) · `config.py` (revendications, seuils) · `__main__.py` (CLI). Mis à part `hemicycle.py`, l'outil ne dépend pas du pipeline.
