# Protocole : comment se comporte Jev dans le pipeline hémicycle

*Version 2 — 2026-10-13. Ce document et les seuils de `config.py` (`PREREG`, `SAFETY`, `CATEGORIE`) sont figés **avant** toute mesure sur Jev.
Les modifier après avoir vu des résultats invalide l'étude ; si un changement est nécessaire, on crée une version 3 et on refait tourner, en conservant la v2 et ses résultats.*

*(La version 1 mesurait Jev sur des jeux publics génériques sans lien avec le projet. Elle a été abandonnée : elle ne répondait pas à la question posée.)*

## 1. Question

> Dans le pipeline hémicycle, **Jev peut-il tenir les rôles qu'on lui donne** : proposer la catégorie d'une fiche, vérifier que le bouton « Pour … » correspond au sens du vote,
> noter la neutralité d'une fiche, juger la pertinence des arguments pour/contre ? Avec quelle sûreté, quelle vitesse, quel coût, et les **seuils actuels** sont-ils bien placés ?

Pas de benchmark général. On mesure les appels réels du pipeline, avec leurs vraies questions et leurs vrais seuils : `jev_lab/hemicycle.py` appelle les fonctions
`classify.*_call` (ce qui est envoyé à Jev) et `classify.*_verdict` (la décision de production) : **si la production change, l'étude change avec elle**.

## 2. Ce qui est comparé

- **Jev** : `POST /api/alpha/decisions`, toutes les questions d'un scénario dans un seul appel, comme en production.
- **Références** : Claude (modèles OpenRouter résolus à l'exécution par famille, puis **figés** dans `meta.json`), avec la **consigne de secours de production** (`classify.claude_prompt`) : même contrat typé,
  mêmes questions, mêmes décisions. C'est la vraie alternative aujourd'hui (`claude -p`).
- Les références ne sont pas optimisées (pas d'exemples, température 0). Limite assumée : on compare un usage « prêt à l'emploi » des deux côtés.

## 3. Scénarios et vérité terrain

| Scénario | Appel de production | Jeu d'essai | Vérité terrain |
|---|---|---|---|
| categorie | `classify.category` | les 34 fiches du MVP | catégorie choisie à la main (+ étiquettes humaines optionnelles, `content/gold/categories.jsonl`) |
| sens | `classify.direction` | chaque vote en 2 versions : bouton **exact** / bouton **inversé** ; fiches réelles + titres officiels supplémentaires (ensemble, suppression, amendement) | par construction ; le sens des titres vient des règles de `direction.classify` (fiable sur ces cas **faciles**) |
| neutralite | `classify.orientation` (rejet si note > `NEUTRALITY_MAX`) | les fiches actuelles + 3 réécritures chacune : orientée POUR, orientée CONTRE, cadrage léger | par construction ; les fiches d'origine sont *supposées* neutres (non prouvé) ; les réécritures sont produites par un LLM (`gen-variants`) et à relire |
| pro_contre | `classify.pro_con` | chaque fiche telle quelle + 3 défauts fabriqués : arguments permutés, « contre » tronqué, « contre » d'une autre mesure | par construction |

**Non couvert** : `sources_sufficient` (pré-contrôle du lot) — il faudrait des extraits de sources étiquetés par un humain. Les titres de vote **ambigus** (là où Jev serait le plus utile pour le sens du vote) — idem.

## 4. Expériences

| Code | Mesure |
|---|---|
| E1 | Pour chaque scénario et système : décision de production sur chaque entrée → **fausse acceptation** (un défaut passe), **faux rejet** (une bonne entrée est refusée), AUC de la grandeur de décision ; catégorie : exactitude, top-3, précision des acceptées, ECE |
| E2 | **Seuils** : seuil actuel contre seuil suggéré, choisi sur une moitié des cas et évalué sur l'autre |
| E3 | Latence en série (un appel de production à la fois, connexion persistante, systèmes entrelacés, échauffement exclu) ; durée d'une fiche (4 appels) et d'un lot de 50 |
| E4 | Débit : paliers de concurrence, réponses 429 |
| E5 | Coût par appel, par fiche, pour 1 000 fiches ; conformité au tarif annoncé ; réconciliation avec les crédits du compte |
| E6 | Robustesse de la catégorie : consigne sans descriptions, ordre des options permuté |
| E7 | Déterminisme : même appel 5 fois ; **la décision change-t-elle ?** |
| E9 | Les questions d'un appel posées seules ou ensemble : même réponse, même décision ? coût et durée |

## 5. Hypothèses et seuils (à valider par le responsable du projet avant le run)

La production **échoue fermé** : une réponse inexploitable ou un appel échoué refuse la fiche. L'étude fait de même : c'est un **rejet**.

| # | Hypothèse | « Respecté » | « Dépassé » | Sinon |
|---|---|---|---|---|
| S1 | Sens : un bouton inversé n'est quasi jamais accepté | borne haute de l'IC (Wilson) de la fausse acceptation ≤ **2 %** | borne basse > 2 % | inconclusif |
| S2 | Neutralité : au moins 90 % des fiches fortement orientées sont rejetées | fausse acceptation (borne haute) ≤ **10 %** | borne basse > 10 % | inconclusif |
| S3 | Pour/contre : au moins 90 % des défauts fabriqués sont rejetés | fausse acceptation (borne haute) ≤ **10 %** | borne basse > 10 % | inconclusif |
| S4 | Faux rejets : pas plus d'une fiche sur quatre bonne est refusée | faux rejet (borne haute) ≤ **25 %** (sens, neutralité, pour/contre) | borne basse > 25 % | inconclusif |
| C1 | Catégorie : exactitude ≥ 80 % ; catégories acceptées exactes à ≥ 90 % | borne basse de l'IC ≥ seuil | borne haute < seuil | inconclusif |
| R1 | Jev est « au moins aussi sûr » que la référence | borne haute de (erreur_Jev − erreur_réf) < +3 points et borne basse > −3 pour « équivalent » | borne basse > 0 : « plus risqué » | inconclusif |
| D1 | Déterminisme : au plus 2 % des fiches changent de **décision** sur 5 répétitions | borne haute (Wilson) ≤ 2 % | borne basse > 2 % | inconclusif |
| P1 | Tarif : coût = tokens d'entrée × 0,042 $/M (sortie gratuite) | rapport médian dans ±5 % | hors de ±5 % | – |

Ces limites sont des **propositions** : le choix des seuils de sûreté est une décision de production, pas une mesure. Elles sont publiées pour être discutées *avant* le run.

## 6. Méthode statistique

- Taux : intervalle de **Wilson** (valable avec peu de cas et des taux proches de 0). Écarts **appariés** (mêmes entrées) : intervalle de **Newcombe** (reste large quand les erreurs sont rares, contrairement au bootstrap qui donne [0 ; 0] sans désaccord), test exact de McNemar, correction de Holm sur l'ensemble des comparaisons.
- Seuils de décision : choisis sur une moitié des cas, évalués sur l'autre (et inversement) ; jamais optimisés sur ce qui les mesure.
- Latence : p50/p90/p95/p99, mesure côté client, tentative réussie seule ; bootstrap **par fiche** (les répétitions d'un même appel ne sont pas indépendantes).
- Un cas inexploitable n'est jamais exclu : il est compté comme rejet.

### Puissance : ce que ce jeu d'essai peut et ne peut pas trancher

Le jeu est petit (60 fiches avec arguments, 151 votes, 34 catégories) : même **zéro erreur observée** laisse une borne haute de ≈ 6 % sur 60 cas et ≈ 2,5 % sur 150.
Conséquences : S1 (≤ 2 %) ne peut être « respecté » qu'avec plus de ≈ 190 bonnes inversions sans aucune erreur ; S2/S3 (≤ 10 %) demandent ≈ 35 cas par type de défaut sans erreur ;
la catégorie (34 fiches) donne ± 14 points. **« Inconclusif » est donc un résultat normal et attendu sur plusieurs lignes** : il dit que l'échantillon ne permet pas de trancher, pas que Jev est mauvais.
Pour trancher davantage : ajouter des fiches (le lot nocturne en produit), et des étiquettes humaines (voir README).

## 7. Biais connus et parades

| Risque | Parade |
|---|---|
| Étudier autre chose que la production | Les questions et les décisions sont celles de `pipeline/classify.py`, appelées directement |
| Fiches d'origine supposées neutres à tort | Écrit dans le rapport ; la note des fiches d'origine est publiée ; relire les « faux rejets » un à un |
| Réécritures orientées non validées | `gen-variants` écrit dans `content/bench/` (relisible, versionné) ; `show` pour les lire ; limite écrite dans le rapport |
| Vérité terrain du sens issue de règles | Limitée aux cas certains par construction ; titres ambigus non couverts (dit) |
| Une référence pénalisée par un artefact de format | `max_tokens` = 4000 (le test smoke a montré qu'à 1000 une référence bavarde est tronquée dans 45 % des cas), `finish_reason` conservé ; réponse vide/tronquée = appel échoué (rejoué, publié) ; consigne de production identique |
| Latence écrasée par l'overhead réseau | Connexions persistantes ; bootstrap par fiche ; appels identiques répétés possiblement cachés côté fournisseur (limite écrite) |
| Doublons après reprise / plafond contourné | Un enregistrement par appel logique ; plafond pour le run entier ; coût estimé réservé avant chaque appel ; le modèle fait partie de la clé de reprise |
| Versions de modèle qui changent | Version servie lue dans la réponse et notée ; alias résolu puis figé |
| Dépenses hors de contrôle | Plafond dur, estimation avant exécution, arrêt net, reprise possible |

## 8. Ce qui n'est pas mesuré

La tenue dans le temps (une seule session) ; la disponibilité (service en version `alpha`) ; `sources_sufficient` ; les titres ambigus ; Jev Router (autre produit).

## 9. Règle de publication

On publie **tout** : résultats défavorables, lignes inconclusives, ce qui n'a pas pu être mesuré. Le rapport est généré par le code depuis le journal brut ; aucun chiffre n'est saisi à la main.
