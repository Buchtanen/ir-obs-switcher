---
name: release-please-manifest
description: Keep .release-please-manifest.json in lockstep with pyproject.toml and the last vX.Y.Z tag. Use when creating a Release PR, bumping a version, tagging, cutting a release, when Release Please does not open a PR after merge to master, or when the manifest is behind pyproject/tag.
---

# Release Please manifest lockstep

Release Please’s **last released version** is `.release-please-manifest.json` `"."`, not `pyproject.toml` and not the latest git tag.

If those three diverge, the next Release PR **never opens**. That is what happened after 1.2.0 (manifest stayed at 1.1.0).

## Lockstep (required)

These three must be the same `X.Y.Z`:

| Source | Field |
|---|---|
| `pyproject.toml` | `[project].version` |
| `.release-please-manifest.json` | `"."` |
| Git tag | `vX.Y.Z` |

CI enforces pyproject == manifest (`scripts/check_release_please_lock.py`). Tag creation in `.github/workflows/release-please.yml` **refuses** to tag when they differ.

## What not to do

- Do **not** bump `project.version` in a normal feature/fix/docs PR. Label `semver:minor` / `semver:patch` / `semver:major` and let Release Please accumulate.
- Do **not** `git tag v…` (or use Create Release Tag) to “force” a release.
- Do **not** bump only `pyproject.toml`. Never leave the manifest behind.
- Do **not** lower `pyproject.toml` to match a stale manifest.

## After a `semver:minor`/`patch`/`major` merge

1. Wait for workflow **Release Please** on `master`.
2. Expect an open PR titled `chore(master): release X.Y.Z` with label `autorelease: pending`.
3. That PR already updates **pyproject + CHANGELOG + manifest**. Merge it (user approval). Tag `vX.Y.Z` follows.

Do **not** open a manual Release PR as the first reaction.

## Recovery: Release Please did not open a PR

Check the triad:

```text
pyproject.toml [project].version
.release-please-manifest.json "."
git tag --list "v*" --sort=-v:refname
```

Also check: repo **Settings → Actions → General → Allow GitHub Actions to create and approve pull requests**.

### Manifest behind pyproject or tag

Open `chore/sync-release-please-manifest` (`semver:none`):

- Set `.release-please-manifest.json` `"."` to the **already released** version (`pyproject` / tag without `v`).
- Do **not** change `pyproject.toml`.
- Do **not** tag.

After merge, re-run **Release Please**. It should open a Release PR for the **next** version from commits since that tag.

### Triad already matches, still no PR

1. Re-run **Release Please** on current `master`.
2. If an orphan branch `release-please--branches--master--components--irswitch` exists without an `autorelease: pending` PR: delete that branch, re-run.
3. Manual Release PR is **last resort** (permissions OK, lockstep OK, RP still silent):

   Bump **all three** to the **same next** version in one PR:

   - `pyproject.toml` `[project].version`
   - `.release-please-manifest.json` `"."`
   - `CHANGELOG.md` `## [X.Y.Z]`
   - title `chore(master): release X.Y.Z`
   - label `autorelease: pending` (exempt from semver-label CI)
   - **do not tag first** — tag comes from the workflow after merge, and only if pyproject == manifest

## Normal PRs vs version files

| PR kind | pyproject version | manifest |
|---|---|---|
| Feature/fix/docs | unchanged | unchanged |
| Manifest sync (stuck RP) | unchanged | set to pyproject/tag |
| Release PR (`autorelease: pending`) | next version | same as pyproject |

## Labels

- Feature work that should ship: `semver:minor` / `patch` / `major` — **not** a version bump in that PR.
- Sync-only: `semver:none`.
- Release PR: `autorelease: pending` only — do not add `semver:*`.

## Reference

- [RELEASE_POLICY.md](../../../RELEASE_POLICY.md)
- [VERSIONING.md](../../../VERSIONING.md)
- [pr-semver-label](../pr-semver-label/SKILL.md)
