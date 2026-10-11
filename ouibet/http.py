"""Petit client HTTP stdlib avec cache disque (évite de marteler les APIs)."""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / ".cache"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36"


def get(url, ttl=600, headers=None):
    """Retourne le texte de l'URL, depuis le cache s'il a moins de `ttl` secondes."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / hashlib.sha1(url.encode()).hexdigest()
    if f.exists() and time.time() - f.stat().st_mtime < ttl:
        return f.read_text(encoding="utf-8")
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8-sig", errors="replace")
    f.write_text(text, encoding="utf-8")
    return text


def get_json(url, ttl=600, headers=None):
    return json.loads(get(url, ttl, headers))
