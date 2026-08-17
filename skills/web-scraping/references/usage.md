# web-scraping skill — 상세 사용 가이드

`SKILL.md`의 빠른 참조를 보완하는 상세 예시·트러블슈팅 문서.

## 목차

1. 설치와 환경
2. 모드별 상세 사용
3. Python import 패턴
4. 공통 옵션 (polite crawling)
5. 출력 형식과 provenance
6. 트러블슈팅
7. 윤리·법적 가이드라인

---

## 1. 설치와 환경

### 핵심 의존성 (필수)

```bash
# base 또는 research-agent conda env에서
cd <skill-root>
pip install -r requirements.txt
```

설치 무게는 약 20~30 MB (Playwright 브라우저 제외). 모두 MIT/BSD/Apache-2.0.

Windows에서 `selectolax`, `lxml`은 pip wheel이 제공되므로 컴파일러 불필요.
conda 혼용 시 `lxml`은 conda-forge를 우선해도 된다:

```bash
conda install -c conda-forge lxml
pip install httpx selectolax trafilatura beautifulsoup4 habanero arxiv markitdown
```

### 동적 모드 (선택)

`fetch_dynamic.py`를 쓸 때만 설치한다. 정적·학술·파일수집 모드는 불필요.

```bash
pip install playwright
playwright install chromium      # 브라우저 바이너리 (~150 MB)
```

미설치 상태로 `fetch_dynamic.py`를 실행하면 친절한 설치 안내 후 종료한다.

### 실행 위치

스크립트는 `_common.py`를 같은 디렉터리에서 import 하므로
**`scripts/` 디렉터리 안에서 실행**한다:

```bash
cd <skill-root>/scripts
python fetch_static.py "https://..." --mode text
```

---

## 2. 모드별 상세 사용

### 2.1 fetch_static.py — 정적 HTML

| 모드 | 반환 내용 |
|---|---|
| `text` | trafilatura 본문 추출 (Markdown) + 메타데이터(title/author/date) |
| `tables` | 모든 HTML `<table>` → `{columns, rows, n_rows, n_cols}` |
| `links` | 모든 `<a href>` → 절대 URL + 앵커 텍스트 (중복 제거) |
| `html` | 원본 HTML 그대로 |

```bash
# 논문 페이지 본문 + 표를 함께 추출
python fetch_static.py \
    "https://pubs.rsc.org/en/content/articlehtml/2024/gc/d4gc00000a" \
    --mode text tables -o article.json

# DB 페이지의 표만 DataFrame 형태로
python fetch_static.py "https://www.uniprot.org/uniprotkb/P12345" \
    --mode tables -o uniprot_tables.json

# rate-limit을 늘려 보수적으로 (도메인당 3초)
python fetch_static.py "https://slow-server.org/page" \
    --mode text --delay 3.0 --timeout 60
```

`text` 모드는 trafilatura가 없거나 본문을 못 찾으면 selectolax 기반
fallback으로 태그를 제거한 텍스트를 반환한다 (`extractor` 필드로 구분).

### 2.2 fetch_academic.py — 학술 메타데이터

세 소스 모두 공식 API만 사용한다. 페이지 스크래핑 없음.

```bash
# Crossref 키워드 검색 (relevance 정렬)
python fetch_academic.py --source crossref \
    --query "enzyme cascade biocatalysis" -n 20 -o crossref_results.json

# Crossref DOI 단건 — EndNote DOI 검증 워크플로우에 직결
python fetch_academic.py --source crossref --doi 10.1021/acscatal.3c00000

# arXiv 검색 (제출일 최신순)
python fetch_academic.py --source arxiv \
    --query "Bayesian optimization enzyme" -n 10

# bioRxiv 최근 프리프린트 (최근 30일)
python fetch_academic.py --source biorxiv --recent 30 --server biorxiv

# medRxiv DOI 조회
python fetch_academic.py --source biorxiv --server medrxiv \
    --doi 10.1101/2024.01.01.24300000
```

