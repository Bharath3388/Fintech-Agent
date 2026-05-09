#!/usr/bin/env python3
"""
Fintech Loan Portfolio Analytics — CLI Entry Point
====================================================
Uses Google Gemini + LangGraph for true AI-powered pipeline.

Usage:
    python run_agentic.py <csv_path1> [csv_path2] ...

Examples:
    python run_agentic.py "../Medium Size data Set/01_Borrowers.csv"
    python run_agentic.py "../Large data set/loans.csv" "../Large data set/transactions.csv"
"""

import sys
import os
import glob

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from agentic.graph import run_pipeline
from core.logger import log_banner, log_info, log_error


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_agentic.py <csv_path1> [csv_path2] ...")
        print()
        print("Examples:")
        print('  python run_agentic.py "../Medium Size data Set/01_Borrowers.csv"')
        print('  python run_agentic.py "../Large data set/"*.csv')
        print()
        print("Make sure .env file has GOOGLE_API_KEY set.")
        print("Get a key from: https://aistudio.google.com/apikey")
        sys.exit(1)

    # Collect CSV paths from args — support files and directories
    csv_paths: list[str] = []
    for arg in sys.argv[1:]:
        path = os.path.abspath(arg)
        if os.path.isfile(path) and path.lower().endswith(".csv"):
            csv_paths.append(path)
        elif os.path.isdir(path):
            csv_paths.extend(sorted(glob.glob(os.path.join(path, "*.csv"))))
        else:
            log_error("Main", f"Not a CSV file or directory: {arg}")
            sys.exit(1)

    if not csv_paths:
        log_error("Main", "No CSV files found")
        sys.exit(1)

    # Check API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        log_error("Main", "GOOGLE_API_KEY not set!")
        log_error("Main", "1. Copy .env.example to .env")
        log_error("Main", "2. Get a key from https://aistudio.google.com/apikey")
        log_error("Main", "3. Paste it in .env")
        sys.exit(1)

    log_banner("Main")
    log_info("Main", "Starting AGENTIC Loan Portfolio Analytics Pipeline")
    log_info("Main", f"CSV files ({len(csv_paths)}):")
    for p in csv_paths:
        log_info("Main", f"  {os.path.basename(p)}")
    log_info("Main", f"LLM: Google Gemini ({os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')})")
    log_info("Main", f"Framework: LangChain + LangGraph")
    log_info("Main", "")

    final_state = run_pipeline(csv_paths)

    # Exit code
    metrics = final_state.get("metrics", {})
    ok = sum(1 for m in metrics.values() if m["status"] == "ok")
    if ok > 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
