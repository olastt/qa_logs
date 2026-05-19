from qa_release_bot.textfmt import compact_text, wrap_text


def test_compact_text_collapses_whitespace():
    raw = "Error: SELECT\n\n  FROM   invoice"
    assert compact_text(raw, max_len=200) == "Error: SELECT FROM invoice"


def test_compact_text_truncates():
    assert compact_text("a" * 100, max_len=20).endswith("…")
    assert len(compact_text("a" * 100, max_len=20)) == 20


def test_wrap_text():
    lines = wrap_text("one two three four five", width=20, indent="  ")
    assert all(line.startswith("  ") for line in lines)
