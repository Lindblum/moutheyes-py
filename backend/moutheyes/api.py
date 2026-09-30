"""HTTP API: upload a face, poll the job, browse finished GIFs.

Run from backend/:  ../.venv/Scripts/python -m uvicorn moutheyes.api:app --port 8000
"""
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from . import jobs, storage
from .config import ANIM_EXT, FRONTEND_DIST, INPUTS, MAX_UPLOAD_BYTES, OUTPUTS, STILL_EXT
from .pipeline import REACTIONS

storage.ensure_dirs()
app = FastAPI(title="Moutheyes")


@app.post("/api/jobs", status_code=202)
def create_job(file: UploadFile,
               mouth_scale: float = Form(1.35, ge=0.8, le=2.5),
               reaction: str = Form("random"),
               seed: int | None = Form(None, ge=0)):
    name = file.filename or ""
    if Path(name).suffix.lower() not in STILL_EXT | ANIM_EXT:
        raise HTTPException(415, "Unsupported file type. Use jpg, png, webp, bmp, gif, mp4, webm or mov.")
    if reaction != "random" and reaction not in REACTIONS:
        raise HTTPException(422, f"Unknown reaction '{reaction}'.")
    dst = storage.reserve_input(name)
    try:
        size = 0
        with dst.open("wb") as out:
            while chunk := file.file.read(1 << 20):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, f"File is larger than {MAX_UPLOAD_BYTES >> 20} MB.")
                out.write(chunk)
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    job = jobs.submit(dst, name, mouth_scale, None if reaction == "random" else reaction, seed)
    return job.to_dict()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found.")
    return job.to_dict()


@app.get("/api/gallery")
def gallery():
    return storage.list_outputs()


@app.delete("/api/gallery/{name}", status_code=204)
def delete_output(name: str):
    path = storage.find_output(name)
    if path is None:
        raise HTTPException(404, "No such GIF.")
    path.unlink()
    storage.eyes_path(path).unlink(missing_ok=True)


app.mount("/media/inputs", StaticFiles(directory=INPUTS), name="inputs")
app.mount("/media/outputs", StaticFiles(directory=OUTPUTS), name="outputs")
if FRONTEND_DIST.is_dir():  # production: serve the built React app from the same port
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
