from datetime import datetime, timedelta, timezone

from app.serializers import age_in_days, issue_to_card, strip_markdown_summary


def test_strip_markdown_summary_removes_common_markup():
    body = "# Heading\n\nSome **bold** _text_ with `code`, a [link](url), and - a dash!"
    summary = strip_markdown_summary(body, length=200)
    for char in "#*_`[]()!-":
        assert char not in summary


def test_strip_markdown_summary_truncates_on_word_boundary():
    body = "word " * 100
    summary = strip_markdown_summary(body, length=20)
    assert summary.endswith("…")
    assert len(summary) <= 21


def test_strip_markdown_summary_handles_empty():
    assert strip_markdown_summary(None) == ""
    assert strip_markdown_summary("") == ""


def test_age_in_days_open_issue_uses_now():
    created = datetime.now(timezone.utc) - timedelta(days=5, hours=1)
    assert age_in_days(created, None) == 5


def test_age_in_days_closed_issue_uses_closed_at():
    created = datetime.now(timezone.utc) - timedelta(days=10)
    closed = created + timedelta(days=3)
    assert age_in_days(created, closed) == 3


def test_age_in_days_never_negative():
    created = datetime.now(timezone.utc) + timedelta(days=1)  # clock skew edge case
    assert age_in_days(created, None) == 0


def _sample_issue(**overrides):
    issue = {
        "number": 1,
        "title": "Sample issue",
        "body": "Some *body* text",
        "state": "open",
        "html_url": "https://github.com/acme/widgets/issues/1",
        "labels": [{"name": "bug", "color": "ff0000", "description": None}],
        "assignees": [{"login": "alice", "avatar_url": "https://example.com/a.png"}],
        "milestone": {"title": "v1"},
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "closed_at": None,
        "comments": 3,
    }
    issue.update(overrides)
    return issue


def test_issue_to_card_maps_all_fields():
    card = issue_to_card(_sample_issue(), has_local_note=True)
    assert card.number == 1
    assert card.title == "Sample issue"
    assert card.labels[0].name == "bug"
    assert card.assignees[0].login == "alice"
    assert card.milestone == "v1"
    assert card.comments_count == 3
    assert card.has_local_note is True
    assert card.closed_at is None


def test_issue_to_card_handles_no_milestone():
    card = issue_to_card(_sample_issue(milestone=None), has_local_note=False)
    assert card.milestone is None


def test_issue_to_card_computes_closed_age():
    issue = _sample_issue(
        created_at="2026-01-01T00:00:00Z",
        closed_at="2026-01-04T00:00:00Z",
    )
    card = issue_to_card(issue, has_local_note=False)
    assert card.age_days == 3
    assert card.closed_at is not None
