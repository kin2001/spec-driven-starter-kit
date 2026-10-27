# Quiet coordination and repeatable local operations

Use existing roles and current model defaults. This is a bounded operating contract, not a scheduler or new agent. Keep independent review, selected acceptance, actual ownership and provider-enforced integration gates.

Apply [inline execution](execution.md) for new coherent deliveries: main implements and later follows the Dock checklist; independent Lens remains separate. Milestone worker/observer rules below govern actual dispatches, not a requirement to create a supervised implementer or Dock. Current delegated tasks retain their mode until a safe transition.

## Milestones and waiting

At dispatch assign one coherent outcome and a return condition: blocker, consequential contract change, review-ready candidate, or completion. Workers keep routine exploration/local logs in their own context and existing evidence files. Return a compact summary of issue/status, repository/head/base/tree and dirty files, changed contracts, commands/results, blockers/unverified gates and next action. Aim for 300 words plus evidence links; expand consequential security/recovery details rather than hiding them behind a word limit.

Relay checks supported completion/status capabilities once for the run. Prefer a native wait that wakes on completion or attention rather than short timeout/status loops. A host with only bounded waits still needs polling; record that fallback honestly. Do not invent background continuation, suppress user input, silently finish the turn while required work runs, or promise zero inference cost. Applicable host communication/wait limits take precedence: within them choose the least frequent useful wait, batch targets, and avoid repeated provider reads or milestone requests on unchanged status. If the host requires frequent commentary, give the shortest truthful update using already-known state; do not fetch more state merely to fill it.

Unchanged timeout is neither a blocker nor evidence a worker stopped. After a task-appropriate liveness deadline, inspect actual status once and reconcile uncertain work before intervention. Timeout length/deadline should reflect the assigned command or milestone; no timeout can authorize a replacement writer. Keep the same worker through ordinary corrections. At a settled checkpoint, refresh context only through existing authorized transfer rules, never a periodic restart timer.

## One observer and bounded evidence

Relay assigns exactly one CI observer per active candidate/run in the dispatch. The observer uses supported completion notifications or a bounded provider wait and retains the full sanitized evidence locally; it sends meaningful stage failure, final result or intervention needs. Other roles consume that receipt; do not also poll the same run or request its full logs. When roles hand off observation, reconcile candidate/run identity and any pending query first. A changed head/base/run or contradictory result invalidates affected evidence. Dock still checks current required checks/protections and expected head immediately before integration; a receipt is not current merge permission.

Use narrow structured fields for status and a relevant failing-log excerpt with the full local evidence path. Mark omitted/truncated output and keep failures visible; do not report only totals when a check failed. No raw transcripts, giant file inventories, repeated complete specifications, environment dumps or secrets in messages. Screenshots/log details stay with the role performing that check until a specific review or decision needs them. Relay does not reimplement or continually inspect a worker's in-progress code; inspect the coherent return and material contract risks.

## Local inventory and preservation helper

Resolve the installed skill path and run `scripts/operations.py` with Python3.11+. These commands replace recurring handwritten hash/copy loops; no new dependencies or runtime installation.

```text
python "<skill>/scripts/operations.py" snapshot --source "<selected-directory>" --receipt "<new-local-inventory.json>"
python "<skill>/scripts/operations.py" check --source "<same-directory>" --receipt "<inventory.json>"
python "<skill>/scripts/operations.py" preserve --source "<selected-directory>" --receipt "<inventory.json>" --destination "<controller>/.spec-team/local/preserved/<unique-name>" --controller-root "<controller>" --claim-id "<current-claim>" --run-id "<existing-run>"
```

Snapshot writes a new exclusive JSON file outside the selected tree and reports only file/byte counts. The receipt contains canonical source and sorted relative file paths, sizes and SHA-256. Check is read-only and compares the complete file inventory. After a separately authorized native move, `check --relocated` explicitly compares the new directory's file content against the original inventory. This flag does not authorize a move or establish ownership/dependency compatibility.

Preserve checks the current exclusive claim, exact source inventory and new destination under ignored controller preservation storage; it copies without overwrites, then verifies source and destination again. Source remains untouched. On failure keep both source and partial destination and inspect the outcome; retries never overwrite partial bytes. File content is checked, not ACLs, executable modes, empty directories or semantic validity. Unsupported symlinks, hardlinks, reparse points and Git metadata cause refusal, not silent omission. Use the platform's authorized native lifecycle for anything this helper does not support.

