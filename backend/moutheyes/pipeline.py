"""Moutheyes: replace a face's eyes with its own (animated) mouth.

- animate_still() turns a photo into a random <=2s reaction GIF.
- make_moutheyes() turns any animation (gif/mp4/webm/mov) into a moutheyes GIF.

Both take an optional progress(stage, fraction) callback.
"""
import shutil
import subprocess

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision
from PIL import Image, ImageSequence

from .config import MODEL


class NoFaceError(Exception):
    """No face could be detected in the input."""


def _no_progress(stage, frac):
    pass


# MediaPipe face-mesh landmark indices
LIPS_OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291,
              375, 321, 405, 314, 17, 84, 181, 91, 146]
MOUTH_L, MOUTH_R, LIP_TOP, LIP_BOT = 61, 291, 0, 17
INNER_TOP, INNER_BOT = 13, 14
# (outer corner, inner corner, top lid, bottom lid) for each eye
EYES = [(33, 133, 159, 145), (263, 362, 386, 374)]


# ---------------------------------------------------------------- landmarks
def make_landmarker(video):
    opts = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL)),
        running_mode=vision.RunningMode.VIDEO if video else vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.3,
        min_face_presence_confidence=0.3,
        min_tracking_confidence=0.3,
    )
    return vision.FaceLandmarker.create_from_options(opts)


def detect(landmarker, rgb, ts_ms=None):
    """Return (478,2) pixel landmarks or None. Upscales small frames first."""
    h, w = rgb.shape[:2]
    up = max(1.0, 480 / max(h, w))
    img = cv2.resize(rgb, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC) if up > 1 else rgb
    mpimg = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(img))
    res = landmarker.detect(mpimg) if ts_ms is None else landmarker.detect_for_video(mpimg, ts_ms)
    if not res.face_landmarks:
        return None
    return np.array([(p.x * w, p.y * h) for p in res.face_landmarks[0]], np.float32)


def track(frames, durations, progress=_no_progress):
    """Landmarks for every frame, gaps filled and jitter smoothed."""
    lms, t = [], 0
    with make_landmarker(video=True) as lm:
        for f, d in zip(frames, durations):
            lms.append(detect(lm, f, t))
            t += max(1, int(d))
            progress("tracking", len(lms) / len(frames))
    found = [i for i, l in enumerate(lms) if l is not None]
    if not found:
        return None
    for i in range(len(lms)):  # fill misses with nearest detection
        if lms[i] is None:
            lms[i] = lms[min(found, key=lambda j: abs(j - i))]
    arr = np.stack(lms)
    # light temporal smoothing (weighted 3-tap), but keep hard cuts intact
    sm = arr.copy()
    for i in range(1, len(arr) - 1):
        scale = np.linalg.norm(arr[i][MOUTH_L] - arr[i][MOUTH_R]) + 1e-6
        if max(np.abs(arr[i - 1] - arr[i]).mean(), np.abs(arr[i + 1] - arr[i]).mean()) < 0.25 * scale:
            sm[i] = 0.25 * arr[i - 1] + 0.5 * arr[i] + 0.25 * arr[i + 1]
    return sm


# ---------------------------------------------------------------- media io
def load_animation(path):
    """Return (list of RGB uint8 frames, list of durations in ms)."""
    if path.suffix.lower() == ".gif":
        im = Image.open(path)
        frames, durs = [], []
        for fr in ImageSequence.Iterator(im):
            frames.append(np.array(fr.convert("RGB")))
            durs.append(fr.info.get("duration", im.info.get("duration", 50)) or 50)
        durs = [d if d >= 20 else 100 for d in durs]  # browsers treat <20ms as 100ms
        return frames, durs
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    frames = []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
    return frames, [1000 / fps] * len(frames)


def save_gif(frames, durations, path, max_side=480):
    """High-quality GIF via ffmpeg palettegen/paletteuse."""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg was not found on PATH; it is required to encode GIFs")
    h, w = frames[0].shape[:2]
    fps = 1000 * len(frames) / sum(durations)
    scale = min(1.0, max_side / max(h, w))
    vf = (f"scale=trunc(iw*{scale}/2)*2:-2:flags=lanczos,split[a][b];"
          "[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", f"{fps:.4f}", "-i", "-",
           "-filter_complex", vf, "-loop", "0", str(path)]
    subprocess.run(cmd, input=b"".join(np.ascontiguousarray(f).tobytes() for f in frames), check=True)


# ---------------------------------------------------------------- still -> reaction animation
def ease(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


INNER_UPPER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308]
INNER_LOWER = [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308]
CHIN, BROWS = 152, (105, 334)
REACTIONS = ("gasp", "scream", "chatter", "double-take")


def reaction_params(rng, kind=None):
    """Pick a reaction (unless one is given) and randomize its timing/intensity."""
    kind = kind or str(rng.choice(REACTIONS))
    p = dict(
        kind=kind,
        seconds=rng.uniform(1.5, 2.0),
        onset=rng.uniform(0.12, 0.35),
        jaw=rng.uniform(0.22, 0.4),
        tremble_hz=rng.uniform(5, 10),
        tremble=rng.uniform(0.03, 0.1),
        bulge=rng.uniform(0.12, 0.32),
        brow=rng.uniform(0.1, 0.3),
        zoom=rng.uniform(0.03, 0.09),
        shake=rng.uniform(0.002, 0.007),
        tilt=rng.uniform(-4, 4),
        take_start=0.0,
    )
    if kind == "scream":
        p.update(jaw=rng.uniform(0.42, 0.55), tremble=rng.uniform(0.06, 0.12),
                 shake=rng.uniform(0.006, 0.012), zoom=rng.uniform(0.07, 0.12))
    elif kind == "chatter":
        p.update(jaw=rng.uniform(0.18, 0.32), tremble_hz=rng.uniform(4, 7), shake=rng.uniform(0.001, 0.004))
    elif kind == "double-take":
        p.update(take_start=rng.uniform(0.4, 0.6), onset=rng.uniform(0.1, 0.2))
    return p


