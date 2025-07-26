"""
Basic tests for the Dify SSE Proxy API
"""
import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from main import app
from models.api_models import WorkflowExecutionRequest
from services.sse_processor import SSEProcessor
from services.dify_client import DifyClient


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def sample_request():
    """Sample workflow request"""
    return {
        "user_query": "Hello, world!"
    }


@pytest.fixture
def sample_sse_lines():
    """Sample SSE lines from Dify API"""
    return [
        "event: workflow_started",
        'data: {"event": "workflow_started", "task_id": "123", "workflow_run_id": "456", "data": {}}',
        "event: node_started", 
        'data: {"event": "node_started", "task_id": "123", "workflow_run_id": "456", "data": {}}',
        "event: node_finished",
        'data: {"event": "node_finished", "task_id": "123", "workflow_run_id": "456", "data": {}}',
        "event: workflow_finished",
        'data: {"event": "workflow_finished", "task_id": "123", "workflow_run_id": "456", "data": {"status": "succeeded", "outputs": {"result": "{\\"translation\\": \\"Bonjour le monde!\\", \\"confidence\\": 0.95}"}}}',
    ]


class TestHealthEndpoints:
    """Test health check endpoints"""
    
    def test_root_endpoint(self, client):
        """Test root health endpoint"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    @patch('services.dify_client.DifyClient.health_check')
    def test_health_check_healthy(self, mock_health_check, client):
        """Test health check when services are healthy"""
        mock_health_check.return_value = True
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["services"]["dify_api"] == "healthy"
    
    @patch('services.dify_client.DifyClient.health_check')
    def test_health_check_unhealthy(self, mock_health_check, client):
        """Test health check when Dify API is unhealthy"""
        mock_health_check.return_value = False
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["services"]["dify_api"] == "unhealthy"


class TestSSEProcessor:
    """Test SSE processor functionality"""
    
    def test_parse_sse_line_data(self):
        """Test parsing SSE data lines"""
        processor = SSEProcessor()
        
        # Test data line
        line = 'data: {"event": "test", "message": "hello"}'
        event = processor._parse_sse_line(line)
        
        assert event is not None
        assert event.event == "message"  # default event type
        assert event.data == '{"event": "test", "message": "hello"}'
    
    def test_parse_sse_line_event(self):
        """Test parsing SSE event lines"""
        processor = SSEProcessor()
        
        # Test event line
        event_line = "event: workflow_started"
        result = processor._parse_sse_line(event_line)
        assert result is None  # Event lines don't return events directly
        
        # Test subsequent data line
        data_line = 'data: {"task_id": "123"}'
        event = processor._parse_sse_line(data_line)
        assert event is not None
        assert event.event == "workflow_started"
    
    def test_parse_sse_line_empty(self):
        """Test parsing empty SSE lines"""
        processor = SSEProcessor()
        
        # Test empty line
        assert processor._parse_sse_line("") is None
        assert processor._parse_sse_line("   ") is None
        
        # Test comment line
        assert processor._parse_sse_line(": this is a comment") is None
    
    def test_is_workflow_finished_event(self):
        """Test workflow_finished event detection"""
        processor = SSEProcessor()
        
        # Test workflow_finished event
        from models.dify_models import DifySSEEvent
        event = DifySSEEvent(
            event="workflow_finished",
            data='{"event": "workflow_finished", "task_id": "123"}'
        )
        assert processor._is_workflow_finished_event(event) is True
        
        # Test other event
        event = DifySSEEvent(
            event="node_started", 
            data='{"event": "node_started", "task_id": "123"}'
        )
        assert processor._is_workflow_finished_event(event) is False
    
    def test_extract_workflow_result(self):
        """Test workflow result extraction"""
        processor = SSEProcessor()
        
        from models.dify_models import DifySSEEvent
        
        # Test successful result extraction
        event_data = {
            "event": "workflow_finished",
            "task_id": "123",
            "workflow_run_id": "456", 
            "data": {
                "status": "succeeded",
                "outputs": {
                    "result": '{"translation": "Bonjour le monde!", "confidence": 0.95}'
                }
            }
        }
        
        event = DifySSEEvent(
            event="workflow_finished",
            data=json.dumps(event_data)
        )
        
        result = processor._extract_workflow_result(event)
        assert result is not None
        assert result["workflow_run_id"] == "456"
        assert result["task_id"] == "123"
        assert result["status"] == "succeeded"
        assert result["result"]["translation"] == "Bonjour le monde!"
        assert result["result"]["confidence"] == 0.95
    
    def test_extract_workflow_result_invalid_json(self):
        """Test workflow result extraction with invalid JSON"""
        processor = SSEProcessor()
        
        from models.dify_models import DifySSEEvent
        
        # Test with invalid JSON in result
        event_data = {
            "event": "workflow_finished",
            "task_id": "123",
            "workflow_run_id": "456",
            "data": {
                "status": "succeeded", 
                "outputs": {
                    "result": "This is not JSON"
                }
            }
        }
        
        event = DifySSEEvent(
            event="workflow_finished",
            data=json.dumps(event_data)
        )
        
        result = processor._extract_workflow_result(event)
        assert result is not None
        assert result["result"]["text"] == "This is not JSON"


class TestDifyClient:
    """Test Dify client functionality"""
    
    def test_get_headers(self):
        """Test authentication headers"""
        client = DifyClient()
        headers = client._get_headers()
        
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Bearer")
        assert "Content-Type" in headers
        assert headers["Content-Type"] == "application/json"
    
    @patch('httpx.AsyncClient.head')
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_head):
        """Test successful health check"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_head.return_value = mock_response
        
        client = DifyClient()
        result = await client.health_check()
        assert result is True
    
    @patch('httpx.AsyncClient.head')
    @pytest.mark.asyncio
    async def test_health_check_failure(self, mock_head):
        """Test failed health check"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_head.return_value = mock_response
        
        client = DifyClient()
        result = await client.health_check()
        assert result is False


class TestAPIModels:
    """Test API model validation"""
    
    def test_workflow_execution_request_valid(self):
        """Test valid workflow execution request"""
        request_data = {
            "user_query": "Hello, how are you?"
        }
        
        request = WorkflowExecutionRequest(**request_data)
        assert request.user_query == "Hello, how are you?"
    
    def test_workflow_execution_request_missing_query(self):
        """Test missing user_query"""
        from pydantic import ValidationError
        request_data = {}
        
        with pytest.raises(ValidationError):
            WorkflowExecutionRequest(**request_data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])