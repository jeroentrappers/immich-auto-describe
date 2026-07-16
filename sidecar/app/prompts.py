"""Prompts + structured-output schema. Language is injected so any language works."""

SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "photo_meta", "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "caption": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "text_in_image": {"type": "string"},
            },
            "required": ["caption", "tags", "text_in_image"],
            "additionalProperties": False,
        },
    },
}


def image_prompt(lang: str, context: str = "") -> str:
    return (
        f"{context}Analyze this photo and answer entirely in the language with code '{lang}'. "
        "caption: one vivid, factual sentence describing the scene. "
        "tags: the main objects, people, setting and activity as short lowercase terms. "
        "text_in_image: short prominent legible text (titles, signs, labels; at most ~15 words; "
        "NOT a full transcription); otherwise an empty string."
    )


def video_prompt(lang: str, context: str = "") -> str:
    return (
        f"{context}This image is a grid of consecutive frames from ONE video, in chronological "
        f"order (left-to-right, top-to-bottom). Infer what happens and answer in language '{lang}'. "
        "caption: one vivid sentence describing the event/action across the video (the progression). "
        "tags: the main subjects, people, action and setting as short lowercase terms. "
        "text_in_image: short prominent text (at most ~15 words), otherwise an empty string."
    )


def build_context(date: str | None, location: str | None, people: list[str]) -> str:
    bits = []
    if people:
        bits.append(f"People likely present: {', '.join(people)}.")
    if location:
        bits.append(f"Location: {location}.")
    if date:
        bits.append(f"Date: {date}.")
    if bits:
        bits.append("Use their names where appropriate. ")
    return " ".join(bits)


def build_description(res: dict, people: list[str], prefix: str = "", is_video: bool = False) -> str:
    parts = [res.get("caption", "").strip()]
    if res.get("tags"):
        parts.append("Objects: " + ", ".join(res["tags"]) + ".")
    if res.get("ocr"):
        parts.append('Text: "' + res["ocr"] + '".')
    if people:
        parts.append("People: " + ", ".join(people) + ".")
    body = " ".join(p for p in parts if p)
    return f"{prefix}{'Video: ' if is_video else ''}{body}"
