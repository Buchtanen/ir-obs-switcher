#!/usr/bin/env python3
"""
Automatické zvýšení verze podle commit message prefixu.

Použití:
    python scripts/bump_version.py <commit_message>

Prefixy:
    fix:  → zvýší PATCH (0.3.0 → 0.3.1)
    feat: → zvýší MINOR (0.3.0 → 0.4.0)
    rel:  → zvýší MAJOR (0.3.0 → 1.0.0)
"""
import re
import sys
from pathlib import Path

# Cesty k souborům s verzí
PROJECT_ROOT = Path(__file__).parent.parent
INIT_FILE = PROJECT_ROOT / "src" / "irswitch" / "__init__.py"
PYPROJECT_FILE = PROJECT_ROOT / "pyproject.toml"


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse version string to (major, minor, patch)."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    return tuple(int(x) for x in match.groups())


def format_version(major: int, minor: int, patch: int) -> str:
    """Format version tuple to string."""
    return f"{major}.{minor}.{patch}"


def bump_version(version_str: str, bump_type: str) -> str:
    """Bump version according to bump_type."""
    major, minor, patch = parse_version(version_str)
    
    if bump_type == "major":
        return format_version(major + 1, 0, 0)
    elif bump_type == "minor":
        return format_version(major, minor + 1, 0)
    elif bump_type == "patch":
        return format_version(major, minor, patch + 1)
    else:
        raise ValueError(f"Unknown bump_type: {bump_type}")


def get_current_version() -> str:
    """Get current version from __init__.py."""
    content = INIT_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError(f"Could not find __version__ in {INIT_FILE}")
    return match.group(1)


def update_version_files(new_version: str) -> None:
    """Update version in both __init__.py and pyproject.toml."""
    # Update __init__.py
    try:
        content = INIT_FILE.read_text(encoding="utf-8")
        old_content = content
        content = re.sub(
            r'__version__\s*=\s*["\'][^"\']+["\']',
            f'__version__ = "{new_version}"',
            content
        )
        if content != old_content:
            INIT_FILE.write_text(content, encoding="utf-8")
            print(f"✓ Updated {INIT_FILE.name}: {new_version}")
        else:
            print(f"⚠ Warning: {INIT_FILE.name} was not modified")
    except Exception as e:
        print(f"✗ Error updating {INIT_FILE}: {e}", file=sys.stderr)
        raise
    
    # Update pyproject.toml
    try:
        content = PYPROJECT_FILE.read_text(encoding="utf-8")
        old_content = content
        # Match version = "..." or version="..." (with or without spaces)
        content = re.sub(
            r'version\s*=\s*["\'][^"\']+["\']',
            f'version = "{new_version}"',
            content
        )
        if content != old_content:
            PYPROJECT_FILE.write_text(content, encoding="utf-8")
            print(f"✓ Updated {PYPROJECT_FILE.name}: {new_version}")
        else:
            print(f"⚠ Warning: {PYPROJECT_FILE.name} was not modified")
    except Exception as e:
        print(f"✗ Error updating {PYPROJECT_FILE}: {e}", file=sys.stderr)
        raise
    
    print(f"✓ Version bumped to {new_version}")


def detect_bump_type(commit_message: str) -> str | None:
    """Detect bump type from commit message prefix."""
    commit_message = commit_message.strip()
    
    # Check for prefix patterns (case-insensitive)
    if re.match(r"^rel:", commit_message, re.IGNORECASE):
        return "major"
    elif re.match(r"^feat:", commit_message, re.IGNORECASE):
        return "minor"
    elif re.match(r"^fix:", commit_message, re.IGNORECASE):
        return "patch"
    
    return None


def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: bump_version.py <commit_message>", file=sys.stderr)
        sys.exit(1)
    
    commit_message = sys.argv[1]
    
    # Detect bump type
    bump_type = detect_bump_type(commit_message)
    if not bump_type:
        # No version bump needed
        sys.exit(0)
    
    # Get current version
    try:
        current_version = get_current_version()
    except Exception as e:
        print(f"Error reading current version: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Bump version
    try:
        new_version = bump_version(current_version, bump_type)
    except Exception as e:
        print(f"Error bumping version: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Update files
    try:
        update_version_files(new_version)
    except Exception as e:
        print(f"Error updating version files: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Return new version for potential use in git hook (to stdout, errors to stderr)
    print(new_version)


if __name__ == "__main__":
    main()
