# Fourteen owner-grouped issues, one branch per checklist item

Date: 2026-11-14

## Context

The first issue draft had 44 issues, one per unit of work. For two people over one week that was more tracking than work.

## Decision

- 14 issues: seven owned by the lead (#2–#8, platform and agent side), six by the second developer (#9–#14, surfaces and integrations) and one joint (#15).
- Each issue only touches paths its owner owns (see CODEOWNERS), so the two of us never edit the same files under one issue.
- Each issue has a checklist. Each checklist item names its branch (`<area>/<issue>-<slug>`) and becomes one short-lived PR. PRs say `Part of #n`; the last one says `Closes #n`.
- Where one person's work feeds the other's, the first item is a contract PR (models, 501 stubs, tool signatures, OpenAPI). The other person depends on that PR, not on the whole issue.
- Every issue has a "Coordination with the other developer" section. It lists the other person's branches this issue waits on and the branches of this issue the other person waits on. A PR from a branch in the second list puts `Unblocks #n` in its body, so the waiting issue gets a cross-reference when it lands.

## Consequences

- An issue can span phases. Its milestone is the phase it must be finished by, and its labels name every phase it touches.
- Progress shows in checklists, not in issue counts.
