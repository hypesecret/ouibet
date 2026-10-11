"""Construit le coupon qui atteint la cote visée avec la plus grande vraie probabilité.

On maximise le produit des probabilités sous contrainte produit des cotes >= cible.
En log : minimiser sum(-ln p) sous sum(ln cote) >= ln(cible) -> sac à dos par groupe (un pari par match).
"""
import math

from . import model
from .match import norm
from .reference import devig

STEP = 0.02  # précision en log-cote
SUSPECT_GAP = 0.10  # écart max PremierBet vs référence du vendredi avant de soupçonner une news

# familles de paris activables avec --marches
FAMILIES = {
    "1x2": {"1X2"},
    "dc": {"Double Chance"},
    "buts": {"Total de Buts"},
    "btts": {"Les Deux Equipes Marquent"},
    "handicap": {"Handicap"},
    "combo": {"Résultat + Plus/Moins De", "Resultat + Les Deux Équipes Marquent"},
}


def _line_key(o):
    """Clé qui regroupe les issues d'une même ligne (pour retirer la marge de PremierBet)."""
    try:
        line = float(o["line"]) if o["line"] not in (None, "") else None
    except ValueError:
        return None
    if o["market"] == "Handicap" and line is not None and o["name"] == "2":
        line = -line  # "1 +1.5" et "2 -1.5" sont les deux côtés du même pari
    return (o["market"], line)


def _pb_probs(ms):
    """Probabilité PremierBet sans marge pour chaque issue (par ligne de marché)."""
    groups = {}
    for o in ms:
        if o["market"] != "Double Chance":
            groups.setdefault(_line_key(o), []).append(o)
    p = {}
    for k, os_ in groups.items():
        if k is None or len(os_) < 2:
            continue
        if not 1.0 <= sum(1 / o["odds"] for o in os_) <= 1.3:
            continue
        for o, q in zip(os_, devig([o["odds"] for o in os_])):
            p[(o["market"], o["name"], o["line"])] = q
    x = {n: p.get(("1X2", n, None)) for n in "1X2"}
    if all(x.values()):
        for n, q in (("1X", x["1"] + x["X"]), ("12", x["1"] + x["2"]), ("X2", x["X"] + x["2"])):
            p[("Double Chance", n, None)] = q
    return p


def _label(e, o):
    h, a, m, n, l = e["home"], e["away"], o["market"], o["name"], o["line"]
    team = {"1": h, "2": a}
    if m == "1X2":
        return f"Victoire {team[n]}" if n in team else "Match nul"
    if m == "Double Chance":
        return {"1X": f"{h} ou nul", "12": f"{h} ou {a} (pas de nul)", "X2": f"{a} ou nul"}[n]
    if m == "Total de Buts":
        return f"{n} {l} buts"
    if m == "Les Deux Equipes Marquent":
        return f"Les deux équipes marquent : {n}"
    if m == "Handicap":
        return f"Handicap {team.get(n, n)} {l}"
    if " + " in n:
        r, rest = n.split(" + ")
        res = {"1": f"Victoire {h}", "X": "Nul", "2": f"Victoire {a}"}.get(r, r)
        return f"{res} + {rest}{' ' + l + ' buts' if l else ''}" if m.startswith("Résultat") \
            else f"{res} + les deux marquent : {rest}"
    return f"{m} : {n} {l or ''}".strip()