반환 레코드의 통일 필드: `title, authors, year, doi, journal/url, pdf_links`.
`pdf_links`에 전문 PDF URL이 있으면 `harvest_files.py`로 바로 내려받을 수 있다.

PubMed/OpenAlex 검색이 필요하면 이 스킬 대신 `pubmed-database`,
`openalex-database` 스킬이나 Biopython(Bio.Entrez) 패키지를 쓴다 (역할 분담, 중복 회피).

### 2.3 fetch_dynamic.py — 동적 JS 페이지

정적 추출이 빈 결과를 주거나 콘텐츠가 JS로 그려질 때만.

```bash
# 기본: networkidle까지 대기 후 본문 추출
python fetch_dynamic.py "https://spa-dashboard.org/data" --mode text

# 특정 요소 등장까지 대기 (검색 결과 테이블 등)
python fetch_dynamic.py "https://search-site.org/results?q=target+compound" \
    --mode tables --wait-selector "div.result-table" --timeout 45

# 디버깅: 브라우저 창 표시
python fetch_dynamic.py "https://site.org" --mode html --no-headless
```

`--wait-until` 옵션: `load` / `domcontentloaded` / `networkidle`(기본).
렌더링 후 HTML은 `StaticScraper`로 넘겨지므로 추출 모드는 정적과 동일하다.

### 2.4 harvest_files.py — 문서 파일 수집

```bash
# 1단계: 어떤 파일이 링크돼 있는지 먼저 확인 (다운로드 안 함)
python harvest_files.py "https://journal.org/article/si" \
    --discover-only --ext pdf xlsx docx

# 2단계: PDF만 다운로드
python harvest_files.py "https://journal.org/article/si" \
    -o ./si_files --ext pdf -n 5 --report harvest.json

# 다운로드 + markitdown 변환 동시
python harvest_files.py "https://journal.org/article/si" \
    -o ./si_files --ext pdf docx xlsx --convert --report harvest.json
```

- 다운로드는 스트리밍(청크 64KB)이라 수백 MB PDF도 메모리 안전.
- 파일명 충돌 시 `_1`, `_2` suffix 자동 부여.
- 개별 다운로드 실패는 raise하지 않고 report의 `status` 필드에 기록 → 배치 계속.
- `--convert`는 `markitdown` 패키지를 사용. 미설치 시 markitdown 스킬
  명령을 안내 메시지로 출력.

---

## 3. Python import 패턴

모든 스크립트는 import 가능하다. `scripts/`를 sys.path에 추가한다.

```python
import sys
sys.path.insert(0, "scripts")  # run from skill root, or use absolute path to scripts/

from _common import PoliteHttpClient, HttpClientConfig, Provenance
from fetch_static import StaticScraper
from fetch_academic import CrossrefProvider, ArxivProvider, BiorxivProvider
from harvest_files import FileHarvester, convert_with_markitdown

# 클라이언트 1개를 여러 페이지에 재사용 (rate-limit 상태 공유)
config = HttpClientConfig(min_delay=1.5, max_retries=5, use_cache=True)
with PoliteHttpClient(config) as client:
    for url in page_urls:
        scraper = StaticScraper.from_url(url, client)
        print(scraper.extract_tables())

    harvester = FileHarvester(client, extensions=("pdf",))
    results = harvester.harvest("https://journal.org/si", "./out")

# 학술 메타데이터
papers = CrossrefProvider().search("target product biosynthesis", limit=10)
for p in papers:
    print(p["title"], p["doi"], p["pdf_links"])
```

### 동적 스크래퍼

```python
from fetch_dynamic import DynamicScraper, DynamicConfig

cfg = DynamicConfig(wait_selector="#results", timeout_ms=45000)
scraper = DynamicScraper(cfg).scrape("https://spa-site.org/page")
text = scraper.extract_text()
```

---

## 4. 공통 옵션 (polite crawling)

`fetch_static.py`, `fetch_academic.py`(biorxiv), `harvest_files.py`가 공유:

