"""Batch mode: process everything in inputs/ without the web app.

Usage (from backend/):  ../.venv/Scripts/python -m moutheyes.cli [--force] [--seed N]

- Still images in inputs/ (jpg/png/webp/bmp) get a random <=2s reaction
  animation generated first, saved as inputs/<name>_anim.gif.
- Every animated input (gif/mp4/webm/mov) becomes outputs/<name>_moutheyes.gif.
"""
import sys

import numpy as np

from . import storage
from .config import ANIM_EXT, INPUTS, STILL_EXT
from .pipeline import NoFaceError, animate_still, make_moutheyes


def main():
    force = "--force" in sys.argv
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else None
    rng = np.random.default_rng(seed)
    storage.ensure_dirs()
    for p in sorted(INPUTS.iterdir()):
        if p.suffix.lower() in STILL_EXT:
            anim = storage.anim_path(p)
            if force or not anim.exists():
                print(f"animating still {p.name} -> {anim.name}")
                try:
                    P = animate_still(p, anim, rng)
                    print(f"  reaction: {P['kind']} ({P['seconds']:.1f}s)")
                except NoFaceError:
                    print(f"  ! no face found in {p.name}, skipping")
    for p in sorted(INPUTS.iterdir()):
        if p.suffix.lower() in ANIM_EXT:
            dst = storage.output_path(p)
            if force or not dst.exists():
                print(f"moutheyes {p.name} -> {dst.name}")
                try:
                    make_moutheyes(p, dst, eyes_path=storage.eyes_path(dst) if p.suffix.lower() != ".gif" else None)
                except NoFaceError:
                    print(f"  ! no face found in {p.name}, skipping")


if __name__ == "__main__":
    main()
