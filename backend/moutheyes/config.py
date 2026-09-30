"""Filesystem layout and limits shared by the pipeline, API and CLI."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# inputs/ and outputs/ live here; override to keep media outside the repo
DATA = Path(os.environ.get("MOUTHEYES_DATA", ROOT)).resolve()
INPUTS, OUTPUTS = DATA / "inputs", DATA / "outputs"
MODEL = ROOT / "models" / "face_landmarker.task"
FRONTEND_DIST = ROOT / "frontend" / "dist"

STILL_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ANIM_EXT = {".gif", ".mp4", ".webm", ".mov"}
ANIM_SUFFIX = "_anim.gif"            # inputs/<name>_anim.gif, generated from a still
OUTPUT_SUFFIX = "_moutheyes.gif"     # outputs/<name>_moutheyes.gif
EYES_SUFFIX = "_eyes.gif"            # outputs/<name>_eyes.gif, untouched frames of a video source

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
