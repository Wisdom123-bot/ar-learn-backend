from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routers import register_routers
import logging

app = FastAPI(
    title="Ar-Learn API",
    description="School Management & Analytics System for Kenyan Schools",
    version="0.1.1",
)

# Global Validation Error Handler to prevent data leakage and return clean 400s
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Invalid input provided.", "errors": exc.errors()},
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

from app.core.redis import cache_result

@app.get("/")
@cache_result(expire=3600, prefix="system")
async def root():
    return {"message": "Ar-Learn API - Hardened Version"}

@app.get("/health")
@cache_result(expire=60, prefix="system")
async def health_check():
    return {"status": "healthy"}

@app.get("/healthz")
@cache_result(expire=60, prefix="system")
async def healthz():
    return {"status": "ok"}
