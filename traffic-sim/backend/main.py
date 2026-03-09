from fastapi import FastAPI  # FastAPI app
from fastapi.middleware.cors import CORSMiddleware  # CORS middleware
from backend.routers.simulation import router as simulation_router  # Simulation router
from backend.routers.rl import router as rl_router  # RL router
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

# Mount simulation router
app.include_router(simulation_router)
app.include_router(rl_router)
