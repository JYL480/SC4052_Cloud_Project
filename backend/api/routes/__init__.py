from fastapi import FastAPI
from . import start
from . import chat

def register_routes(app: FastAPI):
    app.include_router(start.router)
    app.include_router(chat.router)
