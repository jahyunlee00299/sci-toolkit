"""Configuration for mailcheck: neutral defaults, overridable from a TOML file.

Order of precedence: explicit path > MAILCHECK_CONFIG environment variable >
the mailcheck.toml shipped next to this file > built-in defaults. TOML needs
Python 3.11+ (tomllib); on 3.10 the built-in defaults are used and a custom
file raises a clear error.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

PACKAGED = Path(__file__).with_name("mailcheck.toml")


@dataclass(frozen=True)
class Config:
    admin_local_parts: tuple = ("admin", "office", "info", "support", "research", "graduate", "team",
                                "center", "hr", "helpdesk")
    admin_name_keywords: tuple = ("팀", "센터", "행정", "산학", "연구지원", "사무", "담당", "본부", "교무",
                                  "재무", "연구처", "대학원", "도서관")
    signoff_forms: tuple = ("올림", "드림")
    honorifics: tuple = ("교수님", "선생님", "박사님", "연구원님", "팀장님", "담당자님", "위원님", "실장님",
                         "과장님", "부장님", "대표님", "님")
    echo_min_tokens: int = 6
    echo_overlap: float = 0.6
    apology_max: int = 1
    thanks_closing_max: int = 1
    thanks_body_max: int = 1
    internal_note_extra: tuple = field(default_factory=tuple)


def _read_toml(path: Path) -> dict:
    try:
        import tomllib
    except ImportError as exc:  # Python 3.10
        raise RuntimeError("TOML 설정 파일은 Python 3.11 이상이 필요합니다. "
                           "3.10에서는 내장 기본값만 사용할 수 있습니다.") from exc
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def from_dict(data: dict, base: Config | None = None) -> Config:
    cfg = base or Config()
    admin, voice = data.get("admin", {}), data.get("voice", {})
    thr, note = data.get("thresholds", {}), data.get("internal_note", {})
    upd = {}
    if "local_parts" in admin:
        upd["admin_local_parts"] = tuple(admin["local_parts"])
    if "name_keywords" in admin:
        upd["admin_name_keywords"] = tuple(admin["name_keywords"])
    if "signoff_forms" in voice:
        upd["signoff_forms"] = tuple(voice["signoff_forms"])
    if "honorifics" in voice:
        upd["honorifics"] = tuple(voice["honorifics"])
    for key, cast in (("echo_min_tokens", int), ("echo_overlap", float), ("apology_max", int),
                      ("thanks_closing_max", int), ("thanks_body_max", int)):
        if key in thr:
            upd[key] = cast(thr[key])
    if "extra_patterns" in note:
        upd["internal_note_extra"] = tuple(note["extra_patterns"])
    return replace(cfg, **upd)


def load_config(path: str | os.PathLike | None = None) -> Config:
    chosen = path or os.environ.get("MAILCHECK_CONFIG")
    if chosen:
        p = Path(chosen)
        if not p.is_file():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {p}")
        return from_dict(_read_toml(p))
    if PACKAGED.is_file():
        try:
            return from_dict(_read_toml(PACKAGED))
        except RuntimeError:
            pass  # Python 3.10: built-in defaults are identical to the shipped file
    return Config()


_cached: Config | None = None


def default_config() -> Config:
    global _cached
    if _cached is None:
        _cached = load_config()
    return _cached
