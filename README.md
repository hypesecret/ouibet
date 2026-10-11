# ouibet

Constructeur de coupons cumulés pour **PremierBet Congo**. Tu donnes une mise et une cote visée (x10, x100, x1000). L'outil choisit les paris qui ont **la plus grande vraie chance** d'atteindre cette cote, vérifie les news et t'affiche cette chance honnêtement.

Ce n'est pas une machine à gagner. Un x100 reste un pari à environ 1 chance sur 80 à 130. L'outil rend ton coupon **moins mauvais**, c'est tout.

## Utilisation

```bash
cp .env.example .env                      # puis remplir les clés (optionnelles)
python -m ouibet                          # x10 et x100, matchs des 3 prochains jours
python -m ouibet --weekend --cible 10 100 1000 --news
python -m ouibet --marches 1x2 dc buts    # limiter les types de paris
python -m ouibet --ref-seulement          # seulement les matchs couverts par une référence
```

Python 3.10+, aucune dépendance pour le cœur. `pip install anthropic` seulement pour `--news`.

**Bon rythme** : un premier lancement le samedi matin, puis un second avec `--news` **1 h avant le premier match** (compos officielles sorties).

## Ce que l'outil prend en compte

| Paris PremierBet | Vraie probabilité tirée de |
|---|---|
| 1X2, Double chance | **marché** : référence directe |
| Plus/moins 2,5 buts | **marché** si la référence l'a, sinon modèle |
| Plus/moins 0,5 à 5,5 buts, Les deux marquent, Handicap (lignes .5), Résultat + buts, Résultat + BTTS | **modèle** : Dixon-Coles calé sur la référence, mélangé 50/50 avec PremierBet par prudence |
| Score exact, mi-temps, corners, cartons, buteurs | ignorés (pas de référence fiable) |

Matchs sans aucune référence : probabilité PremierBet sans sa marge, marquée `(PremierBet)`. Ils ne peuvent pas avoir de valeur et servent seulement à compléter un coupon.

## Sources

1. **PremierBet** : API publique du site, `sports-api.premierbet.com/cg/v1` (`country=CG&group=g5`). Liste des matchs, puis détail de chaque match (environ 96 marchés).
2. **Référence en direct** (si `ODDS_API_KEY`) : [The Odds API](https://the-odds-api.com), Pinnacle, sinon Bourse Betfair, sinon consensus de 10 bookmakers. Coût : 2 crédits par championnat qui a des matchs, sur 500 gratuits par mois. Les réponses vides sont gratuites.
3. **Référence du vendredi** : [football-data.co.uk](https://www.football-data.co.uk), environ 38 championnats, cotes moyennes et Bourse Betfair. Marge retirée par la méthode « power », sources incohérentes rejetées.
4. **News** (si `ANTHROPIC_API_KEY`, option `--news`) : Claude cherche sur le web blessures, suspensions, compos, rotation et enjeu pour **chaque match retenu**. Un match classé `DANGER` est retiré et les coupons sont reconstruits.

## Garde-fous

- **Écart suspect** : si PremierBet s'écarte de plus de 10 points de la référence du vendredi, il y a probablement eu une news depuis, et le match est écarté (`--garder-suspects` pour le garder).
- Rapprochement des noms FR ↔ EN à ±1 jour, avec exclusion des équipes jeunes, féminines et réserves.
- Un seul pari par match dans un coupon.

## Architecture

`engine.py` est le moteur (données → paris → coupons → alertes). `__main__.py` n'est que l'affichage terminal. Une interface web peut se brancher sur le même moteur.

## Limites

- Les cotes bougent : vérifier sur le site avant de valider.
- L'API PremierBet n'est pas documentée et peut changer à tout moment.
