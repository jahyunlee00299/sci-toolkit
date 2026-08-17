---
name: web-scraping
description: 웹페이지·논문·문서를 크롤링/스크래핑하여 텍스트·표·링크·메타데이터를 추출하고 PDF/xlsx/docx 파일을 수집한다. Use this skill when the user wants to 크롤링, 스크래핑, scrape, 웹페이지 추출, 웹 데이터 수집, 논문 다운로드, fetch a web page, extract tables/text/links from a site, harvest PDFs, or retrieve scholarly metadata (Crossref/arXiv/bioRxiv DOIs and full-text links). Covers static HTML, JavaScript-rendered pages, academic sources, and bulk document harvesting.
allowed-tools: Read Write Edit Bash
license: MIT license
metadata:
    skill-author: web-scraping-skill team
    axis: Research
---

# Web Scraping

연구·서류작업을 위한 재사용 가능한 웹크롤링 스킬. 정적 HTML, 동적 JS 페이지,
학술 메타데이터, 문서 파일 수집을 4개 모드로 다룬다. 모든 스크립트는 CLI
실행과 Python import 양쪽으로 쓸 수 있다.

## Execution Method

코드 실행이 필요한 작업은 **Bash 도구**로 `scripts/` 하위 스크립트를 실행한다.
긴 크롤링(여러 페이지, 대량 다운로드)은 subagent에 위임하고, 단일 페이지
추출은 직접 실행해도 된다.

## When to Use This Skill

- 웹페이지에서 본문 텍스트·표·링크를 추출할 때 ("크롤링", "스크래핑", "추출")
- 논문 메타데이터(DOI, 저자, 전문 PDF 링크)를 Crossref/arXiv/bioRxiv에서 수집할 때
- JavaScript로 렌더링되는 동적 페이지의 콘텐츠가 필요할 때
- 페이지에 링크된 PDF/xlsx/docx 파일을 일괄 다운로드할 때 ("논문 다운로드")
- 수집한 문서를 Markdown으로 변환해 분석에 쓰려 할 때

## When NOT to Use

- PubMed / OpenAlex 검색 → 기존 `pubmed-database`, `openalex-database`,
  `biopython`(Bio.Entrez) 라이브러리를 우선 사용. 이 스킬은 Crossref/arXiv/bioRxiv만 다룬다.
- 이미 받은 로컬 문서의 변환만 필요 → `markitdown` 스킬을 직접 사용.
- 체계적 문헌고찰 → `literature-review` 스킬.

## PDF 다운로드 우선순위 (fetch_academic.py --download)

```
1. Crossref pdf_links      (출판사 CDN, OA 논문 즉시)
2. Unpaywall              (OA 버전 자동 탐색)
3. PubMed Central (PMC)   (무료 전문 저장소)
3.5 LibKey Nomad          (기관 구독 저널 — Chrome MCP 경유, --libkey 플래그)
4. EZproxy (Selenium)     (최후 수단, --ezproxy / --auto-login 플래그)
```

**LibKey Nomad (source 3.5, 권장):** 기관 도서관 구독 저널 원문 접근.
Chrome에 LibKey Nomad 확장 + Claude Code Chrome MCP 연결 상태에서 `--download --libkey` 사용.
EZproxy Selenium보다 가볍고 빠름. 동적 JS가 필요한 경우에만 Chrome MCP 사용.

**EZproxy (source 4, deprecated):** LibKey 실패 시 최후 수단.
`--auto-login` (Chrome 저장 자격증명) 또는 `--ezproxy` (수동 쿠키).

### OA/PMC 다운로드 실전 함정

**1. PMC PDF는 신 도메인 + 브라우저 필수.**
- ✅ `https://pmc.ncbi.nlm.nih.gov/articles/<PMCID>/` — **신 도메인**, 브라우저 자동화로 작동.
  패턴: navigate → interactive 요소에서 `href="pdf/<file>.pdf"` 찾기 → 그 절대 URL navigate → 다운로드.
- ❌ `https://www.ncbi.nlm.nih.gov/pmc/articles/<PMCID>/pdf/` — **구 도메인, 봇 차단**
  (1816 byte "Preparing to download..." HTML). urllib/requests 직접 접근은 신·구 둘 다 차단 → **반드시 브라우저**.