def animate_still(path, out_path, rng, fps=20, kind=None, progress=_no_progress):
    """Random reaction (gasp / scream / chatter / double-take) built from warps of a single photo.

    The jaw is dropped as a solid piece: everything below the line between the lips (lower lip,
    lower teeth, chin) slides down while the upper lip and teeth stay put, and the gap that opens
    is filled with a shaded mouth-cavity colour sampled from the photo. The clip loops cleanly.
    Returns the reaction parameters that were used.
    """
    progress("animating", 0.0)
    rgb = np.array(Image.open(path).convert("RGB"))
    with make_landmarker(video=False) as lm:
        L = detect(lm, rgb)
    if L is None:
        raise NoFaceError(path.name)
    P = reaction_params(rng, kind)
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    mw = np.linalg.norm(L[MOUTH_R] - L[MOUTH_L])
    eye_c = [L[list(e)].mean(0) for e in EYES]
    eye_w = [np.linalg.norm(L[e[0]] - L[e[1]]) for e in EYES]
    face_c = L.mean(0)

    # line between the lips, as a function of x (midway between inner upper and inner lower lip)
    def curve(idx):
        pts = L[idx]
        o = np.argsort(pts[:, 0])
        return pts[o, 0], pts[o, 1]
    ux, uy = curve(INNER_UPPER)
    lx, ly = curve(INNER_LOWER)
    x0, x1 = L[78][0], L[308][0]
    mcx, half = (x0 + x1) / 2, (x1 - x0) / 2
    lip_bot, chin_y = L[LIP_BOT][1], L[CHIN][1]

    def split_at(x):
        return (np.interp(x, ux, uy) + np.interp(x, lx, ly)) / 2

    def mouth_shape(x):  # how far the gap opens per column: 0 at the corners, 1 at the centre
        u = np.clip((x - mcx) / half, -1, 1)
        return (1 - u * u) ** 0.6

    def jaw_disp(x, y, jaw):  # downward displacement of a jaw pixel at source (x, y)
        b = ease((y - lip_bot) / (0.4 * mw))  # near the lips follow the mouth shape, lower down move as a wide chin
        shape = (1 - b) * mouth_shape(x) + b * np.exp(-((x - mcx) / (0.9 * mw)) ** 2)
        fall = np.where(y < chin_y, 1.0, np.exp(-((y - chin_y) / (0.7 * mw)) ** 2))  # neck barely moves
        return jaw * shape * fall

    # cavity colour: darkest part of the existing mouth opening, else a generic dark red
    inner = np.zeros((h, w), np.uint8)
    cv2.fillPoly(inner, [np.concatenate([L[INNER_UPPER], L[INNER_LOWER][::-1]]).astype(np.int32)], 1)
    px = rgb[inner > 0].reshape(-1, 3).astype(np.float32)
    if len(px) > 30:
        lum = px.mean(1)
        cav = px[lum <= np.percentile(lum, 25)].mean(0)
    else:
        cav = np.array([60, 20, 22], np.float32)
    cav = np.minimum(cav, [90, 45, 45])

    n = int(P["seconds"] * fps)
    T = n / fps
    shake = rng.normal(0, 1, (n, 2))
    frames = []
    for i in range(n):
        t = i / fps
        ts = t - P["take_start"]
        env = ease(ts / P["onset"]) * (1 - ease((t - (T - 0.5)) / 0.45))
        wob = np.sin(2 * np.pi * P["tremble_hz"] * t)
        if P["kind"] == "chatter":
            jaw = env * P["jaw"] * (0.55 + 0.45 * wob) * mw
        else:
            jaw = env * P["jaw"] * (1 + P["tremble"] / P["jaw"] * wob) * mw
        jaw = max(jaw, 0.0)

        # camera (inverse): zoom toward face, shake, tilt; double-take adds a sideways jolt first
        z = 1 + P["zoom"] * env
        jit = shake[i] * P["shake"] * max(h, w) * env
        ang = np.radians(P["tilt"] * env)
        if P["kind"] == "double-take" and t < P["take_start"] + 0.1:
            jolt = np.sin(np.pi * min(t / (P["take_start"] + 0.1), 1)) * 0.04 * w
            jit = jit + [jolt * np.sin(2 * np.pi * t / (P["take_start"] + 0.1)), 0]
        dx, dy = (xx - face_c[0]) / z, (yy - face_c[1]) / z
        mx = face_c[0] + np.cos(ang) * dx + np.sin(ang) * dy + jit[0]
        my = face_c[1] - np.sin(ang) * dx + np.cos(ang) * dy + jit[1]

        # brows lift, eyes bulge (inverse radial magnification)
        for c, ew, bi in zip(eye_c, eye_w, BROWS):
            bc = L[bi]
            my = my + P["brow"] * ew * env * np.exp(-((mx - bc[0]) ** 2 + (my - bc[1]) ** 2) / (0.9 * ew) ** 2)
            r2 = (mx - c[0]) ** 2 + (my - c[1]) ** 2
            k = 1 - P["bulge"] * env * np.exp(-r2 / (0.9 * ew) ** 2)
            mx, my = c[0] + (mx - c[0]) * k, c[1] + (my - c[1]) * k

        # jaw drop (inverse): solve y = ys + D(x, ys) for ys below the lip line
        split = split_at(mx)
        gap = jaw * mouth_shape(mx) * ((mx > x0) & (mx < x1))
        below = my >= split
        ys = my - jaw_disp(mx, my, jaw)
        for _ in range(4):
            ys = my - jaw_disp(mx, np.maximum(ys, split), jaw)
        ys = np.maximum(ys, split)
        src_y = np.where(below, ys, my)
        frame = cv2.remap(rgb, mx.astype(np.float32), src_y.astype(np.float32),
                          cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT).astype(np.float32)

        # fill the opened gap with a shaded cavity (darkest mid-gap), anti-aliased edges
        tpos = (my - split) / np.maximum(gap, 1e-3)
        cov = np.clip(my - split + 0.5, 0, 1) * np.clip(split + gap - my + 0.5, 0, 1) * (gap > 0.5)
        shade = 0.45 + 0.55 * np.abs(2 * np.clip(tpos, 0, 1) - 1) ** 2
        cav_px = cav[None, None, :] * shade[..., None]
        frame = frame * (1 - cov[..., None]) + cav_px * cov[..., None]
        frames.append(np.clip(frame, 0, 255).astype(np.uint8))
        progress("animating", 0.7 * (i + 1) / n)  # the full-size GIF save below is the other ~30%
    save_gif(frames, [1000 / fps] * n, out_path, max_side=max(h, w))
    return P


