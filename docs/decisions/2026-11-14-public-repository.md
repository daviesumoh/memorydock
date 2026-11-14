# Public repository with a protected main branch

Date: 2026-11-14

## Context

We planned a private repository. Protecting a branch on a private repository needs a paid GitHub plan, and without protection the review rules would hold by convention only.

## Decision

The repository is public from the first commit. `main` is protected:

- changes land through a pull request with one approving review;
- the rule applies to admins too;
- no force-pushes or branch deletion;
- the `python` and `hygiene` CI checks are required once they have run on the first pull request.

The demo app repository is public as well. It holds fictional data only.

## Consequences

- Everything pushed is visible immediately. The privacy check (`make privacy`) runs in the pre-commit hook and in CI, and it ran on the tree before the first push.
- Commit metadata (author name and email) is public. Each developer chooses which email to commit with.
- Merges need the other developer's approval, so a pull request can't be merged while they're unavailable.
