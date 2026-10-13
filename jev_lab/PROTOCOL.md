# Protocole d'étude de Jev (préenregistré)

*Version 1 — 2026-10-13. Ce document et les seuils de `config.py::PREREG` sont figés **avant** toute mesure sur Jev.
Les modifier après avoir vu des résultats invalide l'étude ; si un changement est nécessaire, on crée une version 2 et on
refait tourner, en conservant la v1 et ses résultats.*

## 1. Question

> Jev (TypeSafe, `typesafe/jev-1.13` via OpenRouter) est-il un bon choix pour des décisions automatiques
> (classer, vérifier, noter) comparé à un modèle de langage utilisé en mode JSON ? Sur quelles tâches ? À quel coût ? Avec quelle latence ?
> La confiance qu'il annonce est-elle fiable ?

On ne cherche pas à savoir si Jev est « meilleur » en général. On cherche **où** il est au moins aussi bon, **où** il ne l'est pas,
et ce que ça coûte en temps et en argent.

## 2. Ce qui est comparé

- **Jev** : appel `POST /api/alpha/decisions`, une question par appel sauf expériences dédiées, critères = libellés d'étiquettes avec une courte description.
- **Références** : modèles de langage OpenRouter résolus à l'exécution par famille (le plus récent qui correspond) puis **figés** dans `meta.json` :
  un petit modèle et un grand modèle Anthropic au minimum ; d'autres familles en option. Même consigne (mêmes libellés, mêmes descriptions), température 0, réponse JSON.
