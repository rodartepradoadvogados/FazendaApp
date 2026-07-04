#!/usr/bin/env python
"""
Script para iniciar o servidor de desenvolvimento do backend.
Uso: python run_dev.py
"""
import subprocess
import sys
from pathlib import Path

backend_dir = Path(__file__).parent / "backend"

subprocess.run(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", "8000",
    ],
    cwd=backend_dir,
)
