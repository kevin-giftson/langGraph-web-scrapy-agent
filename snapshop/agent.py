"""LangGraph agent: photo → product → pick stores → find links → browse → (refine?) → verdict."""
import operator
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from . import llm
from .browser import browse_stores
from .search import find_product_link
from .stores import STORES, catalog_text, default_stores

CATEGORIES = "electronics, appliances, fashion, footwear, beauty, furniture, home, toys, books, grocery, other"


class ShopState(TypedDict, total=False):
    image_path: str | None
    hint: str
    provider: str
    headless: bool
    num_stores: int
    product: dict
    query: str
    stores: list[str]
    links: dict
    results: list[dict]
    attempts: int
    verdict: str
    log: Annotated[list[str], operator.add]


# ---------- nodes ----------

def identify(state: ShopState) -> dict:
    hint = state.get("hint", "").strip()
    prompt = (
        "You are a shopping assistant for India. Identify the exact product"
        + (" in this photo" if state.get("image_path") else "")
        + (f". Extra hint from the user: {hint}" if hint else "")
        + ". Read any visible brand names, model numbers or text on the product/box. "
        "Reply with JSON only: {\"product_name\": str, \"brand\": str, \"model\": str, "
        f"\"category\": one of [{CATEGORIES}], \"key_features\": [up to 4 short strings], "
        "\"search_query\": short query a shopper would type on Amazon India (brand + model + key variant), "
        "\"confidence\": number 0-1}"
    )
    product, label = llm.ask_json(prompt, state["provider"], state.get("image_path"))
    query = product.get("search_query") or product.get("product_name") or hint
    conf = float(product.get("confidence") or 0)
    return {
        "product": product,
        "query": query,
        "attempts": 0,
        "log": [f"👁️ **Vision** ({label}) → **{product.get('product_name', '?')}** "
                f"· {product.get('category', '?')} · confidence {conf:.0%}",
                f"🧾 Search query: `{query}`"],
    }


def pick_stores(state: ShopState) -> dict:
    n = state.get("num_stores", 5)
    p = state["product"]
    prompt = (
        f"Product: {p.get('product_name')} (category: {p.get('category')}).\n"
        f"Pick exactly {n} Indian shopping sites from this catalog that are most likely to sell it:\n"
        f"{catalog_text()}\nAlways include Amazon and Flipkart. "
        "Reply JSON only: {\"stores\": [names exactly as in catalog], \"reason\": one short sentence}"
    )
    try:
        data, label = llm.ask_json(prompt, state["provider"])
        stores = [s for s in data.get("stores", []) if s in STORES]
        reason = data.get("reason", "")
    except Exception as e:
        stores, label, reason = [], "fallback", f"LLM failed ({e}); using defaults"
    for s in ["Amazon", "Flipkart"] + default_stores(p.get("category", ""), n):
        if s not in stores:
            stores.append(s)
    stores = list(dict.fromkeys(stores))[:n]
    return {"stores": stores,
            "log": [f"🧠 **Plan** ({label}) → {', '.join(stores)}" + (f" — _{reason}_" if reason else "")]}


def find_links(state: ShopState) -> dict:
    write = get_stream_writer()
    query = state["query"]

    def one(store):
        return store, find_product_link(store, query)

    with ThreadPoolExecutor(max_workers=5) as pool:
        links = dict(pool.map(one, state["stores"]))
    lines = []
    for store, hit in links.items():
        line = (f"🔗 {store}: product page found via web search" if hit
                else f"🔗 {store}: no direct link — browser will search the site")
        write(line)
        lines.append(line)
    return {"links": links, "log": [f"🌍 **Web search** (DuckDuckGo) for `{query}`"] + lines}


