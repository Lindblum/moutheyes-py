"""Naming and lookup of files in inputs/ and outputs/."""
import glob
import re
import threading
from pathlib import Path
from urllib.parse import quote

from .config import ANIM_EXT, ANIM_SUFFIX, EYES_SUFFIX, INPUTS, OUTPUT_SUFFIX, OUTPUTS

_reserve_lock = threading.Lock()


def ensure_dirs():
    INPUTS.mkdir(parents=True, exist_ok=True)
    OUTPUTS.mkdir(parents=True, exist_ok=True)


def anim_path(still):
    return still.with_name(still.stem + ANIM_SUFFIX)


def output_path(anim):
    return OUTPUTS / (anim.stem + OUTPUT_SUFFIX)


def eyes_path(output):
    """Where the original ("eyes") frames of a moutheyes GIF are kept as a frame-matched GIF.

    Only written for video sources; a GIF source already is that file.
    """
    return output.with_name(output.name.removesuffix(OUTPUT_SUFFIX) + EYES_SUFFIX)


def _taken(stem):
    names = {stem, Path(stem + ANIM_SUFFIX).stem}
    if any(p.stem in names for p in INPUTS.iterdir()):
        return True
    return any((OUTPUTS / (n + OUTPUT_SUFFIX)).exists() for n in names)


def reserve_input(filename):
    """Create an empty, uniquely named file in inputs/ for an upload and return its path."""
    ext = Path(filename).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).stem).strip("._")[:80] or "upload"
    with _reserve_lock:
        n, cand = 1, stem
        while _taken(cand):
            n += 1
            cand = f"{stem}-{n}"
        path = INPUTS / (cand + ext)
        path.touch()
    return path


def _url(kind, path):
    return f"/media/{kind}/{quote(path.name)}?v={int(path.stat().st_mtime)}"


def output_info(path):
    """JSON-ready description of a finished GIF, paired with its source animation if we still have it."""
    stem = path.name.removesuffix(OUTPUT_SUFFIX)
    src = next((p for p in sorted(INPUTS.glob(glob.escape(stem) + ".*"))
                if p.stem == stem and p.suffix.lower() in ANIM_EXT), None)
    # same frames as the output but with the eyes intact, as a GIF the frontend can step through
    eyes = eyes_path(path)
    if src and src.suffix.lower() == ".gif":
        eyes_url = _url("inputs", src)
    else:
        eyes_url = _url("outputs", eyes) if eyes.is_file() else None
    st = path.stat()
    return dict(name=path.name, url=_url("outputs", path),
                source_url=_url("inputs", src) if src else None, eyes_url=eyes_url,
                size=st.st_size, created=st.st_mtime)


def list_outputs():
    files = sorted(OUTPUTS.glob("*" + OUTPUT_SUFFIX), key=lambda p: p.stat().st_mtime, reverse=True)
    return [output_info(p) for p in files]


def find_output(name):
    """Path of outputs/<name>, or None if it isn't one of our GIFs."""
    if Path(name).name != name or not name.endswith(OUTPUT_SUFFIX):
        return None
    path = OUTPUTS / name
    return path if path.is_file() else None
