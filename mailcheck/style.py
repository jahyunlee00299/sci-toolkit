"""Reply-draft style rules and checker for Korean academic mail (deterministic, no LLM, no network).

Trimmed from the approval-inbox mail_style module. Owner-specific tuning (admin address patterns, sign-off
forms, honorifics, thresholds, workflow wording) is read from mailcheck.toml through config.Config.

Severity depends on who wrote the text. A fresh draft is held to the rules (hard); a body you edited yourself
is only warned about (soft), except the two safety rules (internal note, markdown) that are hard for both.

  rule                         fresh draft   owner edited
  apology                      hard          soft          at most `apology_max` apology
  gratitude                    hard          soft          one closing thanks + at most one in the body
  summary_echo                 hard          soft          no sentence that restates the received mail
  unsourced_number             hard          soft          numbers/dates/amounts must exist in the source text
  admin_reasoning              hard          soft          no explanation of your own judgement to an office
  internal_note                hard          hard          no memo / meta remark left in the text
  markdown                     hard          hard          plain mail text
  profile_*                    hard          soft          register / honorific / sign-off / exclamation / language
  ai_tell                      soft          soft          a few Korean and English AI-writing tells
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import voice
from .config import Config, default_config

SEVERITY = {
    "apology": ("hard", "soft"),
    "gratitude": ("hard", "soft"),
    "summary_echo": ("hard", "soft"),
    "unsourced_number": ("hard", "soft"),
    "admin_reasoning": ("hard", "soft"),
    "internal_note": ("hard", "hard"),
    "markdown": ("hard", "hard"),
    "profile_register": ("hard", "soft"),
    "profile_honorific": ("hard", "soft"),
    "profile_signoff": ("hard", "soft"),
    "profile_exclaim": ("hard", "soft"),
    "profile_language": ("hard", "soft"),
    "ai_tell": ("soft", "soft"),
}

# Korean label per rule, shown by the CLI.
RULE_LABELS = {
    "apology": "사과 횟수",
    "gratitude": "감사 횟수",
    "summary_echo": "받은 메일 되풀이",
    "unsourced_number": "출처 없는 숫자",
    "admin_reasoning": "행정 수신자에게 판단 설명",
    "internal_note": "내부 메모 흔적",
    "markdown": "마크다운 문법",
    "profile_register": "말투(존댓말/반말)",
    "profile_honorific": "호칭",
    "profile_signoff": "서명 어미",
    "profile_exclaim": "맺음 느낌표",
    "profile_language": "언어",
    "ai_tell": "AI 말투",
}

RULES_BLOCK = """[회신 문체 규칙]
1. 사과는 본문 전체에서 한 번까지만 쓴다. (죄송, 미안, 송구, 사과드)
2. 감사는 맺음에 한 번, 본문에 한 번까지만 쓴다.
3. 받은 메일의 내용을 다시 요약하는 문장을 쓰지 않는다. 요청을 받아들이거나 하겠다고 약속하는 문장(~하겠습니다, ~드리겠습니다, ~예정입니다)은 요청의 단어를 그대로 써도 된다.
4. 숫자, 날짜, 금액은 받은 메일 등 출처에 있는 것만 쓴다.
5. 행정 담당자에게 내 판단의 근거나 사정을 설명하지 않는다. 결과와 필요한 요청만 쓴다.
6. 내부 메모, 메타 발언, 마크다운을 쓰지 않는다. 일반 메일 본문만 쓴다.
7. 수신자 문체 프로필의 말투, 호칭, 서명 어미, 느낌표 사용, 언어를 따른다. 프로필이 없으면 격식체 존댓말."""

_BASE_INTERNAL_NOTE = (
    r"왜\s*[^.。\n]{0,20}(잡혔는지|분류됐는지|분류된건지)"
    r"|대응\s*불필요"
    r"|대응\s*필요\s*없음"
    r"|이건\s*[^.。\n]{0,20}(에\s*해당|인\s*듯|인\s*것\s*같)"
    r"|이거는\s*[^.。\n]{0,20}(에\s*해당|인\s*듯|인\s*것\s*같)"
    # Drafting markers left in brackets: (검토 필요) [검토] (확인 필요) (TODO) (TBD) (수정 필요) (초안) (draft)
    # (내부 메모). Only whole-bracket forms match, so (첨부 참조) (별첨) (참고) (월) (주) stay legal.
    r"|[(\[（]\s*(?:검토\s*필요|확인\s*필요|수정\s*필요|검토|초안|내부\s*메모|TODO|TBD|draft)"
    r"(?:\s*[-—–:：][^)\]）\n]{0,40})?\s*[)\]）]"
    r"|[(\[（]\s*note\s*[:：][^)\]）\n]{0,80}[)\]）]"
)


def internal_note_re(cfg: Config) -> re.Pattern:
    extra = "".join("|" + p for p in cfg.internal_note_extra)
    return re.compile(_BASE_INTERNAL_NOTE + extra, re.IGNORECASE)


INTERNAL_NOTE_RE = internal_note_re(Config())

_APOLOGY_RE = re.compile(r"죄송|미안|송구|사과\s*드|sorry|apolog", re.IGNORECASE)
_THANKS_RE = re.compile(r"감사|고맙|고마워|thank", re.IGNORECASE)
_MARKDOWN_RE = re.compile(
    r"\*\*[^*\n]+\*\*|^\s{0,3}#{1,6}\s+\S|`[^`\n]+`|\[[^\]\n]+\]\(https?://[^)\s]+\)", re.MULTILINE)
_ADMIN_REASONING_RE = re.compile(
    r"제\s*(판단|생각)(으로는|에는|상|엔)|저는\s*[^.\n]{0,40}(라고\s*)?(판단|생각)(하|했|됩니다)|"
    r"제가\s*[^.\n]{0,30}(판단|생각)(하여|해서|했)")
_AI_TELL_RE = [
    (re.compile(r"말씀드리겠습니다"), "AI 말투: '말씀드리겠습니다'"),
    (re.compile(r"하는\s*바입니다"), "AI 말투: '~하는 바입니다'"),
    (re.compile(r"소중한\s*(의견|시간|말씀)"), "AI 말투: '소중한 ~'"),
    (re.compile(r"i\s+hope\s+this\s+(email|message)\s+finds\s+you", re.IGNORECASE), "AI tell: 'hope this finds you well'"),
    (re.compile(r"don'?t\s+hesitate\s+to", re.IGNORECASE), "AI tell: 'don't hesitate to'"),
    (re.compile(r"\bdelve\b", re.IGNORECASE), "AI tell: 'delve'"),
]
# First-person commitment tail: a sentence that accepts the request must reuse its words, so it is not a
# summary echo. ALLOWLIST of first-person action stems (하/드리/보내/올리/보/맞추/가/뵙 + 겠습니다|겠어요;
# "감사" before 하/드리 is thanks, not an action) plus fixed forms. Anything else ending in 겠습니다 (알겠,
# 하셨겠, 좋겠, 하시겠, 힘드시겠, 모르겠, 있겠) is not a commitment and stays flagged. The tail may then carry
# punctuation, quotes, emoticons and parenthetical notes in any order.
_COMMIT_TAIL_RE = re.compile(
    r"(?:(?:(?<!감사)(?:하|드리)|보내|올리|보|맞추|가|뵙)겠(?:습니다|어요)|할게요|할게|드릴게요|예정입니다|진행합니다|처리합니다|하겠네요)"
    r"(?:[(（][^)）\n]*[)）]|[\W_])*$")
_CONNECTIVE_RE = re.compile(r"아울러|더불어|이에\s*따라")


@dataclass
class StyleContext:
    source_text: str = ""            # received mail body + subject + anything the numbers may come from
    recipient_kind: str = "person"   # person | admin


@dataclass
class Violation:
    rule: str
    message: str
    evidence: str = ""


@dataclass
class StyleReport:
    hard: list = field(default_factory=list)
    soft: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.hard

    def render(self) -> str:
        """Korean findings: [필수 수정] / [권고] rule (label): message | 근거: evidence."""
        def row(tag, v):
            s = f"[{tag}] {v.rule} ({RULE_LABELS.get(v.rule, v.rule)}): {v.message}"
            return s + (f" | 근거: {v.evidence}" if v.evidence else "")
        rows = [row("필수 수정", v) for v in self.hard] + [row("권고", v) for v in self.soft]
        return "\n".join(rows) if rows else "문체 검사: 지적 사항 없음"


# --------------------------------------------------------------------------------------------------
# helpers (pure)
# --------------------------------------------------------------------------------------------------
_JOSA_RE = re.compile(r"(에서|으로|께서|에게|은|는|이|가|을|를|에|의|도|로|와|과)$")


def _tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[가-힣A-Za-z0-9]+", text or ""):
        if re.search(r"[가-힣]", t) and len(t) > 2:
            t = _JOSA_RE.sub("", t)
        if len(t) >= 2:
            out.append(t.lower())
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?。\n]+", text or "") if s.strip()]


# One number token: a comma-grouped integer or a plain int/decimal, an optional Korean unit, an optional 원.
# Matching the whole token at once keeps the '000원' tail of a comma number from reading as a second amount.
_MONEY_RE = re.compile(
    r"(?<![\d,.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(천만|천억|백만|백억|억|만|천)?\s*(원)?"
)
_CODE_RE = re.compile(r"[A-Za-z]{0,3}\d{5,}")
_DATE_PATTERNS = [
    re.compile(r"(\d{4})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})"),
    re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일"),
    re.compile(r"(?<![\d./])(\d{1,2})\s*/\s*(\d{1,2})(?![\d/])"),
    re.compile(r"(?<![\d./])(\d{1,2})\s*\.\s*(\d{1,2})\s*\.(?!\d)"),
]
_UNIT = {"천": 1_000, "만": 10_000, "백만": 1_000_000, "천만": 10_000_000, "억": 100_000_000,
         "백억": 10_000_000_000, "천억": 100_000_000_000}


def amounts(text: str) -> set[int]:
    """Money amounts in `text` normalised to integers, whatever the notation.

    1,200,000 / 1,200,000원 / 120만원 / 1.5억원 / 3천만원 all map to one integer. A comma-grouped number
    counts with or without 원; a plain number or a unit number (만/억/천) counts only when followed by 원.
    """
    vals = set()
    for m in _MONEY_RE.finditer(text or ""):
        num, unit, won = m.group(1), m.group(2), m.group(3)
        if not ("," in num or won):
            continue
        vals.add(int(round(float(num.replace(",", "")) * _UNIT.get(unit or "", 1))))
    return vals


def dates(text: str) -> set[tuple[int, int]]:
    out = set()
    for i, rx in enumerate(_DATE_PATTERNS):
        for m in rx.finditer(text or ""):
            g = [int(x) for x in m.groups()]
            mo, d = (g[1], g[2]) if i == 0 else (g[0], g[1])
            if 1 <= mo <= 12 and 1 <= d <= 31:
                out.add((mo, d))
    return out


def codes(text: str) -> set[str]:
    return {c.lower() for c in _CODE_RE.findall(text or "") if len(re.sub(r"\D", "", c)) >= 5}


def is_admin_recipient(email: str, name: str = "", config: Config | None = None) -> bool:
    """True when the address local part or the display name looks like an administrative office."""
    cfg = config or default_config()
    local = (email or "").split("@")[0]
    local_re = re.compile("^(" + "|".join(re.escape(p) for p in cfg.admin_local_parts) + r")([._-]|\d|$)",
                          re.IGNORECASE)
    name_re = re.compile("|".join(re.escape(k) for k in cfg.admin_name_keywords))
    return bool(local_re.match(local) or (cfg.admin_name_keywords and name_re.search(name or "")))


# --------------------------------------------------------------------------------------------------
# checker
# --------------------------------------------------------------------------------------------------
def check(body: str, ctx: StyleContext | None = None, profile: "voice.VoiceProfile | None" = None, *,
          owner_edited: bool = False, config: Config | None = None) -> StyleReport:
    cfg = config or default_config()
    ctx = ctx or StyleContext()
    text = (body or "").strip()
    rep = StyleReport()
    # Closing-line rules look at the last lines of the BODY: a contact-block signature (name / lab / E-mail)
    # would otherwise push the sign-off out of the last 3 lines.
    lines = [ln.strip() for ln in voice.strip_signature(text, cfg).splitlines() if ln.strip()]

    def add(rule: str, msg: str, evidence: str = "") -> None:
        sev = SEVERITY[rule][1 if owner_edited else 0]
        (rep.hard if sev == "hard" else rep.soft).append(Violation(rule, msg, evidence[:80]))

    if not text:
        return rep

    # 1 apology
    apologies = _APOLOGY_RE.findall(text)
    if len(apologies) > cfg.apology_max:
        add("apology", f"사과가 {len(apologies)}회 (최대 {cfg.apology_max}회)")

    # 2 gratitude: closing thanks + body thanks
    closing = "\n".join(lines[-2:])
    body_part = "\n".join(lines[:-2]) if len(lines) > 2 else ""
    closing_n, body_n = len(_THANKS_RE.findall(closing)), len(_THANKS_RE.findall(body_part))
    if closing_n > cfg.thanks_closing_max or body_n > cfg.thanks_body_max:
        add("gratitude", f"감사 표현 과다 (맺음 {closing_n}회, 본문 {body_n}회; "
                         f"허용 맺음 {cfg.thanks_closing_max} + 본문 {cfg.thanks_body_max})")

    # 3 restating the received mail
    src_tokens = set(_tokens(ctx.source_text))
    if src_tokens:
        for sent in _sentences(text):
            if _COMMIT_TAIL_RE.search(sent):
                continue
            toks = set(_tokens(sent))
            if len(toks) >= cfg.echo_min_tokens and len(toks & src_tokens) / len(toks) >= cfg.echo_overlap:
                add("summary_echo", "받은 메일 내용을 되풀이하는 문장", sent)
                break

    # 4 numbers / dates / amounts must have a source
    if ctx.source_text.strip():
        src_amt, src_dates, src_codes = amounts(ctx.source_text), dates(ctx.source_text), codes(ctx.source_text)
        bad = sorted(a for a in amounts(text) if a not in src_amt)
        if bad:
            add("unsourced_number", "출처에 없는 금액", ", ".join(f"{a:,}" for a in bad))
        bad_d = sorted(d for d in dates(text) if d not in src_dates)
        if bad_d:
            add("unsourced_number", "출처에 없는 날짜", ", ".join(f"{m}/{d}" for m, d in bad_d))
        bad_c = sorted(c for c in codes(text) if c not in src_codes)
        if bad_c:
            add("unsourced_number", "출처에 없는 번호", ", ".join(bad_c))
    elif amounts(text) or dates(text):
        add("unsourced_number", "받은 메일(--source)이 없는데 금액/날짜가 있음")

    # 5 administrator: no explanation of my own judgement
    if ctx.recipient_kind == "admin":
        m = _ADMIN_REASONING_RE.search(text)
        if m:
            add("admin_reasoning", "행정 수신자에게 내 판단 근거를 설명", m.group(0))

    # 6 internal note / markdown
    m = internal_note_re(cfg).search(text)
    if m:
        add("internal_note", "내부 메모/메타 발언 패턴", m.group(0))
    m = _MARKDOWN_RE.search(text)
    if m:
        add("markdown", "마크다운 문법", m.group(0))

    # 7 recipient voice profile
    if profile is not None:
        f = voice.features(text, cfg)
        total = f.casual_n + f.formal_n
        casual_flag = f.casual_n >= 2 or (f.casual_n >= 1 and f.casual_n / total >= 0.3)
        if profile.register == "존댓말" and casual_flag:
            add("profile_register", "수신자는 존댓말인데 초안에 반말 문장이 있음")
        elif profile.register == "반말" and f.casual_n == 0 and f.formal_n >= 2:
            add("profile_register", "수신자 프로필은 반말인데 초안이 존댓말")
        if profile.language == "en" and f.language == "ko":
            add("profile_language", "수신자 프로필은 영어인데 초안이 한국어")
        elif profile.language == "ko" and f.language == "en":
            add("profile_language", "수신자 프로필은 한국어인데 초안이 영어")
        if profile.source == "sent":
            if profile.honorific and profile.honorific != "님" and profile.honorific not in " ".join(lines[:2]):
                add("profile_honorific", f"호칭 '{profile.honorific}' 누락")
            if profile.signoff in cfg.signoff_forms and not any(profile.signoff in ln for ln in lines[-3:]):
                add("profile_signoff", f"서명 어미 '{profile.signoff}' 누락")
            if profile.exclaim_closing is False and any("!" in ln for ln in lines[-2:]):
                add("profile_exclaim", "이 수신자에게는 맺음 느낌표를 쓰지 않음")

    # 8 AI tells (soft)
    for rx, label in _AI_TELL_RE:
        if rx.search(text):
            add("ai_tell", label)
    if len(_CONNECTIVE_RE.findall(text)) >= 2:
        add("ai_tell", "AI 말투: 접속어(아울러/더불어/이에 따라) 반복")
    return rep
