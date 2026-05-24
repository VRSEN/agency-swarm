---
name: policy-maintenance
description: Use when editing AGENTS.md, CLAUDE.md, or .codex/skills/** policy, workflow, and manager-skill files. Keeps durable operating rules concise, separates general policy from manager-only policy, and requires review for distorted meaning or regressions.
---

# Policy Maintenance

Use this skill for policy, workflow-rule, and repo-skill changes. Repo skills are checked-in manager instructions under `.codex/skills/**`; read the relevant `SKILL.md` when `AGENTS.md` routes work to one unless the environment exposes the skill directly.

## Workflow

1. Read the live `AGENTS.md`, the current diff, and any directly related policy branch or skill.
2. Policy workers must load and follow every repo skill that owns the policy area being changed.
3. Policy manager reviewers must load and follow those same relevant skills before accepting worker output.
4. For delegated-output checks, also follow `.codex/skills/delegation-management`.
5. When the edit responds to a material process mistake or repeated failure class, fix the largest durable rule or process gap in the right owner section or skill, not just the literal symptom. Use the ledger only for state tracking: active requests, decisions, blockers, evidence, artifacts, and source links.
6. Preserve the active policy branch or artifact when one exists. Create a new branch or artifact only when the mandate needs one; create a pull request only when the user asks.
7. Follow the Tool And Model Policy floor for policy, repo-skill, and workflow-rule edits: separate isolated policy worker every time, strongest available GPT-5.5 or approved substitute, `xhigh` reasoning required (`high` is not enough), and no policy edits if that path is unavailable.
8. If the policy edit is self-initiated, ask the user before changing files.
9. Stay tightly scoped: use `AGENTS.md`, the current diff, and directly authorized policy inputs. Avoid unrelated repo exploration unless the mandate requires it.
10. Classify each rule before editing: universal policy, manager-only policy, repo-specific invariant, or skill procedure.
11. Keep `AGENTS.md` for rules that apply most of the time. Move step-by-step playbooks, commands, and path-specific procedures into repo skills under `.codex/skills/**`, not product-discoverable config directories such as `.agentswarm/skills`.
12. Treat "add this rule" or feedback as "ensure policy enforces this"; use the shortest coherent path regardless of input length: remove, merge, strengthen, move to a skill, or add text only when needed.
13. Do not combine unrelated obligations in one long bullet. Split policy by owner, trigger, action, evidence, and exception so each list contains comparable items.
14. Preserve public/private boundaries. Do not publish private chats, ledgers, internal drafts, or work-in-progress review artifacts unless the user asks.
15. A manager must personally review the final policy diff, challenge every unexplained line, and iterate until the structure is coherent.
16. Check the whole affected rules tree for internal contradictions, duplicate rules, lost protections, public/private leakage, trigger overreach, and unnecessary process cost.
17. Record or escalate any remaining contradiction with the affected clauses; do not ship a narrower wording fix that hides it.
18. Run a fresh review worker after implementation to check for distorted meaning, lost protections, duplicate rules, contradictions, and regressions.

## Policy Branch Rules

- Do not commit policy directly to `main` unless the user explicitly asks.
- Do not mix policy changes into feature pull requests.
- Create or reuse a policy branch as needed inside the mandate. Push or update an existing pull request only when the mandate explicitly covers remote publication or that pull-request update; otherwise keep changes local and surface the needed approval.
- Preserve already-approved behavior. Wording may change only when the behavior is clearly retained or improved.

## Validation

Run these before commit:

```bash
git diff --check
make format
make check
```

For Requirement Ledger script changes, also run:

```bash
python .codex/skills/requirement-ledger/scripts/test_requirement_ledger.py
```

For repo-skill changes, also reread the changed `SKILL.md` files and verify their descriptions trigger only the intended work.

Before shipping, record the policy gates in your own review notes: line-referenced check for lost or changed protections, proof that the user request is enforced, proof that mandate and privacy constraints are met, contradiction and duplicate-rule scan results, and a judgment that the change improves agent efficiency. If any gate fails, refine the implementation instead of asking the user to decide skill or script mechanics.
