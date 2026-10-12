# Base de promesses

Un fichier JSON par programme (de préférence le **programme officiel** du parti, sinon source de presse), par ex. `rn-2027.json` :

```json
{"id": "rn2027", "titre": "Programme RN 2027", "bloc": "RN", "groups": ["RN"], "url": "https://…", "date": "2026-09-01",
 "officiel": true, "promesses": [{"id": "rn2027-12", "text": "…", "theme": "énergie"}]}
```

Ajouter aussi l'entrée dans `content/sources.json` : `"rn2027": ["Programme RN 2027", "https://…"]`.
Couverture actuelle : `python -m pipeline.promises coverage` (DR, UDR et LIOT sont à compléter).
Ensuite `python -m pipeline.promises propose` puis confirmation humaine (`confirm N INDEX --exp pour|contre|none`).
