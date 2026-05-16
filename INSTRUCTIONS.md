# Book Verres — Catalogue JSON

## Mettre à jour un fichier source

1. Aller sur github.com → ce dépôt → dossier `sources/`
2. Cliquer sur le fichier à remplacer (ex: `Tarifs_Bleu_SEI_Santeclair_...csv`)
3. Cliquer sur l'icône crayon (✏️) en haut à droite
4. Cliquer sur "..." puis "Upload file" — choisir le nouveau fichier
5. Cliquer "Commit changes"

→ GitHub génère automatiquement le nouveau `verres_complet.json` (~5 min)
→ Visible dans l'onglet "Actions" du dépôt

## URL stable du catalogue

```
https://github.com/benjamin1491/bookverres-catalog/releases/latest/download/verres_complet.json
```

Cette URL ne change jamais. Elle pointe toujours vers la dernière version générée.

## Fichiers sources attendus

| Fichier | Obligatoire |
|---------|------------|
| `PAO_SEI_*.xlsx` | ✅ Oui |
| CSV Carte Blanche | ✅ Oui |
| CSV Kalixia | ✅ Oui |
| CSV Optilys | ✅ Oui |
| CSV Santeclair | ✅ Oui |
| CSV Seveane | ✅ Oui |
| CSV Itelis | ❌ Optionnel |
| CSV Actil | ❌ Optionnel |
