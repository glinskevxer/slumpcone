"""``python -m slumpcone``.

The console script is the normal way in, and it is the one the documentation
uses. This exists for the two cases where it is not available: an editable
install whose scripts directory is not on the path, and a machine where
somebody has installed into a virtual environment and is invoking its
interpreter directly. Both happen on a batch computer that somebody set up once,
two years ago, and neither is worth an afternoon.
"""

from __future__ import annotations

from slumpcone.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
