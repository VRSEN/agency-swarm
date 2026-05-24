#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "agentswarm-requirement-ledger/v2"
LEGACY_ACTIVE_SCHEMA_VERSIONS = ("codex-requirement-ledger/v2",)
DEFAULT_LEDGER_DIR = Path(".codex/requirements-ledger")
ACTIVE_FILE = "active.json"
ARCHIVE_FILE = "archive.jsonl"
ACTIVE_STATUSES = ("open", "in_progress", "blocked", "waiting", "deferred")
ARCHIVE_STATUSES = ("completed", "failed")


class LedgerError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except LedgerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Maintain an item-level requirement queue and archive without manual full-file rewrites."
    )
    parser.add_argument("--ledger-dir", type=Path, default=DEFAULT_LEDGER_DIR, help="Directory for ledger files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create ledger files if they do not exist.")
    init_parser.set_defaults(func=command_init)

    add_parser = subparsers.add_parser("add", help="Add a real user request or requirement to the active queue.")
    add_parser.add_argument("--id", help="Optional stable ID for tests or imports.")
    add_parser.add_argument("--status", choices=ACTIVE_STATUSES, default="open")
    add_parser.add_argument("--category", required=True)
    add_parser.add_argument("--title", required=True)
    add_parser.add_argument("--original", help="Proofread, sanitized requirement wording for auditability.")
    add_parser.add_argument(
        "--original-file", type=Path, help="Read reviewed requirement wording from a UTF-8 text file."
    )
    add_parser.add_argument("--intent", required=True)
    add_parser.add_argument("--next-action", required=True)
    add_parser.add_argument("--source-pointer", action="append", required=True, help="Repeat for multiple sources.")
    add_parser.add_argument("--artifact", action="append", help="Repeat for multiple artifacts like PRs or branches.")
    add_parser.set_defaults(func=command_add)

    update_parser = subparsers.add_parser(
        "update",
        help="Update one active queue item without reordering the queue.",
    )
    update_parser.add_argument("item_id")
    update_parser.add_argument("--status", choices=ACTIVE_STATUSES)
    update_parser.add_argument("--category")
    update_parser.add_argument("--title")
    update_parser.add_argument("--original")
    update_parser.add_argument(
        "--original-file", type=Path, help="Read reviewed requirement wording from a UTF-8 text file."
    )
    update_parser.add_argument("--intent")
    update_parser.add_argument("--next-action")
    update_parser.add_argument("--source-pointer", action="append", help="Append one or more source pointers.")
    update_parser.add_argument("--artifact", action="append", help="Append one or more artifacts if missing.")
    update_parser.set_defaults(func=command_update)

    complete_parser = subparsers.add_parser("complete", help="Move an active item to the archive.")
    complete_parser.add_argument("item_id")
    complete_parser.add_argument("--resolution", required=True)
    complete_parser.set_defaults(func=command_complete)

    reject_parser = subparsers.add_parser("reject", help="Archive a rejected ledger revision as failed.")
    reject_parser.add_argument("item_id")
    reject_parser.add_argument("--resolution", required=True)
    reject_parser.set_defaults(func=command_reject)

    list_parser = subparsers.add_parser(
        "list",
        help="Print active unfulfilled items in stored strategic chronological order before optional archive.",
    )
    list_parser.add_argument("--archive", action="store_true", help="Include archived completed items.")
    list_parser.set_defaults(func=command_list)

    return parser


def command_init(args: argparse.Namespace) -> None:
    paths = _paths(args.ledger_dir)
    _ensure_ledger(paths)
    print(f"active: {paths['active']}")
    print(f"archive: {paths['archive']}")


def command_add(args: argparse.Namespace) -> None:
    paths = _paths(args.ledger_dir)
    _ensure_ledger(paths)
    active = _load_active(paths["active"])
    archive = _load_archive(paths["archive"])
    item_id = _required_text("id", args.id) if args.id else _next_item_id(active["items"], archive)
    if _find_item(active["items"], item_id) is not None:
        raise LedgerError(f"active item already exists: {item_id}")
    if _find_item(archive, item_id) is not None:
        raise LedgerError(f"archived item already exists: {item_id}")

    now = _now()
    item = {
        "id": item_id,
        "created_at": now,
        "updated_at": now,
        "status": _required_text("status", args.status),
        "category": _required_text("category", args.category),
        "title": _required_text("title", args.title),
        "original": _text_argument(
            "original", args.original, args.original_file, required=True, preserve_whitespace=True
        ),
        "intent": _required_text("intent", args.intent),
        "next_action": _required_text("next_action", args.next_action),
        "source_pointers": [_required_text("source_pointer", source) for source in args.source_pointer],
        "artifacts": _merge_unique_texts([], _optional_texts("artifact", args.artifact)),
    }
    active["items"].append(item)
    _write_active(paths["active"], active)
    print(item_id)


