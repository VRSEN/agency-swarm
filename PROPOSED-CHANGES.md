# Proposed changes to AGENTS.md

Result: 76 lines down to 45 (limit 100). Three new skills under `.claude/skills/`: `review`, `release`, `sdk-upgrade`. `CLAUDE.md` is still a symlink to `AGENTS.md`.

Why each old rule moved where it did. "Obvious" means a good engineer does it without being told; "internal" means it described how the maintainer's own agents work, not how to work on this repository.

## Head

- Core principle: **kept**, unchanged, still first.
- "This file adds repository rules to the machine-global policy": **removed**. Internal; leaks a private setup into a public repo.
- New pointer line to the three skills: **added**, so agents find the procedures.

## 1. SDK first

- 1.1 (read pinned SDK before coding) and 1.2 (use it, never copy): **merged** into 1.1. Same instruction, half the words.
- 1.3 (custom code only when SDK lacks it; PR names what you checked): **kept** as 1.2.
- 1.4 (wrappers name the SDK class and support every feature or list gaps): **kept** as 1.3, with one sentence on why (the compaction miss). This is the rule that would have caught that bug.
- 1.5 (delete our code when the SDK adds it; deprecate if it breaks the public API, remove in 2.1): **merged** into 1.4 and shortened. The deprecation-and-2.1 clause is gone because backward compatibility is no longer a goal by itself.
- 1.6 (propose deletion when custom code differs accidentally): **removed**. Already implied by 1.3 and 1.4; an agent that reads them does this.
- 1.7 (SDK upgrade changelog check): **moved to skill `sdk-upgrade`**. A multi-step procedure.
- 1.8 (vendor integrations stay out): **kept** as 1.5. Standing maintainer decision that is not obvious to a new agent.

## 2. Users and public actions

- 2.1 (keep backward compatibility, breaking only in a major version): **rewritten** per the maintainer's instruction. Compatibility is not a goal; bump versions, document, no shims; escalate only breakage for users who cannot upgrade.
- 2.2 (maintainer approves every public GitHub action): **kept**. Not obvious to an agent and the cost of getting it wrong is public.
- 2.3 (no AI attribution): **kept**. Agents add trailers by default unless told not to.

## 3. Repository basics

- 3.1 (default branch is main): **removed**. Obvious from git.
- 3.2 (CLAUDE.md symlink): **kept** as 3.3. An agent would otherwise create a second file.
- 3.3 (project venv and make targets): **kept** as 3.1.
- 3.4 (make format, make check): **kept** as 3.2.
- 3.5 (make ci before release, before a broad change, after upgrades): **split**. "Before a broad change" stays in 3.2; the release and upgrade cases live in their skills.
- 3.6 (make prime): **removed**. A tool hint, not a rule; `make help` lists it.

## 4. Review

- 4.1 (review by a different model): **moved to skill `review`**. Internal workflow, not a repo rule.
- 4.2 (strongest model for AGENTS.md and release commits): **moved to skill `review`**.
- 4.3 (save pre-release review output with release evidence): **removed**. This is the rule that forced evidence sections into deliverables.

## 5. Code

- 5.1 (Python 3.12+, develop on 3.13): **kept** as 4.1.
- 5.2 (type every function, X | Y): **merged** into 4.2.
- 5.3 (enforce types at boundaries, no Any, no fallbacks, no type ignores): **merged** into 4.2. Not obvious; agents reach for fallbacks.
- 5.4 (use SDK and dependency types, read code next to your change): **merged** into 4.2; the "read the code next to your change" half **removed** as obvious.
- 5.5 (imports at top, circular import by restructuring): **kept** as 4.3.
- 5.6 (files under 500 lines, shrink when editing): **merged** with 5.7 into 4.4. The "unless the maintainer approves" clauses are gone; the maintainer can always approve an exception.
- 5.7 (methods 10 to 40 lines, under 100): **merged** into 4.4 as "under 40". The 10-line floor and 100-line cap added nothing.
- 5.8 (one name for one thing): **kept** as 4.5.
- 5.9 (update lockfiles with dependency changes): **kept** as 4.6. Agents forget this.

## 6. Tests

- 6.1 (test layout mirrors source): **merged** into 5.1.
- 6.2 (90% coverage, tests under 100 lines): **merged** into 5.1; the 100-line test cap **removed** as covered by 4.4.
- 6.3 (real framework objects for messaging and OpenClaw, not mocks): **kept** as 5.2.
- 6.4 (e2e regression test for each behavior change): **kept** as 5.3, reworded to "a test that fails without it".
- 6.5 (post-upgrade history round-trip test): **moved to skill `sdk-upgrade`**.

## 7. Documentation

- 7.1 (follow writing-docs.mdc): **kept** as 6.1.
- 7.2 (mintlify preview before large docs review): **merged** into 6.1 as one clause; the "say that the preview runs" reporting demand **removed**.
- 7.3 (no fork origins in user docs): **kept** as 6.2. Maintainer preference an agent cannot guess.

## 8. Releases

- 8.1 (clean review of the release commit): **moved to skill `release`**.
- 8.2 (real first message through the installed interface to the local test agency): **moved to skill `release`**, reworded as "run a real example agency from this repository end to end". The original named a private setup.
- 8.3 (launch or credential failure blocks the claim until root cause known): **moved to skill `release`**.
- 8.4 (no skipped tests, real keys): **moved to skill `release`**.
- 8.5 (release page lists every change with test evidence and a confidence level): **removed**. Evidence-section rule. The release skill asks for plain release notes instead.
- 8.6 (compare previous and new release per change): **removed**. Vague, unmeasurable, and the no-skipped-tests run plus the e2e check cover it.
- 8.7 (bugfix releases minimal): **moved to skill `release`**.
- 8.8 (ship AGENTS.md changes directly to main after maintainer approval): **removed**. Internal procedure about this file; 2.2 already covers the approval.
- 8.9 (breaking-change claims need file or commit evidence; a different model verifies before the Owner reads): **removed**. Evidence-section rule, and it named an internal reader. The release skill keeps the useful core: name what worked before and what changes now.
- 8.10 (deployed agency ships via GitHub push, never the platform editor): **moved to skill `release`** as its last line. Operational practice for one deployment, not a repo rule. The maintainer restored this rule two days ago; flagging it so the move is a conscious choice.

## Not changed, worth a look later

- `.claude/README.md` still says "See CLAUDE.md for complete orchestration details", which was true of an older CLAUDE.md. Out of scope here.
