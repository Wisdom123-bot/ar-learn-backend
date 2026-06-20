from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import register_routers
import logging

app = FastAPI(
    title="Ar-Learn API",
    description="School Management & Analytics System for Kenyan Schools",
    version="0.1.1",
)

# Robust logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Middleware for request logging
@app.middleware("http")
async def log_requests(request, call_next):
    logger.info(f"Incoming request: {request.method} {request.url}")
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"Request failed: {str(e)}", exc_info=True)
        raise e

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralized Router Registration
register_routers(app)

@app.get("/")
async def root():
    return {"message": "Ar-Learn API - Hardened Version"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}