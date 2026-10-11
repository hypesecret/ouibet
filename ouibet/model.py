"""Modèle de score Dixon-Coles calé sur les probabilités du marché.

On cherche les buts attendus (lh, la) qui reproduisent au mieux le 1X2 (et le +/-2,5 si connu)
de la référence, puis on en déduit la probabilité de n'importe quel pari : buts, BTTS, handicap,
combinés résultat + buts...
"""
import math

RHO = -0.08  # corrige le léger déficit de 0-0 / 1-1 du Poisson pur
N = 11


def _pmf(lam):
    p = [math.exp(-lam)]
    for k in range(1, N):
        p.append(p[-1] * lam / k)
    return p


def matrix(lh, la, rho=RHO):
    ph, pa = _pmf(lh), _pmf(la)
    m = [[ph[i] * pa[j] for j in range(N)] for i in range(N)]
    m[0][0] *= 1 - lh * la * rho
    m[0][1] *= 1 + lh * rho
    m[1][0] *= 1 + la * rho
    m[1][1] *= 1 - rho
    s = sum(map(sum, m))
    return [[x / s for x in row] for row in m]


def prob(m, pred):
    return sum(m[i][j] for i in range(N) for j in range(N) if pred(i, j))


BASE = {
    "1": lambda h, a: h > a,
    "X": lambda h, a: h == a,
    "2": lambda h, a: h < a,
    "O2.5": lambda h, a: h + a > 2.5,
}


def fit(target):
    """target = {"1": p, "X": p, "2": p, ["O2.5": p]} -> matrice de score."""
    keys = [k for k in BASE if k in target]

    def loss(lh, la):
        m = matrix(lh, la)
        return sum((prob(m, BASE[k]) - target[k]) ** 2 for k in keys)

    best = min(((loss(h, a), h, a) for h in frange(0.2, 4.0, 0.2) for a in frange(0.2, 4.0, 0.2)))
    for step in (0.05, 0.01):
        _, h0, a0 = best
        best = min(((loss(h, a), h, a)
                    for h in frange(max(0.05, h0 - 4 * step), h0 + 4 * step, step)
                    for a in frange(max(0.05, a0 - 4 * step), a0 + 4 * step, step)))
    return matrix(best[1], best[2])


def frange(a, b, s):
    n = int(round((b - a) / s))
    return [a + i * s for i in range(n + 1)]


def _result(r):
    return BASE[r]


def predicate(market, name, line):
    """Traduit un pari PremierBet en condition sur le score final (h, a). None si non géré."""
    try:
        line = float(line) if line not in (None, "") else None
    except ValueError:
        return None
    half = line is not None and abs(line * 2 % 2 - 1) < 1e-9  # ligne en .5 (pas de remboursement)
    if market == "1X2" and name in ("1", "X", "2"):
        return _result(name)
    if market == "Double Chance":
        return {"1X": lambda h, a: h >= a, "12": lambda h, a: h != a, "X2": lambda h, a: h <= a}.get(name)
    if market == "Total de Buts" and half:
        return (lambda h, a: h + a > line) if name == "Plus de" else (lambda h, a: h + a < line)
    if market == "Les Deux Equipes Marquent":
        return {"Oui": lambda h, a: h > 0 and a > 0, "Non": lambda h, a: h == 0 or a == 0}.get(name)
    if market == "Handicap" and half:
        if name == "1":
            return lambda h, a: h + line > a
        if name == "2":
            return lambda h, a: a + line > h
    if market == "Résultat + Plus/Moins De" and half and " + " in name:
        r, t = name.split(" + ")
        if r in BASE:
            over = t.startswith("Plus")
            return lambda h, a, r=r, over=over: BASE[r](h, a) and ((h + a > line) == over)
    if market == "Resultat + Les Deux Équipes Marquent" and " + " in name:
        r, b = name.split(" + ")
        if r in BASE:
            yes = b == "Oui"
            return lambda h, a, r=r, yes=yes: BASE[r](h, a) and ((h > 0 and a > 0) == yes)
    return None
