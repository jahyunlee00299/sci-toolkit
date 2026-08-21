#!/usr/bin/env python3
"""doctor.py credentials-divergence 검사 회귀 테스트.

실행: python tests/test_credentials_divergence.py   (exit 0 = 통과)

[260810] 이슈 #3(실제 설치자 리포트): config/credentials.json 에 토큰을
등록해도 기존 공용 secrets 저장소를 읽는 자동화는 그 값을 못 본다.
doctor.py 가 11/11 OK 를 내면서도 이 분기를 놓쳤다 — 이 검사는 정확히
그 간극을 잡기 위한 것이다.

[260822] 공용 저장소가 ~/.claude/secrets.json 에서 ~/.secrets/secrets.json 으로
옮겨갔다(C-66). 이 테스트는 원래 **사용자의 실제 secrets 경로에 직접 쓰고
지우고 복원**했다 — 그 경로가 마침 비어 있어서 사고가 안 났을 뿐, 설계 자체가
위험했다. 이제는 Path.home() 을 임시 디렉터리로 돌려서 실제 홈을 건드리지
않는다. 두 후보 경로를 모두 검사하므로, 어느 한쪽만 비우는 것으로는
"저장소 없음" 분기를 재현할 수 없다.
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

    # 실제 홈을 건드리지 않는다. doctor 가 보는 두 후보 경로가 모두 이 가짜 홈
    # 아래로 떨어지도록 HOME 환경변수를 돌린다 — 한쪽만 지우면 나머지 한쪽에
    # 있는 진짜 파일이 새어 들어와 "저장소 없음" 케이스가 재현되지 않는다.
    # Path.home() 이 아니라 HOME/USERPROFILE 을 갈아끼우는 이유: doctor 는
    # Path("~/...").expanduser() 를 쓰고, expanduser 는 Path.home() 을 거치지
    # 않고 os.path.expanduser -> 환경변수를 직접 읽는다.
    with tempfile.TemporaryDirectory() as home_td:
        fake_home = Path(home_td)
        (fake_home / ".claude").mkdir()
        (fake_home / ".secrets").mkdir()
        secrets_paths = [
            fake_home / ".secrets" / "secrets.json",
            fake_home / ".claude" / "secrets.json",
        ]
        # 정식(신규) 경로 하나에만 쓴다. 구 경로는 존재하지 않는 상태로 둔다.
        real_secrets = secrets_paths[0]

        def _clear_secrets() -> None:
            for sp in secrets_paths:
                sp.unlink(missing_ok=True)

        fake_env = {"HOME": str(fake_home), "USERPROFILE": str(fake_home)}
        with mock.patch.dict("os.environ", fake_env), \
             tempfile.TemporaryDirectory() as td:
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
            _clear_secrets()
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
            _clear_secrets()
            with mock.patch.dict("os.environ", {"SCITK_TEST_GH_TOKEN_ZZZ": "ghp_fake"}):
                r = doctor.check_credentials_divergence(root)
            check("set ENV var counted as registered -> WARN (no secrets.json)",
                  r.status == doctor.STATUS_WARN, r.message)

    # 가짜 홈은 TemporaryDirectory 가 통째로 걷어간다 — 복원 로직이 필요 없다.

    print("=" * 60)
    print(f"통과 {_pass} / 실패 {_fail}")
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
