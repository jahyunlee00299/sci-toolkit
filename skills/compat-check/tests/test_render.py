"""Tests for compat_check.render — ASCII tree rendering with optional ANSI color."""
from unittest import mock


from compat_check.render import render_tree

_SAMPLE = [{
    "name": "flask", "version": "3.1.3", "children": [
        {"name": "markupsafe", "version": "3.0.3", "children": []},
        {"name": "jinja2", "version": "3.1.6", "children": [
            {"name": "markupsafe", "version": "3.0.3", "children": []},
        ]},
    ],
}]


def test_plain_output_has_no_ansi_codes_when_not_a_tty():
    with mock.patch("sys.stdout.isatty", return_value=False):
        out = render_tree(_SAMPLE)
    assert "\x1b[" not in out
    assert "flask" in out
    assert "markupsafe" in out


def test_colored_output_has_ansi_codes_on_a_tty():
    with mock.patch("sys.stdout.isatty", return_value=True):
        out = render_tree(_SAMPLE)
    assert "\x1b[32m" in out  # green package name
    assert "\x1b[0m" in out   # reset


def test_nested_child_shows_box_drawing_connector():
    with mock.patch("sys.stdout.isatty", return_value=False):
        out = render_tree(_SAMPLE)
    lines = out.splitlines()
    assert any("└──" in l or "├──" in l for l in lines)


def test_label_wraps_roots_under_synthetic_node():
    with mock.patch("sys.stdout.isatty", return_value=False):
        out = render_tree(_SAMPLE, label="https://github.com/pallets/flask")
    lines = out.splitlines()
    assert lines[0] == "https://github.com/pallets/flask"
    # flask itself must now be indented as a child, not a bare root line.
    assert any(l.strip().startswith(("├── flask", "└── flask")) for l in lines)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            print(f"running {name}...")
            fn()
            print(f"  PASS")
    print("\nall render tests passed")
