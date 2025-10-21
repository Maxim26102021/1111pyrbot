import os
import logging
from typing import List, Tuple, Dict, Optional

try:
    import google.generativeai as genai
except ImportError:  # pragma: no cover
    genai = None  # type: ignore

logger = logging.getLogger(__name__)

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("LLM_MODEL", "gemini-1.5-flash")
model = None
if API_KEY and genai:
    try:
        genai.configure(api_key=API_KEY)
        model = genai.GenerativeModel(MODEL_NAME)
    except Exception as exc:  # pragma: no cover
        logger.warning("LLM disabled: failed to init Gemini client: %s", exc)
        model = None
else:
    if not API_KEY:
        logger.info("LLM disabled: GEMINI_API_KEY not set")
    if not genai:
        logger.info("LLM disabled: google-generativeai package missing")

PROMPT = """Ты — опытный контент-редактор. Сделай дайджест строго по формату:

⚡ Новости к этому часу

- До 10 пунктов.
- Каждый пункт: кликабельный заголовок [Текст](URL) + 1–2 предложения сути.
- Только новости по теме (искусственный интеллект/технологии). Рекламу выкинуть.
- Если новостей <3 — верни строку: НЕДОСТАТОЧНО НОВОСТЕЙ.

Вот сырьё (каждый пункт = одна новость):
{content}
"""

def _fallback_digest(items: List[Dict[str, str]]) -> str:
    lines = ["⚡ Новости к этому часу", ""]
    for idx, it in enumerate(items, 1):
        title = (it.get("text") or "").strip().split("\n")[0][:120] or "Без названия"
        url = it.get("link") or ""
        bullet = f"{idx}. [{title}]({url})" if url else f"{idx}. {title}"
        lines.append(bullet)
    return "\n".join(lines).strip()


def build_digest(items: List[Dict[str, str]]) -> Tuple[Optional[str], str]:
    """Вернуть дайджест и источник (llm|fallback|empty|error)."""
    if not items:
        return None, "empty"

    items = items[:10]
    fallback = _fallback_digest(items)

    if len(items) < 3 or not model:
        return fallback, "fallback"

    prompt = PROMPT.format(
    content="\n\n".join(
        f"- [{next((line for line in (it.get('text') or '').strip().splitlines() if line), '')[:120]}]({it.get('link') or ''})\n{(it.get('text') or '')[:300]}"
        for it in items
    ))

    try:
        resp = model.generate_content(prompt, generation_config={"temperature": 0.25})
        txt = (getattr(resp, "text", None) or "").strip()
        if txt:
            return txt, "llm"
        logger.warning("LLM returned empty response, using fallback")
    except Exception as exc:  # pragma: no cover
        logger.warning("LLM call failed (%s), using fallback", exc)
        return fallback, "error"

    return fallback, "fallback"