def command_update(args: argparse.Namespace) -> None:
    paths = _paths(args.ledger_dir)
    active = _load_active(paths["active"])
    item = _require_item(active["items"], args.item_id)

    updates = {
        "status": args.status,
        "category": args.category,
        "title": args.title,
        "intent": args.intent,
        "next_action": args.next_action,
    }
    original = _text_argument("original", args.original, args.original_file, preserve_whitespace=True)
    if (
        not any(value is not None for value in updates.values())
        and original is None
        and not args.source_pointer
        and not args.artifact
    ):
        raise LedgerError("update needs at least one field to change")
    for field, value in updates.items():
        if value is not None:
            item[field] = _required_text(field, value)
    if original is not None:
        item["original"] = original
    if args.source_pointer:
        item["source_pointers"].extend(_required_text("source_pointer", source) for source in args.source_pointer)
    if args.artifact:
        item["artifacts"] = _merge_unique_texts(_read_artifacts(item), _optional_texts("artifact", args.artifact))
    item["updated_at"] = _now()

    _write_active(paths["active"], active)
    print(args.item_id)


def command_complete(args: argparse.Namespace) -> None:
    _archive_active_item(args, "completed")


def command_reject(args: argparse.Namespace) -> None:
    _archive_active_item(args, "failed")


def command_list(args: argparse.Namespace) -> None:
    paths = _paths(args.ledger_dir)
    _ensure_ledger(paths)
    active = _load_active(paths["active"])
    _print_items("Active", active["items"])
    if args.archive:
        _print_items("Archive", _load_archive(paths["archive"]))


def _archive_active_item(args: argparse.Namespace, status: str) -> None:
    paths = _paths(args.ledger_dir)
    active = _load_active(paths["active"])
    index, item = _require_item_with_index(active["items"], args.item_id)

    now = _now()
    archived_item = dict(item)
    archived_item["status"] = status
    archived_item["resolution"] = _required_text("resolution", args.resolution)
    archived_item["artifacts"] = _read_artifacts(item)
    archived_item["updated_at"] = now
    archived_item["archived_at"] = now

    _append_archive(paths["archive"], archived_item)
    del active["items"][index]
    _write_active(paths["active"], active)
    print(args.item_id)


def _paths(ledger_dir: Path) -> dict[str, Path]:
    return {
        "active": ledger_dir / ACTIVE_FILE,
        "archive": ledger_dir / ARCHIVE_FILE,
    }


def _ensure_ledger(paths: dict[str, Path]) -> None:
    paths["active"].parent.mkdir(parents=True, exist_ok=True)
    if not paths["active"].exists():
        _write_active(paths["active"], {"schema": SCHEMA_VERSION, "items": []})
    if not paths["archive"].exists():
        paths["archive"].write_text("", encoding="utf-8")


