# Tekihelp -- AI-Assisted Conversational Workflow Coordination System

Build Weeks 1-4 of the 5-week plan. Week 5 (live beta test + documentation)
has no code deliverable -- it consumes what's here.

## What's implemented, by week

**Week 1 -- Core pipeline (no conversation memory yet)**
- `app/config.py` -- central `.env` loader
- `app/models/event.py` -- `PartialEvent`/`ValidatedEvent` with FIX #2
  (per-field normalization enforced at the Pydantic validator level, not
  only at the end)
- `app/ai/gemini.py`, `app/ai/ollama_engine.py`, `app/ai/router.py` --
  the Inference Router with FIX #1 (failure taxonomy + session
  stickiness)
- `app/agent/prompts.py`, `app/agent/extraction.py` -- single-turn
  extraction
- `app/rendering/typography.py`, `app/rendering/engine.py` -- Pillow
  renderer, auto-scaling text
- `app/broadcast/watch_folder.py` -- FIX #5 (atomic write-then-rename)
- `scripts/week1_manual_test.py` -- run this first, no Telegram needed

**Week 2 -- Statefulness, the ReAct loop, Constitution**
- `app/models/session.py` -- session state machine
- `app/storage/database.py` -- full 4-table SQLite schema
- `app/agent/constitution.md` -- the 8 governance rules, each citing
  exactly where it's enforced in code
- `app/agent/orchestrator.py` -- the Observe-Reason-Act loop, with
  FIX #3 (reject feedback) and FIX #4 (concurrent-event guard)
- `app/channels/base.py`, `app/channels/telegram_adapter.py`,
  `app/main.py` -- full working Telegram bot

**Week 3 -- Calendar tool, second channel, stress testing**
- `app/tools/calendar_tool.py` -- read-only clash-checking lookup
- `app/channels/discord_adapter.py`, `app/channels/discord_runner.py`
  -- second channel via the SAME orchestrator/extraction/rendering code
- `scripts/week3_temporal_stress_test.py` -- messy real-phrasing
  accuracy test across both engines, feeds Chapter 3/5 evidence

**Week 4 -- WhatsApp (conditional), full test suite**
- `app/channels/whatsapp_adapter.py` -- only wire this in if Meta
  Business verification cleared (started Week 1 Day 1); requires a
  separate webhook receiver not included here (see file docstring)
- `tests/` -- 25 passing tests covering the event schema, the router's
  failure/stickiness behavior, the orchestrator's branches (including
  every numbered fix), and atomic Watch Folder delivery

## Setup

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt

cp .env.example .env
# edit .env: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN at minimum

ollama pull qwen3:4b              # local fallback model
```

## Day-1 sanity check (no bot needed)

```bash
python scripts/week1_manual_test.py "Men's breakfast Saturday 3 October 2026 at 8am at Main Church"
```

This exercises the full pipeline end-to-end: router -> extraction ->
validation -> render -> (simulated approval) -> atomic Watch Folder
write. Check `output/previews/` and `watch_folder/` afterward.

## Running the full Telegram bot (Week 2 milestone onward)

```bash
python -m app.main
```

## Running the Discord bot (Week 3 stretch channel)

```bash
python -m app.channels.discord_runner
```

## Running tests

```bash
pytest tests/ -v
```

All 25 tests pass against this codebase as delivered. Tests mock the
Gemini/Ollama clients directly (no real API calls, no cost, runs
offline) -- see `tests/test_router_fallback.py` for the pattern if you
add more.

## Running the temporal stress test (Week 3, Day 20-21)

Requires a real `GEMINI_API_KEY` and a running `ollama serve` with
`qwen3:4b` pulled -- this one DOES make real calls, by design, since its
whole purpose is measuring real accuracy.

```bash
python scripts/week3_temporal_stress_test.py
```

Results land in `output/temporal_stress_results.csv`. Review each row
manually and tally accuracy per engine -- this becomes evidence for
Chapter 3's Qwen3 multilingual-justification section and Chapter 5's
results.

## Known scope boundaries (document these explicitly in Chapter 4)

- The concurrent-event guard (FIX #4, Constitution Rule 7) asks for
  confirmation on an apparent second event; it is NOT full topic-shift
  detection. A cleverly-phrased second event could still slip through
  undetected.
- WhatsApp is conditional on external verification lead time outside
  your control -- documented as a known risk from Week 1, Day 1.
- The SQLite message history save in `database.py` uses a delete-then-
  reinsert strategy per turn (simple, correct, but not efficient at
  scale) -- fine for single-control-room conversation volumes.
- `render_event_graphic`'s background is a flat color unless a real
  branded template PNG is supplied via `template_path` -- swap in
  PCEA's actual template once available.

## Project structure

```
tekihelp/
├── app/
│   ├── config.py
│   ├── main.py                    # Telegram entry point
│   ├── agent/
│   │   ├── orchestrator.py        # the ReAct loop
│   │   ├── constitution.md        # governance rules + code citations
│   │   ├── prompts.py
│   │   └── extraction.py
│   ├── ai/
│   │   ├── gemini.py
│   │   ├── ollama_engine.py
│   │   └── router.py              # FIX #1
│   ├── models/
│   │   ├── event.py                # FIX #2
│   │   └── session.py
│   ├── tools/
│   │   └── calendar_tool.py
│   ├── channels/
│   │   ├── base.py                 # ChannelAdapter interface
│   │   ├── telegram_adapter.py
│   │   ├── discord_adapter.py
│   │   ├── discord_runner.py
│   │   └── whatsapp_adapter.py     # conditional, Week 4
│   ├── rendering/
│   │   ├── engine.py
│   │   └── typography.py
│   ├── storage/
│   │   ├── database.py             # SQLite, 4 tables
│   │   └── session_store.py        # Week 1 in-memory alternative
│   └── broadcast/
│       └── watch_folder.py         # FIX #5
├── data/
│   └── calendar.json
├── scripts/
│   ├── week1_manual_test.py
│   └── week3_temporal_stress_test.py
├── tests/                          # 25 passing tests
├── output/{previews,approved}/
├── watch_folder/
├── .env.example
├── .gitignore
└── requirements.txt
```
