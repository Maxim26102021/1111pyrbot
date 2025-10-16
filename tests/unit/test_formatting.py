from __future__ import annotations

from services.bot.app import formatting


def test_escape_html():
    assert formatting.escape_html('<hello & world>') == '&lt;hello &amp; world&gt;'


def test_split_message_respects_limit():
    text = "Line1\n" + "A" * 10 + "\nLine3"
    chunks = formatting.split_message(text, max_len=8)
    assert all(len(c) <= 8 for c in chunks)
    assert "Line1" in chunks[0]


def test_template_digest_renders_html():
    text = formatting.template_digest("Ваш дайджест", [("Канал", "Summary & more")])
    assert text.startswith("<b>Ваш дайджест</b>")
    assert "&amp;" in text
