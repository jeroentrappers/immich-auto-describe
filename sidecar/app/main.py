"""Auto-describe sidecar API.

POST /describe  { assetId, type, language?, context? }  -> { description, tags }
GET  /healthz                                           -> provider health

The Immich plugin calls /describe on AssetMetadataExtraction and writes the result
back via the workflow. The sidecar holds the model fleet + an Immich read key and
fetches the pixels itself (the plugin can't, since the host httpRequest is text-only).
"""
from fastapi import FastAPI
from pydantic import BaseModel

from . import immich
from .config import PROVIDERS, DEFAULT_LANG, AI_PREFIX
from .fleet import Fleet
from .prompts import image_prompt, video_prompt, build_context, build_description

app = FastAPI(title="immich-auto-describe")
fleet = Fleet(PROVIDERS)


class Context(BaseModel):
    date: str | None = None
    location: str | None = None


class DescribeRequest(BaseModel):
    assetId: str
    type: str = "IMAGE"          # IMAGE | VIDEO
    language: str = DEFAULT_LANG
    context: Context = Context()
    includePeople: bool = True


class DescribeResponse(BaseModel):
    description: str
    tags: list[str]
    caption: str


@app.get("/healthz")
def healthz():
    return {"providers": fleet.health()}


@app.post("/describe", response_model=DescribeResponse)
def describe(req: DescribeRequest):
    is_video = req.type.upper() == "VIDEO"
    people = immich.named_people(req.assetId) if req.includePeople else []
    ctx = build_context(req.context.date, req.context.location, people)

    if is_video:
        image = immich.video_montage(req.assetId)
        if image is None:
            image = immich.thumbnail(req.assetId)  # fallback to poster frame
        prompt = video_prompt(req.language, ctx)
    else:
        image = immich.thumbnail(req.assetId)
        prompt = image_prompt(req.language, ctx)

    res = fleet.analyze(image, prompt)
    description = build_description(res, people, prefix=AI_PREFIX, is_video=is_video,
                                    lang=req.language)
    return DescribeResponse(description=description, tags=res["tags"], caption=res["caption"])
