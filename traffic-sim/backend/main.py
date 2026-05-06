from fastapi import FastAPI  # FastAPI app
from fastapi.middleware.cors import CORSMiddleware  # CORS middleware
from backend.routers.simulation import router as simulation_router  # Simulation router
from backend.routers.upload import router as upload_router  # Upload router
from backend.routers.jobs import router as jobs_router  # Jobs router
from backend.routers.signal import router as signal_router  # Signal AI router
from backend.database.models import create_tables  # DB table setup

app = FastAPI()  # Create FastAPI app

# Add CORS middleware
app.add_middleware(
	CORSMiddleware,
	allow_origins=["http://localhost:3000"],
	allow_methods=["*"],
	allow_headers=["*"],
	allow_credentials=True
)

# Initialize database tables on startup
@app.on_event("startup")
def startup_event():
	create_tables()

# Mount routers
app.include_router(simulation_router)
app.include_router(upload_router)
app.include_router(jobs_router)
app.include_router(signal_router)
