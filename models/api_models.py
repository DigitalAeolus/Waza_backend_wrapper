"""
API Models for Dify SSE Proxy API
"""
from typing import Any, Dict, Optional, Union, Literal
from pydantic import BaseModel, Field, field_validator


class DifyInputFile(BaseModel):
    """Input file object for Dify workflow"""
    type: str = Field(..., description="File type: document, image, etc.")
    transfer_method: str = Field(..., description="Transfer method: local_file, remote_url")
    upload_file_id: Optional[str] = Field(None, description="Upload file ID for local files")
    url: Optional[str] = Field(None, description="URL for remote files")


class WorkflowExecutionRequest(BaseModel):
    """Simplified request model for workflow execution"""
    user_query: str = Field(
        ...,
        description="User query to process",
        json_schema_extra={"example": "Hello, how are you today?"}
    )


class SimplifiedWorkflowResponse(BaseModel):
    """Simplified response model for workflow execution"""
    workflow_run_id: str = Field(..., description="Workflow execution ID")
    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Execution status")
    result: Optional[Dict[str, Any]] = Field(None, description="Parsed result data")


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Error details")
    workflow_run_id: Optional[str] = Field(None, description="Workflow run ID if available")