"""A single inference provider over the OpenAI-compatible chat/completions API.

One code path covers local engines (Ollama, LM Studio, llama.cpp, vLLM) and cloud
APIs (OpenRouter, OpenAI, Together, ...). Cloud auth is a Bearer token.
"""
import base64
import io
import json

import httpx
from PIL import Image

from .config import MAX_OUTPUT_TOKENS
from .prompts import SCHEMA


class Provider:
    def __init__(self, spec: dict):
        self.name = spec["name"]
        self.base_url = spec["base_url"].rstrip("/")
        self.model = spec["model"]
        self.api_key = spec.get("api_key")
        self.max_dim = int(spec.get("max_dim", 768))
        self.concurrency = int(spec.get("concurrency", 4))
        self._client = httpx.Client(timeout=180.0)

    def _headers(self) -> dict:
        h = {"content-type": "application/json"}
        if self.api_key:
            h["authorization"] = f"Bearer {self.api_key}"
        return h

    def analyze(self, image: Image.Image, prompt: str) -> dict:
        im = image
        if self.max_dim and (im.width > self.max_dim or im.height > self.max_dim):
            im = im.copy()
            im.thumbnail((self.max_dim, self.max_dim))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]}],
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
            "response_format": SCHEMA,
        }
        r = self._client.post(f"{self.base_url}/chat/completions",
                              json=payload, headers=self._headers())
        r.raise_for_status()
        data = json.loads(r.json()["choices"][0]["message"]["content"])
        tags, seen = [], set()
        for t in data.get("tags", []):
            t = t.strip().lower()
            if t and t not in seen:
                seen.add(t); tags.append(t)
        return {
            "caption": (data.get("caption") or "").strip(),
            "tags": tags,
            "ocr": (data.get("text_in_image") or "").strip(),
        }

    def healthy(self) -> bool:
        try:
            r = self._client.get(f"{self.base_url}/models", headers=self._headers(), timeout=8.0)
            return r.status_code < 500
        except Exception:
            return False
