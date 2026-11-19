"""App version from the git tag (`git describe`); falls back to VERSION_FALLBACK without git."""
import subprocess
from pathlib import Path

VERSION_FALLBACK = "v1.0"

def get_version() -> str:
    try:
        out = subprocess.run(
            ["git", "tag", "--merged", "HEAD", "--sort=-v:refname"], cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, timeout=3)
        v = out.stdout.split("\n", 1)[0].strip()
        if out.returncode == 0 and v:
            return v
    except Exception:
        pass
    return VERSION_FALLBACK
