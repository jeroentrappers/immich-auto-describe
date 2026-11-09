"""A single inference provider over the OpenAI-compatible chat/completions API.

One code path covers local engines (Ollama, LM Studio, llama.cpp, vLLM) and cloud
APIs (OpenRouter, OpenAI, Together, ...). Cloud auth is a Bearer token.

``"api": "lmstudio"`` instead uses LM Studio's native /api/v1/chat, the only way
to switch off a reasoning model's thinking (``"reasoning": "off"``, the default
there). That is ~5x faster for captions; its OpenAI endpoint ignores the setting.
The native API has no structured output, so the reply is parsed leniently.
"""
import base64
import io
import json
import re

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
        self.api = spec.get("api", "openai")
        self.reasoning = spec.get("reasoning", "off")
        if self.api == "lmstudio":
            self.base_url = re.sub(r"/v1$", "", self.base_url)   # native API lives at the root
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
        data_url = f"data:image/jpeg;base64,{b64}"

        if self.api == "lmstudio":
            data = self._lmstudio(prompt, data_url)
        else:
            data = self._openai(prompt, data_url)
        raw_tags = data.get("tags") or []
        if isinstance(raw_tags, str):                 # "a, b, c" instead of ["a","b","c"]
            raw_tags = raw_tags.split(",")
        tags, seen = [], set()
        for t in raw_tags:
            t = str(t).strip().lower()
            if t and t not in seen:
                seen.add(t); tags.append(t)
        return {
            "caption": (data.get("caption") or "").strip(),
            "tags": tags,
            "ocr": (data.get("text_in_image") or "").strip(),
        }

    def _openai(self, prompt: str, data_url: str) -> dict:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            "max_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
            "response_format": SCHEMA,
        }
        r = self._client.post(f"{self.base_url}/chat/completions",
                              json=payload, headers=self._headers())
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])

    def _lmstudio(self, prompt: str, data_url: str) -> dict:
        payload = {
            "model": self.model,
            "input": [{"type": "text", "content": prompt},
                      {"type": "image", "data_url": data_url}],
            "reasoning": self.reasoning,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
        }
        r = self._client.post(f"{self.base_url}/api/v1/chat", json=payload, headers=self._headers())
        r.raise_for_status()
        text = "".join(o.get("content") or "" for o in r.json().get("output", [])
                       if o.get("type") == "message")
        return _parse_json_object(text)

    def healthy(self) -> bool:
        path = "/api/v1/models" if self.api == "lmstudio" else "/models"
        try:
            r = self._client.get(f"{self.base_url}{path}", headers=self._headers(), timeout=8.0)
            return r.status_code < 500
        except Exception:
            return False


def _parse_json_object(text: str) -> dict:
    """The first JSON object in a model reply, tolerating ```json fences and chatter."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"no JSON object in reply: {text[:120]!r}")
    return json.loads(m.group(0))