**2. "PMC에 있음 ≠ OA subset."**
- PMC 등재돼도 author-deposit이면 출판사 저작권 유지 → 봇 다운 불가.
- 판별: `pmc/utils/oa/oa.fcgi?id=<PMCID>` → `href`(tgz/pdf) 있으면 진짜 OA, `"is not Open Access"`면 기관 접근(EZproxy 등)이 필요.
- 진짜 OA subset이어도 tgz에 PDF 없고 XML/이미지만이면 → 신 PMC 도메인 브라우저로 재시도.

**3. PMID→DOI/PMCID(idconv)는 ≤4개 batch 필수.**
- `pmc/utils/idconv/v1.0/?ids=<csv>` — 큰 batch(10+)는 전부 status=error.
- PMID 키 매칭 시 `str(pmid).strip()` 정규화(dict 매칭 실패 방지).

**4. 출판사별 "막힘"의 실제 원인은 CAPTCHA가 아닌 경우가 더 많다.**
여러 기관 EZproxy에서 다수 출판사를 실측 비교한 결과, 진짜 Cloudflare/reCAPTCHA
차단은 소수이고 대부분은 세션 만료·URL 패턴 노후화·SSO 설정 문제였다.
"이 출판사는 CAPTCHA가 뜬다"고 가정하지 말고 아래 체크리스트로 먼저 원인을 좁힐 것.

- **JBC(J Biol Chem)는 ScienceDirect/Elsevier 호스팅** (ASBMB 표기에 속지 말 것) → Elsevier 한도 대상.
- **원본 출판사 사이트에 doi.org 리다이렉트로 직행하면 Cloudflare 챌린지가 뜨는 경우가 있다** (예: ScienceDirect). 기관 프록시(EZproxy 등)를 정확히 경유하면 대부분 정상 로딩된다 — 프록시를 안 거치고 원본 도메인으로 바로 가는 경로부터 의심할 것.
- **일부 출판사 플랫폼은 진짜로 봇 차단을 강하게 건다**(예: Microbiology Society는 Cloudflare 챌린지에서 완전히 종결되는 것을 실측). 이런 사이트는 자동화 대상에서 제외하고 사람이 직접 처리.
- **"CAPTCHA처럼 보이지만 실은 SSO/OAuth 설정 오류"인 경우도 있다** — 예: 출판사가 Auth0 등 제3자 SSO를 쓰는데, 기관이 프록시 도메인을 변경한 뒤 그 신규 호스트가 SSO의 콜백 URL 허용목록에 등록이 안 돼 있으면 "Callback URL mismatch" 에러가 뜬다. 이건 사용자/스크립트가 못 고치는 기관-대-출판사 설정 문제이므로 도서관/전산 담당자에게 문의해야 한다.
- **출판사가 플랫폼을 마이그레이션하면 옛 URL 패턴이 통째로 404가 될 수 있다** — 원본 사이트 자체에서 그 URL로 재현되는지 먼저 확인해서 "차단"과 "링크가 죽음"을 구분할 것. `/doi/full/<DOI>` 같은 구형 경로가 죽고 `/doi/<DOI>`가 신형 정답인 경우가 실측됨.
- LibKey 같은 링크 리졸버가 PDF 직링크 대신 **"ARTICLE LINK"/"LIBRARY ACCESS OPTIONS"만** 주면 그 출판사엔 리졸버의 PDF 직링크가 없다는 뜻 — 출판사 페이지 직접 접근이나 PMC로 우회.
- 정찰(어디서 막히는지 확인)할 때 임의로 지어낸 DOI/PII로 테스트하면 "진짜 404"와 "진짜 차단"을 구분 못 한다 — Crossref API로 실재하는 최신 DOI를 먼저 확보하고 테스트할 것.

