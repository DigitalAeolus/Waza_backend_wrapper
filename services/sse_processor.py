"""
SSE Stream Processor for handling Dify API responses
"""
import json
import logging
import asyncio
from typing import AsyncGenerator, Dict, Any, Optional
from models.api_models import WorkflowExecutionRequest
from models.dify_models import DifySSEEvent, WorkflowFinishedEvent, ErrorEvent
from services.dify_client import DifyClient
from config import settings

logger = logging.getLogger(__name__)


class SSEProcessor:
    """Processor for handling Dify SSE streams and extracting relevant events"""
    
    def __init__(self):
        self.keepalive_timeout = settings.SSE_KEEPALIVE_TIMEOUT
        
    def _parse_sse_line(self, line: str) -> Optional[DifySSEEvent]:
        """
        Parse a single SSE line into a DifySSEEvent
        
        Args:
            line: Raw SSE line from Dify API
            
        Returns:
            Parsed DifySSEEvent or None if parsing fails
        """
        line = line.strip()
        
        # Skip empty lines and comments
        if not line or line.startswith(':'):
            return None
            
        # Handle event lines
        if line.startswith('event:'):
            # Store event type for next data line
            self._current_event = line[6:].strip()
            return None
            
        # Handle data lines
        if line.startswith('data:'):
            data_content = line[5:].strip()
            
            # Skip empty data or keep-alive pings
            if not data_content or data_content == '':
                return None
                
            # Get event type (default to 'message' if not set)
            event_type = getattr(self, '_current_event', 'message')
            
            try:
                return DifySSEEvent(event=event_type, data=data_content)
            except Exception as e:
                logger.warning(f"Failed to parse SSE event: {str(e)} - Line: {line[:100]}")
                return None
                
        return None
    
    def _is_workflow_finished_event(self, event: DifySSEEvent) -> bool:
        """
        Check if the event is a workflow_finished event
        
        Args:
            event: Parsed SSE event
            
        Returns:
            True if this is a workflow_finished event
        """
        try:
            # Parse the data to check event type
            data = event.parse_data()
            return data.get('event') == 'workflow_finished'
        except Exception as e:
            logger.debug(f"Error checking event type: {str(e)}")
            return False
    
    def _extract_workflow_result(self, event: DifySSEEvent) -> Optional[Dict[str, Any]]:
        """
        Extract and parse the workflow result from a workflow_finished event
        
        Args:
            event: workflow_finished SSE event
            
        Returns:
            Parsed result data or None if extraction fails
        """
        try:
            data = event.parse_data()
            
            # Extract basic info
            workflow_run_id = data.get('workflow_run_id', '')
            task_id = data.get('task_id', '')
            
            # Extract result from nested data structure
            event_data = data.get('data', {})
            status = event_data.get('status', 'unknown')
            
            # Extract and parse the result field
            outputs = event_data.get('outputs', {})
            result_raw = outputs.get('result', '')
            
            # Parse result if it's a JSON string
            parsed_result = None
            if isinstance(result_raw, str) and result_raw.strip():
                try:
                    parsed_result = json.loads(result_raw)
                    logger.info(f"Successfully parsed result JSON for task {task_id}")
                except json.JSONDecodeError as e:
                    logger.warning(f"Result is not valid JSON, treating as raw text: {str(e)}")
                    parsed_result = {"text": result_raw}
            elif result_raw:
                # If result is not a string, use as-is
                parsed_result = result_raw
            
            return {
                "workflow_run_id": workflow_run_id,
                "task_id": task_id,
                "status": status,
                "result": parsed_result,
                "event_type": "workflow_finished"
            }
            
        except Exception as e:
            logger.error(f"Failed to extract workflow result: {str(e)}")
            return None
    
    def _create_error_response(
        self, 
        error_msg: str, 
        workflow_run_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create error response in the expected format
        
        Args:
            error_msg: Error message
            workflow_run_id: Optional workflow run ID
            task_id: Optional task ID
            
        Returns:
            Formatted error response
        """
        return {
            "workflow_run_id": workflow_run_id or "unknown",
            "task_id": task_id or "unknown",
            "status": "error",
            "error": error_msg,
            "event_type": "error"
        }
    
    async def process_dify_stream(
        self, 
        dify_client: DifyClient, 
        request: WorkflowExecutionRequest
    ) -> AsyncGenerator[str, None]:
        """
        Process Dify SSE stream and yield simplified results
        
        Args:
            dify_client: Dify API client
            request: Workflow execution request
            
        Yields:
            JSON strings of simplified workflow results
        """
        logger.info(f"Starting SSE stream processing for query: {request.user_query[:50]}...")
        
        workflow_run_id = None
        task_id = None
        
        try:
            # Create keep-alive task
            keepalive_task = asyncio.create_task(self._send_keepalive())
            
            # Process SSE stream from Dify
            async for sse_line in dify_client.execute_workflow_stream(request):
                
                # Cancel keep-alive since we have real data
                if not keepalive_task.done():
                    keepalive_task.cancel()
                
                # Parse SSE line
                event = self._parse_sse_line(sse_line)
                if not event:
                    continue
                
                logger.debug(f"Processing event: {event.event}")
                
                # Extract workflow metadata from any event
                try:
                    data = event.parse_data()
                    if 'workflow_run_id' in data:
                        workflow_run_id = data['workflow_run_id']
                    if 'task_id' in data:
                        task_id = data['task_id']
                except Exception:
                    pass
                
                # Check for error events
                if event.event == 'error' or (hasattr(event, 'parse_data') and event.parse_data().get('event') == 'error'):
                    try:
                        error_data = event.parse_data()
                        error_msg = error_data.get('data', {}).get('error', 'Unknown error from Dify API')
                        error_response = self._create_error_response(
                            error_msg, workflow_run_id, task_id
                        )
                        yield json.dumps(error_response)
                        return  # End stream on error
                    except Exception as e:
                        logger.error(f"Error processing error event: {str(e)}")
                        continue
                
                # Process workflow_finished events
                if self._is_workflow_finished_event(event):
                    logger.info("Found workflow_finished event, extracting result")
                    
                    result = self._extract_workflow_result(event)
                    if result:
                        # Yield the simplified result
                        result_json = json.dumps(result, ensure_ascii=False)
                        logger.info(f"Yielding simplified result: {result_json[:200]}...")
                        yield result_json
                        return  # End stream after workflow completion
                    else:
                        logger.warning("Failed to extract result from workflow_finished event")
                
                # Restart keep-alive task
                keepalive_task = asyncio.create_task(self._send_keepalive())
            
            # If we reach here without finding workflow_finished, it's an error
            logger.warning("Stream ended without workflow_finished event")
            error_response = self._create_error_response(
                "Stream ended without workflow completion", 
                workflow_run_id, 
                task_id
            )
            yield json.dumps(error_response)
            
        except Exception as e:
            logger.error(f"Error processing Dify stream: {str(e)}")
            error_response = self._create_error_response(
                f"Stream processing error: {str(e)}", 
                workflow_run_id, 
                task_id
            )
            yield json.dumps(error_response)
    
    async def _send_keepalive(self):
        """Send keep-alive signal after timeout"""
        try:
            await asyncio.sleep(self.keepalive_timeout)
            # This function completes when the timeout is reached
            # The caller can check if this task is done to determine if keep-alive is needed
        except asyncio.CancelledError:
            # This is expected when real data arrives
            pass