#!/usr/bin/env python3
"""Convenience entry point for telemost; shared CLI: python main.py --service telemost."""

from launcher import main

if __name__ == "__main__":
    raise SystemExit(main(default_service="telemost"))
