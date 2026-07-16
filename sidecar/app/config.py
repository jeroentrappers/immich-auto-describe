"""Configuration from environment.

PROVIDERS is a JSON array of inference backends (local and/or cloud), e.g.:

  [
    {"name":"local-1","base_url":"http://192.168.1.10:1234/v1",
     "model":"qwen/qwen3-vl-8b","concurrency":4,"max_dim":768},
    {"name":"openrouter","base_url":"https://openrouter.ai/api/v1",
     "model":"qwen/qwen2.5-vl-7b-instruct","api_key_env":"OPENROUTER_API_KEY",
     "concurrency":8,"max_dim":1024}
  ]
"""
import json
import os

IMMICH_URL = os.environ["IMMICH_URL"].rstrip("/")          # e.g. http://immich-server:2283/api
IMMICH_API_KEY = os.environ["IMMICH_API_KEY"]              # a read (backfill also needs write) key
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "en")
MAX_OUTPUT_TOKENS = int(os.environ.get("MAX_OUTPUT_TOKENS", "800"))
VIDEO_FRAMES = int(os.environ.get("VIDEO_FRAMES", "6"))
AI_PREFIX = os.environ.get("AI_PREFIX", "")               # optional marker, e.g. "[AI] "

PROVIDERS = json.loads(os.environ.get("PROVIDERS", "[]"))
for p in PROVIDERS:
    key_env = p.get("api_key_env")
    p["api_key"] = os.environ.get(key_env) if key_env else None
    p.setdefault("concurrency", 4)
    p.setdefault("max_dim", 768)

if not PROVIDERS:
    raise SystemExit("No PROVIDERS configured (set the PROVIDERS env var).")
