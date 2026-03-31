from fastapi import FastAPI
from core.lifespan import lifespan
from api.routes import register_routes
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="KGMAF", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# The routes to for initiation will be tied to the app!
register_routes(app)