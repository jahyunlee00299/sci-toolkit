"""Integration tests for compat_check.fetcher — real network calls to GitHub raw + PyPI."""


from compat_check.fetcher import FetchError, fetch_requirements, parse_github_url


def test_parse_github_url_plain():
    ref = parse_github_url("https://github.com/psf/requests")
    assert ref is not None
    assert ref.owner == "psf"
    assert ref.repo == "requests"
    assert ref.branch is None


def test_parse_github_url_with_tree_branch():
    ref = parse_github_url("https://github.com/psf/requests/tree/main")
    assert ref is not None
    assert ref.branch == "main"


def test_parse_github_url_rejects_non_github():
    assert parse_github_url("requests") is None
    assert parse_github_url("https://pypi.org/project/requests/") is None


def test_fetch_requirements_from_real_github_repo_requests():
    reqs = fetch_requirements("https://github.com/psf/requests")
    assert isinstance(reqs, list)
    assert len(reqs) > 0
    assert all(isinstance(r, str) for r in reqs)


def test_fetch_requirements_from_real_github_repo_flask():
    reqs = fetch_requirements("https://github.com/pallets/flask")
    assert isinstance(reqs, list)
    assert len(reqs) > 0
    names = " ".join(reqs).lower()
    assert "werkzeug" in names or "jinja" in names


def test_fetch_requirements_from_pypi_package_name():
    reqs = fetch_requirements("requests")
    assert isinstance(reqs, list)
    assert len(reqs) > 0


def test_fetch_requirements_nonexistent_github_repo_raises():
    try:
        fetch_requirements("https://github.com/this-owner-does-not-exist-xyz123/also-fake-repo")
        assert False, "expected FetchError"
    except FetchError:
        pass


def test_fetch_requirements_nonexistent_pypi_package_raises():
    try:
        fetch_requirements("this-package-definitely-does-not-exist-xyz123456")
        assert False, "expected FetchError"
    except FetchError:
        pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(f"running {name}...")
            fn()
            print("  PASS")
    print("\nall tests passed")
