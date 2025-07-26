"""
Dify SSE Simplified Proxy API
A FastAPI wrapper for Dify SSE streaming with simplified output
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from config import settings
from models.api_models import WorkflowExecutionRequest, ErrorResponse
from services.dify_client import DifyClient
from services.sse_processor import SSEProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting Dify SSE Proxy API")
    yield
    logger.info("Shutting down Dify SSE Proxy API")


# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
dify_client = DifyClient()
sse_processor = SSEProcessor()


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint"""
    return {
        "message": "Dify SSE Simplified Proxy API is running",
        "version": settings.API_VERSION,
        "status": "healthy"
    }


@app.post("/dify", 
         response_class=StreamingResponse,
         tags=["Dify Proxy"],
         summary="Execute Dify workflow with user query",
         description="Send user query to Dify API and return simplified workflow results via SSE")
async def dify_workflow_proxy(request: WorkflowExecutionRequest):
    """
    Execute Dify workflow with user query and return simplified SSE stream
    
    This endpoint:
    1. Takes only a user_query parameter
    2. Forwards the request to Dify API with fixed parameters
    3. Processes the SSE stream from Dify
    4. Extracts only workflow_finished events
    5. Parses and formats the result JSON
    6. Returns simplified results via SSE
    """
    try:
        logger.info(f"Received workflow request: {request.user_query[:50]}...")
        
        # Create SSE stream generator
        async def generate_sse_stream():
            try:
                # Get SSE stream from Dify API
                async for simplified_result in sse_processor.process_dify_stream(
                    dify_client, request
                ):
                    # Yield SSE formatted data
                    yield f"data: {simplified_result}\n\n"
                    
            except Exception as e:
                logger.error(f"Error in SSE stream generation: {str(e)}")
                error_response = {
                    "error": "Stream processing error",
                    "detail": str(e)
                }
                yield f"data: {error_response}\n\n"
                yield "event: error\ndata: Stream ended due to error\n\n"
        
        return StreamingResponse(
            generate_sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
            }
        )
        
    except Exception as e:
        logger.error(f"Error in dify_workflow_proxy: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process workflow request: {str(e)}"
        )


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check with service status"""
    try:
        # Test Dify API connectivity
        is_dify_healthy = await dify_client.health_check()
        
        return {
            "status": "healthy" if is_dify_healthy else "degraded",
            "services": {
                "dify_api": "healthy" if is_dify_healthy else "unhealthy",
                "sse_processor": "healthy"
            },
            "timestamp": "2024-01-01T00:00:00Z"  # Will be replaced with actual timestamp
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": "2024-01-01T00:00:00Z"
        }


def custom_openapi():
    """Custom OpenAPI schema with enhanced documentation"""
    if app.openapi_schema:
        return app.openapi_schema
        
    openapi_schema = get_openapi(
        title=settings.API_TITLE,
        version=settings.API_VERSION,
        description=settings.API_DESCRIPTION,
        routes=app.routes,
    )
    
    # Add custom documentation
    openapi_schema["info"]["x-logo"] = {
        "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level="info" if not settings.DEBUG else "debug"
    )