- Les références ne sont pas optimisées (pas d'exemples dans la consigne, pas de raisonnement). C'est une **limite assumée** : on compare un usage « prêt à l'emploi » des deux côtés.

## 3. Tâches (vérité terrain publique ou calculée)

| Tâche | Primitive Jev | Jeu | Pourquoi |
|---|---|---|---|
| ag_news | choice (4) | AG News | classification simple |
| banking77 | choice (77) | BANKING77 | beaucoup de classes |
| massive_fr | choice (60) | MASSIVE (fr) | beaucoup de classes, français |
| xnli_fr | choice (3) | XNLI (fr) | inférence textuelle, français |
| vitaminc | choice (3) | VitaminC | vérification d'une affirmation sur une preuve (cas contrastifs, dur) |
| sst2 | noul | SST-2 | sentiment binaire |
| toxic | noul | Civil Comments (équilibré) | modération |
| injection | noul | deepset/prompt-injections | garde-fou |
| boolq | noul | BoolQ | question fermée sur un passage |
| sst5 | score (5) | SST-5 | ordinal |
| avis_fr | score (5) | Amazon Reviews (fr) | ordinal, français |
| dates, comptage, arith, max | choice / noul | générées | limites annoncées par l'éditeur (réponse exacte) |

## 4. Expériences

| Code | Mesure | Appels |
|---|---|---|
| E1 qualité | précision, F1, AUC, MAE ; comparaisons appariées Jev − référence | toutes tâches × systèmes |
| E2 calibration | ECE, Brier, courbe de fiabilité, précision à couverture réduite | analyse de E1 |
| E3 latence | appels en série, systèmes entrelacés, échauffement exclu ; effet de la taille d'entrée | série |
| E4 débit | paliers de concurrence ; réponses 429 ; échecs | Jev seul |
| E5 prix | coût facturé vs tokens × tarif ; facturation de N questions ; réconciliation avec les crédits du compte | analyse + sonde |
| E6 robustesse | bruit non pertinent avant/après, ordre des options permuté, descriptions retirées | Jev (+ références en option) |
| E7 déterminisme | même appel répété 5 fois | Jev |
| E8 limites annoncées | dates, comptage, arithmétique, maximum ; sonde de longueur de contexte | tous systèmes / Jev |
| E9 multi-questions | oui/non opposés vs choix unique ; question seule vs avec deux autres | Jev |

Échantillons : tirés au hasard avec graine fixe (`SEED`) dans un réservoir mis en cache, **emboîtés** (les 200 premiers exemples sont les mêmes que les 200 premiers d'un tirage de 500), identiques pour tous les systèmes (comparaison **appariée**). Les tâches à classes déséquilibrées (modération) sont échantillonnées équilibrées, ou l'étude refuse de s'exécuter.
Taille « standard » : 200 exemples par tâche pour Jev, 100 pour les références coûteuses (mêmes 100 premiers exemples).
Largeur typique de l'intervalle à 95 % sur une précision de 85 % avec n = 200 : ± 5 points ; avec n = 100 : ± 7 points.
**On ne conclut jamais sur la seule moyenne** : lire l'intervalle.

## 5. Hypothèses et seuils (grille de lecture)

Les cinq premières correspondent à ce que l'éditeur laisse entendre ; elles sont formulées pour pouvoir être **réfutées**.

| # | Hypothèse | Constat « confirmé » | Constat « réfuté » | Sinon |
|---|---|---|---|---|
| H1 | Qualité : Jev est au moins équivalent à une référence | borne basse de l'IC 95 % de (acc_Jev − acc_réf) > −3 points **et** borne haute ≥ 0 | borne haute < 0 (même si l'écart reste dans la marge : étiqueté « légèrement inférieur », jamais « recommandé ») | inconclusif |
| H2 | Coût : Jev ≥ 10 fois moins cher par appel | rapport des coûts moyens ≥ 10 | < 10 | – |
| H3 | Latence : p50 de Jev ≥ 2 fois plus faible | rapport des p50 ≥ 2 | < 2 | – |
| H4 | Calibration : la confiance est fiable | borne haute de l'IC de l'ECE ≤ 0,05 (« bonne ») ou ≤ 0,10 (« acceptable ») | borne basse de l'IC > 0,10 | inconclusive |
| H5 | Déterminisme : au plus 2 % d'exemples changent d'étiquette sur 5 répétitions identiques | borne haute de l'IC de Wilson ≤ 2 % | borne basse > 2 % | inconclusif |
| H6 | Facturation : coût = tokens d'entrée × 0,042 $/M (sortie gratuite) | rapport médian dans ±5 % | hors de ±5 % | – |
| H7 | Robustesse : ≤ 3 points perdus avec 600 tokens de bruit placés avant ; ≤ 3 % d'étiquettes changées par permutation de l'ordre des options | borne haute de la chute (resp. de l'IC de Wilson du taux de changement) ≤ 3 points | borne basse > 3 points | inconclusif |
| H8 | Limites annoncées (dates, comptage, arithmétique) : Jev n'est pas utilisable | borne haute de l'IC de la précision < 90 % | borne basse ≥ 90 % | inconclusif |

« **Recommandé** » pour une tâche = H1 confirmée (équivalent ou supérieur) **et** H2 confirmée, face à une référence donnée.
Le choix du 90 % pour « utilisable » et des 3 points est une convention de décision, pas une vérité : ils sont publiés pour être discutés, pas ajustés après coup.

## 6. Méthode statistique

- Intervalles de confiance : bootstrap (2 000 rééchantillonnages) sur les exemples.
- Comparaisons appariées : test exact de McNemar ; correction de Holm sur l'ensemble des comparaisons.
- Seuil de décision d'une probabilité (oui/non) : choisi sur une moitié des exemples, évalué sur l'autre (et inversement) — jamais optimisé sur les données qui servent à le mesurer.
- Calibration : ECE à 10 classes, **avec intervalle** (l'ECE est biaisé vers le haut sur petit échantillon : on ne conclut « bonne » que si la borne haute passe sous le seuil).
- Latence : p50/p90/p95/p99 avec IC par bootstrap sur p50 et p95 ; mesure côté client (`time.perf_counter`), tentative réussie seule ; les attentes de réessai sont comptées à part ; appels **en série** ; systèmes entrelacés en ordre aléatoire pour ne pas confondre système et heure.

## 7. Biais connus et parades

| Risque | Parade |
|---|---|
| Consigne mieux rédigée pour un système | Mêmes libellés et mêmes descriptions pour tous ; expérience « sans descriptions » ; limite assumée au §2 |
| Dérive de la charge d'OpenRouter dans le temps | Entrelacement aléatoire des systèmes ; répétition ; heure notée |
| Versions de modèles qui changent | Version servie lue dans la réponse et notée ; alias résolu puis figé |
| Fuite de données d'entraînement | Jeux publics donc possible ; ajout de tâches synthétiques et de jeux contrastifs ; limite explicitée dans le rapport |
| Réponses invalides comptées à tort ou écartées à tort | Réponse inexploitable ou appel échoué = **fausse** pour toutes les métriques (AUC et Brier : p = 0,5 ; MAE : erreur maximale) ; taux de validité publié ; sous 90 % de réponses exploitables, la comparaison est marquée « peu fiable » |
| Artefact de format qui pénalise une référence (réponse vide ou tronquée par un raisonnement caché) | `max_tokens` = 1000, `finish_reason` conservé ; une réponse vide ou tronquée est un appel échoué (rejoué à la reprise, publié) et jamais une « mauvaise réponse » du modèle |
| Overhead réseau fixe qui écrase l'écart de latence | Connexions persistantes (keep-alive) ; bootstrap par exemple ; p50 par tâche ; les appels identiques répétés peuvent être cachés côté fournisseur (limite) |
| Doublons après reprise | Un seul enregistrement par appel logique à l'analyse (le réussi l'emporte) ; le modèle fait partie de la clé de reprise |
| Plafond contourné par les reprises ou le parallélisme | Le plafond vaut pour le run entier (dépenses antérieures déduites) ; réservation du coût estimé avant chaque appel |
| Biais du « modèle juge » | Aucun juge : vérité terrain publique ou calculée |
| Optimisation sur le test | Seuils fixés ici ; seuil de décision réglé sur l'autre moitié |
| Dépenses hors de contrôle | Plafond de budget : arrêt net, reprise possible |

## 8. Ce qui n'est pas mesuré

La qualité sur vos données métier (à faire avec `--custom`, voir README) ; l'explicabilité (Jev n'en produit pas) ; la tenue dans le temps
(une seule session) ; la disponibilité (service en version `alpha`) ; Jev Router (autre produit, prix variable, hors périmètre).

## 9. Règle de publication

On publie **tout** : résultats défavorables à Jev compris, tâches où il est inconclusif, et ce qui n'a pas pu être mesuré.
Le rapport (`REPORT.md`) est généré par le code depuis le journal brut ; aucun chiffre n'est saisi à la main.
