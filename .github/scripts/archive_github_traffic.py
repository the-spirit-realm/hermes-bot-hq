#!/usr/bin/env python3
"""Fetch GitHub traffic APIs and upsert JSON into a traffic-branch checkout."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_VERSION = "2022-11-28"
USER_AGENT = "hermes-bot-hq-traffic-archive"
README = """# GitHub traffic archive

Daily snapshots of this repository's GitHub Insights traffic APIs (views, clones, popular paths and referrers). GitHub only retains 14 days in the UI and REST API; this branch keeps a longer series.

Do not merge this branch into the default branch. It is unrelated history, not plugin source.
"""


def api_get(repo: str, path: str, token: str):
    url = f"https://api.github.com/repos/{repo}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GET {url} failed: {exc.code} {exc.reason}\n{body}") from exc


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must be a JSON object of date keys")
    return data


def dump_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def utc_day(timestamp: str) -> str:
    return timestamp[:10]


def upsert_series(existing: dict, payload: dict, series_key: str) -> dict:
    merged = dict(existing)
    for row in payload.get(series_key, []):
        day = utc_day(row["timestamp"])
        merged[day] = {"count": row["count"], "uniques": row["uniques"]}
    return dict(sorted(merged.items()))


def main() -> None:
    token = os.environ.get("TRAFFIC_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token:
        raise SystemExit("TRAFFIC_TOKEN is not set")
    if not repo:
        raise SystemExit("GITHUB_REPOSITORY is not set")

    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    today = datetime.now(timezone.utc).date().isoformat()

    views = api_get(repo, "/traffic/views?per=day", token)
    clones = api_get(repo, "/traffic/clones?per=day", token)
    referrers = api_get(repo, "/traffic/popular/referrers", token)
    paths = api_get(repo, "/traffic/popular/paths", token)

    dump_json(out / "views.json", upsert_series(load_json(out / "views.json"), views, "views"))
    dump_json(out / "clones.json", upsert_series(load_json(out / "clones.json"), clones, "clones"))
    dump_json(out / "snapshots" / f"{today}-referrers.json", referrers)
    dump_json(out / "snapshots" / f"{today}-paths.json", paths)

    readme = out / "README.md"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")


if __name__ == "__main__":
    main()
