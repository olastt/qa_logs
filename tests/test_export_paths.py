from qa_release_bot.export_paths import resolve_report_paths


def test_resolve_with_explicit_output(tmp_path):
    base = tmp_path / "my-report"
    txt, pdf = resolve_report_paths(
        output=str(base),
        output_dir="ignored",
        product_names=["extjs"],
    )
    assert txt == base.with_suffix(".txt")
    assert pdf == base.with_suffix(".pdf")


def test_resolve_auto_names(tmp_path):
    out = tmp_path / "out"
    txt, pdf = resolve_report_paths(
        output=None,
        output_dir=str(out),
        product_names=["vetmanager-extjs"],
    )
    assert txt.parent == out
    assert txt.suffix == ".txt"
    assert pdf.suffix == ".pdf"
    assert "qa-report-vetmanager-extjs-" in txt.name
