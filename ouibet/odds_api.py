"""Référence en direct : cotes Pinnacle / Betfair via The Odds API (the-odds-api.com).

Offre gratuite : 500 crédits/mois. Coût = nb de marchés x nb de "régions" (10 bookmakers = 1 région).
On demande h2h + totals -> 2 crédits par championnat qui a des matchs ; les réponses vides sont gratuites.
"""
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from . import config
from .http import UA
from .reference import devig

API = "https://api.the-odds-api.com/v4"
# Pinnacle et la Bourse Betfair d'abord (les plus "justes"), puis 8 autres pour le consensus.
BOOKS = "pinnacle,betfair_ex_eu,williamhill,unibet_eu,onexbet,marathonbet,sport888,betsson,nordicbet,matchbook"
PRIORITY = ["soccer_epl", "soccer_spain_la_liga", "soccer_italy_serie_a", "soccer_germany_bundesliga",
            "soccer_france_ligue_one", "soccer_uefa_champs_league", "soccer_uefa_europa_league",
            "soccer_uefa_europa_conference_league", "soccer_netherlands_eredivisie",
            "soccer_portugal_primeira_liga", "soccer_efl_champ", "soccer_brazil_campeonato",
            "soccer_argentina_primera_division", "soccer_usa_mls", "soccer_turkey_super_league",
            "soccer_belgium_first_div", "soccer_spl", "soccer_germany_bundesliga2",
            "soccer_italy_serie_b", "soccer_spain_segunda_division", "soccer_france_ligue_two",
            "soccer_mexico_ligamx", "soccer_saudi_arabia_pro_league", "soccer_greece_super_league"]
remaining = None


def _get(path, **params):
    global remaining
    params["apiKey"] = config.ODDS_API_KEY
    req = urllib.request.Request(f"{API}{path}?{urllib.parse.urlencode(params)}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        remaining = r.headers.get("x-requests-remaining", remaining)
        return json.loads(r.read().decode())


def _consensus(event):
    """Probabilités sans marge : Pinnacle si dispo, sinon moyenne des bookmakers."""
    by_book = {}
    for b in event.get("bookmakers", []):
        p = {}
        for m in b.get("markets", []):
            if m["key"] == "h2h":
                o = {x["name"]: x["price"] for x in m["outcomes"]}
                if {event["home_team"], event["away_team"], "Draw"} <= set(o):
                    odds = [o[event["home_team"]], o["Draw"], o[event["away_team"]]]
                    if 0.97 <= sum(1 / x for x in odds) <= 1.12:
                        p.update(zip("1X2", devig(odds)))
            if m["key"] == "totals":
                o = {x["name"]: x["price"] for x in m["outcomes"] if x.get("point") == 2.5}
                if {"Over", "Under"} <= set(o):
                    p["O2.5"] = devig([o["Over"], o["Under"]])[0]
        if "1" in p:
            by_book[b["key"]] = p
    if not by_book:
        return None, None
    for sharp in ("pinnacle", "betfair_ex_eu"):
        if sharp in by_book:
            return by_book[sharp], sharp
    keys = set.intersection(*(set(p) for p in by_book.values()))
    return {k: sum(p[k] for p in by_book.values()) / len(by_book) for k in keys}, f"{len(by_book)} bookmakers"


def fixtures(start, end):
    """Matchs entre deux datetimes UTC avec probas de référence en direct. [] sans clé."""
    if not config.ODDS_API_KEY:
        return []
    try:
        sports = [s["key"] for s in _get("/sports") if s["key"].startswith("soccer_")
                  and s.get("active") and not s.get("has_outrights")]
    except Exception as e:
        print(f"The Odds API indisponible ({e}) : référence du vendredi seulement.", file=sys.stderr)
        return []
    sports.sort(key=lambda k: PRIORITY.index(k) if k in PRIORITY else len(PRIORITY))
    sports = sports[:config.ODDS_API_MAX_SPORTS]
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    out = []
    for key in sports:
        try:
            events = _get(f"/sports/{key}/odds", bookmakers=BOOKS, markets="h2h,totals", oddsFormat="decimal",
                          commenceTimeFrom=start.astimezone(timezone.utc).strftime(fmt),
                          commenceTimeTo=end.astimezone(timezone.utc).strftime(fmt))
        except Exception:
            continue
        for e in events:
            p, src = _consensus(e)
            if p:
                t = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
                out.append({"home": e["home_team"], "away": e["away_team"], "date": t.date(),
                            "p": p, "src": f"direct ({src})"})
    print(f"The Odds API : {len(out)} matchs, crédits restants ce mois : {remaining}", file=sys.stderr)
    return out
