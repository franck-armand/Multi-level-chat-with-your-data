from __future__ import annotations

import os


# The repo-local .env currently sets DEBUG to a non-boolean string.
# Force a valid value for tests before importing application settings.
os.environ.setdefault("DEBUG", "false")
