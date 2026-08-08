"""pytest 배선 — 이 폴더의 검사는 standalone 스크립트다.

각 `test_*.py` 는 `python tests/test_x.py` 로 돌리는 스크립트이고, 모듈 레벨에서
검사를 수행한 뒤 `sys.exit()` 로 판정을 낸다. 정식 러너는 `doctor.py` 이며,
그쪽은 각 스크립트를 subprocess 로 실행하므로 이 구조와 잘 맞는다.

문제는 `pytest tests/` 다. 새로 clone 한 사람이 가장 먼저 치는 명령인데, pytest 는
수집 단계에서 각 파일을 **import** 하므로 검사가 그 자리에서 실행되고 모듈 레벨
`sys.exit()` 가 INTERNALERROR 로 터진다(실측 2026-08-08). 도구는 멀쩡한데 저장소가
깨진 것처럼 보였다.

그래서 여기서 pytest 가 스크립트를 import 하지 않고 **subprocess 로 실행**하도록
수집 방식을 바꾼다 — doctor.py 가 하는 것과 같은 방식이다. 결과적으로
`pytest tests/` 와 `python doctor.py` 가 같은 검사를 수행한다.

러너를 별도 `test_*.py` 파일로 두지 않은 이유: tests/ 의 파일 수는 README 에
적힌 "회귀 테스트 N종" 의 SSOT 이고(test_doc_counts.py), 모든 test_*.py 는
doctor 가 실행해야 한다는 규칙도 있다. 배선 파일 하나를 추가하면 그 두 검사가
동시에 어긋나면서, 검사도 아닌 파일을 doctor 목록에 넣게 된다. conftest 는
pytest 전용 파일이라 어느 쪽 개수에도 잡히지 않는다.
"""
from __future__ import annotations

import subprocess
import sys

import pytest


class SelfCheckItem(pytest.Item):
    """자체검사 스크립트 하나를 subprocess 로 실행한다."""

    def __init__(self, *, name, parent, script):
        super().__init__(name, parent)
        self.script = script

    def runtest(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(self.script)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(self.script.parent.parent), timeout=600,
        )
        if proc.returncode != 0:
            detail = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            raise AssertionError(
                f"{self.script.name} exited {proc.returncode}\n{detail[-3000:]}")

    def repr_failure(self, excinfo, style=None):
        # 스크립트가 이미 사람이 읽을 형태로 실패를 출력한다. pytest 의 파이썬
        # 트레이스백을 덧씌우면 정작 읽어야 할 내용이 묻힌다.
        if isinstance(excinfo.value, AssertionError):
            return str(excinfo.value)
        return super().repr_failure(excinfo, style)

    def reportinfo(self):
        return self.script, 0, f"self-check: {self.script.name}"


class SelfCheckFile(pytest.File):
    def collect(self):
        yield SelfCheckItem.from_parent(
            self, name=self.path.name, script=self.path)


def pytest_collect_file(parent, file_path):
    if file_path.suffix == ".py" and file_path.name.startswith("test_"):
        return SelfCheckFile.from_parent(parent, path=file_path)
    return None
