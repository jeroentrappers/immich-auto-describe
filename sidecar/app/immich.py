"""Minimal Immich client: fetch thumbnail / video frames, read people, write description."""
import base64
import io
import math
import subprocess
import tempfile
from pathlib import Path

import httpx
from PIL import Image

from .config import IMMICH_URL, IMMICH_API_KEY, VIDEO_FRAMES

_H = {"x-api-key": IMMICH_API_KEY}
_client = httpx.Client(timeout=60.0, headers=_H)


def thumbnail(asset_id: str, size: str = "preview") -> Image.Image:
    r = _client.get(f"{IMMICH_URL}/assets/{asset_id}/thumbnail", params={"size": size})
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGB")


def named_people(asset_id: str) -> list[str]:
    r = _client.get(f"{IMMICH_URL}/assets/{asset_id}")
    if not r.is_success:
        return []
    seen, out = set(), []
    for p in r.json().get("people", []) or []:
        n = (p.get("name") or "").strip()
        if n and n not in seen:
            seen.add(n); out.append(n)
    return out


def set_description(asset_id: str, description: str, tags: list[str] | None = None) -> None:
    _client.put(f"{IMMICH_URL}/assets/{asset_id}", json={"description": description}).raise_for_status()


def video_montage(asset_id: str, n: int = VIDEO_FRAMES, cols: int = 3, cell: int = 384) -> Image.Image | None:
    """Tile n frames sampled across the clip into one image (ffmpeg range-seek, no full download)."""
    url = f"{IMMICH_URL}/assets/{asset_id}/video/playback"
    hdr = f"x-api-key: {IMMICH_API_KEY}\r\n"
    try:
        pr = subprocess.run(["ffprobe", "-v", "error", "-headers", hdr, "-show_entries",
                             "format=duration", "-of", "csv=p=0", url],
                            capture_output=True, text=True, timeout=60)
        dur = float(pr.stdout.strip() or 0) or 10.0
    except Exception:
        dur = 10.0
    times = [dur * (0.05 + 0.90 * i / max(n - 1, 1)) for i in range(n)]
    frames = []
    with tempfile.TemporaryDirectory() as td:
        for i, t in enumerate(times):
            out = Path(td) / f"f{i}.jpg"
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-ss", f"{t:.2f}", "-headers", hdr,
                            "-i", url, "-frames:v", "1", "-vf", f"scale={cell}:-1", "-q:v", "3", str(out)],
                           capture_output=True, timeout=90)
            if out.exists() and out.stat().st_size:
                frames.append(Image.open(out).convert("RGB"))
    if not frames:
        return None
    rows = math.ceil(len(frames) / cols)
    w = max(f.width for f in frames); h = max(f.height for f in frames)
    grid = Image.new("RGB", (w * cols, h * rows), (20, 20, 20))
    for idx, f in enumerate(frames):
        r, c = divmod(idx, cols)
        grid.paste(f, (c * w, r * h))
    return grid


def iter_assets(asset_type: str = "IMAGE", page_size: int = 1000, **filters):
    """Assets of one type, newest first. ``filters`` go straight into the metadata
    search (e.g. ``createdAfter=<iso>`` for "uploaded since")."""
    page = 1
    while True:
        body = {"size": page_size, "page": page, "type": asset_type, "withExif": True, "withPeople": True,
                "order": "desc", **filters}
        data = _client.post(f"{IMMICH_URL}/search/metadata", json=body, timeout=120).json()
        chunk = data.get("assets", {})
        for a in chunk.get("items", []):
            yield a
        nxt = chunk.get("nextPage")
        if not nxt:
            break
        page = int(nxt)