# ---------------------------------------------------------------- skin colour
# upper cheeks, forehead and nose bridge: skin on most faces, clear of lips, eyes, brows and beards
SKIN_POINTS = [50, 280, 101, 330, 117, 346, 151, 108, 337, 6, 197]


def skin_model(frames, lms, samples=8):
    """Skin colour of the face, pooled over a few frames: Lab chroma mean/covariance + lightness range.

    Returns None when too little skin could be sampled (then nothing is gated on it).
    """
    px = []
    for i in np.linspace(0, len(frames) - 1, min(samples, len(frames))).astype(int):
        rgb, L = frames[i], lms[i]
        h, w = rgb.shape[:2]
        r = max(1, int(0.06 * np.linalg.norm(L[EYES[0][0]] - L[EYES[1][0]])))
        disc = np.zeros((h, w), np.uint8)
        for x, y in L[SKIN_POINTS].astype(int):
            cv2.circle(disc, (int(x), int(y)), r, 1, -1)
        px.append(cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)[disc > 0])
    lab = np.concatenate(px).astype(np.float32)
    if len(lab) < 50:
        return None
    # drop outliers (hair over the forehead, glasses, highlights) by distance from the median
    med = np.median(lab, 0)
    mad = 1.4826 * np.median(np.abs(lab - med), 0) + 2
    lab = lab[(np.abs(lab - med) < 3 * mad).all(1)]
    if len(lab) < 50:
        return None
    ab = lab[:, 1:]
    cov = np.cov(ab.T) + 9 * np.eye(2)  # floor of ~3 units: flat or palette-quantized GIFs are near-degenerate
    lo, hi = np.percentile(lab[:, 0], [5, 95])
    return dict(ab=ab.mean(0), icov=np.linalg.inv(cov), lo=lo, hi=hi, margin=max(12.0, 0.3 * (hi - lo)))


def skin_prob(skin, rgb):
    """0..1 per pixel of an RGB uint8 image: how well it matches the skin model."""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    d = lab[..., 1:] - skin["ab"]
    dist = np.sqrt(np.einsum("...i,ij,...j->...", d, skin["icov"], d))
    chroma = np.clip((4.5 - dist) / 1.5, 0, 1)  # full weight within 3 sigma, none past 4.5
    off = np.maximum(skin["lo"] - lab[..., 0], lab[..., 0] - skin["hi"])
    light = np.clip(1 - off / skin["margin"], 0, 1)
    return chroma * light


