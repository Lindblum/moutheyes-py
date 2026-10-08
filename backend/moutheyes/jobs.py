"""In-memory job queue. Jobs run one at a time on a worker thread; the API polls them."""
import logging
import math
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import pipeline, storage, timing
from .config import STILL_EXT

log = logging.getLogger("moutheyes")

MAX_KEPT = 100
STAGES = ("animating", "tracking", "compositing", "encoding")

_jobs = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moutheyes")


def _soft(x):
    """Elapsed/estimated time -> stage fraction: linear, then easing towards (never reaching) 1."""
    return x if x < 0.8 else 1 - 0.2 * math.exp(-(x - 0.8) / 0.2)


class Job:
    def __init__(self, filename, still):
        self.id = uuid.uuid4().hex[:12]
        self.filename = filename
        self.status = "queued"  # queued | running | done | error
        self.stage = None
        self.progress = 0.0
        self.reaction = None
        self.error = None
        self.result = None
        self._stages = [s for s in STAGES if still or s != "animating"]
        self._units = {}
        self._est = {}
        self._spans = {}
        self._t0 = self._frac_t = time.monotonic()
        self._frac = 0.0

    def plan(self, src, video):
        """Size up the source and lay out the bar so each stage gets its share of estimated time."""
        try:
            frames, mp = timing.probe(src)
        except Exception:
            frames, mp = 50, 0.15
        outputs = 2 if video else 1
        self._units = {s: timing.units(s, frames, mp, outputs) for s in self._stages}
        self._est = {s: max(0.2, timing.estimate(s, u)) for s, u in self._units.items()}
        total, start = sum(self._est.values()), 0.0
        for s in self._stages:
            self._spans[s] = (start / total, self._est[s] / total)
            start += self._est[s]

    def report(self, stage, frac):
        now = time.monotonic()
        if stage != self.stage:
            self._finish_stage(now)
            self._t0 = now
        # fields first, stage last: the API thread reads them while this runs
        self._frac, self._frac_t = frac, now
        self.stage = stage

    def _finish_stage(self, now):
        if self.stage is not None:
            timing.record(self.stage, self._units[self.stage], now - self._t0)

    def complete(self):
        self._finish_stage(time.monotonic())
        self.progress, self.status = 1.0, "done"

    def _stage_progress(self, now):
        """(fraction of the current stage done, its expected total seconds), moving with the clock."""
        est, f = self._est[self.stage], self._frac
        if f > 0:  # trust the stage's own pace more the further it has got
            est = (1 - f) * est + f * (self._frac_t - self._t0) / f
        return max(f, _soft((now - self._t0) / est)), est

    def to_dict(self):
        eta = None
        if self.status == "running" and self.stage:
            frac, est = self._stage_progress(time.monotonic())
            start, width = self._spans[self.stage]
            self.progress = max(self.progress, min(start + width * frac, 0.999))
            later = self._stages[self._stages.index(self.stage) + 1:]
            eta = round(max(0.0, est * (1 - frac)) + sum(self._est[s] for s in later), 1)
        return dict(id=self.id, filename=self.filename, status=self.status, stage=self.stage,
                    progress=round(self.progress, 4), eta=eta, reaction=self.reaction,
                    error=self.error, result=self.result)


def _run(job, src, mouth_scale, reaction, seed):
    job.plan(src, video=src.suffix.lower() not in STILL_EXT | {".gif"})
    job.status = "running"
    made = [src]
    try:
        if src.suffix.lower() in STILL_EXT:
            anim = storage.anim_path(src)
            made.append(anim)
            params = pipeline.animate_still(src, anim, np.random.default_rng(seed),
                                            kind=reaction, progress=job.report)
            job.reaction = params["kind"]
            src = anim
        dst = storage.output_path(src)
        eyes = storage.eyes_path(dst) if src.suffix.lower() != ".gif" else None
        made += [dst] + ([eyes] if eyes else [])
        pipeline.make_moutheyes(src, dst, mouth_scale=mouth_scale, progress=job.report, eyes_path=eyes)
        job.result = storage.output_info(dst)
        job.complete()
        return
    except pipeline.NoFaceError:
        job.error = "No face found. Try a clearer, more front-facing shot."
    except Exception as e:
        log.exception("job %s failed", job.id)
        job.error = str(e) or type(e).__name__
    job.status = "error"
    for p in made:  # don't leave a failed upload lying around in inputs/
        p.unlink(missing_ok=True)


def submit(src, filename, mouth_scale, reaction, seed):
    job = Job(filename, still=src.suffix.lower() in STILL_EXT)
    with _lock:
        _jobs[job.id] = job
        while len(_jobs) > MAX_KEPT:
            _jobs.pop(next(iter(_jobs)))
    _pool.submit(_run, job, src, mouth_scale, reaction, seed)
    return job


def get(job_id):
    with _lock:
        return _jobs.get(job_id)
