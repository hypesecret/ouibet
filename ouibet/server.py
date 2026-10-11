"""Serveur ouibet : le moteur tourne en continu, l'interface web (PWA) affiche.

    python -m ouibet.server            # http://localhost:8800
Variables : OUIBET_PORT (8800), OUIBET_DAYS (3 jours scannés), OUIBET_SCAN_MINUTES (60),
OUIBET_PASSWORD (si défini, mot de passe demandé par le navigateur : à mettre dès que c'est sur un serveur).
"""
import base64
import hmac
import json
import mimetypes
import os
import sys
import threading
import time
import traceback
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, coupon, engine, news, odds_api

WEB = Path(__file__).resolve().parent / "web"
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("text/javascript", ".js")
PORT = int(os.environ.get("OUIBET_PORT", "8800"))
DAYS = int(os.environ.get("OUIBET_DAYS", "3"))
SCAN_MINUTES = int(os.environ.get("OUIBET_SCAN_MINUTES", "60"))
PASSWORD = os.environ.get("OUIBET_PASSWORD", "")
FAMILY_OF = {m: f for f, ms in coupon.FAMILIES.items() for m in ms}


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.events, self.legs, self.reports = [], [], {}
        self.scanned_at, self.scanning, self.error, self.progress = None, False, None, ""
        self.window = None


S = State()


def key_str(k):
    return f"{k[0].isoformat()}|{k[1]}|{k[2]}"


def scan():
    if S.scanning:
        return
    S.scanning, S.error = True, None
    try:
        start, end = engine.window(DAYS)
        evs = engine.load(start, end, log=lambda m: setattr(S, "progress", m))
        S.progress = "Calcul des probabilités..."
        legs = coupon.legs(evs, families=tuple(coupon.FAMILIES), keep_suspects=True)
        with S.lock:
            S.events, S.legs, S.window = evs, legs, (start, end)
            S.scanned_at = datetime.now(timezone.utc)
    except Exception as ex:
        S.error = f"{ex.__class__.__name__}: {ex}"
        traceback.print_exc()
    finally:
        S.scanning, S.progress = False, ""


def scheduler():
    while True:
        scan()
        time.sleep(SCAN_MINUTES * 60)


# ---------- sérialisation ----------

def ev_json(e):
    ref = e.get("ref")
    return {
        "id": e["id"], "start": e["start"].isoformat(), "league": e["league"],
        "home": e["home"], "away": e["away"], "odds": e["odds"],
        "ref": {"src": ref["src"], "p": ref["p"]} if ref else None,
        "suspect": bool(e.get("suspect")),
    }


def leg_json(l):
    return {
        "key": key_str(l["key"]), "event": ev_json(l["event"]), "label": l["label"], "market": l["pick"],
        "family": FAMILY_OF.get(l["pick"]), "odds": l["odds"], "p": round(l["p"], 4),
        "value": round(l["value"], 4), "src": l["src"], "src_ref": l["src_ref"],
    }


def coupon_json(c):
    if not c:
        return None
    return {"legs": [leg_json(l) for l in c["legs"]], "odds": c["odds"], "p": c["p"], "p_book": c["p_book"],
            "risk": c.get("risk")}


# ---------- requêtes ----------

def filter_legs(q):
    d0 = date.fromisoformat(q["from"]) if q.get("from") else None
    d1 = date.fromisoformat(q["to"]) if q.get("to") else None
    fams = set(q.get("families") or coupon.FAMILIES)
    excl = set(q.get("exclude") or [])
    out = []
    for l in S.legs:
        d = l["event"]["start"].astimezone(engine.BZV).date()
        if (d0 and d < d0) or (d1 and d > d1) or FAMILY_OF.get(l["pick"]) not in fams:
            continue
        if key_str(l["key"]) in excl or (l["event"].get("suspect") and not q.get("keep_suspects")):
            continue
        if q.get("ref_only") and l["src"] == "PremierBet":
            continue
        out.append(l)
    return out


