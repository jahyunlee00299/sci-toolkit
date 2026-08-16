# EndNote Citation Integration (manuscript-pipeline reference)

> 단일/소수 DOI를 본문에 점진적으로 삽입할 때의 워크플로우.
> **대량 batch 변환(10개 이상, hallucination 검증 필요)** 은 `endnote-citation-injection` 스킬 사용.
> Track Changes XML 삽입 패턴은 docx 스킬(이 저장소에 없음 — docs/12 참조) 참조.

DOI를 기준으로 서지정보 수집 → 실재성/정합성 검증 → 인용 삽입 순서로 진행한다.

**이 배포판에 실존하는 도구** (배포판 루트 기준 `scripts/`, 이 문서 위치에서는 `../../../scripts/`):
- `../../../scripts/ref_fetch.py` — DOI(또는 제목) → 서지정보/OA PDF 수집 (CrossRef+OpenAlex+Unpaywall, API 키 불필요)
- `../../../scripts/doi_verify.py` — 이미 문서/BibTeX에 들어간 DOI가 실재하는지, 서지정보가 맞는지 교차검증 (환각 DOI 게이트)

EndNote 라이브러리 자체에 대한 DB 검색·RIS 생성·unformatted citation(`{Author, Year #N}`) 조회·
Word 댓글 자동 생성처럼 **EndNote DB에 직접 연결하는 기능은 이 배포판에 포함되어 있지 않다**
(원 저장소에서는 별도의 외부 헬퍼가 담당했다). 대량(10개 이상) EndNote 라이브러리 batch 삽입은
`endnote-citation-injection` 스킬을 사용하고, 그 스킬에도 없는 기능이라면 사용자가 EndNote GUI에서
직접 처리한다.

## DOI 우선 워크플로우

```
DOI 입력
  ↓
../../../scripts/ref_fetch.py --doi <DOI>   : CrossRef+OpenAlex+Unpaywall 서지정보 수집
  ↓
../../../scripts/doi_verify.py --doi <DOI>  : 실재성 + 저자/연도/제목 정합성 + retraction 여부 검증
  ↓
  ├─ OK                         → 서지정보 그대로 인용 삽입
  ├─ MISMATCH / ONE_SOURCE_ONLY → 이슈 보고 후 사용자 확인
  └─ HALLUCINATED / RETRACTED   → 절대 인용하지 않음, 사용자에게 즉시 보고 (exit code 2)
```

## Commands

```bash
# 1) DOI로 서지정보 + OA PDF 수집 (아래는 이 문서 기준 상대경로 — 실행은 배포판 루트에서)
python ../../../scripts/ref_fetch.py --doi "10.1234/xxx" --download

# 여러 DOI 일괄 (결과 JSON 저장)
python ../../../scripts/ref_fetch.py --doi "10.1/a,10.2/b,10.3/c" --output result.json

# DOI 목록 파일로 처리 (줄바꿈 구분)
python ../../../scripts/ref_fetch.py --doi-file dois.txt --output result.json

# 제목으로 검색해 DOI 해석 후 진행 (DOI 모를 때)
python ../../../scripts/ref_fetch.py --title "rare sugar isomerase" --download

# 2) 문서/BibTeX에 이미 들어간 DOI 검증 (환각 게이트)
python ../../../scripts/doi_verify.py --file manuscript.md
python ../../../scripts/doi_verify.py --bibtex refs.bib
```

옵션 전체 목록은 `python ../../../scripts/ref_fetch.py --help` / `python ../../../scripts/doi_verify.py --help`로 직접 확인한다
(위 경로는 이 문서 파일 위치 기준 상대경로다 — 배포판 루트 디렉터리에서 실행할 때는 `scripts/` 부분만 남기고 앞의 `../../../`는 뗀다).

## doi_verify 등급 해석

```json
{
  "doi": "10.xxxx/xxx",
  "grade": "OK",              // HALLUCINATED | RETRACTED | MISMATCH | ONE_SOURCE_ONLY | UNVERIFIED | OK
  "issues": [],
  "crossref_meta": { ... },
  "openalex_meta": { ... }
}
```

| grade | 의미 | 처리 |
|---|---|---|
| `OK` | 존재 확인 + 메타데이터 일치 + 철회 아님 | 그대로 인용 삽입 |
| `MISMATCH` | 존재는 하지만 적힌 저자/연도/제목이 실제 레코드와 다름 | 이슈 보고 후 사용자 결정 |
| `ONE_SOURCE_ONLY` | 두 소스 중 한쪽에서만 조회됨 | 조용히 통과시키지 말고 보고 |
| `UNVERIFIED` | 조회 자체 실패(네트워크 등) | "확인 못 했다" ≠ "괜찮다" — 재시도 또는 보고 |
| `HALLUCINATED` | CrossRef·OpenAlex 양쪽 모두 존재하지 않음 | 절대 인용 금지, 즉시 보고 (exit 2) |
| `RETRACTED` | OpenAlex가 철회로 보고 | 절대 인용 금지, 즉시 보고 (exit 2) |

## Word 댓글 포맷

인용 삽입 시 항상 해당 인용 옆에 Word 댓글을 수동으로 추가한다(자동 생성 도구 없음, docx 스킬(이 저장소에 없음 — docs/12 참조)의
댓글 삽입 기능 사용):

```
[REF] Author et al. (2024) Journal Name
https://doi.org/10.1234/xxx
Key finding: <ref_fetch 결과의 abstract/메타데이터에서 요약>
Why cited: <why this reference supports the cited claim — 명시 안 되면 문맥에서 추론 후 사용자 확인>
```

## EndNote 라이브러리 반영

`ref_fetch`/`doi_verify`는 EndNote DB를 직접 건드리지 않는다. 새 레퍼런스를 EndNote
라이브러리에 넣으려면:

1. `ref_fetch` 결과의 `--bibtex` 출력을 EndNote에서 Import (BibTeX 필터)
2. 또는 EndNote GUI에서 DOI로 직접 검색 후 import
3. import 후 EndNote가 부여한 Record Number로 unformatted citation(`{LastName, Year #N}`)을 만들어 삽입

Record Number는 라이브러리마다 다르므로 하드코딩하거나 이전 세션 값을 재사용하지 않는다 — 매번
EndNote에서 재확인한다.

## Rules

- **Record Number를 기억하거나 저장하지 않는다** — 라이브러리마다 다르므로 항상 EndNote GUI에서 재확인
- 인용을 원고에 넣기 **전에** 반드시 `doi_verify`로 검증한다 — INSERT 전 DOI 검증 필수
- `MISMATCH`/`ONE_SOURCE_ONLY`/`UNVERIFIED` 이슈는 사용자에게 구체적으로 보고하고 판단을 받는다
- `HALLUCINATED`/`RETRACTED`는 무조건 차단 — 어떤 이유로도 원고에 삽입하지 않는다
- 섹션 전체를 한번에 처리할 때는 DOI 목록 파일 → `ref_fetch --doi-file` 사용
- 인용 삽입 시 **항상** Word 댓글을 추가한다 (자동화 없어도 수동으로 반드시 추가)
- Why cited가 불명확하면 문맥 추론 후 댓글에 기재, 불확실하면 사용자 확인 요청
- **EndNote 필드 result text 보존**: `ADDIN EN.CITE` 필드의 separate~end 사이 `[N]`을 plain으로 변환 금지 (변환하면 EndNote 필드가 깨져 재포맷 불가).
