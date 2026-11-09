"""Free web search (DuckDuckGo, no API key) to find a direct product page on each store."""
import re

from .stores import STORES

PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR)\s?([\d,]+(?:\.\d{1,2})?)", re.I)


def _ddgs():
    try:
        from ddgs import DDGS
    except ImportError:  # older package name
        from duckduckgo_search import DDGS
    return DDGS()


def parse_price(text: str | None, strict: bool = False) -> float | None:
    """Pull a rupee amount out of text. strict=True requires a ₹/Rs/INR marker."""
    if not text:
        return None
    m = PRICE_RE.search(text)
    if not m and strict:
        return None
    raw = m.group(1) if m else re.sub(r"[^\d.]", "", text)
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None
    return value if value >= 10 else None


def relevance(query: str, text: str) -> float:
    """Share of query words that appear in text (0..1)."""
    tokens = [t for t in re.split(r"\W+", query.lower()) if len(t) >= 2]
    hay = text.lower()
    return sum(t in hay for t in tokens) / len(tokens) if tokens else 0.0


def find_product_link(store: str, query: str) -> dict | None:
    """Search `<query> site:<domain>` and return the first hit that looks like a product page."""
    s = STORES[store]
    try:
        hits = _ddgs().text(f"{query} site:{s['domain']}", region="in-en", max_results=8) or []
    except Exception:
        return None
    for h in hits:
        url = h.get("href", "")
        if (s["domain"] in url and re.search(s["product_re"], url)
                and relevance(query, f"{url} {h.get('title', '')}") >= 0.5):
            return {
                "url": url,
                "title": h.get("title", ""),
                "snippet_price": parse_price(f"{h.get('title', '')} {h.get('body', '')}", strict=True),
            }
    return None
