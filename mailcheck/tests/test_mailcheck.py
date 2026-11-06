"""mailcheck regression tests. All texts are fictional; addresses use example.edu."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mailcheck import config as cfgmod  # noqa: E402
from mailcheck.style import StyleContext, amounts, check, is_admin_recipient  # noqa: E402
from mailcheck.voice import SentSample, default_profile, extract_profile, features  # noqa: E402

RECEIVED = "수정된 견적서 사본과 책임자 확인 후 진행 결과를 알려 주십시오. 결제 금액은 1,200,000원 입니다. 마감은 11월 20일 입니다."


def rules(rep):
    return {v.rule for v in rep.hard + rep.soft}


def hard_rules(rep):
    return {v.rule for v in rep.hard}


def test_clean_draft_passes():
    rep = check("안녕하세요, 김 교수님.\n견적서를 첨부합니다.\n감사합니다.", StyleContext(source_text=RECEIVED))
    assert rep.ok and not rep.soft


def test_empty_draft_is_clean():
    assert check("").ok


# ---- apology / gratitude ----
def test_apology_twice_is_hard_and_soft_when_owner_edited():
    body = "죄송합니다. 회신이 늦었습니다.\n정말 송구합니다."
    assert "apology" in hard_rules(check(body))
    rep = check(body, owner_edited=True)
    assert rep.ok and "apology" in rules(rep)


def test_single_apology_is_allowed():
    assert "apology" not in rules(check("죄송합니다. 회신이 늦었습니다.\n확인 부탁드립니다."))


def test_gratitude_cap():
    body = "감사드립니다.\n자료를 보냅니다.\n말씀 감사합니다.\n정말 감사합니다.\n감사합니다."
    assert "gratitude" in hard_rules(check(body))
    assert "gratitude" not in rules(check("자료를 보냅니다.\n확인 부탁드립니다.\n감사합니다."))


# ---- summary echo ----
def test_restatement_is_flagged():
    body = "수정된 견적서 사본과 책임자 확인 후 진행 결과를 알려 주셔야 한다고 하셨습니다."
    assert "summary_echo" in hard_rules(check(body, StyleContext(source_text=RECEIVED)))


def test_commitment_tail_is_exempt():
    # 18322-style acceptance: reuses the request words but promises to act
    body = "수정된 견적서 사본과 책임자 확인 후 진행 결과를 알려 드리겠습니다."
    assert "summary_echo" not in rules(check(body, StyleContext(source_text=RECEIVED)))
    body2 = "수정된 견적서 사본과 책임자 확인 진행하겠습니다."
    assert "summary_echo" not in rules(check(body2, StyleContext(source_text=RECEIVED)))


def test_non_commitment_keuseumnida_is_not_exempt():
    body = "수정된 견적서 사본과 책임자 확인 후 진행 결과를 알려 주시면 좋겠습니다."
    assert "summary_echo" in rules(check(body, StyleContext(source_text=RECEIVED)))


def test_echo_thresholds_come_from_config():
    from dataclasses import replace
    body = "수정된 견적서 사본과 책임자 확인 후 진행 결과를 알려 주셔야 한다고 하셨습니다."
    loose = replace(cfgmod.Config(), echo_min_tokens=50)
    assert "summary_echo" not in rules(check(body, StyleContext(source_text=RECEIVED), config=loose))


# ---- numbers ----
def test_money_notation_equality():
    assert amounts("1,200,000원") == amounts("120만원") == {1_200_000}
    assert amounts("1.5억원") == {150_000_000}
    assert amounts("3천만원") == {30_000_000}
    assert amounts("회의 3명") == set()


def test_amount_written_differently_is_sourced():
    assert "unsourced_number" not in rules(check("결제 금액은 120만원입니다.", StyleContext(source_text=RECEIVED)))


def test_unsourced_amount_and_date():
    rep = check("결제 금액은 150만원이고 12월 3일까지 보내겠습니다.", StyleContext(source_text=RECEIVED))
    msgs = " ".join(v.message for v in rep.hard)
    assert "금액" in msgs and "날짜" in msgs


def test_numbers_without_source_flagged():
    assert "unsourced_number" in rules(check("마감은 11월 20일입니다."))


def test_unsourced_code():
    rep = check("접수번호 AB123456 건입니다.", StyleContext(source_text=RECEIVED))
    assert "unsourced_number" in rules(rep)


# ---- admin reasoning ----
def test_admin_reasoning_only_for_admin():
    body = "제 판단으로는 이번 건은 재료비가 맞습니다."
    assert "admin_reasoning" in hard_rules(check(body, StyleContext(recipient_kind="admin")))
    assert "admin_reasoning" not in rules(check(body, StyleContext(recipient_kind="person")))


def test_admin_recipient_detection_uses_config():
    assert is_admin_recipient("office@example.edu")
    assert is_admin_recipient("kim@example.edu", "연구지원팀")
    assert not is_admin_recipient("kim@example.edu", "김 교수")
    from dataclasses import replace
    cfg = replace(cfgmod.Config(), admin_local_parts=("labmanager",))
    assert is_admin_recipient("labmanager1@example.edu", config=cfg)
    assert not is_admin_recipient("office@example.edu", config=cfg)


# ---- internal note / markdown ----
def test_internal_note_hard_even_when_owner_edited():
    rep = check("자료 보냅니다. (확인 필요)", owner_edited=True)
    assert "internal_note" in hard_rules(rep)
    assert "internal_note" not in rules(check("자료 보냅니다. (첨부 참조)"))


def test_internal_note_extra_pattern_from_config():
    from dataclasses import replace
    cfg = replace(cfgmod.Config(), internal_note_extra=("내부용",))
    assert "internal_note" in hard_rules(check("내부용 메모입니다.", config=cfg))
    assert "internal_note" not in rules(check("내부용 메모입니다."))


def test_markdown_hard():
    assert "markdown" in hard_rules(check("**중요** 확인 바랍니다.", owner_edited=True))


# ---- profile ----
def _profile(register="존댓말", **kw):
    p = default_profile("kim@example.edu")
    p.register, p.source = register, "sent"
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def test_profile_register_and_signoff_and_honorific():
    p = _profile(honorific="교수님", signoff="드림", exclaim_closing=False)
    rep = check("안녕하세요.\n자료 보낼게\n내일 줄게\n감사합니다!", profile=p)
    assert {"profile_register", "profile_honorific", "profile_signoff", "profile_exclaim"} <= rules(rep)
    good = check("안녕하세요, 김 교수님.\n자료를 보냅니다.\n이도윤 드림", profile=p)
    assert not {r for r in rules(good) if r.startswith("profile_")}


def test_profile_language_mismatch():
    p = _profile(language="en")
    assert "profile_language" in rules(check("안녕하세요. 자료를 보냅니다.", profile=p))


def test_custom_signoff_form_via_config():
    from dataclasses import replace
    cfg = replace(cfgmod.Config(), signoff_forms=("배상",))
    assert features("안녕하세요.\n자료를 보냅니다.\n홍길동 배상", cfg).signoff == "배상"
    assert features("안녕하세요.\n자료를 보냅니다.\n홍길동 드림", cfg).signoff == "none"


def test_extract_profile_votes_and_defaults():
    assert extract_profile("a@example.edu", []).source == "default"
    sents = [SentSample(str(i), f"2026-01-0{i}", "s", "박 교수님, 안녕하세요.\n자료를 보냅니다.\n이도윤 올림") for i in range(1, 4)]
    p = extract_profile("A@example.edu", sents)
    assert p.register == "존댓말" and p.honorific == "교수님" and p.signoff == "올림" and p.address == "a@example.edu"
    casual = [SentSample(str(i), f"2026-01-0{i}", "s", "야 자료 보냈어\n확인해 줘\n내일 보자") for i in range(1, 4)]
    assert extract_profile("b@example.edu", casual).register == "반말"


def test_signature_block_does_not_hide_signoff():
    body = "안녕하세요.\n자료를 보냅니다.\n이도윤 드림\n\n예시 대학교 연구실\nE-mail: yi@example.edu"
    assert features(body).signoff == "드림"


# ---- AI tell ----
def test_ai_tell_is_soft_only():
    rep = check("말씀드리겠습니다. 소중한 의견 감사합니다.")
    assert "ai_tell" in {v.rule for v in rep.soft} and "ai_tell" not in hard_rules(rep)


# ---- config ----
def test_packaged_toml_matches_builtin_defaults():
    pytest.importorskip("tomllib")
    assert cfgmod.load_config() == cfgmod.Config()


def test_custom_config_file(tmp_path):
    pytest.importorskip("tomllib")
    f = tmp_path / "my.toml"
    f.write_text('[thresholds]\napology_max = 0\n[voice]\nsignoff_forms = ["배상"]\n', encoding="utf-8")
    cfg = cfgmod.load_config(f)
    assert cfg.apology_max == 0 and cfg.signoff_forms == ("배상",)
    assert "apology" in hard_rules(check("죄송합니다. 확인 부탁드립니다.", config=cfg))


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        cfgmod.load_config(tmp_path / "nope.toml")


# ---- CLI ----
def _run(tmp_path, draft, *extra, source=None):
    d = tmp_path / "draft.txt"
    d.write_text(draft, encoding="utf-8")
    args = [sys.executable, "-m", "mailcheck", str(d), *extra]
    if source is not None:
        s = tmp_path / "received.txt"
        s.write_text(source, encoding="utf-8")
        args += ["--source", str(s)]
    return subprocess.run(args, cwd=ROOT, capture_output=True, encoding="utf-8", errors="replace")


def test_cli_clean_exit_0(tmp_path):
    r = _run(tmp_path, "안녕하세요.\n견적서를 첨부합니다.\n감사합니다.", source=RECEIVED)
    assert r.returncode == 0 and "지적 사항 없음" in r.stdout


def test_cli_hard_exit_1_with_korean_rows(tmp_path):
    r = _run(tmp_path, "**중요** 확인 바랍니다.")
    assert r.returncode == 1 and "[필수 수정] markdown" in r.stdout and "근거" in r.stdout


def test_cli_owner_edited_downgrades(tmp_path):
    body = "죄송합니다. 늦었습니다.\n송구합니다."
    assert _run(tmp_path, body).returncode == 1
    r = _run(tmp_path, body, "--owner-edited")
    assert r.returncode == 0 and "[권고] apology" in r.stdout


def test_cli_profile_and_missing_file(tmp_path):
    prof = tmp_path / "p.json"
    prof.write_text(json.dumps(_profile(language="en").to_dict(), ensure_ascii=False), encoding="utf-8")
    r = _run(tmp_path, "안녕하세요. 자료를 보냅니다.", "--profile", str(prof))
    assert r.returncode == 1 and "profile_language" in r.stdout
    r2 = subprocess.run([sys.executable, "-m", "mailcheck", str(tmp_path / "none.txt")], cwd=ROOT,
                        capture_output=True, encoding="utf-8", errors="replace")
    assert r2.returncode == 2
