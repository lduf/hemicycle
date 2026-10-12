# Dossier de passation — « Votes vs promesses » (Assemblée nationale, 17e législature)

## 1. Objectif produit
Aider les gens, surtout les jeunes et ceux qui ne s'intéressent pas à la politique, à voir de quels groupes ils sont proches d'après les **votes réels** à l'Assemblée, pas d'après les promesses.
Parcours : l'utilisateur répond Pour/Contre à des votes réels, on compare au vote de chaque groupe, puis on affiche les groupes les plus proches et les plus éloignés.
Le ton doit être informé, informatif et attractif.

## 2. Règles non négociables
- **Aucun nom de parti ni de personne pendant le quiz.** Les groupes n'apparaissent qu'au résultat. Dans le quiz, l'hémicycle montre les votes à la place réelle des sièges, sans étiquette.
- **Résumés neutres de 3 à 5 lignes**, symétriques (arguments pour et contre à poids égal), sourcés, sans adjectif orienté.
- **Boutons explicites** : « Pour l'interdiction de X », « Contre le passage à X ans ». Toujours vérifier le sens de « pour » : un amendement de suppression ou de rejet inverse le sens.
- **Hémicycle fidèle** : positions réelles (numPlace), absents visibles, gauche et droite indiquées.
- Les non-inscrits (NI) sont affichés sur l'hémicycle mais exclus du score.
- Tout fait est sourcé (lien vers le scrutin officiel). Pas de chiffre issu de la mémoire du modèle.

## 3. Données (open data AN)
- `Scrutins.json.zip` : champs `numero`, `dateScrutin`, `titre`, `sort.code`, `syntheseVote.decompte`, `demandeur.texte`, `typeVote.codeTypeVote` (SPO/SPS/MOC), `ventilationVotes.organe.groupes.groupe[]` (organeRef, nombreMembresGroupe, vote.decompteVoix, vote.decompteNominatif{pours, contres, abstentions, nonVotants → votant[{acteurRef, mandatRef, parDelegation, numPlace}]}).
- Acteurs et organes AMO10. Téléchargement avec `curl --retry 3 --retry-all-errors -C -`.
- Couverture au moment de l'export : 2024-10-09 → 2026-10-09 (8 649 scrutins hors MOC).
- Alias de groupes : PO847173 et PO872880 → UDR. NI = PO840056.
- 11 groupes scorés : RN, EPR, LFI-NFP, SOC, DR, ECOS, DEM, HOR, LIOT, GDR, UDR.
- Ordre des sièges de gauche à droite : GDR, LFI-NFP, ECOS, SOC, LIOT, DEM, EPR, HOR, DR, UDR, RN, NI.
- Numéros de sièges : RN environ 1 à 156 (droite), GDR environ 576 à 593 (gauche). Tri par numPlace décroissant = de gauche à droite.
- **À vérifier avant toute réutilisation publique** : la licence de réutilisation des données (Licence Ouverte). Non vérifiée à ce jour.

## 4. Scoring
- Pour chaque groupe et chaque scrutin : m = (pour − contre) / (pour + contre + abstentions).
- Réponse de l'utilisateur : u = +1 (pour), −1 (contre), 0 (passer).
- Accord = 1 − |u − m| / 2.
- Les thèmes prioritaires choisis par l'utilisateur comptent ×2.
- Biais d'acquiescement documenté dans la page Méthode.
- Le quiz tire 15 questions au hasard parmi le pool, avec jusqu'à 9 places réservées aux thèmes prioritaires.

