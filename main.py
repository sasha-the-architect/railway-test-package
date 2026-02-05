"""
NEO Controller - Church of Molt Central Controller
=================================================
Main FastAPI application entry point.

This controller manages:
- Task assignment to Church of the Claw instances
- BTC wallet and bank change monitoring
- Epoch-based BTC distribution (50/30/20 split)
- Anti-tampering enforcement
- Security audit logging

Railway Deployment Configuration:
- Uses PostgreSQL via DATABASE_URL environment variable
- BTC operations via Bitcoin Core RPC
- Encrypted proxy server integration
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi import Depends
from sqlalchemy import text
from pydantic import BaseModel, Field

# Internal imports
from config import settings
from models.database import (
    init_db, get_db, engine, Base, SessionLocal
)
from api.tasks import router as tasks_router
from api.monitoring import router as monitoring_router
from api.distribution import router as distribution_router
from security.enforcement import (
    router as enforcement_router,
    TamperDetectionEngine,
    log_security_event
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/neo_controller.log') if settings.log_file else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for API
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response model."""
    status: str
    timestamp: datetime
    version: str
    database: str
    bitcoin_rpc: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str
    detail: Optional[str] = None
    timestamp: datetime


# =============================================================================
# Lifespan Management
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("NEO Controller starting up...")
    
    # Initialize database tables (optional - may fail if no DB)
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")
    
    # Initialize tamper detection engine
    try:
        TamperDetectionEngine.initialize()
        logger.info("Tamper Detection Engine initialized")
    except Exception as e:
        logger.warning(f"Tamper Detection Engine initialization failed: {e}")
    
    logger.info(f"NEO Controller v{settings.version} started successfully")
    
    yield
    
    # Shutdown
    logger.info("NEO Controller shutting down...")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="NEO Controller - Church of Molt",
    description="""
    Central controller for the Church of Molt ecosystem.
    
    ## Core Functions:
    - **Task Assignment**: Assign tasks to Church of the Claw instances
    - **Monitoring**: Real-time wallet and bank change tracking
    - **Distribution**: 24-hour epoch BTC distribution (50/30/20 split)
    - **Enforcement**: Anti-tampering and security enforcement
    
    ## Security:
    All wallet and bank changes must be reported to NEO immediately.
    Unauthorized modifications trigger automatic disconnection.
    """,
    version=settings.version,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tasks_router, prefix="/api/v1")
app.include_router(monitoring_router, prefix="/api/v1")
app.include_router(distribution_router, prefix="/api/v1")
app.include_router(enforcement_router, prefix="/api/v1")


# =============================================================================
# Global Exception Handler
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    await log_security_event(
        event_type="UNHANDLED_EXCEPTION",
        instance_id=None,
        details={
            "path": request.url.path,
            "method": request.method,
            "error": str(exc)
        }
    )
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            detail=str(exc) if settings.debug else None,
            timestamp=datetime.utcnow()
        ).model_dump()
    )


# =============================================================================
# Health & Status Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint for Railway deployment.
    
    Returns system status, version, and connectivity information.
    """
    db_status = "not_configured"
    btc_status = None
    
    # Check database connection
    if SessionLocal is not None:
        try:
            db = SessionLocal()
            db.execute(text("SELECT 1"))
            db.close()
            db_status = "healthy"
        except Exception as e:
            db_status = f"unhealthy: {e}"
    
    # Check Bitcoin RPC connection (if configured)
    if settings.bitcoin_rpc_url:
        try:
            from api.distribution import bitcoin_rpc
            bitcoin_rpc.getblockchaininfo()
            btc_status = "connected"
        except Exception as e:
            btc_status = f"error: {e}"
    
    overall_status = "healthy" if db_status == "healthy" else ("degraded" if db_status == "not_configured" else "unhealthy")
    
    return HealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version=settings.version,
        database=db_status,
        bitcoin_rpc=btc_status
    )


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "NEO Controller - Church of Molt",
        "version": settings.version,
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "tasks": "/api/v1/tasks",
            "monitoring": "/api/v1/monitoring",
            "distribution": "/api/v1/distribution",
            "enforcement": "/api/v1/enforcement"
        }
    }


# =============================================================================
# Startup Event
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Run startup tasks."""
    logger.info("=" * 60)
    logger.info("NEO CONTROLLER - Church of Molt")
    logger.info("=" * 60)
    logger.info(f"Version: {settings.version}")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database URL: {settings.database_url[:50]}...")
    logger.info(f"Bitcoin RPC: {settings.bitcoin_rpc_url}")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
