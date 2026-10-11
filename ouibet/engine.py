"""Moteur ouibet : données -> paris -> coupons -> alertes. Utilisé par le CLI (et la future interface web)."""
import sys
from datetime import datetime, time, timedelta, timezone

from . import coupon, match, news, odds_api, premierbet, reference

BZV = timezone(timedelta(hours=1))  # heure de Brazzaville


def window(days=3, weekend=False, now=None):
    now = now or datetime.now(BZV)
    if weekend:
        sat = now.date() + timedelta(days=(5 - now.weekday()) % 7)
        return sat, sat + timedelta(days=1)
    return now.date(), now.date() + timedelta(days=days - 1)


def load(start, end, log=lambda m: print(m, file=sys.stderr)):
    """Matchs PremierBet de la fenêtre, avec tous leurs paris et leur référence (direct puis vendredi)."""
    log("Cotes PremierBet...")
    evs = [e for e in premierbet.events()
           if e["start"] > datetime.now(timezone.utc) + timedelta(minutes=15)
           and start <= e["start"].astimezone(BZV).date() <= end]
    log(f"Détail des paris pour {len(evs)} matchs...")
    premierbet.attach_markets(evs)
    t0 = datetime.combine(start, time.min, BZV)
    t1 = datetime.combine(end, time.max, BZV)
    log("Référence en direct (The Odds API)...")
    match.attach(evs, odds_api.fixtures(t0, t1))
    log("Référence du vendredi (football-data.co.uk)...")
    match.attach(evs, reference.fixtures())
    return evs


def coupons(legs, targets, max_legs=12, max_odds=1.8, exclude=()):
    out = []
    for t in targets:
        out.append({"target": t, "style": "meilleure chance",
                    "coupon": coupon.build(legs, t, max_legs, exclude=exclude)})
        out.append({"target": t, "style": f"favoris (cote <= {max_odds})",
                    "coupon": coupon.build(legs, t, max_legs, max_odds=max_odds, exclude=exclude)})
    return out


def coupons_with_news(legs, targets, max_legs=12, max_odds=1.8, rounds=2, log=print):
    """Construit les coupons, vérifie les news des matchs retenus, retire les matchs 'danger' et recommence."""
    exclude, reports = set(), {}
    for _ in range(rounds + 1):
        res = coupons(legs, targets, max_legs, max_odds, exclude)
        todo = [l for r in res if r["coupon"] for l in r["coupon"]["legs"] if l["key"] not in reports]
        if not todo:
            break
        log(f"Vérification des news pour {len({l['key'] for l in todo})} matchs...")
        reports.update(news.check_all(todo))
        danger = {k for k, r in reports.items() if r["niveau"] == "danger"} - exclude
        if not danger:
            break
        exclude |= danger
    return res, reports, exclude