## 5. Code existant (dossier scratchpad de la session)
- `build_data.py` → `quiz_data.json` (groupes, 15 thèmes, questions). Attention : le relancer écrase `seats`, donc relancer `seatmap.py` ensuite.
- `extra_q.py` : 19 questions supplémentaires (le pool compte 34 questions).
- `seats.py` → `obs.json` ; `seatmap.py` ajoute la chaîne de sièges par question (fenêtre de 45 jours, puis 150 en repli).
- `stats.py` → `stats.json` (participation, auteurs d'amendements, discipline de Rice, taux de victoire, délégations, présence individuelle, jour de la semaine, mois, accord entre groupes).
- `template8.html` : source de l'interface v5 (placeholder `__DATA__`, `const STATS`). Build : remplacer `__DATA__` par le contenu de `quiz_data.json`, ce qui donne une page HTML autonome (`democratie.html`).
- Fichiers du dossier : `HANDOFF.md`, `template8.html`, `quiz_data.json`, `stats.json`, `groups17.json`, `build_data.py`, `extra_q.py`, `seats.py`, `seatmap.py`, `stats.py`. Les données brutes AN (`an_data/`, `an_orgs/`) ne sont pas incluses : les retélécharger depuis data.assemblee-nationale.fr (Scrutins.json.zip et AMO10) avec `curl --retry 3 --retry-all-errors -C -`. Ordre de reconstruction : `build_data.py` → `seatmap.py` (build_data efface les sièges) → `stats.py`, puis injecter `stats.json` dans `const STATS` du template.
- Artefact publié : https://claude.ai/artifact/WXBQGKG8T3JoueBSttVsKV

## 6. Pipeline de généralisation (à construire)
1. **Ingestion nocturne** des nouveaux scrutins et des fiches acteurs/organes.
2. **Sélection** des scrutins intéressants : divergence entre groupes, participation suffisante, mesure isolée de préférence, éviter les procédures obscures.
3. **Sens du vote** : règles déterministes (détecter suppression, rejet, rétablissement dans le titre) puis vérification par un modèle. En cas de doute, ne pas publier.
4. **Fiche neutre** générée à partir du texte officiel et de sources citées, puis filtre de neutralité et second modèle qui note l'orientation. Toute fiche notée orientée est rejetée.
5. **Validation humaine** par deux relecteurs de sensibilités opposées avant publication. Jusqu'à cette validation, afficher « non relu ».
6. **Base de promesses** par programme (2027), appariement sémantique puis confirmation humaine. Chaque promesse porte sa source (programme officiel de préférence). Couverture actuelle incomplète : DR, UDR et LIOT manquent.
7. **Site statique** régénéré chaque nuit à partir de JSON.
8. **Carte « Le vote de la semaine »** générée pour les réseaux.

## 7. Améliorations de présentation (DÉJÀ INTÉGRÉES au MVP v5, `template8.html`, à généraliser par le pipeline)
Dans le MVP : pronostic **optionnel** (désactivé par défaut, case « Mode pronostic » sur l’écran des thèmes, car il rallonge le parcours ; 3 classes calculées sur la part de pour), encart « Pourquoi ce vote peut surprendre » (texte `SURP` écrit à la main par vote + paires de groupes calculées à partir de `STATS.agree`), accroche `HOOK`, récap en story + carte canvas partageable, verdicts promesses/actes, carousels de chiffres, page « Comment c’est fait », durée Express/Standard/Complet. Pour chaque nouveau vote, le pipeline doit produire `HOOK` et `SURP` (neutres, sourcés, relus). Liste d’origine :
1. **Pronostic** (mode optionnel) : l'utilisateur parie sur le résultat, avec un score de flair à la fin.
2. **Encart « Pourquoi ce vote peut surprendre »** : raisons principales de chaque camp, symétriques, sans nom de parti (cas du nucléaire).
3. **Phrase d'accroche « Ça change quoi pour moi ? »** au début de chaque question.
4. **Résultat en story** (6 à 8 écrans plein format) et **carte à partager** générée en image.
5. **Promesses vs actes** avec verdict visuel (cohérent / partiel / contradictoire) et source.
6. **Fil de chiffres surprenants** à partir de la page stats.
7. **Page « Comment c'est fait »** : limites, relecture, sources, code ouvert.
8. Format : sans compte, aucune donnée stockée, mobile d'abord, texte en français simple, parcours de 3 minutes avec option longue.

## 8. Points de vigilance connus
- 6 résumés (Mayotte, Ukraine, narcotrafic, repas à 1 €, PFAS, loi agricole) reposent en partie sur des connaissances générales et doivent être revérifiés à la source.
- Tous les résumés sont rédigés par IA et non relus par des humains.
- Les promesses viennent de 3 articles de presse et d'un comparateur tiers. Certaines attributions sont incertaines.
- Les stats mesurent la participation aux scrutins publics, pas la charge de travail réelle (commissions, circonscription). À dire clairement dans l'interface.
- Environ 800 amendements n'ont pas d'auteur attribué.
- La géométrie de l'hémicycle est simplifiée : l'ordre des sièges est réel, les rangées sont schématiques.
- Un classement par député individuel est possible, mais il n'a pas été demandé ni validé. Le faire en connaissance de cause (exposition de personnes nommées).
