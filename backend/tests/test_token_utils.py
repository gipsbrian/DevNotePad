from app.token_utils import detect_token_type, token_type_label


def test_classic_pat():
    assert detect_token_type("ghp_abcdef123456") == "classic-pat"


def test_fine_grained_pat():
    assert detect_token_type("github_pat_abcdef123456") == "fine-grained-pat"


def test_oauth_token():
    assert detect_token_type("gho_abcdef") == "oauth-token"


def test_github_app_user_token():
    assert detect_token_type("ghu_abcdef") == "github-app-user-token"


def test_github_app_installation_token():
    assert detect_token_type("ghs_abcdef") == "github-app-installation-token"


def test_github_app_refresh_token():
    assert detect_token_type("ghr_abcdef") == "github-app-refresh-token"


def test_no_token():
    assert detect_token_type(None) == "none"
    assert detect_token_type("") == "none"


def test_unrecognized_token():
    assert detect_token_type("some-random-string") == "unrecognized"


def test_token_type_label_known():
    assert token_type_label("classic-pat") == "Classic personal access token"
    assert token_type_label("fine-grained-pat") == "Fine-grained personal access token"


def test_token_type_label_unknown_falls_back():
    assert token_type_label("not-a-real-type") == "Unrecognized token format"
