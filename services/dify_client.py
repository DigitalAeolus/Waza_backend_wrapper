"""
Dify API Client for handling requests and authentication
"""
import json
import logging
from typing import AsyncGenerator, Dict, Any
import httpx
from config import settings
from models.api_models import WorkflowExecutionRequest

logger = logging.getLogger(__name__)


class DifyClient:
    """Client for interacting with Dify API"""
    
    def __init__(self):
        self.base_url = settings.DIFY_BASE_URL
        self.api_key = settings.DIFY_API_KEY
        self.endpoint = settings.DIFY_ENDPOINT
        self.timeout = httpx.Timeout(
            connect=10.0,
            read=settings.SSE_CHUNK_TIMEOUT,
            write=10.0,
            pool=10.0
        )
        
    def _get_headers(self) -> Dict[str, str]:
        """Get HTTP headers with authentication"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cache-Control": "no-cache"
        }
    
    async def health_check(self) -> bool:
        """Check if Dify API is accessible"""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                # Try a simple HEAD request to the base URL
                response = await client.head(
                    self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}"}
                )
                return response.status_code < 500
        except Exception as e:
            logger.error(f"Dify API health check failed: {str(e)}")
            return False
    
    async def execute_workflow_stream(
        self, 
        request: WorkflowExecutionRequest
    ) -> AsyncGenerator[str, None]:
        """
        Execute workflow and return SSE stream
        
        Args:
            request: Workflow execution request
            
        Yields:
            SSE event lines from Dify API
        """
        url = f"{self.base_url}{self.endpoint}"
        
        # Prepare request data with fixed parameters
        request_data = {
            "inputs": {
                "user_query": request.user_query
            },
            "response_mode": "streaming",  # Force streaming mode
            "user": "default_user"  # Fixed user identifier
        }
        
        logger.info(f"Sending request to Dify API: {url}")
        logger.debug(f"Request data: {json.dumps(request_data, indent=2)}")
        
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                headers=self._get_headers()
            ) as client:
                
                async with client.stream(
                    "POST",
                    url,
                    json=request_data
                ) as response:
                    
                    if response.status_code != 200:
                        error_text = await response.aread()
                        logger.error(f"Dify API error: {response.status_code} - {error_text.decode()}")
                        raise httpx.HTTPStatusError(
                            f"Dify API returned {response.status_code}",
                            request=response.request,
                            response=response
                        )
                    
                    logger.info("Successfully connected to Dify API, processing SSE stream")
                    
                    # Buffer for incomplete lines
                    buffer = ""
                    
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            # Decode chunk and add to buffer
                            chunk_str = chunk.decode('utf-8', errors='ignore')
                            buffer += chunk_str
                            
                            # Process complete lines
                            while '\n' in buffer:
                                line, buffer = buffer.split('\n', 1)
                                line = line.strip()
                                
                                if line:
                                    logger.debug(f"Received SSE line: {line[:200]}...")
                                    yield line
                    
                    # Process any remaining data in buffer
                    if buffer.strip():
                        logger.debug(f"Processing final buffer: {buffer[:200]}...")
                        yield buffer.strip()
                        
        except httpx.TimeoutException as e:
            logger.error(f"Timeout connecting to Dify API: {str(e)}")
            raise Exception(f"Dify API timeout: {str(e)}")
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Dify API: {str(e)}")
            raise Exception(f"Dify API HTTP error: {str(e)}")
            
        except Exception as e:
            logger.error(f"Unexpected error connecting to Dify API: {str(e)}")
            raise Exception(f"Dify API connection error: {str(e)}")
    
    async def execute_workflow_blocking(
        self, 
        request: WorkflowExecutionRequest
    ) -> Dict[str, Any]:
        """
        Execute workflow in blocking mode (for testing)
        
        Args:
            request: Workflow execution request
            
        Returns:
            Complete workflow response
        """
        url = f"{self.base_url}{self.endpoint}"
        
        request_data = {
            "inputs": {
                "user_query": request.user_query
            },
            "response_mode": "blocking",
            "user": "default_user"  # Fixed user identifier
        }
        
        logger.info(f"Sending blocking request to Dify API: {url}")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    json=request_data,
                    headers=self._get_headers()
                )
                
                if response.status_code != 200:
                    logger.error(f"Dify API error: {response.status_code} - {response.text}")
                    raise httpx.HTTPStatusError(
                        f"Dify API returned {response.status_code}",
                        request=response.request,
                        response=response
                    )
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Error in blocking request to Dify API: {str(e)}")
            raise Exception(f"Dify API blocking request error: {str(e)}")