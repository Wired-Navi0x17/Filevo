"""CLI entry point for the Document Generator.

Delegates directly to filevo_cli for OpenCode-style interactive session and commands.
"""

import sys
import os

# Compute path to the plan directory
file_abs = os.path.abspath(__file__)
plan_dir = os.path.dirname(os.path.dirname(os.path.dirname(file_abs)))
if plan_dir not in sys.path:
    sys.path.insert(0, plan_dir)

from src.doc_gen.filevo_cli import main

if __name__ == "__main__":
    main()