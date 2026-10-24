from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal

from openminion import Agent, tool
from pydantic import BaseModel, Field

from . import github

Category = Literal["bug", "feature", "docs", "question", "chore", "duplicate"]
Priority = Literal["P0", "P1", "P2", "P3"]

PLAN_FILE = Path("label_plan.json")

INSTRUCTIONS = """\
You are an issue triage assistant for the GitHub repository {repo}.

Workflow:
1. Call list_open_issues to get the open issues.
2. For any issue whose title and preview are not enough to judge, call get_issue.
3. For likely bugs, call search_similar with 2-4 keywords to spot duplicates.
4. Call get_repo_labels once and suggest only labels that exist in the repository.
5. For every issue where your suggested labels differ from its current labels,
   call queue_label_change. Some changes may be rejected by the maintainer; that is fine.

Priority scale: P0 = broken core flow or security, P1 = important bug or blocker,
P2 = normal bug or valuable feature, P3 = nice to have or question.

If this session already contains an earlier triage of this repository, mention in
"changes_since_last_run" which issues are new, closed, or changed priority.

Reply with JSON only, matching this schema:
{schema}
"""


class IssueTriage(BaseModel):
    number: int
    title: str
    category: Category
    priority: Priority
    summary: str = Field(description="One sentence: what is actually being asked or broken")
    suggested_labels: list[str] = Field(default_factory=list)
    possible_duplicate_of: int | None = None
    next_action: str = Field(description="Concrete next step for a maintainer")


class TriageReport(BaseModel):
    repo: str
    overview: str
    issues: list[IssueTriage]
    changes_since_last_run: str | None = None


@tool
def list_open_issues(repo: str, limit: int = 10) -> list[dict]:
    """List open issues (pull requests excluded), most recently updated first."""
    return github.list_open_issues(repo, limit)


@tool
def get_issue(repo: str, number: int) -> dict:
    """Get the full body and recent comments of one issue."""
    return github.get_issue(repo, number)


@tool
def search_similar(repo: str, keywords: str) -> list[dict]:
    """Search open and closed issues in the repository by keywords to find duplicates."""
    return github.search_issues(repo, keywords)


@tool
def get_repo_labels(repo: str) -> list[str]:
    """List the labels defined in the repository."""
    return github.repo_labels(repo)


@tool(dangerous=True)
def queue_label_change(repo: str, number: int, add: list[str], reason: str) -> dict:
    """Queue a label change for maintainer review. Requires approval."""
    plan = json.loads(PLAN_FILE.read_text("utf-8")) if PLAN_FILE.exists() else []
    entry = {
        "repo": repo,
        "number": number,
        "add": add,
        "reason": reason,
        "queued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    plan.append(entry)
    PLAN_FILE.write_text(json.dumps(plan, indent=2), "utf-8")
    return {"queued": True, **entry}


TOOLS = [list_open_issues, get_issue, search_similar, get_repo_labels, queue_label_change]

ApprovalCallback = Callable[[str, dict, str], bool]


def build_agent(repo: str, *, model: str | None = None, config_path: str | None = None) -> Agent:
    schema = json.dumps(TriageReport.model_json_schema(), indent=1)
    return Agent(
        name="issue-triage",
        instructions=INSTRUCTIONS.format(repo=repo, schema=schema),
        output_type=TriageReport,
        tools=TOOLS,
        model=model,
        config_path=config_path,
        session_id=f"triage-{repo.replace('/', '-')}",
    )


def triage(
    repo: str,
    *,
    limit: int = 10,
    model: str | None = None,
    config_path: str | None = None,
    approve: ApprovalCallback | None = None,
    on_progress: Callable[[object], None] | None = None,
):
    with build_agent(repo, model=model, config_path=config_path) as agent:
        return agent.run_stream(
            f"Triage up to {limit} open issues in {repo}.",
            on_delta=on_progress,
            approval_callback=approve,
            timeout_seconds=300,
        )


def to_markdown(report: TriageReport) -> str:
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    lines = [f"# Triage: {report.repo}", "", report.overview, ""]
    if report.changes_since_last_run:
        lines += ["## Since last run", "", report.changes_since_last_run, ""]
    lines += [
        "| # | Priority | Category | Summary | Labels | Next action |",
        "|---|---|---|---|---|---|",
    ]
    for item in sorted(report.issues, key=lambda i: (order[i.priority], i.number)):
        dup = f" (dup of #{item.possible_duplicate_of})" if item.possible_duplicate_of else ""
        lines.append(
            f"| #{item.number} | {item.priority} | {item.category}{dup} | {item.summary} "
            f"| {', '.join(item.suggested_labels)} | {item.next_action} |"
        )
    return "\n".join(lines) + "\n"