def legs(events, ref_only=False, families=tuple(FAMILIES), keep_suspects=False):
    allowed = set().union(*(FAMILIES[f] for f in families))
    out = []
    for e in events:
        ms = e.get("markets") or [{"market": "1X2", "name": k, "line": None, "odds": v}
                                   for k, v in e["odds"].items()]
        pb = _pb_probs(ms)
        ref = e.get("ref")
        if ref is None and ref_only:
            continue
        if ref:
            # garde-fou : une référence du vendredi trop loin de PremierBet = probablement une news depuis
            gap = max(abs(pb.get(("1X2", k, None), ref["p"][k]) - ref["p"][k]) for k in "1X2")
            e["suspect"] = ref["src"].startswith("vendredi") and gap > SUSPECT_GAP
            if e["suspect"] and not keep_suspects:
                continue
            mat = model.fit(ref["p"])
        key = (e["start"].date(), " ".join(norm(e["home"])), " ".join(norm(e["away"])))
        for o in ms:
            if o["market"] not in allowed or o["odds"] <= 1.01:
                continue
            pred = model.predicate(o["market"], o["name"], o["line"])
            q_pb = pb.get((o["market"], o["name"], o["line"]))
            if pred is None:
                continue
            if ref:
                q_model = model.prob(mat, pred)
                direct = o["market"] in ("1X2", "Double Chance") or (
                    o["market"] == "Total de Buts" and str(o["line"]) == "2.5" and "O2.5" in ref["p"])
                if direct:
                    p, src = q_model if o["market"] != "1X2" else ref["p"][o["name"]], "marché"
                    if o["market"] == "Double Chance":
                        r = ref["p"]
                        p = {"1X": r["1"] + r["X"], "12": r["1"] + r["2"], "X2": r["X"] + r["2"]}[o["name"]]
                    if o["market"] == "Total de Buts":
                        p = ref["p"]["O2.5"] if o["name"] == "Plus de" else 1 - ref["p"]["O2.5"]
                elif q_pb is not None:
                    # dérivé du modèle : prudence, moitié modèle moitié PremierBet
                    p, src = (q_model + q_pb) / 2, "modèle"
                else:
                    continue
                src_ref = ref["src"]
            elif q_pb is not None:
                p, src, src_ref = q_pb, "PremierBet", ""
            else:
                continue
            if not 0.001 < p < 0.999:
                continue
            out.append({"event": e, "key": key, "pick": o["market"], "label": _label(e, o), "odds": o["odds"],
                        "p": p, "value": p * o["odds"], "src": src, "src_ref": src_ref})
    return out


LADDER = [1.3, 1.6, 2, 3, 5, 10, 25, 100, 1000, 10000]
RISK = [(0.60, "sur"), (0.25, "modere"), (0.05, "risque"), (0.0, "tres_risque")]


def risk(p):
    return next(name for floor, name in RISK if p >= floor)


def build(legs, target, max_legs=12, max_odds=None, pool=150, per_match=6, exclude=()):
    return build_many(legs, [target], max_legs, max_odds, pool, per_match, exclude)[target]


def build_many(legs, targets, max_legs=12, max_odds=None, pool=150, per_match=6, exclude=()):
    """Pour chaque cote visée, la combinaison la plus probable qui l'atteint (un seul passage de calcul)."""
    targets = sorted(set(targets))
    cands = [l for l in legs if l["odds"] > 1.01 and (max_odds is None or l["odds"] <= max_odds)
             and l["key"] not in exclude]
    # garder les paris les plus "efficaces" (peu de probabilité perdue par unité de cote gagnée)
    cands.sort(key=lambda l: -math.log(l["p"]) / math.log(l["odds"]))
    seen, groups = {}, []
    for l in cands:
        if len(seen) >= pool and l["key"] not in seen:
            continue
        if l["key"] not in seen:
            seen[l["key"]] = len(groups)
            groups.append([])
        if len(groups[seen[l["key"]]]) < per_match:  # les plus efficaces d'abord (tri ci-dessus)
            groups[seen[l["key"]]].append(l)

    B = math.ceil(math.log(max(targets)) / STEP)
    INF = float("inf")
    # dp[n][b] = (coût minimal, paris) avec n paris et b paliers de log-cote (plafonné à la plus grande cible)
    dp = [[(INF, None)] * (B + 1) for _ in range(max_legs + 1)]
    dp[0][0] = (0.0, ())
    for g in groups:
        moves = [(int(math.log(l["odds"]) / STEP), -math.log(l["p"]), l) for l in g]
        new = [row[:] for row in dp]
        for n in range(max_legs):
            row, nrow = dp[n], new[n + 1]
            for b in range(B + 1):
                c, chosen = row[b]
                if chosen is None:
                    continue
                for step, cost, l in moves:
                    nb = min(B, b + step)
                    nc = c + cost
                    if nc < nrow[nb][0]:
                        nrow[nb] = (nc, chosen + (l,))
        dp = new
    # meilleur état atteignant au moins chaque palier, en balayant de la plus grande cote vers la plus petite
    out, best = {}, (INF, None)
    suffix = [None] * (B + 1)
    for b in range(B, -1, -1):
        for n in range(1, max_legs + 1):
            if dp[n][b][0] < best[0]:
                best = dp[n][b]
        suffix[b] = best
    for t in targets:
        c = suffix[math.ceil(math.log(t) / STEP)] if t > 1 else None
        out[t] = None
        if c and c[1] is not None:
            sel = sorted(c[1], key=lambda l: l["event"]["start"])
            odds = math.prod(l["odds"] for l in sel)
            if odds >= t:  # arrondi des paliers : on vérifie quand même
                p = math.prod(l["p"] for l in sel)
                out[t] = {"legs": sel, "odds": odds, "p": p, "p_book": math.prod(1 / l["odds"] for l in sel),
                          "risk": risk(p)}
    return out
