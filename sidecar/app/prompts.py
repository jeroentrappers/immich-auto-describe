"""Prompts + structured-output schema. Language is injected so any language works."""
import re

# Spelled-out language names: small models follow "write in Dutch" far more reliably
# than a bare language code.
LANG_NAMES = {"en": "English", "nl": "Dutch (Nederlands)", "de": "German (Deutsch)",
              "fr": "French (français)", "es": "Spanish (español)", "it": "Italian (italiano)"}

# Labels for the description body, per output language.
LABELS = {
    "en": {"objects": "Objects", "text": "Text", "people": "People", "video": "Video"},
    "nl": {"objects": "Objecten", "text": "Tekst", "people": "Personen", "video": "Video"},
}

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


def _language(lang: str) -> str:
    name = LANG_NAMES.get(lang, f"the language with code '{lang}'")
    return f"Write every field in {name}, never in another language. "


# Spelled out so providers without structured output (LM Studio's native API)
# still return the same object.
_JSON = "Reply with only a JSON object with the keys caption, tags (an array of strings) and text_in_image. "


def image_prompt(lang: str, context: str = "") -> str:
    return (
        f"{context}Analyze this photo. {_language(lang)}{_JSON}"
        "caption: one vivid, factual sentence describing the scene. "
        "tags: the main objects, people, setting and activity as short lowercase terms. "
        "text_in_image: short prominent legible text (titles, signs, labels; at most ~15 words; "
        "NOT a full transcription); otherwise an empty string."
    )


def video_prompt(lang: str, context: str = "") -> str:
    return (
        f"{context}This image is a grid of consecutive frames from ONE video, in chronological "
        f"order (left-to-right, top-to-bottom). Infer what happens. {_language(lang)}{_JSON}"
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


def build_description(res: dict, people: list[str], prefix: str = "", is_video: bool = False,
                      lang: str = "en") -> str:
    lb = LABELS.get(lang, LABELS["en"])
    parts = [res.get("caption", "").strip()]
    if res.get("tags"):
        parts.append(f"{lb['objects']}: " + ", ".join(res["tags"]) + ".")
    ocr = re.sub(r"\s+", " ", res.get("ocr") or "").strip()
    if ocr:
        parts.append(f'{lb["text"]}: "' + ocr + '".')
    if people:
        parts.append(f"{lb['people']}: " + ", ".join(people) + ".")
    body = " ".join(p for p in parts if p)
    return f"{prefix}{lb['video'] + ': ' if is_video else ''}{body}"
