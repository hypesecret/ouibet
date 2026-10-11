"""python -m ouibet --mise 10000 --cible 10 100 [--weekend | --jours 3] [--news]"""
import argparse
import sys
from datetime import timedelta, timezone

from . import config, coupon, engine, news

BZV = timezone(timedelta(hours=1))  # heure de Brazzaville
JOURS = ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"]
ICON = {"ok": "OK", "attention": "ATTENTION", "danger": "DANGER"}


def fmt_chance(p):
    return f"1 sur {round(1 / p):,}".replace(",", " ") if p > 0 else "-"


def when(e):
    t = e["start"].astimezone(BZV)
    return f"{JOURS[t.weekday()]} {t:%d/%m %Hh%M}"


def show(title, c, mise, reports):
    print(f"\n=== {title} ===")
    if not c:
        print("  Impossible d'atteindre la cote avec ces matchs.")
        return
    for l in c["legs"]:
        e = l["event"]
        print(f"  {when(e)}  {e['home']} - {e['away']}  [{e['league']}]")
        print(f"      -> {l['label']}  cote {l['odds']:.2f}  vraie proba {l['p']:.0%}  "
              f"valeur {l['value'] - 1:+.0%}  ({l['src']}{', ' + l['src_ref'] if l['src_ref'] else ''})")
        r = reports.get(l["key"])
        if r:
            print(f"      [{ICON[r['niveau']]}] {r['resume']}")
            if r["absents"]:
                print(f"      Absents : {', '.join(r['absents'])}")
            print(f"      Impact : {r['impact_pari']}{'  (compo officielle sortie)' if r['compo_officielle'] else ''}")
    gain = mise * c["odds"]
    print(f"  Cote totale {c['odds']:.2f}  ->  {mise:,.0f} FCFA rapportent {gain:,.0f} FCFA".replace(",", " "))
    print(f"  Vraie chance de passer : {fmt_chance(c['p'])}   "
          f"(le bookmaker la paie comme {fmt_chance(c['p_book'])})")
    print(f"  Espérance : {c['p'] * c['odds'] - 1:+.0%} de la mise sur le long terme")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Coupon cumulé PremierBet Congo optimisé")
    ap.add_argument("--mise", type=float, default=10000)
    ap.add_argument("--cible", type=float, nargs="+", default=[10, 100], help="multiplicateurs visés, ex. 10 100 1000")
    ap.add_argument("--jours", type=int, default=3, help="matchs des N prochains jours")
    ap.add_argument("--weekend", action="store_true", help="seulement samedi + dimanche prochains")
    ap.add_argument("--max-matchs", type=int, default=12)
    ap.add_argument("--cote-max", type=float, default=1.8, help="cote max par match pour le coupon 'favoris'")
    ap.add_argument("--marches", nargs="+", default=list(coupon.FAMILIES), choices=list(coupon.FAMILIES),
                    help="types de paris autorisés")
    ap.add_argument("--ref-seulement", action="store_true", help="seulement les matchs couverts par une référence")
    ap.add_argument("--news", action="store_true", help="vérifier les news des matchs retenus (clé Anthropic)")
    ap.add_argument("--garder-suspects", action="store_true",
                    help="garder les matchs où PremierBet s'écarte beaucoup de la référence du vendredi")
    a = ap.parse_args()

    start, end = engine.window(a.jours, a.weekend)
    evs = engine.load(start, end)
    n_ref = sum("ref" in e for e in evs)
    n_live = sum("ref" in e and e["ref"]["src"].startswith("direct") for e in evs)
    print(f"\n{len(evs)} matchs du {start:%d/%m} au {end:%d/%m} : {n_ref} avec référence "
          f"({n_live} en direct, {n_ref - n_live} du vendredi).")
    if not config.ODDS_API_KEY:
        print("  Astuce : ajoute ODDS_API_KEY dans .env pour une référence en direct (voir README).")
    if n_ref == 0:
        print("  Sans référence, aucune valeur n'est détectable : relance vendredi/samedi ou ajoute ODDS_API_KEY.")

    legs = coupon.legs(evs, a.ref_seulement, a.marches, a.garder_suspects)
    suspects = [e for e in evs if e.get("suspect")]
    if suspects and not a.garder_suspects:
        print(f"\nÉcartés car PremierBet a bougé depuis vendredi (news probable) : "
              + ", ".join(f"{e['home']}-{e['away']}" for e in suspects[:8]) + ("..." if len(suspects) > 8 else ""))

    value = sorted((l for l in legs if l["src"] != "PremierBet" and l["value"] > 1.02), key=lambda l: -l["value"])
    if value:
        print("\nMeilleures valeurs (PremierBet paie plus que la référence) :")
        for l in value[:10]:
            e = l["event"]
            print(f"  {e['home']} - {e['away']} : {l['label']}  cote {l['odds']:.2f}, vraie proba {l['p']:.0%}, "
                  f"valeur {l['value'] - 1:+.0%} ({l['src']})")

    reports = {}
    if a.news and news.available():
        res, reports, excluded = engine.coupons_with_news(legs, a.cible, a.max_matchs, a.cote_max)
        if excluded:
            print(f"\n{len(excluded)} match(s) retiré(s) suite aux news (niveau DANGER), coupons reconstruits.")
    else:
        if a.news:
            print("\n--news ignoré : il faut ANTHROPIC_API_KEY dans .env et `pip install anthropic`.")
        res = engine.coupons(legs, a.cible, a.max_matchs, a.cote_max)
    for r in res:
        show(f"x{r['target']:g} - {r['style']}", r["coupon"], a.mise, reports)


if __name__ == "__main__":
    main()
