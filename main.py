"""The whole app in one process: the API and the built frontend.

    npm --prefix frontend run build   # once, and after frontend changes
    uv run main.py                    # http://localhost:2024

Vercel runs the same `app` (`tool.vercel` in pyproject.toml) and builds the
frontend first (`tool.vercel.scripts`).
"""

import os
import sys
from pathlib import Path

import uvicorn

# Vercel bundles the source but does not install this project as a package.
sys.path.insert(0, str(Path(__file__).parent / "src"))

from meta_hackathon.main import app  # noqa: E402

# Low priority: API routes always match first. Absent until the frontend is built, and
# not needed for `next dev`, which serves the frontend itself and calls this for the API.
dist = Path(__file__).parent / "frontend" / "dist"
if dist.is_dir():
    app.frontend("/", directory=dist)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 2024)))
