---
name: pr-semver-label
description: "Mandatory semver label on every PR to master for ir-obs-switcher. Use immediately when creating or updating pull requests — CI blocks merge without exactly one semver:* label."
---

# PR SemVer Label (required)

**Every PR to `master` must have exactly one semver label before CI can pass.**  
Workflow: `PR Policy (semver labels)` — first push without label fails; retry passes after label is added.

## When to apply

- **Immediately after** `ManagePullRequest` `create_pr` (same turn, before ending).
- After opening a PR for a subagent branch you orchestrate.
- When user says a PR was created without label — add label and note CI will retry or re-run.

## How to apply

Use `EditPullRequestLabels` with **exactly one** label:

| Label | When |
|---|---|
| `semver:minor` | `feat:` — new feature, backward compatible (default for Event Engine / overlay work) |
| `semver:patch` | `fix:` — bugfix, small compatible change |
| `semver:major` | Breaking change — title must include `!` or body `BREAKING CHANGE:` |
| `semver:none` | Docs-only, chore, refactor with no release impact |

```text
EditPullRequestLabels → add_labels: ["semver:minor"]  # example
```

**Do not** add multiple semver labels. Release PRs (`autorelease: pending`) are exempt — do not label those.

## Checklist (every PR)

1. Push branch
2. `ManagePullRequest` `create_pr`
3. **`EditPullRequestLabels`** — pick label from table (align with PR title prefix)
4. If label add fails (404/race): retry once after a few seconds
5. Optionally `update_pr` `draft: false` when CI green

## Common mistakes

- Creating PR and forgetting label → **semver-label CI failure** (known race on first run)
- Labeling only at end of turn after user notification
- Using `semver:patch` for `feat:` PRs without reason (allowed but prefer alignment)

## Reference

- [RELEASE_POLICY.md](../../RELEASE_POLICY.md)
- [.github/workflows/pr-policy.yml](../../.github/workflows/pr-policy.yml)
