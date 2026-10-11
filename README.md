# ouibet

Constructeur de coupons cumulés pour **PremierBet Congo**. Tu donnes une mise et une cote visée (x10, x100, x1000). L'outil choisit les matchs qui ont **la plus grande vraie chance** d'atteindre cette cote, et il t'affiche cette chance honnêtement.

Ce n'est pas une machine à gagner. Un x100 reste un pari à environ 1 chance sur 80 à 130. L'outil rend ton coupon **moins mauvais**, c'est tout.

## Utilisation

```bash
python -m ouibet                          # x10 et x100, matchs des 3 prochains jours
python -m ouibet --weekend --cible 10 100 1000
python -m ouibet --mise 5000 --cible 50 --jours 2
python -m ouibet --ref-seulement          # seulement les matchs couverts par la référence marché
```

Aucune dépendance : Python 3.10+ et la bibliothèque standard suffisent.

Pour chaque cible, l'outil sort deux coupons :
- **meilleure chance** : la combinaison mathématiquement la plus probable (souvent peu de matchs, parfois un outsider) ;
- **style favoris** : uniquement des matchs à cote ≤ 1,80 (modifiable avec `--cote-max`).

## Comment ça marche

1. **Cotes PremierBet** : API publique du site, `sports-api.premierbet.com/cg/v1` (paramètres `country=CG&group=g5`), environ 900 matchs de foot avant-match, marché 1X2.
2. **Vraie probabilité** : [football-data.co.uk](https://www.football-data.co.uk) publie chaque semaine (en général le **vendredi**) les cotes moyennes de 6+ bookmakers et de la Bourse Betfair pour environ 38 championnats. On retire la marge (méthode « power ») et on fait la moyenne. Les sources dont la marge est absurde sont rejetées : la Bourse affiche parfois des cotes vides.
3. **Rapprochement** : noms français PremierBet ↔ noms anglais football-data, à ±1 jour (alias : Valence→Valencia, La Corogne→Coruna…). Les équipes jeunes, féminines et réserves sont exclues.
4. **Coupon** : sac à dos en log, avec un seul pari par match. On maximise le produit des probabilités sous la contrainte « produit des cotes ≥ cible ».

Sans référence marché (championnats non couverts, ou avant le vendredi), la probabilité est celle de PremierBet sans sa marge, et la ligne est marquée `(PremierBet)`. Ces paris ont toujours une valeur négative : ils servent seulement à compléter.

**Lancer l'outil le vendredi soir ou le samedi** pour le week-end : c'est là que la référence couvre le plus de matchs.

## Limites connues

- Uniquement le marché 1X2 (pas encore double chance, +/- buts, les deux équipes marquent).
- Les cotes bougent : vérifier sur le site avant de valider.
- L'API PremierBet n'est pas documentée et peut changer à tout moment.
