# QA Release Bot

Мониторинг Glitchtip: сбор ошибок, группировка, классификация для релиза, алерты по новым issue.

## Быстрый старт

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
# заполните GLITCHTIP_*_TOKEN в .env

qa-release-bot report              # markdown + HTML reports/qa_report_YYYY-MM-DD.html
qa-release-bot report -o reports/qa.md
qa-release-bot report --pdf        # дополнительно PDF
qa-release-bot report --legacy     # старый текст + PDF test vs stage
qa-release-bot summary             # сводка + HTML (config/report.yaml → summaries)
qa-release-bot summary --instance selectel --project webappswidgets-test
qa-release-bot summary --pdf       # дополнительно PDF
qa-release-bot list-projects
qa-release-bot run-once
qa-release-bot poll
```

Токены только в `.env`, не в репозитории.
