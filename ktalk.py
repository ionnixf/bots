#!/usr/bin/env python3
"""Convenience entry point for ktalk; shared CLI: python main.py --service ktalk."""

from launcher import main


if __name__ == "__main__":
    raise SystemExit(main(default_service="ktalk"))
