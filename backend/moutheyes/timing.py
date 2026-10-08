"""Per-stage time estimates, learned from past jobs, so progress can advance between updates.

Each stage's cost is modelled as rate * units, where units scale with the work it does
(frames x megapixels, mostly). Rates start from defaults measured on a typical machine and
are nudged towards each finished stage's actual time, persisted in DATA/timings.json.
"""
import json
import logging
import threading

import cv2
from PIL import Image

from .config import DATA, STILL_EXT

log = logging.getLogger("moutheyes")

PATH = DATA / "timings.json"
STILL_FRAMES = 35          # a reaction is 1.5-2s at 20fps
DETECT_MP = 480 * 480 / 1e6  # detect() upscales small frames to this
ALPHA = 0.3                # weight of the newest observation in the running rate

# seconds per unit (see units()), measured on a mid-range desktop CPU
DEFAULT_RATE = {"animating": 2.3, "tracking": 0.055, "compositing": 0.22, "encoding": 0.12}

_lock = threading.Lock()
_rates = None


def probe(path):
    """(frames, megapixels) of an upload, cheaply, without decoding every frame."""
    if path.suffix.lower() in STILL_EXT:
        with Image.open(path) as im:
            return STILL_FRAMES, im.width * im.height / 1e6
    if path.suffix.lower() == ".gif":
        with Image.open(path) as im:
            return getattr(im, "n_frames", 1), im.width * im.height / 1e6
    cap = cv2.VideoCapture(str(path))
    try:
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        return frames, cap.get(cv2.CAP_PROP_FRAME_WIDTH) * cap.get(cv2.CAP_PROP_FRAME_HEIGHT) / 1e6
    finally:
        cap.release()


def units(stage, frames, mp, outputs=1):
    if stage == "animating":    # warp every frame of the reaction, then encode it
        return frames * mp
    if stage == "tracking":     # decode the frames, then a roughly fixed-size face-mesh pass each
        return frames * (mp + max(mp, DETECT_MP))
    if stage == "compositing":
        return frames * mp
    return frames * mp * outputs  # encoding: ffmpeg palettegen + paletteuse per GIF written


def _load():
    global _rates
    if _rates is None:
        _rates = dict(DEFAULT_RATE)
        try:
            saved = json.loads(PATH.read_text())
            _rates.update({k: float(v) for k, v in saved.items() if k in DEFAULT_RATE and v > 0})
        except FileNotFoundError:
            pass
        except (ValueError, TypeError, AttributeError, OSError):
            log.warning("ignoring unreadable %s", PATH)
    return _rates


def estimate(stage, n_units):
    with _lock:
        return _load()[stage] * n_units


def record(stage, n_units, seconds):
    """Fold one finished stage's actual time into its rate."""
    if n_units <= 0 or seconds <= 0:
        return
    with _lock:
        rates = _load()
        rates[stage] = (1 - ALPHA) * rates[stage] + ALPHA * seconds / n_units
        try:
            PATH.write_text(json.dumps(rates, indent=2))
        except OSError:
            log.warning("could not save %s", PATH)
