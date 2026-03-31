from fastapi import FastAPI
from . import start

def register_routes(app: FastAPI):
    app.include_router(start.router)

