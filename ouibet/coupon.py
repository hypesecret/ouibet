"""Construit le coupon qui atteint la cote visée avec la plus grande vraie probabilité.

On maximise le produit des probabilités sous contrainte produit des cotes >= cible.
En log : minimiser sum(-ln p) sous sum(ln cote) >= ln(cible) -> sac à dos par groupe (un pari par match).
"""
import math

from .match import norm
from .reference import devig

STEP = 0.02  # précision en log-cote


def legs(events, ref_only=False):
    out = []
    for e in events:
        o = e["odds"]
        if "ref" in e:
            p, src = e["ref"]["p"], "marché"
        elif ref_only:
            continue
        else:
            p = dict(zip("1X2", devig([o["1"], o["X"], o["2"]])))
            src = "PremierBet"
        key = (e["start"].date(), " ".join(norm(e["home"])), " ".join(norm(e["away"])))
        label = {"1": e["home"], "X": "Nul", "2": e["away"]}
        for k in "1X2":
            out.append({"event": e, "key": key, "pick": k, "label": label[k], "odds": o[k],
                        "p": p[k], "value": p[k] * o[k], "src": src})
    return out


def build(legs, target, max_legs=12, max_odds=None, pool=200):
    cands = [l for l in legs if l["odds"] > 1.01 and (max_odds is None or l["odds"] <= max_odds)]
    # garder les paris les plus "efficaces" (peu de probabilité perdue par unité de cote gagnée)
    cands.sort(key=lambda l: -math.log(l["p"]) / math.log(l["odds"]))
    seen, groups = {}, []
    for l in cands:
        if len(seen) >= pool and l["key"] not in seen:
            continue
        if l["key"] not in seen:
            seen[l["key"]] = len(groups)
            groups.append([])
        groups[seen[l["key"]]].append(l)

    B = math.ceil(math.log(target) / STEP)
    INF = float("inf")
    # dp[n][b] = (coût minimal, liste de paris) avec n paris et b paliers de cote (plafonné à B)
    dp = [[(INF, None)] * (B + 1) for _ in range(max_legs + 1)]
    dp[0][0] = (0.0, ())
    for g in groups:
        new = [row[:] for row in dp]
        for n in range(max_legs):
            for b in range(B + 1):
                c, chosen = dp[n][b]
                if chosen is None:
                    continue
                for l in g:
                    nb = min(B, b + int(math.log(l["odds"]) / STEP))
                    nc = c - math.log(l["p"])
                    if nc < new[n + 1][nb][0]:
                        new[n + 1][nb] = (nc, chosen + (l,))
        dp = new
    best = min((dp[n][B] for n in range(1, max_legs + 1)), key=lambda x: x[0])
    if best[1] is None:
        return None
    sel = sorted(best[1], key=lambda l: l["event"]["start"])
    odds = math.prod(l["odds"] for l in sel)
    if odds < target:  # arrondi des paliers : on vérifie quand même
        return None
    return {"legs": sel, "odds": odds, "p": math.prod(l["p"] for l in sel),
            "p_book": math.prod(1 / l["odds"] for l in sel)}
