#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mail connector — sci-toolkit mail integration script using only the IMAP/SMTP standard library.

⭐ Core safety principle (DRAFT-FIRST, AGENTS.md §9) ⭐
    This script only ever saves a composed mail to the IMAP Drafts folder.
    There is no path that sends automatically.

    - The `draft` / `reply` subcommands only build a message and APPEND it
      to the Drafts folder — they never call SMTP send.
    - The only path that can actually send is the `send` subcommand, and it
      only reaches the send logic when *both* of the following hold:
        1) the `--send` flag is given explicitly on the command line.
        2) the interactive prompt is confirmed by typing the exact uppercase
           word `SEND`.
      In a non-interactive environment where stdin isn't a tty (cron, a
      pipe, an automation pipeline, etc.), `send` itself is refused — no
      path can send without a human confirming it.

    "Connecting is easy; sending is deliberate." (docs/05_external_service_integration.md)

Usage examples:
    python mail_connector.py list --account work --n 10
    python mail_connector.py read --account work --uid 12345
    python mail_connector.py draft --account work --to a@b.com --subject "Subject" --body "Body"
    python mail_connector.py reply --account work --uid 12345 --body "Reply body"
    python mail_connector.py send --account work --to a@b.com --subject "Subject" --body "Body" --send

Credentials are read from config/credentials.json (see
config/credentials.example.json, mail.accounts.<account>) or the
environment variable it points to (ENV:NAME). Passwords are never printed.
"""
from __future__ import annotations

# Windows' default console is cp949 and dies on Korean/symbol output. Force UTF-8.
# Use reconfigure: wrapping in TextIOWrapper would take ownership of the
# underlying stream, so once this module is imported and the wrapper gets
# GC'd, it closes the caller's stdout too (measured).
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
    pass  # reconfigure isn't possible in some environments (e.g. piped redirect) — ignore and proceed


# --------------------------------------------------------------------------
# Credential helpers
# --------------------------------------------------------------------------

def _account_field(account: str, field: str, required: bool = True):
    """Read mail.accounts.<account>.<field>. If required and missing, print guidance and exit."""
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
# IMAP connection / utilities
# --------------------------------------------------------------------------

def _imap_connect(acc: dict) -> imaplib.IMAP4_SSL:
    try:
        ctx = ssl.create_default_context()
        conn = imaplib.IMAP4_SSL(acc["imap_host"], acc["imap_port"], ssl_context=ctx)
        conn.login(acc["user"], acc["password"])
        return conn
    except imaplib.IMAP4.error as e:
        sys.exit(
            "[Error] IMAP login failed.\n"
            f"  Details: {e}\n"
            "  - If your password is your regular login password, issue and use an App Password instead"
            " (required for accounts with 2-step verification, e.g. Gmail).\n"
            "  - Double-check the user/password in config/credentials.json or your environment variables."
        )
    except (OSError, ssl.SSLError) as e:
        sys.exit(
            "[Error] Could not connect to the IMAP server.\n"
            f"  Details: {e}\n"
            f"  - Check host/port (currently: {acc.get('imap_host')}:{acc.get('imap_port')}).\n"
            "  - Check your firewall/network status and whether port 993 (SSL) is reachable."
        )


def _decode_mime_words(s: str | None) -> str:
    if not s:
        return "(none)"
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s


def _find_drafts_mailbox(conn: imaplib.IMAP4_SSL) -> str:
    """Auto-detect the Drafts mailbox name. Tries common names first, falls
    back to the first mailbox whose name contains 'draft', and finally to
    'Drafts' if nothing matches."""
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
            # Example format: (\HasNoChildren \Drafts) "/" "[Gmail]/Drafts"
            # The last quoted token is usually the actual mailbox name
            if '"' in line:
                parts = line.rsplit('"', 2)
                if len(parts) >= 2:
                    mailbox_names.append(parts[-2])
            else:
                mailbox_names.append(line.strip().split(" ")[-1])
            # If the \Drafts special-use flag is present, take it as the top priority
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
        sys.exit(f"[Error] Could not find message UID {uid}.")
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
                    return "(failed to decode body)"
        return "(no plain-text body — may contain only an attachment/HTML)"
    else:
        try:
            return msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            return "(failed to decode body)"


# --------------------------------------------------------------------------
# Subcommand: list (read-only)
# --------------------------------------------------------------------------

def cmd_list(args):
    acc = _load_account(args.account)
    conn = _imap_connect(acc)
    try:
        typ, _ = conn.select(args.mailbox, readonly=True)
        if typ != "OK":
            sys.exit(f"[Error] Could not open mailbox '{args.mailbox}'.")

        typ, data = conn.search(None, "ALL")
        if typ != "OK" or not data or not data[0]:
            print("(No messages.)")
            return
        uids = data[0].split()
        recent = uids[-args.n:][::-1]  # newest first

        print(f"[{args.account}] {args.mailbox} — {len(recent)} most recent")
        print("-" * 70)
        for uid in recent:
            typ, msg_data = conn.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                continue
            header_bytes = msg_data[0][1]
            msg = email.message_from_bytes(header_bytes)
            from_ = _decode_mime_words(msg.get("From"))
            subject = _decode_mime_words(msg.get("Subject"))
            date_ = msg.get("Date") or "(no date)"
            print(f"UID {uid.decode()}\n  From   : {from_}\n  Subject: {subject}\n  Date   : {date_}\n")
    except imaplib.IMAP4.error as e:
        sys.exit(f"[Error] IMAP query failed: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()


# --------------------------------------------------------------------------
# Subcommand: read (read-only)
# --------------------------------------------------------------------------

def cmd_read(args):
    acc = _load_account(args.account)
    conn = _imap_connect(acc)
    try:
        typ, _ = conn.select(args.mailbox, readonly=True)
        if typ != "OK":
            sys.exit(f"[Error] Could not open mailbox '{args.mailbox}'.")

        msg = _fetch_message(conn, args.uid)
        print("-" * 70)
        print(f"From    : {_decode_mime_words(msg.get('From'))}")
        print(f"To      : {_decode_mime_words(msg.get('To'))}")
        print(f"Subject : {_decode_mime_words(msg.get('Subject'))}")
        print(f"Date    : {msg.get('Date') or '(no date)'}")
        print(f"Message-ID: {msg.get('Message-ID') or '(none)'}")
        print("-" * 70)
        print(_plain_text_body(msg))
    except imaplib.IMAP4.error as e:
        sys.exit(f"[Error] IMAP query failed: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()


# --------------------------------------------------------------------------
# Shared Drafts-save logic
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
            sys.exit(f"[Error] Failed to save to Drafts (mailbox: {drafts_name}): {resp}")
    except imaplib.IMAP4.error as e:
        sys.exit(
            f"[Error] Error while saving to the Drafts folder ('{drafts_name}'): {e}\n"
            "  The server may use a Drafts mailbox under a different name — check the server's mailbox list."
        )
    print(f"[{acc['user']}] Saved to folder '{drafts_name}'.")
    print("Saved to Drafts. Send it yourself from your mail app.")


def _read_body_arg(args) -> str:
    if args.body_file:
        try:
            with open(args.body_file, encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            sys.exit(f"[Error] Could not read --body-file: {e}")
    if args.body is not None:
        return args.body
    sys.exit("[Error] You must specify either --body or --body-file.")


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
# Subcommand: draft (Drafts save only, never sends)
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
# Subcommand: reply (fetch original → build reply headers → Drafts save only, never sends)
# --------------------------------------------------------------------------

def cmd_reply(args):
    acc = _load_account(args.account)
    body = _read_body_arg(args)

    conn = _imap_connect(acc)
    try:
        typ, _ = conn.select(args.mailbox, readonly=True)
        if typ != "OK":
            sys.exit(f"[Error] Could not open mailbox '{args.mailbox}'.")

        original = _fetch_message(conn, args.uid)

        orig_subject = _decode_mime_words(original.get("Subject")) or "(no subject)"
        subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

        orig_from = original.get("From") or ""
        to_addr = args.to or orig_from
        if not to_addr:
            sys.exit("[Error] Could not determine a reply recipient. Specify --to.")

        orig_msg_id = original.get("Message-ID") or ""
        orig_refs = original.get("References") or ""
        references = (orig_refs + " " + orig_msg_id).strip() if orig_msg_id else orig_refs

        orig_date = original.get("Date") or ""
        orig_body = _plain_text_body(original)
        quoted = "\n".join(f"> {line}" for line in orig_body.splitlines())
        full_body = f"{body}\n\n--- Original message ({_decode_mime_words(orig_from)}, {orig_date}) ---\n{quoted}"

        msg = _build_message(acc, to_addr, subject, full_body, cc=args.cc)
        if orig_msg_id:
            msg["In-Reply-To"] = orig_msg_id
        if references:
            msg["References"] = references

        _append_to_drafts(conn, acc, msg)
    finally:
        conn.logout()


# --------------------------------------------------------------------------
# Subcommand: send (the only real send path — requires --send flag + typed confirmation)
# --------------------------------------------------------------------------

def cmd_send(args):
    if not args.send:
        sys.exit(
            "[Refused] The send logic cannot be reached without the --send flag.\n"
            "  To only save a message to Drafts, use the `draft` subcommand:\n"
            "    python mail_connector.py draft --account ... --to ... --subject ... --body ..."
        )

    if not sys.stdin.isatty():
        sys.exit(
            "[Refused] Actual sending is refused in a non-interactive environment (pipe/script/automation).\n"
            "  Send confirmation must be typed by a human directly in a terminal.\n"
            "  Re-run `python mail_connector.py send ... --send` from an interactive terminal."
        )

    acc = _load_account(args.account)
    body = _read_body_arg(args)
    msg = _build_message(acc, args.to, args.subject, body, cc=args.cc)

    print("=" * 70)
    print("The following mail is about to be sent for real — this cannot be undone.")
    print("=" * 70)
    print(f"From   : {acc['user']}")
    print(f"To     : {args.to}")
    if args.cc:
        print(f"Cc     : {args.cc}")
    print(f"Subject: {args.subject}")
    print("-" * 70)
    print(body)
    print("=" * 70)

    confirm = input("To actually send, type exactly SEND: ")
    if confirm != "SEND":
        sys.exit("Send cancelled")

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(acc["smtp_host"], acc["smtp_port"]) as smtp:
            smtp.starttls(context=ctx)
            smtp.login(acc["user"], acc["password"])
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        sys.exit(
            "[Error] SMTP authentication failed.\n"
            f"  Details: {e}\n"
            "  - Check whether this account requires an App Password (not your regular login password).\n"
            "  - Double-check the user/password in config/credentials.json or your environment variables."
        )
    except (OSError, smtplib.SMTPException, ssl.SSLError) as e:
        sys.exit(
            "[Error] Error connecting to or sending via the SMTP server.\n"
            f"  Details: {e}\n"
            f"  - Check host/port (currently: {acc.get('smtp_host')}:{acc.get('smtp_port')}).\n"
            "  - Check whether port 587 (STARTTLS) is reachable and your firewall/network status."
        )

    print("Send complete.")


# --------------------------------------------------------------------------
# argparse
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mail_connector.py",
        description=(
            "sci-toolkit mail connector — DRAFT-FIRST principle: draft/reply always save only to "
            "IMAP Drafts and never auto-send. Actually sending requires both `send --send` and "
            "typing 'SEND' at the interactive confirmation prompt."
        ),
        epilog=(
            "Examples:\n"
            "  mail_connector.py list --account work\n"
            "  mail_connector.py read --account work --uid 12345\n"
            "  mail_connector.py draft --account work --to a@b.com --subject Subject --body Body\n"
            "  mail_connector.py reply --account work --uid 12345 --body ReplyBody\n"
            "  mail_connector.py send --account work --to a@b.com --subject Subject --body Body --send\n"
            "\n"
            "⭐ draft/reply = always safe (Drafts save only). send only goes out for real when both "
            "the --send flag and typed 'SEND' confirmation are present."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    p_list = sub.add_parser("list", help="List recent mail (read-only)")
    p_list.add_argument("--account", choices=["work", "personal"], default="work")
    p_list.add_argument("--n", type=int, default=10, help="Number of messages to list (default 10)")
    p_list.add_argument("--mailbox", default="INBOX")
    p_list.set_defaults(func=cmd_list)

    p_read = sub.add_parser("read", help="Fetch one message by UID (read-only)")
    p_read.add_argument("--account", choices=["work", "personal"], default="work")
    p_read.add_argument("--uid", required=True, help="UID of the message to fetch")
    p_read.add_argument("--mailbox", default="INBOX")
    p_read.set_defaults(func=cmd_read)

    p_draft = sub.add_parser("draft", help="Compose a new mail → save to Drafts only (does not send)")
    p_draft.add_argument("--account", choices=["work", "personal"], default="work")
    p_draft.add_argument("--to", required=True)
    p_draft.add_argument("--cc")
    p_draft.add_argument("--subject", required=True)
    p_draft.add_argument("--body")
    p_draft.add_argument("--body-file")
    p_draft.set_defaults(func=cmd_draft)

    p_reply = sub.add_parser("reply", help="Compose a reply to an original message → save to Drafts only (does not send)")
    p_reply.add_argument("--account", choices=["work", "personal"], default="work")
    p_reply.add_argument("--uid", required=True, help="UID of the original message to reply to")
    p_reply.add_argument("--mailbox", default="INBOX")
    p_reply.add_argument("--to", help="If unset, replies to the original sender")
    p_reply.add_argument("--cc")
    p_reply.add_argument("--body")
    p_reply.add_argument("--body-file")
    p_reply.set_defaults(func=cmd_reply)

    p_send = sub.add_parser(
        "send",
        help="[Dangerous] Actually sends via SMTP — requires --send flag + typed interactive 'SEND' confirmation",
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
        help="Without this flag, sending is refused (interactive SEND confirmation is still additionally required)",
    )
    p_send.set_defaults(func=cmd_send)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        print(
            "\n⭐ Core principle: this script is draft-first. "
            "Mail is always saved only to Drafts, and never auto-sent.\n"
            "If you actually need to send, pass the --send flag to the `send` subcommand "
            "and type 'SEND' directly at the interactive prompt."
        )
        return

    args.func(args)


if __name__ == "__main__":
    main()
