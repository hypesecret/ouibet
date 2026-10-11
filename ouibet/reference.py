"""Probabilités de référence : consensus du marché publié par football-data.co.uk.

Deux fichiers mis à jour chaque semaine (en général le vendredi) :
- fixtures.csv : ~22 championnats européens majeurs
- new_league_fixtures.csv : ~16 autres (Argentine, Brésil, USA, Japon...)

On prend la Bourse Betfair (BFE, marge quasi nulle) et la moyenne des bookmakers (Avg),
on retire la marge (méthode "power") et on fait la moyenne des deux.
"""
import csv
import io
from datetime import datetime

from .http import get

FILES = [
    "https://www.football-data.co.uk/fixtures.csv",
    "https://www.football-data.co.uk/new_league_fixtures.csv",
]


def devig(odds):
    """Retire la marge par la méthode power : p_i = (1/o_i)^k avec somme = 1."""
    raw = [1 / o for o in odds]
    lo, hi = 0.5, 3.0
    for _ in range(60):
        k = (lo + hi) / 2
        s = sum(r ** k for r in raw)
        lo, hi = (k, hi) if s > 1 else (lo, k)
    k = (lo + hi) / 2
    return [r ** k for r in raw]


def _num(row, key):
    try:
        v = float(row.get(key) or "")
        return v if v > 1 else None
    except ValueError:
        return None


def fixtures():
    out = []
    for url in FILES:
        try:
            text = get(url, ttl=3 * 3600)
        except Exception:
            continue
        for row in csv.DictReader(io.StringIO(text)):
            home = row.get("HomeTeam") or row.get("Home")
            away = row.get("AwayTeam") or row.get("Away")
            try:
                date = datetime.strptime(row["Date"], "%d/%m/%Y").date()
            except (KeyError, ValueError):
                continue
            probs = []
            for pre in ("PS", "BFE", "Avg"):
                o = [_num(row, pre + s) for s in "HDA"]
                # marge plausible seulement (la bourse a parfois des cotes vides type 1.17/1.12/1.17)
                if all(o) and 0.97 <= sum(1 / x for x in o) <= 1.12:
                    probs.append(devig(o))
            if not (home and away and probs):
                continue
            p = [sum(x[i] for x in probs) / len(probs) for i in range(3)]
            p = {"1": p[0], "X": p[1], "2": p[2]}
            overs = []
            for pre in ("BFE", "Avg"):
                o = [_num(row, f"{pre}>2.5"), _num(row, f"{pre}<2.5")]
                if all(o) and 0.97 <= sum(1 / x for x in o) <= 1.12:
                    overs.append(devig(o)[0])
            if overs:
                p["O2.5"] = sum(overs) / len(overs)
            out.append({"home": home, "away": away, "date": date, "p": p, "src": "vendredi (football-data)"})
    return out
