def main() -> None:
    """The API alone on :2024, for working on the frontend with `next dev`."""
    import uvicorn

    uvicorn.run("meta_hackathon.main:app", host="0.0.0.0", port=2024)
