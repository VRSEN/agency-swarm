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
4. For delegated-output checks, also follow `.codex/skills/delegation-management` when available.
5. When the edit responds to a material process mistake or repeated failure class, fix the largest durable rule or process gap in the right owner section or skill, not just the literal symptom. Use the ledger only for state tracking: active requests, decisions, blockers, evidence, artifacts, and source links.
6. Preserve the active policy branch or artifact when one exists. Create a new branch or artifact only when the mandate needs one; create a pull request only when the user asks.
7. Follow the policy-worker floor for policy, repo-skill, and workflow-rule edits: use a scoped built-in subagent or a user-assigned isolated worker session for policy file writes, avoid external CLI agents and ad hoc agent processes unless the user explicitly names that tool and grants that scope, and use the highest-reliability built-in path available inside the mandate. If no safe worker path exists, stop and report instead of editing. Managers must not pass custom subagent model overrides unless the user or platform explicitly provides that exact path.
8. If the policy edit is self-initiated, ask the user before changing files.
9. Stay tightly scoped: use `AGENTS.md`, the current diff, and directly authorized policy inputs. Avoid unrelated repo exploration unless the mandate requires it.
10. Classify each rule before editing: universal policy, manager-only policy, repo-specific invariant, or skill procedure.
11. Keep `AGENTS.md` for rules that apply most of the time. Move step-by-step playbooks, commands, path-specific procedures, and workflow-specific validation into skills, not product-discoverable config directories.
12. Treat "add this rule" or feedback as "ensure policy enforces this"; use the shortest coherent path: remove, merge, strengthen, move to a skill, or add text only when needed.
13. Preserve user meaning exactly. Do not transform feedback about one term, repo, branch, product name, or workflow into broader policy or skill duties unless direct user words, standing policy, or checked evidence supports that expansion; escalate unresolved ambiguity before editing.
14. Do not combine unrelated obligations in one long bullet. Split policy by owner, trigger, action, evidence, and exception so each list contains comparable items.
15. Preserve public/private boundaries. Do not publish private chats, ledgers, internal drafts, or work-in-progress review artifacts unless the user asks.
16. A manager must personally review the final policy diff, challenge every unexplained line, and iterate until the structure is coherent.
17. Check the whole affected rules tree for internal contradictions, duplicate rules, lost protections, public/private leakage, trigger overreach, and unnecessary process cost.
18. Record or escalate any remaining contradiction with the affected clauses; do not ship a narrower wording fix that hides it.
19. After non-trivial policy edits, reread the affected rules tree for distorted meaning, lost protections, duplicate rules, contradictions, and regressions. High-risk policy edits require fresh independent review after implementation; high-risk means changes touching user words, mandates, evidence gates, privacy, public-mutation gates, manager-worker boundaries, escalation rules, repo baseline/reset rules, or review gates. When Codex CLI is used for policy review, use the `xhigh` review path in `.codex/skills/codex-cli-review`.

## Policy Branch Rules

- Do not commit policy directly to a shared default branch unless the user explicitly asks.
- Do not mix policy changes into feature pull requests.
- Create or reuse a policy branch as needed inside the mandate. Push only when the mandate covers branch publication; open a pull request only when the user asks.
- Preserve already-approved behavior. Wording may change only when the behavior is clearly retained or improved.

## Validation

Run the repo's formatting or markdown checks before commit. If the repo has no policy formatter, run `git diff --check` and reread every changed policy or skill file.

For repo-skill changes, verify each changed `description` triggers only the intended work.

Before shipping, record the policy gates in review notes: line-referenced check for lost protections, proof that the user request is enforced, proof that mandate and privacy constraints are met, contradiction and duplicate-rule scan results, and a judgment that the change improves agent efficiency.