**5. rate-limit은 자정-기준 트래커를 믿지 말 것.**
- 상업 출판사의 기관 다운로드 한도는 보통 **롤링 윈도우(예: ~24h)** 로 걸린다 → "오늘 N건" 같은 자정 리셋 트래커는 과소집계되어 실제로는 한도를 넘겨 차단(CAPTCHA/이용정지)당할 수 있다.
- 24h 롤링 기준으로 재확인하고, 연속/일괄 다운로드는 피할 것(건당 수초~수십초 간격).
- 짧은 시간에 같은 출판사에서 다량(10편 이상) 연속 다운로드하면 기관 전체가 그 출판사 DB에서 일정 기간(예: 한 달) 차단될 수 있다 — OA를 먼저 소진하고 구독분은 천천히, 소량씩.

**6. 구독 논문 = 브라우저로 출판사 페이지 직접 열기가 1순위.**
- 실패 순서 교훈: curl 직접 → HTML 로그인페이지만 옴(세션 없음). 링크 리졸버 우회 서비스(EBSCO/ProQuest류)로 돌면 **별도 로그인 팝업 벽**("기관 찾기")으로 막히는 경우가 있다(도서관 포털 로그인만으론 그 서비스로 세션이 전파 안 됨). 링크 리졸버(LibKey 등)가 해당 저널의 PDF 직링크를 못 주면 "LIBRARY ACCESS OPTIONS"만 나온다.
- **정답 = 브라우저 자동화로 출판사 논문 페이지(`link.springer.com/article/{DOI}` 등) 직접 navigate → 페이지의 PDF 링크(`/content/pdf/{DOI}.pdf` 등) 클릭/navigate.** 브라우저에 기관 구독 세션(IP/쿠키)이 살아있으면 그대로 다운로드됨(로그인 팝업 없음).
- **curl로 못 받으면 우회 서비스로 돌지 말 것** — 출판사 페이지 직접 접근을 먼저. 우회 경로는 오히려 로그인 벽이 더 많다. 2-3회 벽에 막히면 rabbit hole → 사용자에게 직접 다운로드 요청(대개 브라우저에서 "PDF파일 보기" 원클릭이라 어렵지 않음).
- 자격증명 입력·로그인 대행 금지(보안). 사용자가 기관 로그인만 해주면 그 세션에서 이어받기 가능.

## 4 Modes

| 모드 | 스크립트 | 용도 |
|---|---|---|
| 정적 HTML | `fetch_static.py` | 본문 텍스트·표·링크 추출 (requests/httpx + selectolax/trafilatura) |
| 학술 메타데이터 | `fetch_academic.py` | Crossref/arXiv/bioRxiv 검색 + DOI·전문 PDF 링크 |
| 동적 JS | `fetch_dynamic.py` | Playwright headless 렌더링 후 추출 (선택적 의존성) |
| 파일 수집 | `harvest_files.py` | 페이지의 PDF/xlsx/docx 자동 탐색·다운로드 + markitdown 변환 |

공통 모듈 `_common.py`가 robots.txt 체크, 도메인별 rate limiter, 응답 캐시,
재시도/백오프 HTTP 클라이언트, provenance 기록을 제공한다.

## Setup

```bash
# 의존성 설치 (base 또는 research-agent conda env)
pip install -r requirements.txt

# 동적 모드를 쓸 때만 추가 (선택)
pip install playwright
playwright install chromium
```

## Usage

스크립트는 모두 `scripts/` 디렉터리에서 실행한다 (`_common.py` import 때문).

### 1. 정적 HTML — fetch_static.py

```bash
cd scripts

# 본문 텍스트 추출 (boilerplate 제거, Markdown 출력)
python fetch_static.py "https://example.com/article" --mode text -o out.json

# 표 + 링크 동시 추출
python fetch_static.py "https://example.com/data" --mode tables links -o out.json

# rate-limit 조정 (도메인당 2초 간격)
python fetch_static.py "https://example.com" --mode text --delay 2.0
```

모드: `text` (본문+메타데이터), `tables` (모든 HTML 표 → 행 데이터),
`links` (절대 URL+앵커 텍스트), `html` (원본 HTML).

### 2. 학술 메타데이터 — fetch_academic.py

