"""Write the source snapshot to embed before PyInstaller starts."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from irswitch.build_identity import BUILD_IDENTITY  # noqa: E402

if __name__ == "__main__":
    if BUILD_IDENTITY["commit"] is None:
        raise SystemExit("Cannot resolve build commit; refusing an unidentified EXE")
    target = Path(sys.argv[1])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(BUILD_IDENTITY, indent=2) + "\n", encoding="utf-8")
