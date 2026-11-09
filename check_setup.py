"""Pre-demo health check. Run this ~1 hour before going on stage."""
import sys

from snapshop import config


def check(name, fn):
    try:
        print(f"✅ {name}: {fn()}")
        return True
    except Exception as e:
        print(f"❌ {name}: {type(e).__name__}: {e}")
        return False


def groq_models():
    from groq import Groq

    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY missing in .env")
    ids = sorted(m.id for m in Groq(api_key=config.GROQ_API_KEY).models.list().data)
    for want in (config.GROQ_VISION_MODEL, config.GROQ_TEXT_MODEL):
        if want not in ids:
            print(f"   ⚠️ configured model '{want}' not available. Available: {', '.join(ids)}")
    return f"{len(ids)} models available"


def groq_chat():
    from snapshop import llm

    text, label = llm.ask("Say 'ready' in one word.", "groq")
    return f"{label} → {text.strip()[:30]}"


def ollama_models():
    import ollama

    names = [m.model for m in ollama.Client(host=config.OLLAMA_HOST).list().models]
    if config.OLLAMA_VISION_MODEL not in names:
        print(f"   ⚠️ run: ollama pull {config.OLLAMA_VISION_MODEL}")
    return ", ".join(names) or "no models pulled"


def web_search():
    from snapshop.search import find_product_link

    hit = find_product_link("Amazon", "boAt Airdopes 141")
    return hit["url"] if hit else "search works but no product link returned"


def browser():
    from snapshop.browser import browse_stores

    r = browse_stores([{"store": "Amazon", "query": "boAt Airdopes 141", "url": None}], True, print)[0]
    return f"{r['status']} · price={r['price']} · {r['url']}"


if __name__ == "__main__":
    ok = [check("Groq API key + models", groq_models), check("Groq chat", groq_chat),
          check("Ollama (offline)", ollama_models), check("Web search (DuckDuckGo)", web_search),
          check("Browser (Playwright)", browser)]
    print(f"\n{sum(ok)}/{len(ok)} checks passed")
    sys.exit(0 if all(ok) else 1)
