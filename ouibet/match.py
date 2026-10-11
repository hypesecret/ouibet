"""Rapproche un match PremierBet (noms français) d'un match football-data (noms anglais courts)."""
import re
import unicodedata
from datetime import timedelta
from difflib import SequenceMatcher

# Exonymes français -> nom local, et abréviations football-data.
ALIASES = {
    "seville": "sevilla", "valence": "valencia", "corogne": "coruna", "grenade": "granada",
    "majorque": "mallorca", "cordoue": "cordoba", "cadix": "cadiz", "gerone": "girona",
    "barcelone": "barcelona", "saragosse": "zaragoza", "espanyol": "espanol",
    "cologne": "koln", "mayence": "mainz", "hambourg": "hamburg", "fribourg": "freiburg",
    "brunswick": "braunschweig", "nuremberg": "nurnberg", "munich": "munich",
    "naples": "napoli", "rome": "roma", "turin": "torino", "florence": "fiorentina",
    "genes": "genoa", "venise": "venezia", "lisbonne": "lisbon", "bruges": "brugge",
    "anvers": "antwerp", "gand": "gent", "manchester": "man", "nottingham": "nottm",
    "wolverhampton": "wolves", "sheffield wednesday": "sheffield weds",
    "atletico": "ath", "athletic": "ath", "internazionale": "inter",
    "paris saint germain": "paris sg", "saint": "st", "sporting cp": "sp lisbon",
    "borussia monchengladbach": "mgladbach", "eintracht": "ein",
}
NOISE = {"fc", "afc", "cf", "sc", "ac", "as", "ud", "cd", "sd", "rc", "ca", "club", "de", "the",
         "calcio", "balompie", "hotspur", "albion", "and", "hove", "1", "sv", "vfb", "vfl", "tsg",
         "fk", "sk", "if", "bk", "ssc", "us", "afc"}


NOT_SENIOR = re.compile(r"\bU ?\d{2}\b|f[ée]min|women|dames|\(f\)|r[ée]serve|\bII\b|\bB$|jeunes|youth", re.I)


def norm(name):
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s.replace("'", ""))
    s = " ".join(s.split())
    for k, v in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
        s = re.sub(rf"\b{k}\b", v, s)
    return [t for t in s.split() if t not in NOISE] or s.split()


def similarity(a, b):
    ta, tb = norm(a), norm(b)
    short, long_ = sorted((ta, tb), key=len)
    hits = sum(any(l.startswith(t) or t.startswith(l) for l in long_ if min(len(t), len(l)) >= 3 or t == l)
               for t in short)
    tokens = hits / len(short)
    return max(tokens * 0.9, SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio())


def attach(events, refs, threshold=0.6):
    """Ajoute e['ref'] (probabilités de référence) aux événements qui trouvent leur match."""
    by_date = {}
    for r in refs:
        by_date.setdefault(r["date"], []).append(r)
    for e in events:
        # appels successifs : la première source qui matche gagne (direct avant vendredi)
        if "ref" in e:
            continue
        # la référence ne couvre que les équipes premières seniors masculines
        if NOT_SENIOR.search(f"{e['league']} {e['home']} {e['away']}"):
            continue
        d = e["start"].date()
        cands = by_date.get(d, []) + by_date.get(d - timedelta(days=1), []) + by_date.get(d + timedelta(days=1), [])
        best, score = None, 0
        for r in cands:
            h, a = similarity(e["home"], r["home"]), similarity(e["away"], r["away"])
            if min(h, a) >= threshold and h + a > score:
                best, score = r, h + a
        if best:
            e["ref"] = best
    return events
