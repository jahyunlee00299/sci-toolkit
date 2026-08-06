#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""메일 커넥터 — IMAP/SMTP 표준 라이브러리만 사용하는 sci-toolkit 메일 연동 스크립트.

⭐ 핵심 안전 원칙 (DRAFT-FIRST, AGENTS.md §9) ⭐
    이 스크립트는 메일을 작성하면 항상 IMAP 임시보관함(Drafts)에만 저장합니다.
    자동으로 발송하는 경로는 존재하지 않습니다.

    - `draft` / `reply` 서브커맨드는 메일을 만들어 Drafts 폴더에 APPEND 할 뿐,
      SMTP 발송을 절대 호출하지 않습니다.
    - 실제 발송이 가능한 유일한 경로는 `send` 서브커맨드이며, 다음 두 가지를
      *모두* 충족해야만 발송 로직에 도달합니다.
        1) 커맨드라인에 `--send` 플래그를 명시적으로 준다.
        2) 대화형 프롬프트에서 정확히 대문자 `SEND` 를 타이핑해 확인한다.
      표준입력이 tty가 아닌 비대화형 환경(cron, 파이프, 자동화 파이프라인 등)에서는
      `send` 자체를 거부합니다 — 사람의 확인 없이는 어떤 경로로도 발송이 불가능합니다.

    "연결은 쉽게, 발송은 신중하게." (docs/05_외부서비스_연동.md)

사용 예:
    python mail_connector.py list --account work --n 10
    python mail_connector.py read --account work --uid 12345
    python mail_connector.py draft --account work --to a@b.com --subject "제목" --body "내용"
    python mail_connector.py reply --account work --uid 12345 --body "회신 내용"
    python mail_connector.py send --account work --to a@b.com --subject "제목" --body "내용" --send

