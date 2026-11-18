"""One Streamlit ASGI service, with a dedicated read-only synthetic API."""
import asyncio
import logging
from contextlib import asynccontextmanager
import streamlit as st
from starlette.routing import Route
from sample_endpoint import sample_rows
from demo_store import DemoStoreError
from scripts.seed_public_sample import seed_public


@asynccontextmanager
async def lifespan(app):
    # Publish automatically applies the development schema to managed production.
    # This is data-only initialization, before requests are served. The advisory
    # lock makes first startup safe across multiple deployment instances.
    try:
        await asyncio.to_thread(seed_public)
    except DemoStoreError:
        logging.getLogger(__name__).error(
            "Public sample initialization unavailable. Ensure the managed schema "
            "was applied through Publish. Private session-only inspection remains available."
        )
    yield


app = st.App("app.py", lifespan=lifespan,
             routes=[Route("/api/demo/sample", sample_rows, methods=["GET"])])

if __name__ == "__main__":
    app.run()
