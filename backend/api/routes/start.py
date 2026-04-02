import os
import sys
# Fix import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))



from fastapi import FastAPI, APIRouter
from pydantic import BaseModel
from core.lifespan import lifespan

# Need to import the shared resources
from core.lifespan import shared_resources

router = APIRouter()

class Item(BaseModel):
    name: str
    description: str | None = None

@router.get("/health")
def health_check():
    print(shared_resources)
    health_status = {
        "status": "healthy",
        "services": {
            "graph": shared_resources.get('graph') is not None,
            "db_connection": shared_resources.get('db_connection') is not None,
            "saver": shared_resources.get('saver') is not None,
        },
        "shared_resources_count": len(shared_resources)
    }
    
    # If any service is down, return 503
    if not all(health_status["services"].values()):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "services": health_status["services"],
                "message": "Some services are not available"
            }
        )
    
    return health_status

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