def api_coupons(q):
    """Échelle de possibilités, de la plus sûre à la plus folle.

    mode "simple" = un seul match par pari ; "combine" = cumulé. style "favorites" = cotes <= max_odds par match.
    targets : cotes visées (par défaut l'échelle x1,3 ... x10 000).
    """
    legs = filter_legs(q)
    simple = q.get("mode") == "simple"
    favorites = q.get("style") == "favorites"
    max_odds = float(q.get("max_odds") or 1.8) if favorites else None
    max_legs = 1 if simple else int(q.get("max_legs") or (16 if favorites else 12))
    targets = [float(t) for t in q.get("targets") or coupon.LADDER if float(t) > 1]
    if simple:
        targets = [t for t in targets if t <= 50]
    found = coupon.build_many(legs, targets, max_legs, max_odds)
    res, seen = [], set()
    for t in sorted(found):
        c = found[t]
        sig = tuple(sorted((key_str(l["key"]), l["label"]) for l in c["legs"])) if c else None
        if c and sig in seen:
            continue  # la même combinaison sert déjà pour une cote plus petite
        seen.add(sig)
        res.append({"target": t, "coupon": coupon_json(c), "risk": c["risk"] if c else None})
    return {"coupons": res, "candidates": len(legs), "mode": "simple" if simple else "combine",
            "style": "favorites" if favorites else "best", "max_odds": max_odds}


def api_news(q):
    if not news.available():
        return {"error": "Ajoute ANTHROPIC_API_KEY dans .env et installe anthropic pour activer les news."}
    wanted = set(q.get("keys") or [])
    legs = {key_str(l["key"]): l for l in S.legs if key_str(l["key"]) in wanted}
    todo = [l for k, l in legs.items() if k not in S.reports]
    if todo:
        for k, r in news.check_all(todo).items():
            S.reports[key_str(k)] = r
    return {"reports": {k: S.reports[k] for k in wanted if k in S.reports}}


def api_status():
    evs = S.events
    n_ref = sum(1 for e in evs if e.get("ref"))
    n_live = sum(1 for e in evs if e.get("ref") and e["ref"]["src"].startswith("direct"))
    return {
        "scanned_at": S.scanned_at.isoformat() if S.scanned_at else None, "scanning": S.scanning,
        "progress": S.progress, "error": S.error, "scan_minutes": SCAN_MINUTES,
        "window": [S.window[0].isoformat(), S.window[1].isoformat()] if S.window else None,
        "matches": len(evs), "with_ref": n_ref, "live_ref": n_live,
        "suspects": sum(1 for e in evs if e.get("suspect")), "legs": len(S.legs),
        "keys": {"odds_api": bool(config.ODDS_API_KEY), "news": news.available()},
        "odds_api_remaining": odds_api.remaining,
        "families": list(coupon.FAMILIES),
    }


def api_matches(q):
    d = q.get("day")
    evs = [e for e in S.events if not d or e["start"].astimezone(engine.BZV).date().isoformat() == d]
    return {"matches": [ev_json(e) for e in sorted(evs, key=lambda e: e["start"])]}


def api_values(q):
    legs = [l for l in filter_legs(q) if l["src"] != "PremierBet" and l["value"] > 1.02]
    legs.sort(key=lambda l: -l["value"])
    return {"values": [leg_json(l) for l in legs[:50]]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _auth(self):
        if not PASSWORD:
            return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                _, pw = base64.b64decode(h[6:]).decode().split(":", 1)
                if hmac.compare_digest(pw, PASSWORD):
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="ouibet"')
        self.end_headers()
        return False

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _query(self):
        from urllib.parse import parse_qs, urlparse
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def do_GET(self):
        if not self._auth():
            return
        path = self.path.split("?")[0]
        routes = {"/api/status": api_status, "/api/matches": lambda: api_matches(self._query()),
                  "/api/values": lambda: api_values(self._query())}
        if path in routes:
            return self._json(routes[path]())
        f = (WEB / ("index.html" if path in ("/", "") else path.lstrip("/"))).resolve()
        if WEB not in f.parents and f != WEB / "index.html" or not f.is_file():
            f = WEB / "index.html"
        body = f.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", (mimetypes.guess_type(f.name)[0] or "text/plain") + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if not self._auth():
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            q = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "JSON invalide"}, 400)
        path = self.path.split("?")[0]
        try:
            if path == "/api/coupons":
                return self._json(api_coupons(q))
            if path == "/api/values":
                return self._json(api_values(q))
            if path == "/api/news":
                return self._json(api_news(q))
            if path == "/api/refresh":
                threading.Thread(target=scan, daemon=True).start()
                return self._json({"ok": True})
        except Exception as ex:
            traceback.print_exc()
            return self._json({"error": str(ex)}, 500)
        self._json({"error": "introuvable"}, 404)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    threading.Thread(target=scheduler, daemon=True).start()
    host = os.environ.get("OUIBET_HOST", "0.0.0.0")
    print(f"ouibet : http://localhost:{PORT}  (scan toutes les {SCAN_MINUTES} min, {DAYS} jours)"
          + ("" if PASSWORD else "  -- sans mot de passe : définis OUIBET_PASSWORD avant de l'exposer"))
    ThreadingHTTPServer((host, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
