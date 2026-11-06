"""Writing-voice features and recipient profiles, rule based (no LLM, no network).

Trimmed from the approval-inbox mail_voice module: only the pure parts remain.
  features(text)                  feature vector of one message body
  extract_profile(addr, samples)  profile from a few of your own sent mails
  default_profile(addr, name)     formal profile used when there is no evidence
Reading a mailbox (IMAP) is deliberately not part of this tool: save sent mails
as text and pass them in as SentSample objects.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field

from .config import Config, default_config

SAMPLES_PER_ADDRESS = 5


@dataclass
class SentSample:
    uid: str
    date: str          # YYYY-MM-DD
    subject: str
    text: str          # own text


@dataclass
class VoiceFeatures:
    formal_n: int = 0
    casual_n: int = 0
    honorific: str | None = None
    self_intro: str = "none"            # none | name | lab | univ
    intro_line: str = ""
    exclaim_closing: bool = False
    signoff: str = "none"               # one of config.signoff_forms | none
    english_signature: bool = False
    language: str = "ko"                # ko | en
    greeting_line: str = ""
    closing_line: str = ""


@dataclass
class OwnerVoice:
    signoff: str = "none"
    intro_line: str = ""
    closing_line: str = ""
    n_samples: int = 0


@dataclass
class VoiceProfile:
    address: str
    source: str = "default"             # sent | default
    n_samples: int = 0
    register: str = "존댓말"             # 존댓말 | 반말
    honorific: str | None = None
    self_intro: str = "none"
    intro_line: str = ""
    exclaim_closing: bool | None = None
    signoff: str = "none"
    english_signature: bool = False
    language: str = "ko"
    greeting_line: str = ""
    closing_line: str = ""
    evidence: list = field(default_factory=list)
    learned_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VoiceProfile":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


# --------------------------------------------------------------------------------------------------
# text features (pure)
# --------------------------------------------------------------------------------------------------
_QUOTE_CUT_RE = re.compile(
    r"^\s*(-{3,}\s*Original\s+Message\s*-{3,}|-{3,}\s*원본\s*메시지\s*-{3,}|보낸\s*사람\s*:|From\s*:|"
    r"On\s.{5,80}\swrote\s*:|\d{4}[.-]\d{1,2}[.-]\d{1,2}.{0,40}(작성|wrote)|>.*)$",
    re.IGNORECASE | re.MULTILINE)
_FORMAL_END_RE = re.compile(
    r"(습니다|ㅂ니다|입니다|합니다|드립니다|됩니다|십시오|십니까|습니까|니다|니까|세요|셔요|해요|에요|예요|이에요|"
    r"어요|아요|지요|죠|네요|군요|드려요|겠어요|ㄹ게요|할게요|까요|래요|거예요|께요|바랍니다)$")
_CASUAL_END_RE = re.compile(r"(다|야|어|아|해|지|줘|자|네|니|냐|까|래|게|걸|데|군|라|구나|거든|잖아)$")
_SENT_SPLIT_RE = re.compile(r"[.!?。\n]+")
_EN_SIGNATURE_RE = re.compile(r"(best\s+regards|kind\s+regards|sincerely|regards|best|thanks|thank\s+you)\s*,?\s*$",
                              re.IGNORECASE)
_INTRO_RE = re.compile(r"입니다[.!]?$")
_UNIV_RE = re.compile(r"대학교|대학원|대학|university", re.IGNORECASE)
_LAB_RE = re.compile(r"연구실|실험실|랩|\blab\b|공학실|연구센터|연구소|팀", re.IGNORECASE)
_CONTACT_LINE_RE = re.compile(
    r"^\s*(e-?mail|mobile|tel|fax|phone|cell|전화|휴대폰|이메일)\s*[:：]"
    r"|\+\d{1,3}[-\s]?\d{2,4}[-\s]?\d{3,4}[-\s]?\d{4}"
    r"|^[^\s@]+@[^\s@]+\.[a-z]{2,}\s*$",
    re.IGNORECASE)
_SIG_NAME_LINE_RE = re.compile(r"laborator|department|universit|institute|korea|\blab\b|연구실|학과|대학교|연구소",
                               re.IGNORECASE)


def _alt(words) -> str:
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


def _honorific_re(cfg: Config) -> re.Pattern:
    return re.compile("(" + _alt(cfg.honorifics) + ")")


def _signoff_re(cfg: Config) -> re.Pattern:
    return re.compile("(" + _alt(cfg.signoff_forms) + ")")


def strip_quote(text: str) -> str:
    """Cut the quoted tail (reply/forward headers, '>' lines) and trim."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    m = _QUOTE_CUT_RE.search(text)
    if m:
        text = text[: m.start()]
    return text.strip()


def strip_signature(text: str, config: Config | None = None) -> str:
    """Cut a trailing contact-block signature (name / lab / university / e-mail / phone lines).

    A sign-off such as "OOO 올림" is a sentence-like closing and stays.
    """
    cfg = config or default_config()
    signoff_re = _signoff_re(cfg)
    lines = (text or "").splitlines()
    first = next((i for i, ln in enumerate(lines) if _CONTACT_LINE_RE.search(ln)), None)
    if first is None:
        return (text or "").strip()
    cut = first
    while cut > 0:
        prev = lines[cut - 1].strip()
        if not prev:
            cut -= 1
            continue
        sentence_like = bool(re.search(r"[.!?다요]$", prev)) or bool(signoff_re.search(prev))
        affiliation = bool(_SIG_NAME_LINE_RE.search(prev)) and len(prev) < 120
        name_only = len(prev) < 60 and len(prev.split()) <= 3
        if not sentence_like and (affiliation or name_only):
            cut -= 1
            continue
        break
    return "\n".join(lines[:cut]).strip()


