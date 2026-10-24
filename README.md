# Issue Triage Agent (OpenMinion 0.1)

A small agent that triages open GitHub issues of any public repository. It reads the
issues, opens the unclear ones, searches for duplicates, and returns a prioritized
report (P0–P3, category, one-line summary, existing labels to add, next action).
Label changes are never written to GitHub: they go to a local `label_plan.json`
queue and each one passes through an approval step first.

Built for Cortensor Hackathon #5 on the OpenMinion 0.1 Python SDK.

## Run

Requires Python 3.11+.

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -r requirements.txt

openminion config init --provider groq        # or cortensor, openrouter, ollama ...
export GROQ_API_KEY=...                        # the free tier is enough

python -m triage_agent openminion/openminion --limit 8
```

Options:

| Flag | Meaning |
|---|---|
| `--limit N` | how many open issues to triage (default 10) |
| `--model ID` | override the model from the OpenMinion config |
| `--config PATH` | use a project-owned `agents.json` |
| `--yes` | approve every queued label change without asking |
| `--out FILE` | report path (default `triage_report.md`, plus a `.json` copy) |

Set `GITHUB_TOKEN` if you hit the anonymous GitHub rate limit (60 requests/hour).
The token is only used for reads.

Run the same command again later: the agent keeps one session per repository
(`triage-<owner>-<name>`), so the second report includes a "Since last run" section.

## How it uses the OpenMinion SDK

```
python -m triage_agent owner/repo
        │
        ▼
Agent(instructions, output_type=TriageReport, tools=[...], session_id="triage-owner-repo")
        │  run_stream(on_delta=progress, approval_callback=approve)
        ▼
 list_open_issues ─► get_issue ─► search_similar ─► get_repo_labels ─► queue_label_change*
        │                                                       *dangerous=True → approval
        ▼
 JSON reply ─► validated into TriageReport (pydantic) ─► triage_report.md / .json
```

- `triage_agent/agent.py`: tools (`@tool`), the `TriageReport` output model, and the agent
- `triage_agent/github.py`: read-only GitHub REST calls on the standard library
- `triage_agent/__main__.py`: CLI, approval prompt, progress output, error handling

## Building Blocks Tested

| Block | How it is used | Result |
|---|---|---|
| Agent execution | `Agent.run_stream()` with a 300 s timeout | works |
| Tools | 5 functions registered with `@openminion.tool` per run | works |
| Permissions | `queue_label_change` is `dangerous=True`; approved through `approval_callback` | TODO after a model run |
| Structured output | `output_type=TriageReport`, invalid replies caught as `AgentOutputValidationError` | works (validated on echo provider) |
| Sessions | stable `session_id` per repository, used for the "Since last run" diff | TODO after a second model run |
| Models | Groq `llama-3.3-70b-versatile` | TODO |
| Diagnostics | `result.stats`, `run_id`, `ProviderError` handling | TODO |

## What We Learned

- **Echo provider cannot exercise tools.** `config init --provider echo` is the only
  credential-free mode, but it just echoes the prompt, so there is no offline way to
  test a tool loop or approvals. A scripted/mock provider that replays tool calls would
  make SDK users' CI tests possible.
- **`output_type` does not tell the model the schema.** The reply is validated against
  the pydantic model, but the schema has to be pasted into `instructions` by hand.
  Injecting `model_json_schema()` automatically (or using native JSON mode where the
  provider has it) would remove a common failure.
- **Python 3.14** installs and runs `openminion 0.1.11` without problems, although the
  docs only mention 3.11+.
- **`config init` has no `--model` flag**; the model can only be chosen in the
  interactive `openminion setup` or by editing `agents.json`.

## Demo

Video: TODO (1–5 min: one run on `openminion/openminion`, an approval prompt, the report,
then a second run showing "Since last run").

## License

MIT
