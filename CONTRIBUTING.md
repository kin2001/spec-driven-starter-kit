# Contributing to Spec Team

Keep the kit small, reproducible and honest about its boundaries. Changes should solve an observed workflow problem while preserving explicit approval, single-controller ownership, independent review, phase acceptance and safe local cleanup.

## Development checks

Use Python 3.11 or newer. The kit's tests and runtime helpers use the standard library; no `pip install` is needed.

```text
python -B -m unittest discover -s tests -v
python -B .agents/skills/spec-team/scripts/validate.py --root . --project .agents/skills/spec-team/templates/project.json --run .agents/skills/spec-team/templates/run.json
git diff --check
```

Run checks on the actual shipped templates and on a disposable consumer when changing setup behavior. Preserve existing consumer files; never test installers against someone else's active project. Platform-dependent skips must be reported instead of counted as passed behavior.

## Pull requests

- Explain the concrete problem, resulting behavior and applicable edge/recovery cases.
- Keep related work in one reviewable delivery. Update callers, role instructions, templates and documentation affected by the contract.
- Include actual commands, results and environment. Separate instruction probes, local tests and live service evidence.
- Keep project/run/environment examples inert and free of real identities, secrets or readiness claims.
- Keep third-party revisions, checksums and license notices together. Runtime setup remains offline and additive.
- Never include `.spec-team/`, `.superpowers/`, `.worktrees/`, credentials, personal memory or local command transcripts.

Bundled skill updates use `scripts/build_skill_bundles.py`; inspect its pinned source mapping before running it. That maintainer operation accesses upstream GitHub archives. It is separate from normal offline setup. Review upstream changes, retained licenses, archive checksums and installed behavior before proposing an update.

Code authored with Codex keeps the configured human Git author and includes `Co-authored-by: Codex <codex@openai.com>` once, preserving other actual coauthors. Attribution does not grant account access or guarantee GitHub's contributor display.

For a security concern, follow [SECURITY.md](SECURITY.md). Do not disclose credentials or exploit details in a public issue.
