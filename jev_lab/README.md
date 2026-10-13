# jev_lab — statuer à froid sur Jev

Banc d'essai **indépendant** (il ne dépend pas du projet hémicycle) pour répondre, chiffres à l'appui, à :
*Jev est-il bon ? sur quelles tâches ? à quel coût ? avec quelle latence ? sa confiance est-elle fiable ?*

> ⚠️ **État au moment de l'écriture : rien n'a encore été mesuré sur le vrai Jev** (aucune clé n'était disponible quand l'outil a été construit).
> Toute la chaîne a été testée contre un serveur factice (`python -m jev_lab demo`, 20 tests) ; ses rapports portent un bandeau « DONNÉES SIMULÉES ».
> Les seuils de lecture sont dans [`PROTOCOL.md`](PROTOCOL.md), fixés avant les mesures.

## Démarrage en 5 minutes

```bash
export OPENROUTER_API_KEY=...                  # jamais dans un fichier du dépôt
python -m jev_lab ping                         # 1 appel : clé, schéma de réponse, usage, coût. À lancer en premier.
python -m jev_lab models                       # catalogue OpenRouter et modèles de comparaison résolus
python -m jev_lab plan --suite standard --baselines claude-petit,claude-grand      # coût estimé, rien n'est dépensé
python -m jev_lab run  --suite smoke    --baselines claude-petit --budget 1        # quelques centimes : vérifie toute la chaîne
python -m jev_lab run  --suite standard --baselines claude-petit,claude-grand,gpt-petit --budget 5 --run etude1
python -m jev_lab report etude1                # (re)génère jev_lab/runs/etude1/REPORT.md depuis le journal brut
```

Une exécution interrompue (réseau, plafond de budget) **se reprend** : relancer la même commande avec le même `--run`
(un appel réussi n'est jamais rejoué, un appel échoué l'est).

Ou dans GitHub : *Actions → jev-lab → Run workflow* (secret `OPENROUTER_API_KEY` requis ; le rapport et le journal brut sont publiés en artefact).
La latence mesurée dépend alors de l'emplacement du runner GitHub : pour une valeur représentative de **votre** usage, lancez aussi en local.

## Ce que ça mesure

| | |
|---|---|
| **Réponses reçues** | chaque requête et chaque réponse brute sont conservées (`calls.jsonl`), avec durée, tentatives, tokens, coût, version servie. Le rapport est recalculé depuis ce journal ; rien n'est saisi à la main. |
| **Latence** | appels en série, systèmes entrelacés aléatoirement, échauffement exclu, p50/p90/p95/p99 avec intervalles ; effet de la taille d'entrée ; débit et réponses 429 par palier de concurrence. |
| **Prix** | coût rapporté vs tokens × 0,042 $/M ; la sortie est-elle vraiment gratuite ? facturation de plusieurs questions par requête ; réconciliation avec la consommation du compte OpenRouter ; coût par bonne réponse. |
| **Qualité** | 11 tâches à vérité terrain publique (classification de 3 à 77 classes, vérification, modération, ordinal ; anglais et français), comparées **à mêmes exemples** à des modèles de langage ; intervalles, test de McNemar, correction de Holm. |
| **Confiance** | ECE avec intervalle, courbe de fiabilité, précision si l'on s'abstient sous un seuil de confiance. |
| **Robustesse** | bruit non pertinent, ordre des options permuté, descriptions retirées. |
| **Déterminisme** | même appel répété 5 fois : étiquettes changées, écart de probabilité. |
| **Limites annoncées** | dates, comptage, arithmétique, maximum ; sonde de longueur de contexte (32 k ou 64 k : la doc se contredit). |
| **Multi-questions** | oui/non opposés vs choix unique ; une question seule vs avec deux autres. |

Le rapport s'ouvre sur une grille « supérieur / équivalent / inférieur / inconclusif » par tâche et par référence, et sur un verdict
« recommandé » (au moins équivalent **et** au moins 10 fois moins cher).

## Suites et coût

| Suite | Contenu | Coût typique (Jev + 2 références) |
|---|---|---|
| `smoke` | 2 tâches × 20 exemples + latence, limites, facturation | quelques centimes |
| `standard` | 11 tâches × 200 (références : 100) + toutes les expériences | ≈ 2,7 $ (dont ≈ 0,11 $ pour Jev ; le grand modèle domine) |
| `full` | n = 500 (références : 250), paliers jusqu'à 64 en parallèle | à estimer avec `plan` |

Les chiffres viennent de `plan` (prix lus au catalogue OpenRouter ; tarif de Jev = celui annoncé). Les tailles d'entrée sont **estimées** quand un jeu
public est injoignable au moment du plan. Le plafond `--budget` est dur : le run s'arrête avant de le dépasser.

## Vos propres données (`--custom`)

C'est le test qui compte vraiment pour décider. Fichier JSONL : 1ʳᵉ ligne = la tâche, lignes suivantes = exemples.

```json
{"task": "tri_tickets", "title": "Tri des tickets", "primitive": "choice", "instructions": "Which team owns this ticket?", "options": {"paiement": "Payment issues.", "compte": "Login issues."}}
{"id": "1", "state": {"ticket": "Je ne peux plus me connecter"}, "gold": "compte"}
```

`python -m jev_lab run --suite smoke --custom mes_tickets.jsonl --baselines claude-petit`
⚠️ Les requêtes sont conservées telles quelles dans `calls.jsonl` : ne publiez pas un run fait sur des données confidentielles.

## Lire les résultats sans se tromper

- **Regardez les intervalles**, pas les moyennes : avec 100 exemples, ±7 points est normal.
- « Inconclusif » n'est pas « Jev est mauvais » : c'est « pas assez d'exemples pour trancher ». Relancez avec une suite plus grande ou `--custom`.
- Une référence n'est pas optimisée (pas d'exemples dans la consigne). Jev non plus (critères sans réglage). La comparaison est « prêt à l'emploi » des deux côtés.
- La latence dépend du réseau, de l'heure, de la charge d'OpenRouter : une session ne vaut pas une garantie.
- Le modèle servi est un millésime (`typesafe/jev-1.13-AAAAMMJJ`) : une conclusion ne vaut que pour lui. Refaire l'étude à chaque nouvelle version.

## Dépannage

| Symptôme | Cause probable |
|---|---|
| `ping` : HTTP 4xx avec un message sur les critères | format des critères inattendu : le message de l'API est affiché tel quel ; corriger `tasks.spec` |
| `ping` : schéma inattendu | l'API alpha a changé : l'étude refuse de continuer (échec fermé) |
| `jeu indisponible … 429/503` | Hugging Face limite le débit : relancer ; les jeux déjà tirés sont en cache |
| beaucoup de 429 Jev | limite de cadence : baisser `--workers`, voir le palier de débit du rapport |
| dépassement du plafond | normal : le run s'arrête proprement ; relever `--budget` et relancer le même `--run` |

## Organisation du code

`config.py` (constantes, revendications, seuils) · `client.py` (HTTP instrumenté) · `tasks.py` / `synth.py` / `datasets.py` (tâches et données) ·
`runner.py` (expériences, plan, reprise, budget) · `analysis.py` / `metrics.py` (statistiques) · `report.py` (REPORT.md + SVG) · `mock.py` (serveur factice) · `__main__.py` (CLI).
