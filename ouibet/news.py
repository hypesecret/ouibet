"""Alertes news par match : Claude cherche sur le web blessures, suspensions, compos, rotation, enjeu.

Nécessite ANTHROPIC_API_KEY et `pip install anthropic`. Coût indicatif : quelques centimes par match
(recherches web + lecture des pages), seulement pour les matchs retenus dans les coupons.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone

from . import config

MODEL = "claude-opus-5-5"
BZV = timezone(timedelta(hours=1))

REPORT_TOOL = {
    "name": "rapport",
    "description": "Rendre le rapport final sur le match, une fois les recherches terminées.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "niveau": {"type": "string", "enum": ["ok", "attention", "danger"],
                       "description": "danger = le pari proposé est clairement fragilisé par une info récente"},
            "resume": {"type": "string", "description": "2 phrases max, en français"},
            "absents": {"type": "array", "items": {"type": "string"},
                        "description": "joueurs importants blessés, suspendus ou incertains (équipe entre parenthèses)"},
            "compo_officielle": {"type": "boolean", "description": "la composition officielle est-elle sortie ?"},
            "impact_pari": {"type": "string", "description": "effet des infos sur le pari proposé, 1 phrase"},
        },
        "required": ["niveau", "resume", "absents", "compo_officielle", "impact_pari"],
        "additionalProperties": False,
    },
}

SYSTEM = (
    "Tu es analyste football. On te donne un match et un pari envisagé. Cherche sur le web les informations "
    "les plus récentes : blessures, suspensions, compositions probables ou officielles, rotation (coupe d'Europe "
    "en milieu de semaine), changement d'entraîneur, enjeu du match, conditions particulières. "
    "Privilégie les sources des dernières 72 heures et ne rapporte que des faits trouvés, jamais d'invention. "
    "Quand tu as fini, appelle l'outil `rapport`."
)


def available():
    if not config.ANTHROPIC_API_KEY:
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def check(leg):
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    e = leg["event"]
    when = e["start"].astimezone(BZV).strftime("%d/%m/%Y %Hh%M (heure de Brazzaville)")
    messages = [{"role": "user", "content": (
        f"Match : {e['home']} - {e['away']} ({e['league']}), le {when}.\n"
        f"Pari envisagé : {leg['label']} (cote {leg['odds']:.2f}).")}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}, REPORT_TOOL]
    for _ in range(6):  # pause_turn possible sur les longues recherches
        r = client.beta.messages.create(
            model=MODEL, max_tokens=16000, system=SYSTEM, messages=messages, tools=tools,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
        for b in r.content:
            if b.type == "tool_use" and b.name == "rapport":
                return b.input if isinstance(b.input, dict) else json.loads(b.input)
        if r.stop_reason == "refusal":
            break
        messages.append({"role": "assistant", "content": r.content})
        if r.stop_reason != "pause_turn":
            messages.append({"role": "user", "content": "Appelle maintenant l'outil `rapport`."})
    return {"niveau": "attention", "resume": "Pas de rapport obtenu.", "absents": [],
            "compo_officielle": False, "impact_pari": "Vérifier manuellement."}


def check_all(legs):
    """{clé de match: rapport} pour une liste de paris (un appel par match, en parallèle)."""
    uniq = {l["key"]: l for l in legs}
    with ThreadPoolExecutor(4) as ex:
        reports = list(ex.map(_safe_check, uniq.values()))
    return dict(zip(uniq, reports))


def _safe_check(leg):
    try:
        return check(leg)
    except Exception as ex:
        return {"niveau": "attention", "resume": f"Erreur pendant la recherche : {ex}", "absents": [],
                "compo_officielle": False, "impact_pari": "Vérifier manuellement."}
