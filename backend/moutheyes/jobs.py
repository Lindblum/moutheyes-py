"""In-memory job queue. Jobs run one at a time on a worker thread; the API polls them."""
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from . import pipeline, storage
from .config import STILL_EXT

log = logging.getLogger("moutheyes")

# relative cost of each pipeline stage, used to turn per-stage progress into one overall bar
STAGE_WEIGHT = {"animating": 35, "tracking": 20, "compositing": 35, "encoding": 10}
MAX_KEPT = 100

_jobs = {}
_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="moutheyes")


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
        stages = [s for s in STAGE_WEIGHT if still or s != "animating"]
        total, start, self._spans = sum(STAGE_WEIGHT[s] for s in stages), 0, {}
        for s in stages:
            self._spans[s] = (start / total, STAGE_WEIGHT[s] / total)
            start += STAGE_WEIGHT[s]

    def report(self, stage, frac):
        start, width = self._spans[stage]
        self.stage, self.progress = stage, start + width * frac

    def to_dict(self):
        return dict(id=self.id, filename=self.filename, status=self.status, stage=self.stage,
                    progress=round(self.progress, 4), reaction=self.reaction,
                    error=self.error, result=self.result)


def _run(job, src, mouth_scale, reaction, seed):
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
        job.progress, job.status = 1.0, "done"
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
