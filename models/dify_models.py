"""
Dify API Models for SSE Events and Responses
"""
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import json


class DifySSEEvent(BaseModel):
    """Dify SSE Event model"""
    event: str = Field(..., description="Event type")
    data: str = Field(..., description="Event data as JSON string")
    
    def parse_data(self) -> Dict[str, Any]:
        """Parse the data field from JSON string to dict"""
        try:
            return json.loads(self.data)
        except json.JSONDecodeError:
            return {"raw_data": self.data}


class WorkflowStartedEvent(BaseModel):
    """Workflow started event data"""
    task_id: str
    workflow_run_id: str
    event: str = "workflow_started"
    data: Dict[str, Any]


class WorkflowFinishedEvent(BaseModel):
    """Workflow finished event data"""
    task_id: str
    workflow_run_id: str
    event: str = "workflow_finished"
    data: Dict[str, Any]
    
    def extract_result(self) -> Optional[Dict[str, Any]]:
        """Extract and parse the result field from data"""
        if "data" in self.data and "outputs" in self.data["data"]:
            result_str = self.data["data"]["outputs"].get("result", "")
            if isinstance(result_str, str):
                try:
                    return json.loads(result_str)
                except json.JSONDecodeError:
                    return {"raw_result": result_str}
            else:
                return result_str
        return None


class NodeStartedEvent(BaseModel):
    """Node started event data"""
    task_id: str
    workflow_run_id: str
    event: str = "node_started"
    data: Dict[str, Any]


class NodeFinishedEvent(BaseModel):
    """Node finished event data"""
    task_id: str
    workflow_run_id: str
    event: str = "node_finished"
    data: Dict[str, Any]


class ErrorEvent(BaseModel):
    """Error event data"""
    task_id: str
    workflow_run_id: str
    event: str = "error"
    data: Dict[str, Any]