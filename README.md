# 🛒 SnapShop Agent — Multimodal AI demo

**Snap a photo of any product → the AI recognises it → searches the web → a browser agent opens 5 Indian
shopping sites in parallel → you get a price-comparison table, screenshots and a verdict.**

Everything is free: Groq (free API key), Ollama (local/offline), LangGraph, DuckDuckGo search (no key),
Playwright (real Chromium), Gradio.

```
photo ──► identify ──► pick_stores ──► find_links ──► browse ──┬──► compare ──► verdict
          (vision LLM)  (LLM reasons)   (web search)  (Playwright)│
                                             ▲                    │ < 2 prices found?
                                             └──── refine ◄───────┘ (self-correction loop)
```

| Talk topic | Where it shows up |
|---|---|
| 👁️ Vision AI / VLMs / OCR | `identify` reads brand, model number and box text from the photo |
| 🤖 AI Agents — reasoning | `pick_stores` decides *which* shops fit the product category |
| 🤖 Tool use | DuckDuckGo search + Playwright browser are the agent's tools |
| 🔁 Autonomy | `refine` loop: if too few prices, the agent rewrites its own query and retries |
| 🖥️ Computer/browser-use | Real Chromium opens all stores in parallel tabs (watch it live) |
| ⚡ Real-time | Agent trace streams step by step into the UI |
| 🔌 Cloud vs edge | Switch "Brain" between Groq (cloud) and Ollama (offline) live |

## Setup (≈10 min)

1. **Groq key** (free): https://console.groq.com/keys → paste into `.env` as `GROQ_API_KEY=...`
2. **Ollama** (offline fallback): install from https://ollama.com/download, then
   ```bash
   ollama pull gemma3:4b
   ```
3. Run (first run installs everything):
   ```bash
   run.bat
   ```
   Opens http://127.0.0.1:7860
4. **Health check before going on stage:**
   ```bash
   .venv\Scripts\python -X utf8 check_setup.py
   ```
   If it says a Groq model isn't available, it prints the list. Pick a vision model from it and set
   `GROQ_VISION_MODEL` in `.env`.

## Project layout

| File | What it does |
|---|---|
| `app.py` | Gradio UI: upload/webcam, live agent trace, price table, screenshots, "How it works" tab |
| `snapshop/agent.py` | LangGraph state graph (6 nodes + conditional retry edge) |
| `snapshop/llm.py` | Groq ↔ Ollama wrapper with automatic fallback |
| `snapshop/search.py` | Free DuckDuckGo search, finds product pages per store |
| `snapshop/browser.py` | Playwright browser agent: parallel tabs, price extraction, screenshots |
| `snapshop/stores.py` | 12 Indian stores (Amazon, Flipkart, Croma, Reliance Digital, Vijay Sales, Tata CLiQ, Myntra, Ajio, Nykaa, JioMart, Pepperfry, FirstCry) |
| `check_setup.py` | Pre-demo health check |

## Suggested 18-min talk flow

| Time | Segment |
|---|---|
| 0–2 | Hook: "What if your phone camera could shop for you?" Show the finished result screenshot |
| 2–6 | Slides: text-only AI vs multimodal AI. Vision LLMs, voice, video, agents = see + reason + act |
| 6–8 | Architecture: open the **🧩 How it works** tab (LangGraph diagram) |
| 8–14 | **Live demo** (below) |
| 14–16 | Turn off Wi-Fi idea: switch Brain → Ollama, show the *same* vision step runs locally |
| 16–18 | The free stack + what else you can build (voice agent, video Q&A) → Q&A |

### Live demo script
1. Hold up a product (earbuds, a phone, shoes, a perfume) → **webcam** button → capture.
2. Keep **Show browser window** ticked so the audience sees Chromium open 5 tabs by itself.
3. While it runs, narrate the **Agent trace**: vision → plan → search → browse → verdict.
4. Point at the 🏆 cheapest row, the ⚠️ "may be a different product" flags, and the screenshots.
5. Second run: type a hint like *"the 256GB one"* to show text + image together (multimodal input).

### Demo-day safety net
- **Run it once 30 minutes before** so Chromium and DNS are warm. Record a screen capture as backup.
- Phones, earbuds and shoes work best. Generic, unbranded items give vague results.
- Shopping sites change layouts and sometimes block bots. Expect 3–5 of 5 prices. The agent falls back to
  search-snippet prices and says so in the **Source** column. That is a fine talking point about
  real-world agents.
- Prices are scraped live and may be a different variant. Always mention "verify before buying".
