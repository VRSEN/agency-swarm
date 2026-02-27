"""Starter-template compatible FastAPI entrypoint for the OpenClaw PoC."""

import os

# Keep this import for server discovery (`module:app`).

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=False)
