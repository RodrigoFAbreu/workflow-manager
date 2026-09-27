#!/usr/bin/env python3
"""Run every workflow-manager test. Stdlib only.

    python3 tests/run_all.py            # the full selection, in parallel -- the gate
    python3 tests/run_all.py --help     # every mode, flag and exit code

A thin shim: the command is `tests/parallel/cli.py`, run against the checkout
this file lives in -- the only root it ever reads.
"""

import sys

# Before anything else is imported: the tooling's own imports must not write
# `__pycache__` into the checkout.
sys.dont_write_bytecode = True

from pathlib import Path  # noqa: E402

TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

from parallel import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:], repo_root=TESTS_DIR.parent))
