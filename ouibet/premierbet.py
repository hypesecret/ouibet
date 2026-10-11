"""Cotes avant-match football de PremierBet Congo (API publique du site)."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .http import get_json

API = "https://sports-api.premierbet.com/cg/v1"
PARAMS = "country=CG&group=g5&platform=desktop&locale=fr"
HEADERS = {"Referer": "https://www.premierbet.com/", "Accept": "application/json"}
FOOTBALL = 1


def competitions():
    d = get_json(f"{API}/competitions?{PARAMS}&sportId={FOOTBALL}", ttl=1800, headers=HEADERS)
    for cat in d["categories"]:
        for comp in cat["competitions"]:
            if comp.get("eventCount"):
                yield {"id": comp["id"], "name": comp["name"], "country": cat["name"]}


def _events(comp):
    url = f"{API}/events?{PARAMS}&sportId={FOOTBALL}&eventState=PRE_MATCH&isGroup=false&competitionId={comp['id']}"
    try:
        d = get_json(url, ttl=600, headers=HEADERS)
    except Exception:
        return []
    data = d.get("data") or []
    data = data if isinstance(data, list) else [data]
    out = []
    for s in data:
        for cat in s["categories"]:
            for c in cat["competitions"]:
                for e in c["events"]:
                    m = next((m for m in e.get("markets", []) if m["name"] == "1X2" and m.get("active")), None)
                    if not m or len(e["eventNames"]) != 2:
                        continue
                    odds = {o["name"]: float(o["value"]) for o in m["outcomes"] if o.get("active")}
                    if set(odds) != {"1", "X", "2"}:
                        continue
                    out.append({
                        "id": e["id"],
                        "home": e["eventNames"][0],
                        "away": e["eventNames"][1],
                        "start": datetime.fromtimestamp(e["startTime"] / 1000, tz=timezone.utc),
                        "league": f"{comp['country']} - {comp['name']}",
                        "odds": odds,
                    })
    return out


def events():
    """Tous les matchs de foot avant-match avec leurs cotes 1X2."""
    comps = list(competitions())
    with ThreadPoolExecutor(8) as ex:
        return [e for evs in ex.map(_events, comps) for e in evs]


def markets(event_id):
    """Tous les paris d'un match : liste de {market, name, line, odds}."""
    url = f"{API}/events/{event_id}?{PARAMS}"
    try:
        d = get_json(url, ttl=600, headers=HEADERS)
    except Exception:
        return []
    out, seen = [], set()
    for g in d.get("marketGroups", []):
        for m in g.get("markets", []):
            if not m.get("active"):
                continue
            for o in m.get("outcomes", []):
                key = (m["name"], o["name"], o.get("handicap"))
                if not o.get("active") or key in seen:
                    continue
                seen.add(key)
                try:
                    out.append({"market": m["name"], "name": o["name"], "line": o.get("handicap"),
                                "odds": float(o["value"])})
                except (TypeError, ValueError):
                    pass
    return out


def attach_markets(events):
    with ThreadPoolExecutor(8) as ex:
        for e, ms in zip(events, ex.map(lambda e: markets(e["id"]), events)):
            e["markets"] = ms
    return events