```bash
cd scripts

# Crossref 키워드 검색
python fetch_academic.py --source crossref --query "enzyme cascade biosynthesis" -n 10

# Crossref DOI 단건 조회
python fetch_academic.py --source crossref --doi 10.1039/D0GC00000A

# arXiv 검색
python fetch_academic.py --source arxiv --query "enzyme cascade optimization" -n 5

# bioRxiv 최근 30일 프리프린트
python fetch_academic.py --source biorxiv --recent 30 --server biorxiv
```

각 결과는 제목·저자·연도·DOI·전문 PDF 링크를 통일된 형식으로 반환한다.
Crossref는 polite pool(`mailto`)을 사용한다.

### 3. 동적 JS 페이지 — fetch_dynamic.py

정적 추출이 빈 결과를 주거나 JS 렌더링이 명확할 때만 사용.

```bash
cd scripts

# JS 렌더링 후 본문 추출
python fetch_dynamic.py "https://spa-site.com/page" --mode text

# 특정 요소가 나타날 때까지 대기 후 표 추출
python fetch_dynamic.py "https://site.com/results" --mode tables \
    --wait-selector "#results-table"
```

Playwright 미설치 시 명확한 설치 안내 메시지를 출력하고 종료한다.

### 4. 파일 수집 — harvest_files.py

```bash
cd scripts

# 페이지의 PDF/xlsx 링크 미리보기 (다운로드 안 함)
python harvest_files.py "https://journal.com/article" --discover-only --ext pdf

# PDF만 다운로드 + Markdown 변환
python harvest_files.py "https://journal.com/si" -o ./downloads \
    --ext pdf docx xlsx --convert --report harvest.json
```

다운로드는 스트리밍 방식(대용량 PDF도 메모리 절약)이고,
`--convert` 시 `markitdown` 패키지로 Markdown 변환을 연계한다.

## Python Import (재사용)

```python
import sys
sys.path.insert(0, "scripts")

from _common import PoliteHttpClient, HttpClientConfig
from fetch_static import StaticScraper
from fetch_academic import CrossrefProvider

with PoliteHttpClient(HttpClientConfig(min_delay=1.0)) as client:
    scraper = StaticScraper.from_url("https://example.com", client)
    tables = scraper.extract_tables()

papers = CrossrefProvider().search("target compound", limit=5)
```

## Safety Rules (반드시 준수)

이 스킬은 윤리적·합법적 크롤링만 한다 — `_common.py`에 강제 구현되어 있다.

1. **robots.txt 준수** — 요청 전 대상 도메인 robots.txt를 확인하고 `Disallow`
   경로는 차단한다. `--ignore-robots`는 명시적 권한이 있을 때만 사용한다.
2. **Rate limiting** — 도메인당 최소 1초 간격(기본값), robots.txt의
   `Crawl-delay`가 더 길면 그 값을 따른다.
3. **식별 가능한 User-Agent** — 연락처(이메일)를 포함한 정직한 UA를 보낸다.
   브라우저 위장은 하지 않는다 (연구·공공 데이터 용도엔 불필요).
4. **공식 API 우선** — HTML 스크래핑보다 Crossref/arXiv 등 공식 API를 항상 우선한다.
5. **HTTP 429 / Retry-After 존중** — 지수 백오프 + 최대 재시도 제한.
6. **캐싱** — 동일 URL 반복 요청을 막아 서버 부하를 줄이고 재현성을 높인다
   (`.cache/`, 기본 24h TTL, `--no-cache`로 비활성화).
7. **저작권·이용약관** — 로그인/페이월 콘텐츠 우회 금지. Sci-Hub 등 비합법
   경로 배제. 소속 기관 도서관 EZproxy 등 합법적 기관 접근을 사용한다.
8. **데이터 출처 기록** — 모든 출력 JSON에 `provenance`(원본 URL, 수집 시각,
   방법)를 기록한다.
9. **공개 repo 주의** — raw 크롤링 데이터를 public repo에 커밋하지 않는다.

## Output Format

모든 스크립트는 JSON을 출력한다 (`-o`/`--report`로 파일 저장, 미지정 시 stdout).