def _load_active(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise LedgerError(f"active ledger does not exist; run init first: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LedgerError(f"invalid active ledger JSON: {path}") from exc
    schema = data.get("schema")
    if schema not in (SCHEMA_VERSION, *LEGACY_ACTIVE_SCHEMA_VERSIONS) or not isinstance(data.get("items"), list):
        raise LedgerError(f"unsupported active ledger schema: {path}")
    migrated = schema != SCHEMA_VERSION
    if migrated:
        data["schema"] = SCHEMA_VERSION
    for item in data["items"]:
        if migrated and "artifacts" not in item:
            item["artifacts"] = []
        _validate_item(item, "active ledger", ACTIVE_STATUSES)
    if migrated:
        _write_active(path, data)
    return data


def _load_archive(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"invalid archive JSONL at {path}:{line_number}") from exc
        if not isinstance(item, dict):
            raise LedgerError(f"archive entry must be an object at {path}:{line_number}")
        if "artifacts" not in item:
            item = dict(item)
            item["artifacts"] = []
        _validate_item(item, f"archive entry at {path}:{line_number}", ARCHIVE_STATUSES)
        items.append(item)
    return items


def _write_active(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f"{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temp_file:
        temp_file.write(json.dumps(data, indent=2) + "\n")
        temp_path = Path(temp_file.name)
    temp_path.replace(path)


def _append_archive(path: Path, item: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as archive:
        archive.write(json.dumps(item, separators=(",", ":")) + "\n")


def _require_item(items: list[dict[str, Any]], item_id: str) -> dict[str, Any]:
    item = _find_item(items, item_id)
    if item is None:
        raise LedgerError(f"active item not found: {item_id}")
    return item


def _require_item_with_index(items: list[dict[str, Any]], item_id: str) -> tuple[int, dict[str, Any]]:
    for index, item in enumerate(items):
        if item.get("id") == item_id:
            return index, item
    raise LedgerError(f"active item not found: {item_id}")


def _find_item(items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
    for item in items:
        if item.get("id") == item_id:
            return item
    return None


def _validate_item(item: dict[str, Any], location: str, allowed_statuses: tuple[str, ...]) -> None:
    status = item.get("status")
    if status not in allowed_statuses:
        raise LedgerError(f"{location} has unsupported status: {status!r}")
    original = item.get("original")
    if not isinstance(original, str) or not original.strip():
        raise LedgerError(f"{location} is missing sanitized requirement wording")
    source_pointers = item.get("source_pointers")
    if not isinstance(source_pointers, list) or not source_pointers:
        raise LedgerError(f"{location} is missing source pointers")
    if not all(isinstance(source, str) and source.strip() for source in source_pointers):
        raise LedgerError(f"{location} has invalid source pointers")
    _read_artifacts(item, location)


def _read_artifacts(item: dict[str, Any], location: str = "ledger item") -> list[str]:
    artifacts = item.get("artifacts")
    if artifacts is None:
        raise LedgerError(f"{location} is missing artifacts")
    if not isinstance(artifacts, list):
        raise LedgerError(f"{location} has invalid artifacts")
    if not all(isinstance(artifact, str) and artifact.strip() for artifact in artifacts):
        raise LedgerError(f"{location} has invalid artifacts")
    return list(artifacts)


def _next_item_id(*item_groups: list[dict[str, Any]]) -> str:
    prefix = f"REQ-{datetime.now(UTC):%Y%m%d}"
    existing_ids = {item.get("id") for items in item_groups for item in items}
    counter = 1
    while True:
        item_id = f"{prefix}-{counter:03d}"
        if item_id not in existing_ids:
            return item_id
        counter += 1


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _required_text(field: str, value: str) -> str:
    text = value.strip()
    if not text:
        raise LedgerError(f"{field} cannot be empty")
    return text


def _required_preserved_text(field: str, value: str) -> str:
    if not value.strip():
        raise LedgerError(f"{field} cannot be empty")
    return value


def _text_argument(
    field: str,
    value: str | None,
    file_path: Path | None,
    *,
    required: bool = False,
    preserve_whitespace: bool = False,
) -> str | None:
    if value is not None and file_path is not None:
        raise LedgerError(f"cannot combine --{field} with --{field}-file")
    if file_path is not None:
        try:
            value = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise LedgerError(f"cannot decode {field} file as UTF-8: {file_path}") from exc
        except OSError as exc:
            raise LedgerError(f"cannot read {field} file: {file_path}") from exc
    if value is None:
        if required:
            raise LedgerError(f"{field} is required")
        return None
    if preserve_whitespace:
        return _required_preserved_text(field, value)
    return _required_text(field, value)


def _optional_texts(field: str, values: list[str] | None) -> list[str]:
    if not values:
        return []
    return [_required_text(field, value) for value in values]


def _merge_unique_texts(current: list[str], incoming: list[str]) -> list[str]:
    merged = list(current)
    seen = set(current)
    for value in incoming:
        if value in seen:
            continue
        merged.append(value)
        seen.add(value)
    return merged


def _print_items(label: str, items: list[dict[str, Any]]) -> None:
    print(f"{label} ({len(items)})")
    for item in items:
        print(f"- {item['id']} [{item['status']}/{item['category']}] {item['title']}")
        _print_text_field("original", item["original"])
        _print_text_field("intent", item["intent"])
        _print_text_field("next", item.get("next_action", "none"))
        print(f"  source: {', '.join(item.get('source_pointers', []))}")
        if artifacts := _read_artifacts(item):
            print(f"  artifacts: {', '.join(artifacts)}")
        if item.get("resolution"):
            _print_text_field("resolution", item["resolution"])


def _print_text_field(label: str, value: str) -> None:
    prefix = f"  {label}: "
    lines = value.splitlines() or [""]
    print(f"{prefix}{lines[0]}")
    continuation = " " * len(prefix)
    for line in lines[1:]:
        print(f"{continuation}{line}")


if __name__ == "__main__":
    raise SystemExit(main())
