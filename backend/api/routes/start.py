from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
from core.lifespan import lifespan


router = APIRouter()

class Item(BaseModel):
    name: str
    description: str | None = None

@router.get("/health")
def health_check():
    """Health check endpoint to verify the API is running."""
    return {"status": "ok"}

@router.get("/api/hello")
def say_hello(name: str | None = "World"):
    """Simple GET endpoint."""
    return {"message": f"Hello, {name}!"}

@router.put("/api/items/{item_id}")
def update_item(item_id: int, item: Item):
    """Simple PUT endpoint."""
    return {
        "item_id": item_id,
        "name": item.name,
        "description": item.description,
        "status": "updated"
    }
