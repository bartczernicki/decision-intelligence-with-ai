#!/usr/bin/env python3
"""Compatibility wrapper for the website build script."""

from __future__ import annotations

import runpy
from pathlib import Path


TARGET = Path(__file__).resolve().parents[1] / "website" / "src" / "build_website.py"
runpy.run_path(str(TARGET), run_name="__main__")
