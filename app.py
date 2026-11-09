"""SnapShop Agent — snap a product photo, get prices from 5 Indian stores.

Run:  .venv\\Scripts\\python app.py   →  http://127.0.0.1:7860
"""
import html

import gradio as gr

from snapshop import config
from snapshop.agent import graph

PROVIDERS = {
    "Auto (Groq → Ollama fallback)": "auto",
    "Groq (cloud, fast)": "groq",
    "Ollama (offline, local)": "ollama",
}


def product_card(p: dict) -> str:
    if not p:
        return ""
    feats = " · ".join(p.get("key_features") or [])
    return (f"### 🏷️ {p.get('product_name', '?')}\n"
            f"**Brand:** {p.get('brand') or '—'} &nbsp; **Model:** {p.get('model') or '—'} &nbsp; "
            f"**Category:** {p.get('category') or '—'}\n\n{feats}")


def price_table(results: list[dict]) -> str:
    if not results:
        return ""
    priced = [r["price"] for r in results if r["price"]]
    best = min(priced) if priced else None
    rows = []
    for r in sorted(results, key=lambda r: r["price"] or float("inf")):
        is_best = best is not None and r["price"] == best
        price = f"₹{r['price']:,.0f}" if r["price"] else "—"
        badge = " 🏆" if is_best else ""
        style = "background:rgba(34,197,94,.15);font-weight:600;" if is_best else ""
        link = (f"<a href='{html.escape(r['url'])}' target='_blank'>Open ↗</a>" if r.get("url") else "—")
        rows.append(
            f"<tr style='{style}'><td>{html.escape(r['store'])}{badge}</td><td>{price}</td>"
            f"<td style='font-size:12px'>{html.escape(r['title'] or '')}"
            f"{'' if r.get('match', True) else ' <b>⚠️ may be a different product</b>'}</td>"
            f"<td style='font-size:12px;opacity:.75'>{html.escape(r['price_source'] or r['status'])}</td>"
            f"<td>{link}</td></tr>")
    return ("<table style='width:100%;border-collapse:collapse' cellpadding='8'>"
            "<tr style='text-align:left;border-bottom:1px solid #8884'><th>Store</th><th>Price</th>"
            "<th>Listing</th><th>Source</th><th>Link</th></tr>" + "".join(rows) + "</table>")


def run_agent(image, hint, provider_label, show_browser, n_stores):
    if not image and not (hint or "").strip():
        yield "", "⚠️ Upload a photo or type a product name.", "", "", "", []
        return
    init = {"image_path": image, "hint": hint or "", "provider": PROVIDERS[provider_label],
            "headless": not show_browser, "num_stores": int(n_stores), "log": []}
    state: dict = {}
    log: list[str] = []
    status = "🚀 Agent started…"

    def view():
        shots = [(r["screenshot"], f"{r['store']} · " + (f"₹{r['price']:,.0f}" if r["price"] else "no price"))
                 for r in state.get("results", []) if r.get("screenshot")]
        return (product_card(state.get("product", {})), status, "\n\n".join(log),
                price_table(state.get("results", [])), state.get("verdict", ""), shots)

    yield view()
    try:
        for mode, chunk in graph.stream(init, stream_mode=["updates", "custom"]):
            if mode == "custom":
                status = f"⏳ {chunk}"
            else:
                for node, update in chunk.items():
                    log.extend(update.get("log", []))
                    state.update({k: v for k, v in update.items() if k != "log"})
                    status = f"✔️ step done: `{node}`"
            yield view()
        status = "✅ Done"
    except Exception as e:
        status = f"❌ {type(e).__name__}: {e}"
    yield view()


with gr.Blocks(title="SnapShop Agent") as demo:
    gr.Markdown("# 🛒 SnapShop Agent\n**Snap a photo → AI sees it → searches the web → browses 5 stores → "
                "tells you the best price.** &nbsp; Vision LLM · LangGraph · Web search · Browser automation")
    with gr.Tab("🔍 Find best price"):
        with gr.Row():
            with gr.Column(scale=1):
                image = gr.Image(type="filepath", label="Product photo",
                                 sources=["upload", "webcam", "clipboard"], height=300)
                hint = gr.Textbox(label="Optional hint / or type a product name",
                                  placeholder="e.g. 'boAt Airdopes 141' or 'the 128GB one'")
                provider = gr.Radio(list(PROVIDERS), value=list(PROVIDERS)[0], label="Brain")
                with gr.Row():
                    show_browser = gr.Checkbox(value=True, label="Show browser window")
                    n_stores = gr.Slider(3, 6, value=5, step=1, label="Stores")
                go = gr.Button("🚀 Find best price", variant="primary")
                status = gr.Markdown()
                with gr.Accordion("🧠 Agent trace (what the AI is thinking)", open=True):
                    trace = gr.Markdown()
            with gr.Column(scale=2):
                product = gr.Markdown()
                table = gr.HTML()
                verdict = gr.Markdown()
                gallery = gr.Gallery(label="What the browser saw", columns=3, height=360)
        go.click(run_agent, [image, hint, provider, show_browser, n_stores],
                 [product, status, trace, table, verdict, gallery])

    with gr.Tab("🧩 How it works"):
        gr.Markdown(
            "### LangGraph agent graph\n```mermaid\n" + graph.get_graph().draw_mermaid() + "\n```\n"
            "| Step | What happens | Tech |\n|---|---|---|\n"
            "| identify | Vision model reads the photo (brand, model, text on box) | Groq Qwen 3.8 (vision) / Ollama Gemma 3 |\n"
            "| pick_stores | LLM chooses which shops fit the product category | LLM reasoning |\n"
            "| find_links | Searches `<product> site:amazon.in` etc. | DuckDuckGo (free, no key) |\n"
            "| browse | Opens all stores in parallel tabs, reads price, screenshots | Playwright + Chromium |\n"
            "| refine | If < 2 prices found, rewrites the query and loops back | Self-correction |\n"
            "| compare | Picks best deal, flags wrong variants | LLM |\n\n"
            f"**Models:** Groq vision `{config.GROQ_VISION_MODEL}`, Groq text `{config.GROQ_TEXT_MODEL}`, "
            f"Ollama `{config.OLLAMA_VISION_MODEL}` "
            f"{'· ✅ Groq key loaded' if config.GROQ_API_KEY else '· ⚠️ no GROQ_API_KEY in .env'}"
        )

if __name__ == "__main__":
    demo.launch(inbrowser=True)
