"""
Demo script to showcase the rich-based logger.
Run:  uv run python3 demo_logger.py
"""
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.logger import pipeline, timer_step, info, success, console, get_log_dir


def run_demo():
    console.rule("[bold cyan]RAG2Prod — Pipeline Logger Demo[/]")
    console.print()

    # ── Part 1: Full pipeline with animated progress bar ──
    with pipeline("Ingestion Pipeline", total_steps=5) as p:

        with p.step("parser", "Parsing PDF documents"):
            time.sleep(0.6)

        with p.step("parser", "Cleaning & normalising text"):
            time.sleep(0.3)

        with p.step("chunker", "Structure-aware chunking"):
            time.sleep(0.5)

        with p.step("embeddings", "Generating dense embeddings"):
            time.sleep(0.8)

        with p.step("storage", "Writing chunks to Postgres"):
            time.sleep(0.4)

    console.print()

    # ── Part 2: Standalone timers (no progress bar) ──
    console.rule("[bold cyan]Standalone Timer Steps[/]")
    console.print()

    with timer_step("ocr", "OCR on scanned page 3"):
        time.sleep(0.35)

    with timer_step("cache", "Writing OCR result to cache"):
        time.sleep(0.1)

    console.print()


if __name__ == "__main__":
    run_demo()
