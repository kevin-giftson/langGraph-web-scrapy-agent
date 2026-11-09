"""Catalog of Indian shopping sites the agent can choose from.

search:       the store's own search URL (used when web search finds no direct product link)
product_re:   what a product-page URL looks like on that store
selectors:    CSS selectors for the price, tried in order (regex fallback covers class renames)
categories:   what the store is good for; the agent uses this to pick stores
"""
from urllib.parse import quote_plus

STORES = {
    "Amazon": {
        "domain": "amazon.in",
        "search": "https://www.amazon.in/s?k={q}",
        "product_re": r"/(dp|gp/product)/[A-Z0-9]{10}",
        "selectors": [
            "#corePrice_feature_div .a-price .a-offscreen",
            "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
            ".a-price .a-offscreen",
            ".a-price-whole",
        ],
        "categories": ["all"],
    },
    "Flipkart": {
        "domain": "flipkart.com",
        "search": "https://www.flipkart.com/search?q={q}",
        "product_re": r"/p/itm",
        "selectors": ["div.Nx9bqj.CxhGGd", "div.Nx9bqj", "div._30jeq3._16Jk6d", "div._30jeq3"],
        "categories": ["all"],
    },
    "Croma": {
        "domain": "croma.com",
        "search": "https://www.croma.com/searchB?q={q}%3Arelevance&text={q}",
        "product_re": r"/p/\d+",
        "selectors": ["#pdp-product-price", "span.amount", ".new-price .amount"],
        "categories": ["electronics", "appliances"],
    },
    "Reliance Digital": {
        "domain": "reliancedigital.in",
        "search": "https://www.reliancedigital.in/products?q={q}",
        "product_re": r"/product/|/p/\d+",
        "selectors": [".pdp__offerPrice", ".product-price", ".price"],
        "categories": ["electronics", "appliances"],
    },
    "Vijay Sales": {
        "domain": "vijaysales.com",
        "search": "https://www.vijaysales.com/search-listing?q={q}",
        "product_re": r"/p/|/\d+/",
        "selectors": [".product__price--price", ".price", ".offer-price"],
        "categories": ["electronics", "appliances"],
    },
    "Tata CLiQ": {
        "domain": "tatacliq.com",
        "search": "https://www.tatacliq.com/search/?searchCategory=all&text={q}",
        "product_re": r"/p-mp",
        "selectors": ["h3.ProductDetailsMainCard__price", ".ProductDescription__discount", ".ProductDescription__price"],
        "categories": ["electronics", "fashion", "footwear", "home", "watches", "beauty"],
    },
    "Myntra": {
        "domain": "myntra.com",
        "search": "https://www.myntra.com/{dash}",
        "product_re": r"/\d+/buy",
        "selectors": [".pdp-price strong", "span.product-discountedPrice", ".product-price"],
        "categories": ["fashion", "footwear", "watches", "beauty", "bags"],
    },
    "Ajio": {
        "domain": "ajio.com",
        "search": "https://www.ajio.com/search/?text={q}",
        "product_re": r"/p/\d+",
        "selectors": [".prod-sp", ".price strong", ".price"],
        "categories": ["fashion", "footwear", "bags", "watches"],
    },
    "Nykaa": {
        "domain": "nykaa.com",
        "search": "https://www.nykaa.com/search/result/?q={q}",
        "product_re": r"/p/\d+",
        "selectors": [".css-1jczs19", "span.css-111z9ua", ".css-17x46n5 span"],
        "categories": ["beauty", "personal care", "fragrance"],
    },
    "JioMart": {
        "domain": "jiomart.com",
        "search": "https://www.jiomart.com/search/{q}",
        "product_re": r"/p/",
        "selectors": [".product-price .jm-heading-xs", "#price_section .final-price", ".jm-heading-xs"],
        "categories": ["grocery", "home", "electronics", "kitchen"],
    },
    "Pepperfry": {
        "domain": "pepperfry.com",
        "search": "https://www.pepperfry.com/site_product/search?q={q}",
        "product_re": r"/product/|\.html",
        "selectors": [".text-xxl", ".vip-offer-price", ".price"],
        "categories": ["furniture", "home", "decor"],
    },
    "FirstCry": {
        "domain": "firstcry.com",
        "search": "https://www.firstcry.com/search?q={q}",
        "product_re": r"/product-detail|/\d+/\d+",
        "selectors": ["#prod_price", ".prod-price", ".r1 span"],
        "categories": ["toys", "kids", "baby"],
    },
}

DEFAULT_PICKS = {
    "electronics": ["Amazon", "Flipkart", "Croma", "Reliance Digital", "Vijay Sales"],
    "appliances": ["Amazon", "Flipkart", "Croma", "Reliance Digital", "Vijay Sales"],
    "fashion": ["Amazon", "Flipkart", "Myntra", "Ajio", "Tata CLiQ"],
    "footwear": ["Amazon", "Flipkart", "Myntra", "Ajio", "Tata CLiQ"],
    "beauty": ["Amazon", "Flipkart", "Nykaa", "Tata CLiQ", "Myntra"],
    "furniture": ["Amazon", "Flipkart", "Pepperfry", "JioMart", "Tata CLiQ"],
    "toys": ["Amazon", "Flipkart", "FirstCry", "JioMart", "Tata CLiQ"],
}


def default_stores(category: str, n: int) -> list[str]:
    picks = DEFAULT_PICKS.get((category or "").lower(), ["Amazon", "Flipkart", "Croma", "Tata CLiQ", "JioMart"])
    return picks[:n]


def search_url(store: str, query: str) -> str:
    return STORES[store]["search"].format(q=quote_plus(query), dash=quote_plus(query.lower().replace(" ", "-")))


def catalog_text() -> str:
    return "\n".join(f"- {name}: {', '.join(s['categories'])}" for name, s in STORES.items())