```json
{
  "provenance": {
    "source_url": "https://...",
    "method": "fetch_static",
    "retrieved_at": "2026-05-23T...Z",
    "tool": "web-scraping-skill/1.0"
  },
  "data": { ... }
}
```

## Integration with Other Skills

- `markitdown` — 수집한 PDF/DOCX를 Markdown으로 변환 (harvest_files `--convert`).
- `pubmed-database`, `openalex-database`, `biopython` library — PubMed/OpenAlex 검색.
  이 스킬은 중복하지 않고 Crossref/arXiv/bioRxiv만 담당.
- `literature-review` — 체계적 문헌고찰. 이 스킬로 수집한 메타데이터를 입력으로 활용.
- `onedrive` — OneDrive 경로 저장 시. OneDrive Safety 규칙(recursive glob 금지,
  대용량 파일 사전 확인) 준수.

## 기관 교외접속 PDF 다운로드 규칙
1. OA 논문 먼저 수집 → `python scripts/pdf_download_tracker.py log OA`
   (또는 your own helper script for tracking download quota)
2. 교외접속 필요분만 → `python scripts/pdf_download_tracker.py log [출판사]`
   - ScienceDirect = Elsevier (동일 카운터)
3. 작업 전 반드시 한도 확인: `python scripts/pdf_download_tracker.py status`
4. 기관 도서관 정책 위반 시 접근 정지 가능 — 출판사별 일일/월간 한도를 준수할 것

## 제출 전 ref 원문 대조 감사

원고 참고문헌 PDF를 "다 받았는지" 판정할 때:

1. **원고(docx)가 SSOT** — 다운로드 목록/폴더가 아니라 **최신 정본 원고에서 실제 ref 목록을 추출**해 기준으로 삼는다.
   `manuscript_text.py <docx> --count-only`로 tracked-change 여부 먼저 확인(CITE 필드는 EN.CITE로 카운트) → `--mode accept`로 텍스트 추출 → 번호별 (첫저자성, 연도, 저널) 파싱.
2. **폴더가 여러 개면 상위집합을 정본으로** — 파일명 규칙이 달라도(`저자_연도.pdf` vs `저자연도_태그_약어.pdf`) 저자성+연도 정규화 매칭으로 대조. 상위집합 폴더 하나를 정본, 나머지는 부분집합으로 처리.
3. **"MISSING"을 다운로드 대상과 구분** — 책/북챕터(원문없음 확정)와 **서지 오류**를 걸러낸다.
   ⚠️ 서지오류 사각지대: 저자+연도 매칭은 **연도만 틀린 케이스를 놓친다**. 예) Wong & Whitesides "JACS 2002, **103**, 4890" → JACS vol.103은 **1981년**(연도 오기, PDF는 wong_1981로 이미 있음). vol/page가 맞으면 CrossRef로 연도 독립검증 → 다운로드가 아니라 **원고/EndNote 서지 정정** 대상.
4. **EndNote 원고의 서지 정정은 텍스트 find-replace 금지** — 참고문헌이 `ADDIN EN.CITE` 필드로 렌더링되면 텍스트만 고쳐도 다음 "Update Citations"에서 되돌아가고 필드가 깨질 수 있다. 근본 수정 = **EndNote 라이브러리(sdb.eni)의 해당 레퍼런스 필드**를 고친 뒤 Update.
5. 오다운로드 잔재(`*_FIRSTPAGE_ONLY`, `*_WRONG_*`, `*_BROKEN*.bak`)는 **영구삭제 말고 `_quarantine/`로 격리**. Korean OneDrive 경로는 mv가 잠기므로 PowerShell `Move-Item -LiteralPath`.

## Resources

- `scripts/_common.py` — 공통 인프라 (robots, rate limiter, cache, HTTP client, provenance)
- `scripts/fetch_static.py` — 정적 HTML 추출
- `scripts/fetch_academic.py` — 학술 메타데이터 (Crossref/arXiv/bioRxiv)
- `scripts/fetch_dynamic.py` — 동적 JS 렌더링 (Playwright)
- `scripts/harvest_files.py` — 문서 파일 수집
- `requirements.txt` — 의존성
- `references/usage.md` — 상세 사용 예시 + 트러블슈팅
