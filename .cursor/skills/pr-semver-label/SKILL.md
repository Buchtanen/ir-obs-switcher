---
name: pr-semver-label
description: "Mandatory semver label on every PR to master for ir-obs-switcher. Use immediately when creating or updating pull requests — CI blocks merge without exactly one semver:* label. Do not bump pyproject.toml version in a normal PR; keep .release-please-manifest.json in lockstep."
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

## Version files (do not bump here)

A `semver:minor` / `patch` / `major` label is **not** a version bump in this PR.

Do **not** edit `[project].version` in `pyproject.toml` on a normal PR. Release Please bumps these together in the Release PR:

- `pyproject.toml`
- `CHANGELOG.md`
- `.release-please-manifest.json` (`"."` must equal the new pyproject version)

If Release Please does not open a PR after merge, do **not** bump pyproject. Follow [release-please-manifest](../release-please-manifest/SKILL.md): sync the manifest to the last tag/pyproject (`semver:none`), then re-run Release Please.

A manual Release PR (last resort) must bump **pyproject + manifest + CHANGELOG** to the same version. Never tag first.

## Checklist (every PR)

1. Push branch
2. `ManagePullRequest` `create_pr`
3. **`EditPullRequestLabels`** — pick label from table (align with PR title prefix)
4. If label add fails (404/race): wait a few seconds, retry **label only**
5. If CI already failed on missing label: `gh run rerun <id>` (or re-run the semver-label job). **Do not** empty-commit to retrigger.
6. Optionally `update_pr` `draft: false` when CI green

## Common mistakes

- Creating PR and forgetting label → **semver-label CI failure** (known race on first run)
- Empty commit “to retrigger CI” after the label is already correct
- Labeling only at end of turn after user notification
- Using `semver:patch` for `feat:` PRs without reason (allowed but prefer alignment)
- Bumping `pyproject.toml` without `.release-please-manifest.json` → Release Please will not open the next Release PR
- Tagging `vX.Y.Z` while the manifest still has the previous version

## Reference

- [RELEASE_POLICY.md](../../RELEASE_POLICY.md)
- [release-please-manifest](../release-please-manifest/SKILL.md)
- [.github/workflows/pr-policy.yml](../../.github/workflows/pr-policy.yml)
