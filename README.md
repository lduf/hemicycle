# Hémicycle — votes vs promesses

Quiz civique : l'utilisateur répond Pour/Contre à de **vrais votes** de l'Assemblée nationale (17e législature), on compare
au vote de chaque groupe, puis on affiche les groupes les plus proches et les plus éloignés. Les groupes n'apparaissent
qu'au résultat ; pendant le quiz, l'hémicycle montre les votes à la place réelle des sièges, sans étiquette.

Ce dépôt contient le **pipeline de généralisation** : il ingère chaque nuit les nouveaux scrutins, propose les plus
intéressants, prépare des fiches neutres, les fait relire par des humains, puis régénère un site statique.

## Règles non négociables (appliquées par le code)

| Règle | Où elle est appliquée |
|---|---|
| Aucun nom de parti ni de personne dans les textes du quiz | `neutrality.deterministic` (sigles, noms de groupes, « M./Mme + nom », noms complets des députés) |
| Résumé de 3 à 5 phrases, arguments pour/contre symétriques, sans adjectif orienté | `neutrality.deterministic` + note d'orientation par un second modèle (`NEUTRALITY_MAX`) |
| Boutons explicites, sens de « pour » vérifié | `direction.classify` (règles) puis `direction.llm_check` ; en cas de doute la fiche est **bloquée** |
| Non publié sans validation humaine de deux sensibilités opposées | `review.can_publish` ; modifier le texte efface les relectures (`store.text_hash`) |
| Tout fait est sourcé | `store.sources_ok`, lien vers le scrutin officiel, domaines officiels uniquement (`sources.py`) |
| Pas de chiffre issu de la mémoire du modèle | le prompt n'autorise que les extraits de sources fournis |
| Hémicycle fidèle (numPlace, absents visibles) | `seatmap.py` |
| NI affichés mais exclus du score | `config.SCORED` |
| « Non relu » affiché tant que non validé | `status != published` → étiquette dans l'interface |

Échec fermé partout : pas de clé API, pas de second modèle, sens douteux, sources absentes → la fiche reste `blocked`.

## Utilisation

```bash
pip install -r requirements.txt           # Pillow, seulement pour la carte à partager
python -m pipeline.nightly                # tout : ingest, select, drafts, audit, stats, build, card, report
python -m pipeline.nightly --no-download  # sans réseau (réutilise an_data/)
python -m unittest discover -s tests
```

Étapes isolées : `python -m pipeline.ingest`, `.select_votes`, `.audit`, `.stats_build`, `.build_site`, `.weekly_card`.

### Cycle d'une fiche
1. `select_votes` classe les candidats (divergence entre groupes, participation, mesure isolée, pas de procédure) → `data/candidates.json`.
2. Un humain choisit un candidat et ajoute ses **sources officielles** dans `content/inbox.json` : `{"8427": ["https://www.assemblee-nationale.fr/…"]}`.
3. `nightly` rédige la fiche (via `claude -p`, donc ton abonnement Claude ; `HEMI_LLM=api` + `ANTHROPIC_API_KEY` pour l'API ; `HEMI_LLM=none` pour désactiver ; modèles : `HEMI_MODEL_WRITER`, `HEMI_MODEL_JUDGE`), vérifie le sens et la neutralité → `pending_review` ou `blocked` (raison dans `content/questions/N.json`).
4. Deux relecteurs de bords opposés : `python -m pipeline.review sign 8427 --by Nom --side gauche --verdict approve` puis `--side droite`. → `published`.
5. Le build n'inclut que `published`, `pending_review` et `legacy` (ces deux derniers étiquetés « non relue »). Options : `build_site.build(include_pending=False)`.

`python -m pipeline.review list` montre l'état ; `data/REVIEW_QUEUE.md` (et le résumé du job GitHub) liste le travail humain.

### Promesses
Déposer les programmes dans `content/programmes/` (voir son README), puis `python -m pipeline.promises propose` et
`confirm`. Rien n'est affiché sans confirmation humaine. `promises coverage` liste les groupes sans promesse (DR, UDR, LIOT aujourd'hui).

## Organisation

```
pipeline/            code (ingest, select_votes, direction, fiche, neutrality, review, promises, seatmap, stats_build, build_site, weekly_card, nightly)
pipeline/templates/  interface (placeholders __DATA__, __SRC__, __PROM__, __STATS__, __HOOK__, __SURP__, __LABELS__)
content/             contenu éditorial versionné : questions/N.json, promise_matches.json, sources.json, programmes/
data/, an_data/      données dérivées/brutes (non versionnées, régénérées)
docs/                site généré (déployé sur GitHub Pages par .github/workflows/nightly.yml)
legacy/              scripts du MVP v5 (build_data.py, seats.py, …), conservés pour référence
tests/
```

## Données et licence

Données : [data.assemblee-nationale.fr](https://data.assemblee-nationale.fr) (scrutins et AMO10), sous **Licence Ouverte / Open
Licence v2.0 (Etalab)**, vérifiée sur la page de licence du site de l'Assemblée : réutilisation libre, y compris commerciale,
à condition de **mentionner la source et la date de dernière mise à jour**. Le site généré affiche la source et `docs/data.json`
reprend la mention de licence et la date de génération.

## Limites connues
- Les statistiques mesurent la participation aux scrutins **publics**, pas la charge de travail réelle (commissions, circonscription).
- ~800 amendements sans auteur attribué (la liste des acteurs AMO10 ne couvre que les députés en exercice).
- Géométrie de l'hémicycle schématique : l'ordre des sièges est réel, les rangées ne le sont pas.
- Un classement par député n'est ni demandé ni validé : le pipeline n'en produit pas.
- Les 34 fiches héritées du MVP sont `legacy` (rédigées par IA, non relues) ; `pipeline.audit` en signale 12 qui ne respectent pas
  les règles de longueur ou de symétrie ; 6 d'entre elles (Mayotte, Ukraine, narcotrafic, repas à 1 €, PFAS, loi agricole) sont à revérifier à la source.