The operator must select an approved non-secret artifact tree and ensure no active writer/process, suitable capacity and local access restrictions before preservation. Never use this generic helper to copy credentials, authentication sessions, private customer data, or whole repositories. It does not scan for unknown secrets, stop processes, check provider authority or sandbox a malicious concurrent actor. A success proves selected local bytes only, never acceptance or safe deletion. Keep inventories local/ignored; do not send all entries to an agent. Hashes themselves can expose filenames: sanitize before external publication.

Prefer existing native worktree cleanup after settled merge and preservation; do not write another removal engine. Preserve required evidence and unrelated ignored files, but don't retain every reproducible build output by default. Classify necessary versus reproducible outputs before removal; unclear artifacts stay preserved. No deletion, move, merge, command execution or deployment is implemented by operations.py.

## Dependency and check reuse

Fresh context does not require a new dependency directory. Prefer the existing meaningful-phase checkout and exclusive writer when compatible with approved branch/review isolation. If a dedicated task worktree is required, use a reproducible isolated install with supported cache reuse when capacity permits. Reuse/move a retained dependency tree only with manifest/lock/runtime/platform compatibility, exclusive ownership, process quiescence and verified pre/post inventories; no mutable shared installations or junction shortcuts. Stop on changed inputs or unavailable disk, not blind reinstall or unapproved system changes. Inventory verification after a move remains necessary; avoid repeated identical full hashing merely for narration.

For each affected feature, check relevant transport/domain boundaries before hosted diagnostics: raw bytes versus decoded text, malformed/expired tokens versus actual provider outage, current-state permissions, valid lifecycle fixtures and changed UI viewport/MFA/error states. Reuse existing domain fixtures rather than bypass production guards. A known baseline failure may reuse its diagnosis only while relevant source/runtime/input evidence matches; don't repeatedly normalize and restore unrelated trees. Run affected checks then required final full CI. Missing services remain unverified; no new universal test matrix per tiny edit.

## Conditional quota checkpoint and continuation

Only when the owner authorizes automatic continuation, record its exact remaining-allowance threshold, buffer and scope in the existing dispatch/checkpoint. At meaningful milestones and before expensive dispatches, read the actual account's relevant window, remaining percentage and provider reset timestamp once; shared account allowance is not per-task billing. Missing or stale quota/reset data stays unknown. Do not add a monitoring agent or tight quota polling.

For an owner-selected 5% remaining cutoff, begin quiescing by 10% remaining when workers or long checks are active, or earlier if the next operation cannot safely settle within that reserve. At <=5% remaining, start no new expensive work, tests, review or provider mutation; collect already-running outcomes and save the existing precise checkpoint. An operation that cannot be interrupted safely must be reconciled, not abandoned to satisfy a percentage. Percentages are a checkpoint policy, not a guarantee against sudden accountwide exhaustion.

When quiet and reconciled, use a supported same-chat heartbeat automation to continue at the ACTUAL provider reset time plus the owner's buffer (for example120seconds); inspect existing matching automations to avoid duplicates and verify the returned target/time/status. Record its actual ID and receipt. Unsupported scheduling or an uncertain creation outcome is not success: read back before retry, retain the checkpoint and report the gap. Do not invent a background waiter, use a separate cron chat as a substitute, or assume an idle worker message will wake the controller. If another chat is the authorized destination, finish exclusive ownership transfer before its writes.

The continuation prompt must recheck current quota/reset, latest human stop, ownership, approved bytes, Git/WIP and uncertain provider outcomes before resuming the exact remaining work. A later human pause/stop cancels automatic resumption until explicitly revoked. Once the single continuation is consumed or superseded, disable/remove it through the supported tool and verify readback; no perpetual unchanged-state wakeups. A reset timestamp alone never proves allowance is now available. Without explicit scheduling authorization, save the checkpoint and wait for the owner.

## Pilot and fallback

In the existing phase report record observed Relay model wakeups, unchanged timeouts/messages, start/end context when exposed, CI correction rounds and cleanup/helper failures, plus retained quality gates. Unknown counters remain unknown. Compare similar deliverables; raw cached token counts are not subscription billing and no savings percentage is promised. Keep model defaults unchanged for this pilot.

For partial helpers, unsupported host waits or changed evidence, fall back to the existing safe workflow for the affected operation. No additional controller or monitor agent. Reversible installation requires a quiet boundary, exact workflow/profile baseline backups and hash-guarded restore; changed files require reconciliation, never forced rollback. Preserve run/claim/approvals/product work and update the actual handoff through Relay after installation.
