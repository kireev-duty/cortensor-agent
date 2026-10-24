from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from openminion import AgentOutputValidationError, ProviderError

from .agent import to_markdown, triage


def _approve_interactively(tool_name: str, args: dict, approval_id: str) -> bool:
    print(f"\n[approval] {tool_name} {json.dumps(args, ensure_ascii=False)}")
    answer = input("Allow? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def _approve_all(tool_name: str, args: dict, approval_id: str) -> bool:
    print(f"[auto-approved] {tool_name} #{args.get('number')} +{args.get('add')}")
    return True


def _progress(event: object) -> None:
    kind = getattr(event, "kind", None) or (event.get("kind") if isinstance(event, dict) else None)
    name = getattr(event, "tool_name", None) or (
        event.get("tool_name") if isinstance(event, dict) else None
    )
    if name:
        print(f"  -> {kind or 'tool'}: {name}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Triage open GitHub issues with an OpenMinion agent")
    parser.add_argument("repo", help="owner/name, e.g. openminion/openminion")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--model", help="override the model from the OpenMinion config")
    parser.add_argument("--config", help="path to agents.json")
    parser.add_argument("--out", default="triage_report.md")
    parser.add_argument("--yes", action="store_true", help="approve every label change")
    args = parser.parse_args()

    started = time.monotonic()
    try:
        result = triage(
            args.repo,
            limit=args.limit,
            model=args.model,
            config_path=args.config,
            approve=_approve_all if args.yes else _approve_interactively,
            on_progress=_progress,
        )
    except ProviderError as exc:
        print(f"Model provider error: {exc}", file=sys.stderr)
        return 2
    except AgentOutputValidationError as exc:
        Path(args.out).with_suffix(".raw.txt").write_text(exc.raw_text, "utf-8")
        print(f"Reply was not valid TriageReport JSON, raw text saved: {exc}", file=sys.stderr)
        return 3

    report = result.output
    Path(args.out).write_text(to_markdown(report), "utf-8")
    Path(args.out).with_suffix(".json").write_text(report.model_dump_json(indent=2), "utf-8")
    print(to_markdown(report))
    print(
        f"Saved {args.out} | session={result.session_id} run={result.run_id} "
        f"| {time.monotonic() - started:.1f}s | stats={json.dumps(result.stats)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
