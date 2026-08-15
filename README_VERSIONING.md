# Verzování – rychlý odkaz

Releasy řídí **Release PR model** (ne commit-hook bump ani ruční tagy).

- Policy: **[RELEASE_POLICY.md](RELEASE_POLICY.md)**
- Kde žije verze / zobrazení v app: **[VERSIONING.md](VERSIONING.md)**

Běžné PR do `master` musí mít přesně jeden label `semver:*`. Verzi v `pyproject.toml` bumpuje až merge Release PR.