| 옵션 | 기본값 | 의미 |
|---|---|---|
| `--delay` | 1.0 | 도메인당 요청 간 최소 초 |
| `--timeout` | 30.0 | 요청 타임아웃 (초) |
| `--retries` | 3 | 429/5xx/전송오류 최대 재시도 |
| `--ignore-robots` | off | robots.txt 무시 (권한 있을 때만) |
| `--no-cache` | off | 응답 캐시 비활성화 |

`fetch_dynamic.py`는 `--timeout`, `--ignore-robots`, `--no-headless`,
`--wait-selector`, `--wait-until`을 사용한다.

### 캐시

- 위치: `web-scraping/.cache/` (URL의 SHA-256 해시로 키)
- 기본 TTL: 24시간
- 캐시 비우기: `.cache/` 디렉터리 내용 삭제 (휴지통 경유 권장)

---

## 5. 출력 형식과 provenance

모든 출력 JSON은 동일 구조:

```json
{
  "provenance": {
    "source_url": "https://example.com/page",
    "method": "fetch_static",
    "retrieved_at": "2026-05-23T04:12:00+00:00",
    "tool": "web-scraping-skill/1.0"
  },
  "data": { "...": "모드별 추출 결과" }
}
```

`provenance`는 데이터 출처 기록 정책에 따라 항상 포함된다. 수집 데이터를
연구 노트·runs/ 디렉터리에 저장할 때 이 메타데이터를 함께 보관한다.

---

## 6. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `ImportError: httpx is required` | `pip install -r requirements.txt` |
| `robots.txt disallows fetching` | 대상이 크롤링을 금지함. 공식 API 사용 검토. 권한이 있으면 `--ignore-robots` (책임은 사용자) |
| `text` 모드가 빈 결과 | JS 렌더링 페이지일 가능성 → `fetch_dynamic.py` 사용 |
| `tables` 모드가 빈 리스트 | 페이지에 HTML `<table>`이 없음 (div 기반 격자) → selectolax CSS 선택자로 직접 파싱하거나 동적 모드 |
| `Playwright is not installed` | `pip install playwright && playwright install chromium` |
| `Chromium browser binary missing` | `playwright install chromium` |
| HTTP 429 반복 | `--delay`를 늘리고 `--retries` 확인. 서버가 강하게 제한 중 |
| `habanero is required` | `pip install habanero` |
| 한글 깨짐 | 출력 JSON은 UTF-8. 터미널 인코딩 확인 (`chcp 65001`) |
| OneDrive 경로 저장 시 느림 | cloud-only 파일 강제 다운로드. 로컬 경로에 저장 후 이동 권장 |

### 동적 모드가 느릴 때

`--wait-until domcontentloaded`로 바꾸면 networkidle보다 빠르다 (단,
지연 로딩 콘텐츠를 놓칠 수 있음). 또는 `--wait-selector`로 필요한 요소만
기다린다.

---

## 7. 윤리·법적 가이드라인

이 스킬은 윤리적 크롤링을 코드 레벨에서 강제한다. 사용자도 다음을 지킨다:

1. **공식 API 우선** — 스크래핑 전에 Crossref/arXiv/PubMed/OpenAlex API를 먼저 검토.
2. **robots.txt** — 기본 준수. `--ignore-robots`는 본인이 소유하거나 명시적
   허가를 받은 사이트에만.
3. **rate limit** — 기본 1초 간격을 함부로 0으로 낮추지 않는다. 대상 서버
   부하를 고려.
4. **페이월 우회 금지** — 로그인·구독 콘텐츠를 우회하지 않는다. Sci-Hub 등
   비합법 경로는 스킬에서 배제됨. 소속 기관 도서관의 EZproxy 등 합법적 기관
   접근을 사용한다.
5. **개인정보** — 수집 데이터에 개인정보가 섞이지 않도록 주의. raw 크롤링
   데이터를 public repo에 커밋하지 않는다.
6. **저작권** — 수집한 텍스트·PDF의 재배포는 원저작권·라이선스를 따른다.

문제가 되는 요청(대량 페이월 우회, 안티봇 회피 목적의 위장 등)은 이 스킬의
설계 범위 밖이다.