def browse(state: ShopState) -> dict:
    write = get_stream_writer()
    jobs = []
    for store in state["stores"]:
        hit = state["links"].get(store) or {}
        jobs.append({"store": store, "query": state["query"], "url": hit.get("url"),
                     "snippet_price": hit.get("snippet_price")})

    # Playwright runs on its own thread; relay its progress messages to the UI as they arrive.
    msgs: queue.Queue = queue.Queue()
    box: dict = {}

    def run():
        try:
            box["r"] = browse_stores(jobs, state.get("headless", True), msgs.put)
        except Exception as e:
            box["error"] = e

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    lines = []
    while worker.is_alive() or not msgs.empty():
        try:
            m = msgs.get(timeout=0.2)
        except queue.Empty:
            continue
        write(m)
        lines.append(m)
    if "error" in box:
        first_line = str(box["error"]).splitlines()[0]
        raise RuntimeError(f"Browser failed to start: {first_line}. "
                           "Fix: .venv\\Scripts\\python -m playwright install chromium")
    results = box.get("r", [])
    found = sum(1 for r in results if r["price"])
    return {"results": results,
            "log": [f"🖥️ **Browser agent** visited {len(jobs)} stores in parallel"] + lines
                   + [f"📊 Prices found on {found}/{len(jobs)} stores"]}


def needs_retry(state: ShopState) -> str:
    found = sum(1 for r in state.get("results", []) if r["price"])
    return "refine" if found < 2 and state.get("attempts", 0) < 1 else "compare"


def refine(state: ShopState) -> dict:
    prompt = (
        f"A shopping search for '{state['query']}' found almost no results on Indian stores. "
        f"Product: {state['product']}. Write a broader, simpler search query (brand + product type, "
        "drop rare details). Reply JSON only: {\"search_query\": str}"
    )
    data, label = llm.ask_json(prompt, state["provider"])
    q = data.get("search_query") or state["query"]
    return {"query": q, "attempts": state.get("attempts", 0) + 1,
            "log": [f"🔁 **Self-correction** ({label}): too few prices, retrying with `{q}`"]}


def compare(state: ShopState) -> dict:
    priced = sorted([r for r in state["results"] if r["price"]], key=lambda r: r["price"])
    if not priced:
        return {"verdict": "No store showed a price this time (sites may be blocking bots). "
                           "Use the links in the table to check manually.",
                "log": ["⚖️ **Compare**: nothing to compare"]}
    rows = "\n".join(f"- {r['store']}: ₹{r['price']:,.0f} — listing title: {r['title']}" for r in priced)
    prompt = (
        f"Product the user photographed: {state['product'].get('product_name')}.\n"
        f"Prices found:\n{rows}\n\n"
        "Write a short verdict in markdown (max 5 bullets): best deal and how much it saves vs the most "
        "expensive, flag any listing whose title looks like a different product/variant/accessory, "
        "and one practical buying tip. Use ₹. No preamble."
    )
    try:
        verdict, label = llm.ask(prompt, state["provider"])
    except Exception as e:
        best, worst = priced[0], priced[-1]
        verdict = (f"- Best price: **{best['store']} ₹{best['price']:,.0f}**\n"
                   f"- Saves ₹{worst['price'] - best['price']:,.0f} vs {worst['store']}")
        label = f"rule-based ({e})"
    return {"verdict": verdict, "log": [f"⚖️ **Verdict** written by {label}"]}


# ---------- graph ----------

def build_graph():
    g = StateGraph(ShopState)
    g.add_node("identify", identify)
    g.add_node("pick_stores", pick_stores)
    g.add_node("find_links", find_links)
    g.add_node("browse", browse)
    g.add_node("refine", refine)
    g.add_node("compare", compare)
    g.add_edge(START, "identify")
    g.add_edge("identify", "pick_stores")
    g.add_edge("pick_stores", "find_links")
    g.add_edge("find_links", "browse")
    g.add_conditional_edges("browse", needs_retry, {"refine": "refine", "compare": "compare"})
    g.add_edge("refine", "find_links")
    g.add_edge("compare", END)
    return g.compile()


graph = build_graph()
