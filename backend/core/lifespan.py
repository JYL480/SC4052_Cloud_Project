import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging
import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Fix import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from logic.graph.graph import setup_graph

logger = logging.getLogger(__name__)

DB_PATH = Path("./checkpoints.sqlite")

shared_resources = {}
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up...")

    # Ensure directory exists
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("DB Path:", DB_PATH.resolve())
    print("Dir exists:", DB_PATH.parent.exists())

    # Connect to SQLite
    conn = await aiosqlite.connect(str(DB_PATH))

    # Workaround for langgraph checkpoint bug
    if not hasattr(conn, 'is_alive'):
        conn.is_alive = lambda: True

    # SQLite pragmas
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA synchronous=NORMAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")

    print("SQLite connection established")

    # Initialize saver
    saver = AsyncSqliteSaver(conn)
    await saver.setup()

    print("AsyncSqliteSaver initialized + tables created")

    # Setup graph
    graph = await setup_graph(saver)
    print("Graph initialized successfully")

    # Store shared resources
    shared_resources["saver"] = saver
    shared_resources["graph"] = graph
    shared_resources["db_connection"] = conn

    print("SQLite + LangGraph checkpoint DB initialized")

    try:
        yield  # ✅ App runs here
    finally:
        logger.info("Application shutting down...")

        # Cleanup saver (if supported)
        if saver and hasattr(saver, "aclose"):
            await saver.aclose()

        # Close DB connection
        if conn:
            await conn.close()

        print("Shutdown complete")