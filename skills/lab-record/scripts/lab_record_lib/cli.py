"""Command-line interface. Exit codes: 0 ok / clean, 1 violations or not found, 2 config/parse error."""
from __future__ import annotations

import argparse
import datetime as dt
import sys

from . import catalog as catmod
from . import commands, queries
from .config import announce_root
from .model import Index, TYPES, resolve_config, scan, scan_strict
from .parse import LabRecordError
from .rules import Context, run_all


def _stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _cfg(args, announce: bool = False):
    cfg = resolve_config(args.root, args.config)
    if announce:
        announce_root(cfg)
    return cfg


def _day(args):
    if not getattr(args, "date", None):
        return None
    try:
        return dt.datetime.strptime(args.date, "%y%m%d").date()
    except ValueError as exc:
        raise LabRecordError(f"--date must be YYMMDD: {exc}") from exc


def cmd_new(args) -> int:
    cfg = _cfg(args, True)
    if args.from_prot:
        if args.type != "prot":
            raise LabRecordError("--from-prot only applies to `new prot`")
        path = commands.new_prot_version(cfg, args.from_prot, title=args.title,
                                         reason=args.reason or "", day=_day(args))
    else:
        if not args.title:
            raise LabRecordError("--title is required")
        path = commands.new_record(cfg, args.type, args.title, protocol=args.protocol,
                                   about=args.about or [], from_ids=args.from_ids or [],
                                   version=args.version or "v1", owner=args.owner,
                                   project=args.project, day=_day(args))
    print(path)
    return 0


def cmd_lint(args) -> int:
    cfg = _cfg(args, True)
    records, errors = scan(cfg.root)
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    violations = run_all(Context(cfg.root, cfg.people, Index(records), cfg.projects,
                                  catmod.load_catalog(cfg)))
    for v in violations:
        print(v)
    if errors:
        return 2
    return 1 if violations else 0


def cmd_close(args) -> int:
    print(commands.close_record(_cfg(args), args.id))
    return 0


def cmd_index(args) -> int:
    print(commands.write_index(_cfg(args, True)))
    return 0


def _index(args):
    cfg = _cfg(args)
    return cfg, Index(scan_strict(cfg.root))


def cmd_trace(args) -> int:
    cfg, index = _index(args)
    try:
        print("\n".join(queries.trace(index, args.id, cfg.root, cfg.projects)))
    except KeyError:
        print(f"not found: {args.id}", file=sys.stderr)
        return 1
    return 0


def cmd_impact(args) -> int:
    _, index = _index(args)
    try:
        print("\n".join(queries.impact(index, args.id)))
    except KeyError:
        print(f"not found or not a pinned PROT id (PROT-007@v3): {args.id}", file=sys.stderr)
        return 1
    return 0


def cmd_uses(args) -> int:
    cfg, index = _index(args)
    try:
        print("\n".join(queries.uses(index, catmod.load_catalog(cfg), args.name)))
    except KeyError:
        print(f"not in the catalog: {args.name}", file=sys.stderr)
        return 1
    return 0


def cmd_catalog(args) -> int:
    cfg, index = _index(args)
    print("\n".join(queries.catalog_table(index, catmod.load_catalog(cfg), args.kind)))
    return 0


def cmd_open(args) -> int:
    _, index = _index(args)
    lines = queries.open_items(index)
    print("\n".join(lines) if lines else "nothing open")
    return 0


def build_parser() -> argparse.ArgumentParser:
    # --root/--config are accepted before OR after the subcommand. The subcommand copies use
    # SUPPRESS so an absent flag there does not overwrite a value given before the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", default=argparse.SUPPRESS,
                        help="record root (overrides LAB_RECORD_ROOT and config)")
    common.add_argument("--config", default=argparse.SUPPRESS,
                        help="lab-record.config.json (default ~/.config/lab-record/config.json)")
    p = argparse.ArgumentParser(prog="lab_record.py", description="PROT -> EXP -> DISC -> DEC record tool")
    p.add_argument("--root", default=None, help=argparse.SUPPRESS)
    p.add_argument("--config", default=None, help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)

    n = sub.add_parser("new", parents=[common], help="create a record")
    n.add_argument("type", choices=sorted(TYPES))
    n.add_argument("--title")
    n.add_argument("--protocol", help="EXP: pinned protocol, e.g. PROT-007@v3")
    n.add_argument("--about", nargs="+", help="DISC: EXP/PROT ids")
    n.add_argument("--from", dest="from_ids", nargs="+", help="DEC: DISC ids")
    n.add_argument("--version", help="PROT: version label, default v1")
    n.add_argument("--from-prot", help="PROT: copy latest version of PROT-NNN to the next vN")
    n.add_argument("--reason", help="PROT --from-prot: change_reason")
    n.add_argument("--owner", help="people-map key (default: the only key of the map)")
    n.add_argument("--project")
    n.add_argument("--date", help="YYMMDD override for ids/created (default today)")
    n.set_defaults(func=cmd_new)

    for name, fn, hlp in (("lint", cmd_lint, "check integrity rules 1-9"),
                          ("index", cmd_index, "regenerate INDEX.md"),
                          ("open", cmd_open, "list loose ends")):
        sub.add_parser(name, parents=[common], help=hlp).set_defaults(func=fn)
    for name, fn, hlp in (("close", cmd_close, "freeze a record (status closed)"),
                          ("trace", cmd_trace, "upstream chain of a record"),
                          ("impact", cmd_impact, "downstream of PROT-x@vN")):
        s = sub.add_parser(name, parents=[common], help=hlp)
        s.add_argument("id")
        s.set_defaults(func=fn)
    u = sub.add_parser("uses", parents=[common], help="records using a catalog entry (name or alias)")
    u.add_argument("name")
    u.set_defaults(func=cmd_uses)
    c = sub.add_parser("catalog", parents=[common], help="list catalog entries")
    c.add_argument("--kind", choices=catmod.KINDS)
    c.set_defaults(func=cmd_catalog)
    return p


def main(argv=None) -> int:
    _stdio()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except LabRecordError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
