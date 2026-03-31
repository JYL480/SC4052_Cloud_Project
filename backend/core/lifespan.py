from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver



logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI.
    Put your startup and shutdown logic here.
    """
    logger.info("Application starting up...")
    print("Application starting up...")
    # Add startup logic here (e.g., connect to DB, load ML models)
    
    yield
    
    # Add shutdown logic here (e.g., close DB connections)
    print("Application shutting down...")
    logger.info("Application shutting down...")


