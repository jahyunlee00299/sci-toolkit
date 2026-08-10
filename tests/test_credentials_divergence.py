#!/usr/bin/env python3
"""doctor.py credentials-divergence 검사 회귀 테스트.

실행: python tests/test_credentials_divergence.py   (exit 0 = 통과)

[260810] 이슈 #3(실제 설치자 리포트): config/credentials.json 에 토큰을
등록해도 기존 ~/.claude/secrets.json 을 읽는 자동화는 그 값을 못 본다.
doctor.py 가 11/11 OK 를 내면서도 이 분기를 놓쳤다 — 이 검사는 정확히
그 간극을 잡기 위한 것이다.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

spec = importlib.util.spec_from_file_location(
    "doctor", str(Path(__file__).resolve().parent.parent / "doctor.py"))
doctor = importlib.util.module_from_spec(spec)
sys.modules["doctor"] = doctor
spec.loader.exec_module(doctor)

_pass = 0
_fail = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _pass, _fail
    if cond:
        _pass += 1
        print(f"  PASS  {name}")
    else:
        _fail += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("credentials-divergence 검사 회귀 테스트")
    print("=" * 60)

    real_secrets = Path.home() / ".claude" / "secrets.json"
    backup = Path.home() / ".claude" / "secrets.json.doctor_test_backup"
    had_original = real_secrets.exists()
    if had_original:
        shutil.copy2(real_secrets, backup)

    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = root / "config"
            cfg.mkdir()

            print("\n[1] credentials.json 없음 -> OK (검사할 게 없음)")
            r = doctor.check_credentials_divergence(root)
            check("no credentials.json -> OK", r.status == doctor.STATUS_OK, r.message)

            print("\n[2] 등록된 서비스 없음(ENV 플레이스홀더만) -> OK")
            (cfg / "credentials.json").write_text(
                json.dumps({"notion": {"token": "ENV:SCITK_NOTION_TOKEN_NONEXISTENT_XYZ"}}),
                encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("unset ENV placeholder not counted as registered",
                  r.status == doctor.STATUS_OK, r.message)

            print("\n[3] 등록됨 + secrets.json 자체가 없음 -> WARN")
            (cfg / "credentials.json").write_text(
                json.dumps({"notion": {"token": "ntn_real_value_not_env"}}),
                encoding="utf-8")
            real_secrets.unlink(missing_ok=True)
            r = doctor.check_credentials_divergence(root)
            check("secrets.json absent -> WARN", r.status == doctor.STATUS_WARN, r.message)

            print("\n[4] 등록됨 + secrets.json 있지만 대응 키 없음 -> WARN")
            real_secrets.write_text(json.dumps({"GITHUB_PAT": "x"}), encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("secrets.json missing matching key -> WARN",
                  r.status == doctor.STATUS_WARN, r.message)
            check("WARN message names the correct key mapping",
                  "NOTION_TOKEN" in r.message, r.message)

            print("\n[5] 등록됨 + secrets.json에 대응 키 있음 -> OK")
            real_secrets.write_text(json.dumps({"NOTION_TOKEN": "x"}), encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("matching key present -> OK", r.status == doctor.STATUS_OK, r.message)

            print("\n[6] 여러 서비스 중 일부만 어긋남 -> WARN에 어긋난 것만 언급")
            (cfg / "credentials.json").write_text(
                json.dumps({
                    "notion": {"token": "ntn_real"},
                    "asana": {"token": "asana_real"},
                }),
                encoding="utf-8")
            real_secrets.write_text(json.dumps({"NOTION_TOKEN": "x"}), encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("partial mismatch -> WARN", r.status == doctor.STATUS_WARN, r.message)
            check("only the missing service is named (notion not flagged)",
                  "asana" in r.message and "notion" not in r.message.split("registered")[0],
                  r.message)

            print("\n[7] 깨진 JSON -> WARN(크래시 없이)")
            (cfg / "credentials.json").write_text("{ not valid json", encoding="utf-8")
            r = doctor.check_credentials_divergence(root)
            check("malformed JSON doesn't crash", r.status == doctor.STATUS_WARN, r.message)

            print("\n[8] ENV 변수가 실제로 설정된 경우 -> registered로 취급")
            (cfg / "credentials.json").write_text(
                json.dumps({"github": {"token": "ENV:SCITK_TEST_GH_TOKEN_ZZZ"}}),
                encoding="utf-8")
            real_secrets.unlink(missing_ok=True)
            with mock.patch.dict("os.environ", {"SCITK_TEST_GH_TOKEN_ZZZ": "ghp_fake"}):
                r = doctor.check_credentials_divergence(root)
            check("set ENV var counted as registered -> WARN (no secrets.json)",
                  r.status == doctor.STATUS_WARN, r.message)

    finally:
        real_secrets.unlink(missing_ok=True)
        if had_original:
            shutil.move(str(backup), str(real_secrets))
        else:
            backup.unlink(missing_ok=True)

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
