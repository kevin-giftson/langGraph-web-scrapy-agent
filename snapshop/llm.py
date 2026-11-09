"""Thin wrapper over Groq (cloud) and Ollama (offline) with automatic fallback.

Every call returns (text, model_label) so the UI can show which model did each step.
"""
import base64
import io
import json
import re

from PIL import Image

from . import config

PROVIDERS = ("auto", "groq", "ollama")


def _image_to_b64(path: str, max_side: int = 1024) -> str:
    img = Image.open(path).convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _groq(prompt: str, image_b64: str | None, json_mode: bool) -> tuple[str, str]:
    from groq import Groq

    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set")
    client = Groq(api_key=config.GROQ_API_KEY, timeout=60)
    model = config.GROQ_VISION_MODEL if image_b64 else config.GROQ_TEXT_MODEL
    content: list | str = prompt
    if image_b64:
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ]
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        temperature=0.2,
        max_tokens=4096,  # reasoning models (gpt-oss) spend tokens thinking before answering
        **kwargs,
    )
    return resp.choices[0].message.content, f"Groq · {model}"


def _ollama(prompt: str, image_b64: str | None, json_mode: bool) -> tuple[str, str]:
    import ollama

    client = ollama.Client(host=config.OLLAMA_HOST, timeout=180)
    model = config.OLLAMA_VISION_MODEL if image_b64 else config.OLLAMA_TEXT_MODEL
    msg = {"role": "user", "content": prompt}
    if image_b64:
        msg["images"] = [image_b64]
    try:
        resp = client.chat(
            model=model,
            messages=[msg],
            format="json" if json_mode else "",
            options={"temperature": 0.2},
        )
    except ConnectionError:
        raise RuntimeError("Ollama is not running. Install it from https://ollama.com/download, "
                           f"run `ollama pull {model}`, or switch Brain to Groq") from None
    except ollama.ResponseError as e:
        if e.status_code == 404:
            raise RuntimeError(f"Ollama model missing. Run: ollama pull {model}") from None
        raise
    return resp["message"]["content"], f"Ollama · {model} (offline)"


def ask(prompt: str, provider: str = "auto", image_path: str | None = None, json_mode: bool = False):
    """Run a prompt (optionally with an image). Returns (text, model_label)."""
    image_b64 = _image_to_b64(image_path) if image_path else None
    order = {"groq": [_groq], "ollama": [_ollama]}.get(provider, [_groq, _ollama])
    errors = []
    for fn in order:
        try:
            return fn(prompt, image_b64, json_mode)
        except Exception as e:  # fall through to the next provider
            errors.append(f"{fn.__name__[1:]}: {e}")
    raise RuntimeError("All LLM providers failed → " + " | ".join(errors))


def ask_json(prompt: str, provider: str = "auto", image_path: str | None = None) -> tuple[dict, str]:
    text, label = ask(prompt, provider, image_path, json_mode=True)
    return parse_json(text), label


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise
