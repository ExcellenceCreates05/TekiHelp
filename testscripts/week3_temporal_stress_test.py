"""
Week 3, Day 20-21: temporal normalization stress test.

Feeds deliberately messy, real East African informal phrasing through
BOTH engines and logs accuracy per engine. This data is genuinely useful
evidence for Chapter 3's Qwen3 multilingual-justification section, and
for Chapter 4/5's results -- don't skip it even under time pressure.

Run:  python scripts/week3_temporal_stress_test.py
Output: a CSV at output/temporal_stress_results.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai.gemini import GeminiEngine
from app.ai.ollama_engine import OllamaEngine
from app.agent.prompts import build_extraction_prompt
from app.models.session import Session

# Replace/extend with real redacted messages from your document analysis (Chapter 3, 3.6.3).
TEST_MESSAGES = [
    "Men's breakfast this Saturday at church, saa mbili asubuhi",
    "Kesho tuko na mkutano wa vijana saa tisa jioni at Main Hall",
    "Choir practice this Sat 3pm at the sanctuary",
    "Please join us for the youth conference tomorrow at saa nane mchana, Fellowship Hall",
    "Prayer meeting this Wed evening 6:30pm church auditorium",
    "Harambee itakuwa Jumamosi ijayo saa tatu asubuhi kwa Main Church",
    "Hello, how is everyone doing today",  # non-event control case
    "Please remember to pray for the sick",  # non-event control case
]


def run_engine(engine, label: str, results: list[dict]) -> None:
    session = Session(session_key=f"stress:{label}", channel="stress-test", chat_id=label)
    from datetime import date as date_cls
    today = date_cls.today().isoformat()

    for message in TEST_MESSAGES:
        prompt = build_extraction_prompt(session, message, today)
        try:
            raw = engine.generate(prompt)
        except Exception as exc:
            results.append({
                "engine": label, "message": message, "raw_output": f"ERROR: {exc}",
                "title": "", "date": "", "time": "", "venue": "", "is_event": "",
            })
            continue

        import json
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}

        results.append({
            "engine": label,
            "message": message,
            "raw_output": raw.replace("\n", " ")[:200],
            "title": parsed.get("title", ""),
            "date": parsed.get("date", ""),
            "time": parsed.get("time", ""),
            "venue": parsed.get("venue", ""),
            "is_event": parsed.get("is_event", ""),
        })


def main() -> None:
    results: list[dict] = []

    print("Running against Gemini...")
    run_engine(GeminiEngine(), "gemini", results)

    print("Running against Ollama/Qwen3...")
    run_engine(OllamaEngine(), "ollama", results)

    out_path = Path(__file__).resolve().parent.parent / "output" / "temporal_stress_results.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)

    print(f"\nDone. Results written to {out_path}")
    print("Manually review each row for correctness and tally accuracy per engine --")
    print("this becomes your Chapter 3/5 evidence table.")


if __name__ == "__main__":
    main()
