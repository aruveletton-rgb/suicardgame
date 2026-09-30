from pathlib import Path

from fastapi.staticfiles import StaticFiles

from backend.app.main import app


app.mount(
    "/",
    StaticFiles(directory=Path(__file__).resolve().parent / "frontend" / "dist", html=True),
    name="frontend",
)
