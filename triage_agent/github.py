from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API = "https://api.github.com"


class GitHubError(RuntimeError):
    pass


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "issue-triage-agent",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise GitHubError(f"GitHub {exc.code} for {path}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(f"GitHub unreachable: {exc.reason}") from exc


def _short(issue: dict[str, Any], body_chars: int) -> dict[str, Any]:
    body = (issue.get("body") or "").strip()
    return {
        "number": issue["number"],
        "title": issue["title"],
        "author": (issue.get("user") or {}).get("login"),
        "labels": [label["name"] for label in issue.get("labels", [])],
        "comments": issue.get("comments", 0),
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "body": body[:body_chars] + ("…" if len(body) > body_chars else ""),
        "url": issue.get("html_url"),
    }


def list_open_issues(repo: str, limit: int = 10) -> list[dict[str, Any]]:
    items = _get(
        f"/repos/{repo}/issues",
        {"state": "open", "per_page": min(max(limit, 1) * 3, 100), "sort": "updated"},
    )
    issues = [item for item in items if "pull_request" not in item]
    return [_short(issue, 400) for issue in issues[:limit]]


def get_issue(repo: str, number: int) -> dict[str, Any]:
    issue = _short(_get(f"/repos/{repo}/issues/{number}"), 3000)
    comments = _get(f"/repos/{repo}/issues/{number}/comments", {"per_page": 10})
    issue["recent_comments"] = [
        {
            "author": (c.get("user") or {}).get("login"),
            "body": (c.get("body") or "")[:600],
        }
        for c in comments
    ]
    return issue


def search_issues(repo: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
    result = _get(
        "/search/issues",
        {"q": f"repo:{repo} is:issue {query}", "per_page": min(max(limit, 1), 20)},
    )
    return [
        {
            "number": item["number"],
            "title": item["title"],
            "state": item["state"],
            "url": item["html_url"],
        }
        for item in result.get("items", [])
    ]


def repo_labels(repo: str) -> list[str]:
    return [label["name"] for label in _get(f"/repos/{repo}/labels", {"per_page": 100})]
