import pytest

from app.repo_ref import parse_org_url, parse_repo_ref


@pytest.mark.parametrize(
    "value",
    [
        "acme/widgets",
        "https://github.com/acme/widgets",
        "http://github.com/acme/widgets",
        "https://www.github.com/acme/widgets",
        "github.com/acme/widgets",
        "https://github.com/acme/widgets/",
        "https://github.com/acme/widgets.git",
        "git@github.com:acme/widgets.git",
        "https://github.com/acme/widgets/issues",
        "https://github.com/acme/widgets/tree/main/src",
        "https://github.com/acme/widgets?tab=readme",
        "  acme/widgets  ",
    ],
)
def test_parses_every_shape_a_user_might_paste(value):
    assert parse_repo_ref(value) == ("acme", "widgets")


@pytest.mark.parametrize("value", ["", "   ", "acme", "https://github.com/acme", "not a repo"])
def test_rejects_non_repo_references(value):
    assert parse_repo_ref(value) is None


def test_parse_org_url():
    assert parse_org_url("https://github.com/acme") == "acme"
    assert parse_org_url("https://github.com/acme/") == "acme"
    assert parse_org_url("acme") == "acme"
    assert parse_org_url(None) is None
    assert parse_org_url("") is None
