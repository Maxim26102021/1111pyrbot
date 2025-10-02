import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-1.5-flash")

PROMPT = """Ты — опытный контент-редактор. Сделай дайджест строго по формату:

⚡ Новости к этому часу

- До 10 пунктов.
- Каждый пункт: кликабельный заголовок [Текст](URL) + 1–2 предложения сути.
- Только новости по теме (искусственный интеллект/технологии). Рекламу выкинуть.
- Если новостей <3 — верни строку: НЕДОСТАТОЧНО НОВОСТЕЙ.

Вот сырьё (каждый пункт = одна новость):
{content}
"""

def build_digest(items):
    if len(items) < 3:
        return "НЕДОСТАТОЧНО НОВОСТЕЙ"
    items = items[:10]
    content = []
    for it in items:
        title = (it.get('text') or '').strip().split('\n')[0][:120]
        url = it.get('link') or ''
        content.append(f"- [{title}]({url})\n{(it.get('text') or '')[:300]}")
    prompt = PROMPT.format(content='\n\n'.join(content))
    try:
        resp = model.generate_content(prompt, generation_config={'temperature': 0.25})
        txt = (resp.text or '').strip()
        return txt
    except Exception as e:
        return f"Ошибка LLM: {e}"