# ---------------------------------------------------------------- moutheyes compositing
def moutheye_frame(rgb, L, mouth_scale=1.35, skin=None):
    h, w = rgb.shape[:2]
    out = rgb.astype(np.float32)
    ml, mr = L[MOUTH_L], L[MOUTH_R]
    mw = np.linalg.norm(mr - ml)
    mouth_ang = np.degrees(np.arctan2(mr[1] - ml[1], mr[0] - ml[0]))
    lips = L[LIPS_OUTER]
    mc = lips.mean(0)

    # soft mouth mask in source space: lip hull dilated into surrounding skin, then feathered.
    # Past a thin border that always comes along (lip edges aren't skin-coloured), the dilated
    # margin only keeps skin, so shadow, stubble or background there doesn't ring the new mouths.
    mask = np.zeros((h, w), np.float32)
    hull = cv2.convexHull(lips.astype(np.int32))
    cv2.fillConvexPoly(mask, hull, 1.0)

    def grow(m, pad):
        return cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pad + 1, 2 * pad + 1)))
    pad = max(2, int(0.12 * mw))
    core, mask = grow(mask, max(1, int(0.04 * mw))), grow(mask, pad)
    if skin is not None:
        x, y, bw, bh = cv2.boundingRect(hull)
        x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad)
        p = np.zeros((h, w), np.float32)
        p[y0:y1, x0:x1] = skin_prob(skin, rgb[y0:y1, x0:x1])
        p = cv2.GaussianBlur(p, (0, 0), 0.03 * mw + 0.5)  # no speckle from dither or noise
        mask = np.maximum(core, mask * p)
    m = int(0.2 * mw) + 1
    mask[:m], mask[-m:], mask[:, :m], mask[:, -m:] = 0, 0, 0, 0
    # clear margin + zero border so a mouth near the frame edge still gets a feathered edge, not a hard seam
    mask = cv2.GaussianBlur(mask, (0, 0), 0.1 * mw + 1, borderType=cv2.BORDER_CONSTANT)
    mask = np.clip((mask - 0.04) / 0.96, 0, 1)  # kill faint blur tails that would ghost the whole frame

    # both eyes share the eye-line angle so the pair looks consistent
    e_centers = [L[[e[0], e[1]]].mean(0) for e in EYES]
    eye_ang = np.degrees(np.arctan2(e_centers[1][1] - e_centers[0][1], e_centers[1][0] - e_centers[0][0]))
    for (o, i_, top, bot), ec in zip(EYES, e_centers):
        ew = np.linalg.norm(L[o] - L[i_])
        ec = (L[o] + L[i_] + L[top] + L[bot]) / 4
        s = mouth_scale * ew / mw
        M = cv2.getRotationMatrix2D((float(mc[0]), float(mc[1])), -(eye_ang - mouth_ang), s)
        M[:, 2] += ec - mc
        patch = cv2.warpAffine(rgb, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT).astype(np.float32)
        a = cv2.warpAffine(mask, M, (w, h), flags=cv2.INTER_LINEAR)[..., None]

        # match the patch's skin tone to the skin around the eye (ring of the mask), skin pixels only
        ring = ((a[..., 0] > 0.05) & (a[..., 0] < 0.5))
        if skin is not None and ring.sum() > 20:
            both = np.minimum(skin_prob(skin, rgb[ring][:, None]),
                              skin_prob(skin, np.clip(patch[ring], 0, 255).astype(np.uint8)[:, None]))[:, 0]
            if (both > 0.5).sum() > 20:
                ring[ring] = both > 0.5
        if ring.sum() > 20:
            gain = (out[ring].mean(0) + 1) / (patch[ring].mean(0) + 1)
            patch *= np.clip(gain, 0.88, 1.14)
        out = out * (1 - a) + patch * a
    return np.clip(out, 0, 255).astype(np.uint8)


def make_moutheyes(path, out_path, mouth_scale=1.35, progress=_no_progress, eyes_path=None):
    """Write the moutheyes GIF; with eyes_path, also write the untouched frames as a matching GIF."""
    progress("tracking", 0.0)
    frames, durs = load_animation(path)
    if not frames:
        raise ValueError(f"could not read any frames from {path.name}")
    lms = track(frames, durs, progress)
    if lms is None:
        raise NoFaceError(path.name)
    skin = skin_model(frames, lms)
    out = []
    for f, l in zip(frames, lms):
        out.append(moutheye_frame(f, l, mouth_scale, skin))
        progress("compositing", len(out) / len(frames))
    progress("encoding", 0.0)
    save_gif(out, durs, out_path)
    if eyes_path is not None:
        save_gif(frames, durs, eyes_path)
