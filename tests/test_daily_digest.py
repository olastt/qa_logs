from qa_release_bot.notify_format import format_daily_digest


def test_format_daily_digest_links_reports():
    text = format_daily_digest(
        [
            {
                "command": "summary",
                "project_id": "selectel-webappswidgets-test",
                "new_issues": 0,
                "new_critical": 0,
                "disappeared": 1,
                "report_url": "https://qa-widgets-test.surge.sh",
            },
            {
                "command": "summary",
                "project_id": "hetzner-vetmanager-extjs-review",
                "project_display_name": "vetmanager-extjs-review",
                "new_issues": 2,
                "new_critical": 1,
                "disappeared": 0,
                "top_new_titles": ["[ExtJS] Ошибка сохранения"],
                "report_url": "https://qa-extjs-review.surge.sh",
            },
        ]
    )

    assert "QA daily digest" in text
    assert "Проверено проектов: 2" in text
    assert "Новых ошибок сегодня: 2" in text
    assert "Критичных новых: 1" in text
    assert "vetmanager-extjs-review: новых 2, критичных 1" in text
    assert "https://qa-extjs-review.surge.sh" in text
    assert "selectel-webappswidgets-test" in text