자격증명은 config/credentials.json (config/credentials.example.json 참고, mail.accounts.<account>)
또는 그 안에서 가리키는 환경변수(ENV:NAME)에서 읽습니다. 비밀번호는 화면에 출력되지 않습니다.
"""
from __future__ import annotations

# Windows 기본 콘솔은 cp949 라서 한글/기호 출력에서 죽는다. UTF-8로 맞춘다.
# reconfigure 를 쓴다: TextIOWrapper 로 감싸면 원본 스트림을 소유하게 되어,
# 이 모듈이 import 된 뒤 래퍼가 GC 될 때 호출자의 stdout 까지 닫는다(실측).
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

import argparse
import email
import imaplib
import smtplib
import ssl
import sys
from datetime import datetime
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime

import _credentials as cred

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass  # 일부 환경(파이프 리다이렉트 등)에서는 reconfigure 불가 — 무시하고 진행


# --------------------------------------------------------------------------
# 자격증명 헬퍼
# --------------------------------------------------------------------------

def _account_field(account: str, field: str, required: bool = True):
    """mail.accounts.<account>.<field> 값을 읽는다. 필수인데 없으면 안내 후 종료."""
    if required:
        return cred.require("mail", "accounts", account, field)
    return cred.get("mail", "accounts", account, field)


def _load_account(account: str) -> dict:
    return {
        "imap_host": _account_field(account, "imap_host"),
        "imap_port": int(_account_field(account, "imap_port")),
        "smtp_host": _account_field(account, "smtp_host"),
        "smtp_port": int(_account_field(account, "smtp_port")),
        "user": _account_field(account, "user"),
        "password": _account_field(account, "password"),
    }


# --------------------------------------------------------------------------
# IMAP 연결/유틸
# --------------------------------------------------------------------------

def _imap_connect(acc: dict) -> imaplib.IMAP4_SSL:
    try:
        ctx = ssl.create_default_context()
        conn = imaplib.IMAP4_SSL(acc["imap_host"], acc["imap_port"], ssl_context=ctx)
        conn.login(acc["user"], acc["password"])
        return conn
    except imaplib.IMAP4.error as e:
        sys.exit(
            "[오류] IMAP 로그인에 실패했습니다.\n"
            f"  세부사항: {e}\n"
            "  - 비밀번호가 일반 로그인 비밀번호라면, 앱 비밀번호(App Password)를 발급받아 사용하세요"
            "(Gmail 등 2단계 인증 계정은 필수).\n"
            "  - config/credentials.json 의 user/password, 환경변수 설정을 다시 확인하세요."
        )
    except (OSError, ssl.SSLError) as e:
        sys.exit(
            "[오류] IMAP 서버에 연결할 수 없습니다.\n"
            f"  세부사항: {e}\n"
            f"  - host/port를 확인하세요 (현재: {acc.get('imap_host')}:{acc.get('imap_port')}).\n"
            "  - 방화벽/네트워크 상태, 993 포트(SSL) 접근 가능 여부를 확인하세요."
        )


def _decode_mime_words(s: str | None) -> str:
    if not s:
        return "(없음)"
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s


def _find_drafts_mailbox(conn: imaplib.IMAP4_SSL) -> str:
    """Drafts 메일함 이름을 자동 탐지한다. 흔한 이름들을 우선 시도하고,
    목록에서 'draft'가 포함된 첫 메일함으로 폴백, 그래도 없으면 'Drafts'."""
    common_names = ["Drafts", "[Gmail]/Drafts", "INBOX.Drafts"]

    typ, data = conn.list()
    mailbox_names: list[str] = []
    if typ == "OK" and data:
        for raw in data:
            if raw is None:
                continue
            try:
                line = raw.decode("utf-8", errors="replace")
            except AttributeError:
                line = str(raw)
            # 형식 예: (\HasNoChildren \Drafts) "/" "[Gmail]/Drafts"
            # 마지막 따옴표로 감싼 토큰이 실제 메일함 이름인 경우가 대부분
            if '"' in line:
                parts = line.rsplit('"', 2)
                if len(parts) >= 2:
                    mailbox_names.append(parts[-2])
            else:
                mailbox_names.append(line.strip().split(" ")[-1])
            # \Drafts 특수 속성 플래그가 붙어 있으면 최우선으로 채택
            if "\\Drafts" in line:
                name = mailbox_names[-1] if mailbox_names else None
                if name:
                    return name

    for name in common_names:
        if name in mailbox_names:
            return name

    for name in mailbox_names:
        if "draft" in name.lower():
            return name

    return "Drafts"


def _fetch_message(conn: imaplib.IMAP4_SSL, uid: str):
    typ, data = conn.uid("fetch", uid, "(RFC822)")
    if typ != "OK" or not data or data[0] is None:
        sys.exit(f"[오류] UID {uid} 메시지를 찾을 수 없습니다.")
    raw = data[0][1]
    return email.message_from_bytes(raw)


def _plain_text_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if ctype == "text/plain" and "attachment" not in disp:
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    return "(본문 디코딩 실패)"
        return "(텍스트 본문 없음 — 첨부/HTML만 존재할 수 있음)"
    else:
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            return "(본문 디코딩 실패)"


# --------------------------------------------------------------------------
# 서브커맨드: list (읽기 전용)
# --------------------------------------------------------------------------

def cmd_list(args):
    acc = _load_account(args.account)
    conn = _imap_connect(acc)
    try:
        typ, _ = conn.select(args.mailbox, readonly=True)
        if typ != "OK":
            sys.exit(f"[오류] 메일함 '{args.mailbox}'을(를) 열 수 없습니다.")

        typ, data = conn.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            print("(메시지가 없습니다.)")
            return
        uids = data[0].split()
        recent = uids[-args.n:][::-1]  # 최신순

        print(f"[{args.account}] {args.mailbox} 최근 {len(recent)}건")
        print("-" * 70)
        for uid in recent:
            typ, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                continue
            header_bytes = msg_data[0][1]
            msg = email.message_from_bytes(header_bytes)
            from_ = _decode_mime_words(msg.get("From"))
            subject = _decode_mime_words(msg.get("Subject"))
            date_ = msg.get("Date") or "(날짜 없음)"
            print(f"UID {uid.decode()}\n  From   : {from_}\n  Subject: {subject}\n  Date   : {date_}\n")
    except imaplib.IMAP4.error as e:
        sys.exit(f"[오류] IMAP 조회 중 오류가 발생했습니다: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()


# --------------------------------------------------------------------------
# 서브커맨드: read (읽기 전용)
# --------------------------------------------------------------------------

def cmd_read(args):
    acc = _load_account(args.account)
    conn = _imap_connect(acc)
    try:
        typ, _ = conn.select(args.mailbox, readonly=True)
        if typ != "OK":
            sys.exit(f"[오류] 메일함 '{args.mailbox}'을(를) 열 수 없습니다.")

        msg = _fetch_message(conn, args.uid)
        print("-" * 70)
        print(f"From    : {_decode_mime_words(msg.get('From'))}")
        print(f"To      : {_decode_mime_words(msg.get('To'))}")
        print(f"Subject : {_decode_mime_words(msg.get('Subject'))}")
        print(f"Date    : {msg.get('Date') or '(날짜 없음)'}")
        print(f"Message-ID: {msg.get('Message-ID') or '(없음)'}")
        print("-" * 70)
        print(_plain_text_body(msg))
    except imaplib.IMAP4.error as e:
        sys.exit(f"[오류] IMAP 조회 중 오류가 발생했습니다: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()


# --------------------------------------------------------------------------
# Drafts 저장 공통 로직
# --------------------------------------------------------------------------

def _append_to_drafts(conn: imaplib.IMAP4_SSL, acc: dict, msg: EmailMessage):
    drafts_name = _find_drafts_mailbox(conn)
    try:
        typ, resp = conn.append(
            drafts_name,
            r"\Draft",
            imaplib.Time2Internaldate(datetime.now().timetuple()),
            msg.as_bytes(),
        )
        if typ != "OK":
            sys.exit(f"[오류] Drafts 저장에 실패했습니다 (메일함: {drafts_name}): {resp}")
    except imaplib.IMAP4.error as e:
        sys.exit(
            f"[오류] Drafts 폴더('{drafts_name}')에 저장하는 중 오류가 발생했습니다: {e}\n"
            "  서버가 다른 이름의 Drafts 메일함을 쓸 수 있습니다 — 서버 메일함 목록을 확인하세요."
        )
    print(f"[{acc['user']}] '{drafts_name}' 폴더에 저장 완료.")
    print("초안(Drafts)에 저장했습니다. 발송은 메일 앱에서 직접 하세요.")


def _read_body_arg(args) -> str:
    if args.body_file:
        try:
            with open(args.body_file, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            sys.exit(f"[오류] --body-file을 읽을 수 없습니다: {e}")
    if args.body is not None:
        return args.body
    sys.exit("[오류] --body 또는 --body-file 중 하나는 반드시 지정해야 합니다.")


def _build_message(acc: dict, to: str, subject: str, body: str, cc: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = acc["user"]
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(body)
    return msg


# --------------------------------------------------------------------------
# 서브커맨드: draft (Drafts 저장만, 발송 없음)
# --------------------------------------------------------------------------

def cmd_draft(args):
    acc = _load_account(args.account)
    body = _read_body_arg(args)
    msg = _build_message(acc, args.to, args.subject, body, cc=args.cc)

    conn = _imap_connect(acc)
    try:
        _append_to_drafts(conn, acc, msg)
    finally:
        conn.logout()


# --------------------------------------------------------------------------
# 서브커맨드: reply (원본 조회 → 회신 헤더 구성 → Drafts 저장만, 발송 없음)
# --------------------------------------------------------------------------

def cmd_reply(args):
    acc = _load_account(args.account)
    body = _read_body_arg(args)

    conn = _imap_connect(acc)
    try:
        typ, _ = conn.select(args.mailbox, readonly=True)
        if typ != "OK":
            sys.exit(f"[오류] 메일함 '{args.mailbox}'을(를) 열 수 없습니다.")

        original = _fetch_message(conn, args.uid)

        orig_subject = _decode_mime_words(original.get("Subject")) or "(제목 없음)"
        subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

        orig_from = original.get("From") or ""
        to_addr = args.to or orig_from
        if not to_addr:
            sys.exit("[오류] 회신 대상 주소를 확인할 수 없습니다. --to 를 명시하세요.")

        orig_msg_id = original.get("Message-ID") or ""
        orig_refs = original.get("References") or ""
        references = (orig_refs + " " + orig_msg_id).strip() if orig_msg_id else orig_refs

        orig_date = original.get("Date") or ""
        orig_body = _plain_text_body(original)
        quoted = "\n".join(f"> {line}" for line in orig_body.splitlines())
        full_body = f"{body}\n\n--- 원본 메시지 ({_decode_mime_words(orig_from)}, {orig_date}) ---\n{quoted}"

        msg = _build_message(acc, to_addr, subject, full_body, cc=args.cc)
        if orig_msg_id:
            msg["In-Reply-To"] = orig_msg_id
        if references:
            msg["References"] = references

        _append_to_drafts(conn, acc, msg)
    finally:
        conn.logout()


# --------------------------------------------------------------------------
# 서브커맨드: send (유일한 실제 발송 경로 — --send 플래그 + 타이핑 확인 필수)
# --------------------------------------------------------------------------

def cmd_send(args):
    if not args.send:
        sys.exit(
            "[거부] --send 플래그 없이는 발송 로직에 도달할 수 없습니다.\n"
            "  메일을 임시보관함에만 저장하려면 `draft` 서브커맨드를 사용하세요:\n"
            "    python mail_connector.py draft --account ... --to ... --subject ... --body ..."
        )

    if not sys.stdin.isatty():
        sys.exit(
            "[거부] 비대화형 환경(파이프/스크립트/자동화)에서는 실제 발송을 거부합니다.\n"
            "  발송 확인은 사람이 터미널에서 직접 입력해야 합니다.\n"
            "  대화형 터미널에서 `python mail_connector.py send ... --send` 를 다시 실행하세요."
        )

    acc = _load_account(args.account)
    body = _read_body_arg(args)
    msg = _build_message(acc, args.to, args.subject, body, cc=args.cc)

    print("=" * 70)
    print("다음 메일을 실제로 발송합니다 — 되돌릴 수 없습니다.")
    print("=" * 70)
    print(f"From   : {acc['user']}")
    print(f"To     : {args.to}")
    if args.cc:
        print(f"Cc     : {args.cc}")
    print(f"Subject: {args.subject}")
    print("-" * 70)
    print(body)
    print("=" * 70)

    confirm = input("정말로 발송하려면 정확히 SEND 라고 입력하세요: ")
    if confirm != "SEND":
        sys.exit("발송 취소됨")

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(acc["smtp_host"], acc["smtp_port"]) as smtp:
            smtp.starttls(context=ctx)
            smtp.login(acc["user"], acc["password"])
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        sys.exit(
            "[오류] SMTP 인증에 실패했습니다.\n"
            f"  세부사항: {e}\n"
            "  - 앱 비밀번호(App Password)가 필요한 계정인지 확인하세요(일반 로그인 비밀번호 아님).\n"
            "  - config/credentials.json 의 user/password, 환경변수 설정을 다시 확인하세요."
        )
    except (OSError, smtplib.SMTPException, ssl.SSLError) as e:
        sys.exit(
            "[오류] SMTP 서버 연결/발송 중 오류가 발생했습니다.\n"
            f"  세부사항: {e}\n"
            f"  - host/port를 확인하세요 (현재: {acc.get('smtp_host')}:{acc.get('smtp_port')}).\n"
            "  - 587 포트(STARTTLS) 접근 가능 여부, 방화벽/네트워크 상태를 확인하세요."
        )

    print("발송 완료.")


# --------------------------------------------------------------------------
# argparse
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mail_connector.py",
        description=(
            "sci-toolkit 메일 커넥터 — DRAFT-FIRST 원칙: draft/reply는 항상 IMAP Drafts에만 저장하고 "
            "절대 자동 발송하지 않습니다. 실제 발송은 `send --send` + 대화형 'SEND' 타이핑 확인이 "
            "모두 있어야만 가능합니다."
        ),
        epilog=(
            "예시:\n"
            "  mail_connector.py list --account work\n"
            "  mail_connector.py read --account work --uid 12345\n"
            "  mail_connector.py draft --account work --to a@b.com --subject 제목 --body 내용\n"
            "  mail_connector.py reply --account work --uid 12345 --body 회신내용\n"
            "  mail_connector.py send --account work --to a@b.com --subject 제목 --body 내용 --send\n"
            "\n"
            "⭐ draft/reply = 항상 안전(Drafts 저장만). send는 --send 플래그와 'SEND' 타이핑 확인 "
            "둘 다 있어야 실제로 나갑니다."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="최근 메일 목록 조회 (읽기 전용)")
    p_list.add_argument("--account", choices=["work", "personal"], default="work")
    p_list.add_argument("--n", type=int, default=10, help="조회할 메시지 개수 (기본 10)")
    p_list.add_argument("--mailbox", default="INBOX")
    p_list.set_defaults(func=cmd_list)

    p_read = sub.add_parser("read", help="UID로 메일 1건 조회 (읽기 전용)")
    p_read.add_argument("--account", choices=["work", "personal"], default="work")
    p_read.add_argument("--uid", required=True, help="조회할 메시지 UID")
    p_read.add_argument("--mailbox", default="INBOX")
    p_read.set_defaults(func=cmd_read)

    p_draft = sub.add_parser("draft", help="새 메일 작성 → Drafts 저장만 (발송 안 함)")
    p_draft.add_argument("--account", choices=["work", "personal"], default="work")
    p_draft.add_argument("--to", required=True)
    p_draft.add_argument("--cc")
    p_draft.add_argument("--subject", required=True)
    p_draft.add_argument("--body")
    p_draft.add_argument("--body-file")
    p_draft.set_defaults(func=cmd_draft)

    p_reply = sub.add_parser("reply", help="원본 메일에 대한 회신 작성 → Drafts 저장만 (발송 안 함)")
    p_reply.add_argument("--account", choices=["work", "personal"], default="work")
    p_reply.add_argument("--uid", required=True, help="회신 대상 원본 메시지 UID")
    p_reply.add_argument("--mailbox", default="INBOX")
    p_reply.add_argument("--to", help="지정하지 않으면 원본 발신자에게 회신")
    p_reply.add_argument("--cc")
    p_reply.add_argument("--body")
    p_reply.add_argument("--body-file")
    p_reply.set_defaults(func=cmd_reply)

    p_send = sub.add_parser(
        "send",
        help="[위험] 실제 SMTP 발송 — --send 플래그 + 대화형 'SEND' 타이핑 확인 필수",
    )
    p_send.add_argument("--account", choices=["work", "personal"], default="work")
    p_send.add_argument("--to", required=True)
    p_send.add_argument("--cc")
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body")
    p_send.add_argument("--body-file")
    p_send.add_argument(
        "--send",
        action="store_true",
        help="이 플래그 없이는 발송 거부됨(그래도 대화형 SEND 확인이 추가로 필요)",
    )
    p_send.set_defaults(func=cmd_send)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        print(
            "\n⭐ 기본 원칙: 이 스크립트는 draft-first 입니다. "
            "메일은 항상 Drafts에만 저장되고, 자동 발송은 절대 하지 않습니다.\n"
            "실제 발송이 필요하면 `send` 서브커맨드에 --send 플래그를 주고, "
            "대화형 프롬프트에서 'SEND'를 직접 입력해야 합니다."
        )
        return

    args.func(args)


if __name__ == "__main__":
    main()
