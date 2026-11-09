"""Browser agent: opens every store in a real Chromium (Playwright), reads the price, takes a screenshot.

All stores are visited in parallel tabs. Run with headless=False on stage so the audience
can watch the browser work.
"""
import asyncio
import re
import sys
import threading
import time
from urllib.parse import urljoin

from . import config
from .search import parse_price, relevance
from .stores import STORES, search_url

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# Runs inside the page: gathers every price signal we know about.
EXTRACT_JS = r"""
(selectors) => {
  const out = {title: (document.querySelector('meta[property="og:title"]') || {}).content || document.title,
               sel: null, ld: null, meta: null, text: null};
  for (const s of selectors) {
    const el = document.querySelector(s);
    if (el && el.textContent.trim()) { out.sel = el.textContent.trim(); break; }
  }
  const prices = [];
  const walk = (o) => {
    if (!o || typeof o !== 'object') return;
    if (Array.isArray(o)) return o.forEach(walk);
    if (o.offers) {
      for (const f of [].concat(o.offers)) {
        const p = f && (f.price ?? f.lowPrice);
        if (p) prices.push(String(p));
      }
    }
    ['@graph', 'itemListElement', 'item'].forEach(k => o[k] && walk(o[k]));
  };
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { walk(JSON.parse(s.textContent)); } catch (e) {}
  }
  if (prices.length) out.ld = prices[0];
  const m = document.querySelector('meta[property="product:price:amount"], meta[property="og:price:amount"], meta[itemprop="price"]');
  if (m) out.meta = m.getAttribute('content');
  const t = document.body ? document.body.innerText : '';
  const r = t.match(/(₹|Rs\.?|INR)\s?[\d,]+(\.\d{1,2})?/);
  if (r) out.text = r[0];
  return out;
}
"""


def _pick_price(sig: dict) -> tuple[float | None, str]:
    for key, label in (("sel", "price tag"), ("ld", "structured data"), ("meta", "meta tag")):
        p = parse_price(sig.get(key))
        if p:
            return p, label
    p = parse_price(sig.get("text"), strict=True)
    return (p, "page text") if p else (None, "")


async def _best_product_link(page, store: str, query: str) -> str | None:
    """Among product links on a search page, pick the one whose URL/text matches the query best
    (skips sponsored or unrelated items that often appear first)."""
    links = await page.eval_on_selector_all(
        "a[href]", "els => els.map(e => [e.getAttribute('href'), (e.innerText || e.title || '').slice(0, 200)])")
    pattern = re.compile(STORES[store]["product_re"])
    best, best_score = None, 0.0
    for href, text in links:
        if href and pattern.search(href):
            score = relevance(query, f"{href} {text}")
            if score > best_score:
                best, best_score = href, score
    return urljoin(page.url, best) if best and best_score >= 0.5 else None


async def _open(page, url: str):
    """Navigate, but don't fail on slow sites: read whatever has loaded by the deadline."""
    await page.goto(url, wait_until="commit", timeout=config.PAGE_TIMEOUT_MS)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
    except Exception:
        pass
    await page.wait_for_timeout(2500)


async def _visit(context, job: dict, report) -> dict:
    store = job["store"]
    s = STORES[store]
    result = {"store": store, "url": job.get("url"), "title": "", "price": None,
              "price_source": "", "screenshot": None, "status": "not found"}
    page = await context.new_page()
    try:
        if not result["url"]:
            # No direct link from web search → use the store's own search and click the first product.
            report(f"🔎 {store}: searching on the site")
            await _open(page, search_url(store, job["query"]))
            link = await _best_product_link(page, store, job["query"])
            result["url"] = link or page.url
        if result["url"] != page.url:
            report(f"🌐 {store}: opening product page")
            await _open(page, result["url"])

        sig = await page.evaluate(EXTRACT_JS, s["selectors"])
        result["title"] = (sig.get("title") or "").strip()[:140]
        result["match"] = relevance(job["query"], f"{result['title']} {result['url']}") >= 0.5
        result["price"], result["price_source"] = _pick_price(sig)
        if result["price"] and result["url"] == page.url and not re.search(s["product_re"], page.url):
            result["price_source"] += " · search results (approx)"
        if not result["price"] and job.get("snippet_price"):
            result["price"], result["price_source"] = job["snippet_price"], "search snippet"

        shot = config.SCREENSHOT_DIR / f"{re.sub(r'\W+', '_', store)}_{int(time.time())}.jpg"
        await page.screenshot(path=str(shot), type="jpeg", quality=60)
        result["screenshot"] = str(shot)
        result["status"] = "ok" if result["price"] else "no price visible"
        report(f"{'✅' if result['price'] else '⚠️'} {store}: "
               f"{'₹{:,.0f}'.format(result['price']) if result['price'] else 'price not visible'}")
    except Exception as e:
        if job.get("snippet_price"):
            result["price"], result["price_source"] = job["snippet_price"], "search snippet"
        result["status"] = f"error: {type(e).__name__}"
        report(f"❌ {store}: {type(e).__name__} (site blocked or slow)")
    finally:
        if job.get("headless", True):
            await page.close()
    return result


async def _browse(jobs: list[dict], headless: bool, report) -> list[dict]:
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(user_agent=USER_AGENT, locale="en-IN",
                                            viewport={"width": 1280, "height": 860})
        for j in jobs:
            j["headless"] = headless
        results = await asyncio.gather(*[_visit(context, j, report) for j in jobs])
        if not headless:
            await asyncio.sleep(2)  # let the audience see the tabs before closing
        await browser.close()
    return list(results)


def browse_stores(jobs: list[dict], headless: bool, report) -> list[dict]:
    """Sync entry point. Runs Playwright on its own thread + event loop (Windows needs Proactor)."""
    box: dict = {}

    def runner():
        loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        try:
            box["result"] = loop.run_until_complete(_browse(jobs, headless, report))
        except Exception as e:
            box["error"] = e
        finally:
            loop.close()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]
    return box["result"]
