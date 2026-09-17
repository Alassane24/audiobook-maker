"""Every machine-specific path and address, resolved in one place.

Why this module exists
----------------------
This app was built on one machine and grew absolute paths (`A:\\Cowork\\...`,
`D:\\Transfer\\Audiobooks`, a WinGet ffmpeg directory) and one Tailscale IP baked
into the source. That is fine for a single install and useless to anyone else -
the server fails at bind time on an address their machine does not have, and the
CLI scripts write to drives they do not have.

Resolution order for every setting: `local.env` at the repo root, then the
process environment, then a portable default that assumes a self-contained
checkout on loopback. `local.env` is gitignored, so each machine keeps its own
values and the committed defaults stay machine-neutral.

Run `python web/paths.py` to print what actually resolved and where each value
came from. See `local.env.example` for the full list.
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_ENV = REPO_ROOT / "local.env"

_WINDOWS = os.name == "nt"
_VENV_BIN = "Scripts" if _WINDOWS else "bin"
_EXE = ".exe" if _WINDOWS else ""


def _read_local_env(path: Path = None) -> dict:
    """Parse the gitignored local.env. A missing file is normal, not an error."""
    path = path or LOCAL_ENV
    values = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


_LOCAL = _read_local_env()


def setting(key: str, default: str = "") -> str:
    """local.env wins, then the process environment, then the default.

    local.env is checked first on purpose: it is the per-machine file a human
    edited, and it should not be silently overridden by an environment variable
    inherited from a parent process.
    """
    if key in _LOCAL and _LOCAL[key] != "":
        return _LOCAL[key]
    return os.environ.get(key) or default


def source_of(key: str) -> str:
    if key in _LOCAL and _LOCAL[key] != "":
        return "local.env"
    if os.environ.get(key):
        return "environment"
    return "default"


# --- where the server listens ---------------------------------------------
# Loopback by default. The original install binds a Tailscale IP on purpose so
# the app is reachable from a phone without being exposed to the local Wi-Fi;
# that address belongs in local.env, not in the repo.
HOST = setting("AUDIOBOOK_HOST", "127.0.0.1")
PORT = setting("AUDIOBOOK_PORT", "8765")
BASE_URL = f"http://{HOST}:{PORT}"

# --- where things get written ----------------------------------------------
JOBS_DIR = setting("AUDIOBOOK_JOBS_DIR", str(REPO_ROOT / "web" / "jobs"))
TRANSFER_DIR = setting("AUDIOBOOK_TRANSFER_DIR", str(REPO_ROOT / "out" / "audiobooks"))
SAMPLES_DIR = setting("AUDIOBOOK_SAMPLES_DIR", str(REPO_ROOT / "samples"))

# --- external tools ---------------------------------------------------------
# Empty means "already on PATH", which is what the README asks for.
FFMPEG_DIR = setting("AUDIOBOOK_FFMPEG_DIR", "")

# Tesseract language data. The repo does not ship tessdata/ (it is fetched, not
# authored), so use a copy beside the repo when one is there and otherwise let
# Tesseract fall back to its own install.
TESSDATA_DIR = setting("AUDIOBOOK_TESSDATA", str(REPO_ROOT / "tessdata"))
TESS_CONFIG = f'--tessdata-dir "{TESSDATA_DIR}"' if os.path.isdir(TESSDATA_DIR) else ""

# --- launcher ---------------------------------------------------------------
VENV_PYTHON = setting("AUDIOBOOK_PYTHON", str(REPO_ROOT / ".venv" / _VENV_BIN / f"python{_EXE}"))
CHROME_PROFILE = setting("AUDIOBOOK_CHROME_PROFILE", str(REPO_ROOT / ".chrome-profile"))


_KEYS = [
    ("AUDIOBOOK_HOST", HOST),
    ("AUDIOBOOK_PORT", PORT),
    ("AUDIOBOOK_JOBS_DIR", JOBS_DIR),
    ("AUDIOBOOK_TRANSFER_DIR", TRANSFER_DIR),
    ("AUDIOBOOK_SAMPLES_DIR", SAMPLES_DIR),
    ("AUDIOBOOK_FFMPEG_DIR", FFMPEG_DIR),
    ("AUDIOBOOK_TESSDATA", TESSDATA_DIR),
    ("AUDIOBOOK_PYTHON", VENV_PYTHON),
    ("AUDIOBOOK_CHROME_PROFILE", CHROME_PROFILE),
]


if __name__ == "__main__":
    print(f"repo root : {REPO_ROOT}")
    print(f"local.env : {LOCAL_ENV}  ({'present' if LOCAL_ENV.exists() else 'absent'})")
    print()
    width = max(len(k) for k, _ in _KEYS)
    for key, value in _KEYS:
        print(f"{key:<{width}}  {value or '(empty)'}   [{source_of(key)}]")
    print()
    print(f"server would listen on {BASE_URL}")
