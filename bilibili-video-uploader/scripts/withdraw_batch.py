#!/usr/bin/env python3
"""Withdraw an exact, audited batch of Bilibili submissions.

The command is a dry-run unless ``--apply`` is supplied. It resolves every
target through Creator Center before deleting anything and writes an atomic
receipt after every successful withdrawal so an interrupted run is auditable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


COOKIE_PATH = Path(
    os.environ.get("BILIBILI_COOKIE_FILE", Path.home() / ".bilibili" / "cookies.json")
).expanduser()
ARCHIVES_URL = "https://member.bilibili.com/x/web/archives"
DELETE_URL = "https://member.bilibili.com/x/web/archive/delete"
BV_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}")
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://member.bilibili.com",
    "Referer": "https://member.bilibili.com/platform/upload-manager/article",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def cookie_values() -> dict[str, str]:
    payload = json.loads(COOKIE_PATH.read_text(encoding="utf-8"))
    records = payload.get("cookie_info", {}).get("cookies", [])
    values = {
        str(item["name"]): str(item["value"])
        for item in records
        if isinstance(item, dict) and item.get("name") and item.get("value")
    }
    for required in ("SESSDATA", "bili_jct"):
        if not values.get(required):
            raise RuntimeError(f"Cookie file is missing {required}")
    return values


def parse_indices(value: str) -> list[int]:
    indices: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"Invalid index range: {part}")
            indices.update(range(start, end + 1))
        else:
            indices.add(int(part))
    if not indices:
        raise ValueError("No withdrawal indices supplied")
    return sorted(indices)


def creator_archives(cookies: dict[str, str]) -> dict[str, dict[str, Any]]:
    archives: dict[str, dict[str, Any]] = {}
    for status in ("pubed", "is_pubing", "not_pubed"):
        for page in range(1, 101):
            response = requests.get(
                ARCHIVES_URL,
                params={
                    "status": status, "pn": page, "ps": 30,
                    "coop": 1, "interactive": 1,
                },
                cookies=cookies, headers=HEADERS, timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 0:
                raise RuntimeError(
                    f"Creator Center listing failed: {payload.get('message')}"
                )
            records = (payload.get("data") or {}).get("arc_audits") or []
            if not records:
                break
            new_records = 0
            for record in records:
                archive = record.get("Archive") or {}
                bvid = str(archive.get("bvid") or "")
                if not BV_PATTERN.fullmatch(bvid):
                    continue
                if bvid not in archives:
                    new_records += 1
                archives[bvid] = {
                    "aid": int(archive["aid"]),
                    "bvid": bvid,
                    "title": str(archive.get("title") or ""),
                    "state": archive.get("state"),
                    "state_desc": str(archive.get("state_desc") or status),
                }
            # The endpoint may cap ps below the requested value. Stop only
            # when a page adds nothing, which also protects against a server
            # repeatedly returning page one.
            if new_records == 0:
                break
    return archives


def load_targets(
    audit_path: Path, snapshot_path: Path, indices: list[int],
) -> list[dict[str, Any]]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    audit_by_index = {int(item["index"]): item for item in audit.get("papers", [])}
    snapshot_by_bvid = {str(item["bvid"]): item for item in snapshot}
    missing = sorted(set(indices) - set(audit_by_index))
    if missing:
        raise RuntimeError(f"Indices missing from audit: {missing}")
    targets: list[dict[str, Any]] = []
    for index in indices:
        audit_item = audit_by_index[index]
        bvid = str(audit_item.get("bvid") or "")
        if not BV_PATTERN.fullmatch(bvid):
            raise RuntimeError(f"Invalid BVID for paper {index}: {bvid}")
        snapshot_item = snapshot_by_bvid.get(bvid)
        if not snapshot_item:
            raise RuntimeError(f"BVID missing from Creator Center snapshot: {bvid}")
        targets.append({
            "index": index,
            "bvid": bvid,
            "title_en": str(audit_item.get("title_en") or ""),
            "title_zh": str(audit_item.get("title_zh") or ""),
            "creator_title": str(snapshot_item.get("title") or ""),
        })
    if len({item["bvid"] for item in targets}) != len(targets):
        raise RuntimeError("Withdrawal targets contain duplicate BVIDs")
    return targets


def build_plan(
    targets: list[dict[str, Any]], live: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for target in targets:
        archive = live.get(target["bvid"])
        if not archive:
            raise RuntimeError(
                f"Target is absent from live Creator Center: {target['bvid']}"
            )
        if archive["title"] != target["creator_title"]:
            raise RuntimeError(
                f"Title mismatch for {target['bvid']}: "
                f"{archive['title']!r} != {target['creator_title']!r}"
            )
        plan.append({**target, **archive})
    return plan


def withdraw(
    plan: list[dict[str, Any]], cookies: dict[str, str], receipt_path: Path,
    audit_path: Path, apply: bool,
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "mode": "applied" if apply else "dry-run",
        "source_audit": str(audit_path.resolve()),
        "source_audit_sha256": sha256_file(audit_path),
        "targets": len(plan),
        "excluded_indices": [1, 2],
        "started_at": utc_now(),
        "papers": [],
    }
    if not apply:
        receipt["papers"] = [
            {**item, "status": "ready_to_withdraw"} for item in plan
        ]
        return receipt

    csrf = cookies["bili_jct"]
    for item in plan:
        response = requests.post(
            DELETE_URL,
            params={"csrf": csrf},
            data={"aid": item["aid"], "csrf": csrf},
            cookies=cookies, headers=HEADERS, timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        result = {
            **item,
            "withdrawn_at": utc_now(),
            "response_code": payload.get("code"),
            "response_message": payload.get("message"),
        }
        if payload.get("code") != 0:
            result["status"] = "failed"
            receipt["papers"].append(result)
            receipt["status"] = "partial_failure"
            atomic_json(receipt_path, receipt)
            raise RuntimeError(
                f"Withdrawal failed for {item['bvid']}: {payload.get('message')}"
            )
        result["status"] = "withdrawn"
        receipt["papers"].append(result)
        atomic_json(receipt_path, receipt)
        time.sleep(0.5)

    live_after = creator_archives(cookies)
    remaining = [item["bvid"] for item in plan if item["bvid"] in live_after]
    receipt["verified_at"] = utc_now()
    receipt["remaining_bvids"] = remaining
    receipt["status"] = "verified_withdrawn" if not remaining else "verification_pending"
    atomic_json(receipt_path, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--indices", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    indices = parse_indices(args.indices)
    # This task's completed papers are hard exclusions. A future batch can use
    # different indices, but may never include 1 or 2 without changing code.
    if {1, 2} & set(indices):
        raise RuntimeError("Indices 1 and 2 are protected from withdrawal")
    cookies = cookie_values()
    targets = load_targets(args.audit, args.snapshot, indices)
    live = creator_archives(cookies)
    plan = build_plan(targets, live)
    result = withdraw(
        plan, cookies, args.receipt, args.audit, apply=args.apply,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
