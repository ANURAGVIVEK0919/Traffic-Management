from fastapi import FastAPI  # FastAPI app
from fastapi.middleware.cors import CORSMiddleware  # CORS middleware
from backend.api.routers.simulation import router as simulation_router
from backend.api.routers.upload import router as upload_router
from backend.api.routers.jobs import router as jobs_router
from backend.api.routers.signal import router as signal_router
from backend.api.routers.v2i import router as v2i_router
from contextlib import asynccontextmanager
from backend.infra.database.models import create_tables  # DB table setup

@asynccontextmanager
async def lifespan(app: FastAPI):
	# Initialize database tables on startup
	create_tables()
	yield
	# Shutdown logic if needed

app = FastAPI(lifespan=lifespan)  # Create FastAPI app with lifespan

# Add CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:3000"],
	allow_methods=["*"],
	allow_headers=["*"],
	allow_credentials=True
)

# Mount routers
app.include_router(simulation_router)
app.include_router(upload_router)
app.include_router(jobs_router)
app.include_router(signal_router)
app.include_router(v2i_router)

if __name__ == "__main__":
	import uvicorn
	uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
