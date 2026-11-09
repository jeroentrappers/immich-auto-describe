"""Backfill descriptions for the EXISTING library (the plugin only fires on new uploads).

  python -m app.backfill --type IMAGE           # all photos missing a description
  python -m app.backfill --type VIDEO --limit 50
  python -m app.backfill --since-days 7         # only assets uploaded in the last week

Newest first. Resumable via out/backfill_<type>.txt; writes via the Immich API
(needs a write key). Concurrency = sum of provider concurrency across the fleet.
"""
import argparse
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import immich
from .config import PROVIDERS, DEFAULT_LANG, AI_PREFIX
from .fleet import Fleet
from .prompts import image_prompt, video_prompt, build_context, build_description

CKDIR = Path("out")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=["IMAGE", "VIDEO"], default="IMAGE")
    ap.add_argument("--language", default=DEFAULT_LANG)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--since-days", type=float, default=0,
                    help="only assets uploaded to Immich in the last N days (0 = whole library)")
    args = ap.parse_args()

    is_video = args.type == "VIDEO"
    fleet = Fleet(PROVIDERS)
    workers = sum(int(p.get("concurrency", 4)) for p in PROVIDERS)
    CKDIR.mkdir(exist_ok=True)
    ckpt = CKDIR / f"backfill_{args.type.lower()}.txt"
    done = set(ckpt.read_text().split()) if ckpt.exists() else set()
    print(f"{args.type}: {len(done)} already done; {workers} workers across {len(PROVIDERS)} providers")

    lock = threading.Lock()
    ck = open(ckpt, "a")
    filters = {}
    if args.since_days:
        since = datetime.now(timezone.utc) - timedelta(days=args.since_days)
        filters["createdAfter"] = since.isoformat()
        print(f"only assets uploaded since {since:%Y-%m-%d %H:%M} UTC")
    gen = immich.iter_assets(args.type, **filters)
    counters = {"done": 0, "skip": 0, "err": 0}
    t0 = time.time()
    stop = threading.Event()

    def nxt():
        with lock:
            if args.limit and counters["done"] >= args.limit:
                return None
            for a in gen:
                if a["id"] in done:
                    counters["skip"] += 1
                    continue
                if not args.overwrite and (a.get("exifInfo") or {}).get("description"):
                    counters["skip"] += 1
                    continue
                return a
            return None

    def worker():
        while not stop.is_set():
            a = nxt()
            if a is None:
                return
            aid = a["id"]
            try:
                exif = a.get("exifInfo") or {}
                loc = ", ".join(x for x in (exif.get("city"), exif.get("state"), exif.get("country")) if x)
                people = [p["name"] for p in (a.get("people") or []) if p.get("name")]
                ctx = build_context(exif.get("dateTimeOriginal"), loc or None, people)
                if is_video:
                    img = immich.video_montage(aid) or immich.thumbnail(aid)
                    prompt = video_prompt(args.language, ctx)
                else:
                    img = immich.thumbnail(aid)
                    prompt = image_prompt(args.language, ctx)
                res = fleet.analyze(img, prompt)
                desc = build_description(res, people, prefix=AI_PREFIX, is_video=is_video,
                                         lang=args.language)
                immich.set_description(aid, desc, res["tags"])
                with lock:
                    ck.write(aid + "\n"); ck.flush()
                    counters["done"] += 1
                    if counters["done"] % 25 == 0:
                        rate = counters["done"] / (time.time() - t0)
                        print(f"  {counters['done']} done ({rate:.2f}/s) | {res['caption'][:60]}")
                    if args.limit and counters["done"] >= args.limit:
                        stop.set()
            except Exception as e:
                with lock:
                    counters["err"] += 1
                print(f"  ! {a.get('originalFileName')}: {str(e)[:80]}")

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    ck.close()
    print(f"\nDONE — {counters['done']} generated, {counters['skip']} skipped, {counters['err']} errors")


if __name__ == "__main__":
    main()
