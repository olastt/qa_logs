from __future__ import annotations

from datetime import datetime
from pathlib import Path


def resolve_report_paths(
    *,
    output: str | None,
    output_dir: str,
    product_names: list[str],
) -> tuple[Path, Path]:
    """
    Возвращает пути (.txt, .pdf) для пары файлов отчёта.

    - output=reports/release → reports/release.txt + reports/release.pdf
    - output=None → {output_dir}/qa-report-{product}-{timestamp}.txt|.pdf
    """
    if output:
        base = Path(output)
        if base.suffix.lower() in {".txt", ".pdf"}:
            base = base.with_suffix("")
        base.parent.mkdir(parents=True, exist_ok=True)
        return base.with_suffix(".txt"), base.with_suffix(".pdf")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    product = product_names[0] if len(product_names) == 1 else "all"
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in product)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = out_dir / f"qa-report-{safe}-{stamp}"
    return base.with_suffix(".txt"), base.with_suffix(".pdf")
