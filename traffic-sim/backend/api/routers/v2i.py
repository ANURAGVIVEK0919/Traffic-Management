from fastapi import APIRouter, Body
from backend.core.services.v2i_service import process_beacon_signal, get_v2i_status
from typing import List

router = APIRouter()

@router.post("/v2i/beacon")
async def receive_beacon(
    vehicle_id: str = Body(...),
    lane: str = Body(...),
    distance: float = Body(...),
    speed: float = Body(15.0)
):
    """Endpoint for emergency vehicles to send their digital beacon."""
    process_beacon_signal(vehicle_id, lane, distance, speed)
    return {"status": "received", "vehicle": vehicle_id}

@router.get("/v2i/active")
async def get_active_beacons():
    """Endpoint for frontend to poll active V2I alerts."""
    return get_v2i_status()