def _hangul_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 1.0
    return sum(1 for c in letters if "가" <= c <= "힣") / len(letters)


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def _end_token(sentence: str) -> str:
    s = sentence.strip().rstrip("~^ㅋㅎ)]\"' ").strip()
    return re.sub(r"[ㅋㅎㅠㅜ]+$", "", s).strip()


def _count_endings(text: str) -> tuple[int, int]:
    formal = casual = 0
    for sent in _SENT_SPLIT_RE.split(text):
        tok = _end_token(sent)
        if len(tok) < 3 or _hangul_ratio(tok) < 0.5:
            continue
        if _FORMAL_END_RE.search(tok):
            formal += 1
        elif _CASUAL_END_RE.search(tok):
            casual += 1
    return formal, casual


def features(text: str, config: Config | None = None) -> VoiceFeatures:
    """Feature vector of one message body (the quoted tail and contact signature are cut here too)."""
    cfg = config or default_config()
    honorific_re, signoff_re = _honorific_re(cfg), _signoff_re(cfg)
    own = strip_signature(strip_quote(text), cfg)
    lines = _lines(own)
    f = VoiceFeatures()
    if not lines:
        return f
    f.language = "en" if _hangul_ratio(own) < 0.2 else "ko"
    f.greeting_line = lines[0]
    f.formal_n, f.casual_n = _count_endings(own)
    for ln in lines[:2]:
        hits = honorific_re.findall(ln)
        if hits:
            f.honorific = max(hits, key=len)
            break
    for ln in lines[:3]:
        if _INTRO_RE.search(ln) and (("저는" in ln) or ln.startswith("안녕하세요") or _UNIV_RE.search(ln) or _LAB_RE.search(ln)):
            f.intro_line = ln
            f.self_intro = "univ" if _UNIV_RE.search(ln) else ("lab" if _LAB_RE.search(ln) else "name")
            break
    for ln in reversed(lines[-3:]):
        m = signoff_re.search(ln)
        if m:
            f.signoff = m.group(1)
            break
    f.english_signature = any(_EN_SIGNATURE_RE.search(ln) for ln in lines[-4:])
    f.exclaim_closing = any("!" in ln for ln in lines[-2:])
    for ln in reversed(lines):
        if signoff_re.search(ln) and len(ln) <= 20:
            continue
        f.closing_line = ln if len(ln) <= 60 else ""
        break
    return f


def sample_register(f: VoiceFeatures) -> str:
    """formal | casual | unknown for one sample. Mixed evidence counts as formal (asymmetric safety)."""
    if f.formal_n == 0 and f.casual_n == 0:
        return "unknown"
    if f.casual_n > 0 and f.formal_n == 0:
        return "casual"
    return "formal"


# --------------------------------------------------------------------------------------------------
# profile extraction (pure)
# --------------------------------------------------------------------------------------------------
def _vote(values: list):
    """Majority of non-None values; a tie goes to the newest (values are newest first)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    counts = Counter(vals)
    top = max(counts.values())
    for v in vals:
        if counts[v] == top:
            return v


def _sorted_newest(samples: list[SentSample]) -> list[SentSample]:
    return sorted(samples, key=lambda s: (s.date, str(s.uid).zfill(12)), reverse=True)


def default_profile(address: str, display_name: str = "", owner: OwnerVoice | None = None) -> VoiceProfile:
    """Formal default used when there is no (or too little) evidence."""
    name = (display_name or "").strip()
    owner = owner or OwnerVoice()
    return VoiceProfile(
        address=(address or "").lower(), source="default", n_samples=0, register="존댓말",
        honorific=None, self_intro="none", intro_line="", exclaim_closing=None,
        signoff=owner.signoff or "none", english_signature=False, language="ko",
        greeting_line=(f"안녕하세요, {name}님." if name else "안녕하세요."),
        closing_line=owner.closing_line or "감사합니다.", evidence=[], learned_at="")


def extract_profile(address: str, samples: list[SentSample], display_name: str = "",
                    owner: OwnerVoice | None = None, config: Config | None = None) -> VoiceProfile:
    """Pure rule extraction from the 5 newest samples. No samples -> the default profile.

    반말 only with >= 2 casual samples and 0 formal samples; everything else is 존댓말.
    """
    ordered = _sorted_newest(samples)[:SAMPLES_PER_ADDRESS]
    if not ordered:
        return default_profile(address, display_name, owner)
    feats = [features(s.text, config) for s in ordered]
    kinds = [sample_register(f) for f in feats]
    n_casual, n_formal = kinds.count("casual"), kinds.count("formal")
    register = "반말" if (n_casual >= 2 and n_formal == 0) else "존댓말"
    intro_class = _vote([f.self_intro for f in feats]) or "none"
    intro_line = next((f.intro_line for f in feats if f.self_intro == intro_class and f.intro_line), "")
    exclaims = [f.exclaim_closing for f in feats]
    return VoiceProfile(
        address=(address or "").lower(), source="sent", n_samples=len(ordered), register=register,
        honorific=_vote([f.honorific for f in feats]),
        self_intro=intro_class, intro_line=intro_line,
        exclaim_closing=Counter(exclaims).get(True, 0) * 2 > len(exclaims),
        signoff=_vote([f.signoff for f in feats]) or "none",
        english_signature=Counter([f.english_signature for f in feats]).get(True, 0) * 2 > len(feats),
        language=_vote([f.language for f in feats]) or "ko",
        greeting_line=feats[0].greeting_line, closing_line=feats[0].closing_line,
        evidence=[[s.date, s.subject[:60]] for s in ordered], learned_at=ordered[0].date)
