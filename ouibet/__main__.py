"""python -m ouibet --mise 10000 --cible 10 [--weekend | --jours 3]"""
import argparse
import sys
from datetime import datetime, timedelta, timezone

from . import coupon, match, premierbet, reference

BZV = timezone(timedelta(hours=1))  # heure de Brazzaville
JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]


def fmt_chance(p):
    return f"1 sur {round(1 / p):,}".replace(",", " ") if p > 0 else "-"


def show(title, c, mise):
    print(f"\n=== {title} ===")
    if not c:
        print("  Impossible d'atteindre la cote avec ces matchs.")
        return
    for l in c["legs"]:
        e = l["event"]
        t = e["start"].astimezone(BZV)
        when = f"{JOURS[t.weekday()]} {t:%d/%m %Hh%M}"
        print(f"  {when}  {e['home']} - {e['away']}  [{e['league']}]")
        print(f"      -> {l['pick']} ({l['label']})  cote {l['odds']:.2f}  "
              f"vraie proba {l['p']:.0%}  valeur {l['value'] - 1:+.0%}  ({l['src']})")
    gain = mise * c["odds"]
    print(f"  Cote totale {c['odds']:.2f}  ->  {mise:,.0f} FCFA rapportent {gain:,.0f} FCFA".replace(",", " "))
    print(f"  Vraie chance de passer : {fmt_chance(c['p'])}   "
          f"(le bookmaker la paie comme {fmt_chance(c['p_book'])})")
    ev = c["p"] * c["odds"] - 1
    print(f"  Espérance : {ev:+.0%} de la mise sur le long terme")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Coupon cumulé PremierBet Congo optimisé")
    ap.add_argument("--mise", type=float, default=10000)
    ap.add_argument("--cible", type=float, nargs="+", default=[10, 100],
                    help="multiplicateurs visés, ex. 10 100 1000")
    ap.add_argument("--jours", type=int, default=3, help="matchs des N prochains jours")
    ap.add_argument("--weekend", action="store_true", help="seulement samedi + dimanche prochains")
    ap.add_argument("--max-matchs", type=int, default=12)
    ap.add_argument("--cote-max", type=float, default=1.8, help="cote max par match pour le coupon 'favoris'")
    ap.add_argument("--ref-seulement", action="store_true",
                    help="n'utiliser que les matchs couverts par la référence marché")
    a = ap.parse_args()

    now = datetime.now(BZV)
    if a.weekend:
        sat = now.date() + timedelta(days=(5 - now.weekday()) % 7)
        start, end = sat, sat + timedelta(days=1)
    else:
        start, end = now.date(), now.date() + timedelta(days=a.jours - 1)

    print("Récupération des cotes PremierBet...", file=sys.stderr)
    evs = [e for e in premierbet.events()
           if e["start"] > datetime.now(timezone.utc) + timedelta(minutes=15)
           and start <= e["start"].astimezone(BZV).date() <= end]
    print("Récupération de la référence marché (football-data.co.uk)...", file=sys.stderr)
    match.attach(evs, reference.fixtures())
    n_ref = sum("ref" in e for e in evs)
    print(f"\n{len(evs)} matchs du {start:%d/%m} au {end:%d/%m}, dont {n_ref} avec référence marché.")
    if n_ref == 0:
        print("  (La référence de la semaine sort en général le vendredi : relance vendredi/samedi.)")

    legs = coupon.legs(evs, ref_only=a.ref_seulement)
    value = sorted((l for l in legs if l["src"] == "marché" and l["value"] > 1.02), key=lambda l: -l["value"])
    if value:
        print("\nMeilleures valeurs (PremierBet paie plus que le marché) :")
        for l in value[:10]:
            e = l["event"]
            print(f"  {e['home']} - {e['away']}: {l['pick']} ({l['label']}) cote {l['odds']:.2f}, "
                  f"vraie proba {l['p']:.0%}, valeur {l['value'] - 1:+.0%}")

    for t in a.cible:
        show(f"x{t:g} - meilleure chance", coupon.build(legs, t, a.max_matchs), a.mise)
        show(f"x{t:g} - style favoris (cote <= {a.cote_max} par match)",
             coupon.build(legs, t, a.max_matchs, max_odds=a.cote_max), a.mise)


if __name__ == "__main__":
    main()
