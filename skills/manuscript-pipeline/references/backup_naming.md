# Edit Categories — backup 파일명 규칙 (manuscript-pipeline reference)

장시간 편집 시 `working.docx`를 단계별로 저장할 때, 의미 있는 파일명 suffix를 사용한다. (선택) `manuscript_workdir.py record` 같은 changelog 기록 헬퍼가 있으면 그 호출과 짝을 맞춰 일관성을 유지한다.

## Naming convention

```
{base}_backup_{category}.docx
```

`{category}` 는 아래 카탈로그 중 하나:

| Category | 의미 | 언제 사용 |
|---|---|---|
| `restructure` | 섹션 재구조화 | 큰 단위 이동·통합 |
| `{N}fix` | 섹션 N 수정 | 섹션 단위 마이크로 수정 (예: `21fix`, `211_23fix`) |
| `{N}_{M}_replace` | 섹션 N·M 대체 | 두 섹션 동시 교체 |
| `doi_fix` | DOI/citation 수정 | 참고문헌 정합성 |
| `table_fix`, `table_v{N}` | 표 수정 | 표 번호·컬럼·데이터 |
| `pre_abbrev` | 약어 통일 (도메인 어휘) | 명명법 일제 정리 |
| `body_accuracy` | 본문 정확도 | 수치·인용 검증 후 |
| `separation_edit` | 편집 분리 | 큰 변경을 둘로 쪼개서 저장 |
| `rebuild_base` | 베이스 재구축 | 손상 복구 후 |
| `reftest` | reference 검증 결과 반영 | reference_validator.py 후 |
| `tracked` | tracked changes 적용본 | accept 전 검토용 |
| `accepted` | tracked 수락본 | 최종 깨끗한 버전 |
| `commented` | 코멘트만 단 버전 | 논문 저자에게 회람 |
| `reviewed` | 다른 저자 review 완료 | 멘토/공동저자 마크업 받은 후 |
| `QCfixed` | QC 통과 후 | 최종 검수 |

**Rule:** `record` 호출 시 `--rationale` 에 category를 포함. 예:
```bash
manuscript_workdir.py record paper1 "Section 2.4" "..." "..." --rationale "[ABBREV] sugar 약어 통일"
```

## 사용자가 직접 만든 backup vs 에이전트 backup

- 사용자가 클라우드 동기화 폴더에 직접 복사한 backup → 참고용
- 에이전트가 만든 backup → 별도 작업 디렉터리 `~/manuscripts/{paper_id}/working_history/{ts}_{category}.docx`
- 둘이 충돌하지 않음 (다른 디렉토리)

## 클라우드 동기화 폴더 충돌 주의
동기화 폴더의 DOCX가 Word에 열려 있으면 덮어쓰기 실패 → 임시 폴더에서 작업 후 `_v2`로 저장.
