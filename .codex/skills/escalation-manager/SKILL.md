---
name: escalation-manager
description: Use when requirement meaning, mandate scope, permission, ownership, escalation tracking, duplicate suppression, or durable resolution handoff may require a user decision in Agency Swarm work.
---

# Escalation Manager

Use this skill to decide whether Agency Swarm work needs a real user decision, record that blocker durably when needed, and resume work after resolution.

An escalation is not a progress update. It is a structured decision request for a blocker the agent cannot safely resolve inside the active mandate.

## Role Rules

Manager owns:

- user-message intake and requirement classification
- mandate definition and boundary checks
- queue and critical-path decisions
- worker prompt quality and worker evidence review
- final user-facing escalation approval
- final delivery to the user

Workers own:

- one scoped mandate
- evidence collection inside that scope
- implementation, research, writing, or validation inside that scope
- structured completion or blocker reports

Workers do not own:

- the global queue
- final truth
- user messaging
- merges, releases, deployments, public mutations, or destructive actions
- scope expansion
- final escalation routing

## Escalation Levels

Use three levels. Do not collapse them.

1. Worker signal
   - A worker reports uncertainty, missing evidence, runtime failure, mandate conflict, or risk.
   - This goes to the manager only.

2. Manager decision
   - The manager verifies, resolves internally, asks for more worker evidence, rejects the signal, or approves a user-facing escalation.
   - This is not automatically shown to the user.

3. User action
   - The system cannot proceed safely without the user's decision, permission, missing input, or tradeoff choice.
   - Only this level may be surfaced as an Escalation.

## When To Escalate

Use `AGENTS.md` Section 9 and `/Users/nick/.codex/AGENTS.md` as the source of truth for required escalation triggers.

Surface a user-action escalation when a blocker remains after bounded evidence gathering and the governing policy makes the decision user-owned, including:

- unclear requirement meaning, mandate scope, permission, ownership, visibility, or repository target
- verified conflict between evidence and a core user requirement
- no clear plan can be articulated
- a product, architecture, behavior, or user-visible tradeoff needs explicit direction
- an essential command, tool, credential, sandbox path, or service is truly blocked
- unrelated or unattributed changes create real ambiguity
- proceeding would cross a destructive, public, release, deploy, merge, tag, push, external-message, or other approved-boundary gate

Before surfacing, confirm all are true:

- the blocker is real after checking available context, files, logs, transcripts, ledger, and worker evidence
- the decision belongs to the user rather than the manager or worker
- the manager or worker cannot resolve it safely inside the active mandate
- the question is concrete enough to answer in one message
- independent in-scope work either continues separately or is explicitly blocked

Do not escalate for:

- routine status
- process recaps
- missing context that can be recovered locally
- uncertainty a worker can resolve with more evidence
- asking the user to do work the agent can do
- generic attention labels such as "important", "blocked", or "FYI"

## Requirement Disambiguation

Use this skill before work starts when user wording still has more than one plausible meaning after bounded evidence gathering.

For requirement-disambiguation escalations:

- Quote only the minimum user words that create the ambiguity.
- List the plausible meanings without adding unsupported options.
- State the evidence checked and why it did not resolve the meaning.
- Ask one concrete question that chooses the intended meaning or scope.
- Do not implement a broader or adjacent reading while waiting.

## Durable Record Shape

Record a durable escalation through `.codex/skills/requirement-ledger` when the blocker changes active work state or must survive the current chat.

Use the current requirement-ledger CLI fields only:

- `--category`: use `escalation`
- `--title`: short noun phrase naming the decision
- `--status`: one of `open`, `in_progress`, `blocked`, `waiting`, or `deferred`
- `--original`: sanitized one-paragraph restatement of the blocker, question, options, and recommendation
- `--intent`: why the decision matters to the active mandate
- `--next-action`: the exact next action, such as waiting for the user's answer or collecting one missing evidence item
- `--source-pointer`: source refs for task, worker, repo, branch, pull request, session, or file evidence
- `--artifact`: active repo, branch, pull request, temp evidence, or other live artifact handle

Use `blocked` when the critical path needs a user answer. Use `waiting` when the user-facing question has already been surfaced. Use `deferred` only when the manager intentionally delays the escalation. Use `complete --resolution` when the decision is resolved, and `reject --resolution` when the item is obsolete or superseded.

Do not invent unsupported ledger fields or hand-edit ledger JSON.

Use neutral operational wording in durable records. Preserve exact private wording only when the resolution itself requires it.

`Escalations: none` means no user decision is required right now. It does not mean no work remains.

## Workflow

1. Reconstruct state.
   - Read the relevant mandate, queue item, worker output, ledger, source refs, and existing escalation records.
   - Do not answer from memory when evidence exists.

2. Check for duplicates.
   - Search active and archived ledger items by title, source pointers, and linked artifacts.
   - If the same decision is active, reuse or update that item with supported CLI fields.
   - If it is archived as completed, follow the recorded resolution.

3. Classify the signal.
   - Resolve internally when the manager has enough authority and evidence.
   - Ask the worker for more evidence when the blocker is under-specified.
   - Surface to the user only when it is a real user-owned decision.

4. Record the blocker when durable state is needed.
   - Use `.codex/skills/requirement-ledger`.
   - Store detailed evidence in linked artifacts or notes, not in the user-facing question.
   - Keep durable state in the user-folder ledger location required by `/Users/nick/.codex/AGENTS.md`.

5. Surface or continue.
   - If the decision must be surfaced to the user, use the exact user-facing format below.
   - If not user-owned, continue manager or worker execution without bothering the user.

6. Resolve and resume.
   - Record the answer in operational terms.
   - Unblock affected tasks.
   - Keep independent work moving.

## User-Facing Format

Use this shape only for real user-action escalations, matching `AGENTS.md`:

```text
Problem: State the concrete blocker, checked evidence, and real risk.
Options:
(1) State one viable path and its tradeoff.
(2) State one viable path and its tradeoff.
(3) State one viable path and its tradeoff.
Recommendation: Pick one option and give the reason.
```

Use only the options needed, up to three. If there is only one safe path, state that and ask only for the missing permission or input.

Avoid apologies, hype, broad status, long reasoning traces, and multiple unrelated questions.

## Worker Handoff Format

Worker blocker reports to the manager should be structured like this:

```json
{
  "level": "worker_signal",
  "summary": "Blocked on missing release approval.",
  "source_ref": {
    "kind": "task",
    "id": "task_123"
  },
  "mandate_boundary": "release",
  "evidence": [
    "/absolute/path/to/report.md"
  ],
  "recommended_manager_action": "surface_user_action"
}
```

The manager must verify this before creating a user-facing escalation.

## Duplicate Suppression

Before surfacing:

- If the same active item is `blocked` or `waiting`, do not create a duplicate ledger item or invent a new question. Reuse the existing escalation, re-raise it at task boundaries when it still blocks the critical path, and update supported fields only when source facts changed.
- If the same active item is `in_progress`, finish the manager or worker evidence step before surfacing.
- If the same item is archived as completed, apply the recorded resolution.
- If the same item is archived as failed, create a new item only when source facts changed.

## Checklist

- I checked existing ledger items, escalation records, or source refs for duplicates.
- I separated worker signal, manager decision, and user action.
- I verified the blocker cannot be resolved by agent-owned work.
- The user-facing question has one decision.
- The options are directly comparable.
- The recommendation is defensible and not persuasive fluff.
- The durable record points back to the mandate and source evidence when durable tracking is needed.
