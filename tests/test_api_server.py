"""
Tests for api_server.py FastAPI HTTP endpoints
"""

import sys
import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

# Configure environment for tests
os.environ["PG_HOST"] = "localhost"
os.environ["PG_PORT"] = "5432"
os.environ["PG_DATABASE"] = "claude_memory"
os.environ["PG_USER"] = "claude"
os.environ["PG_PASSWORD"] = "test_password"
os.environ["OLLAMA_HOST"] = "http://localhost:11434"
os.environ["REQUIRE_AUTH"] = "false"
sys.path.insert(0, "src")

from fastapi.testclient import TestClient

@pytest.fixture
def test_client():
    with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create_pool:
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()
        mock_create_pool.return_value = mock_pool
        
        from api_server import app
        with TestClient(app) as client:
            yield client

def test_health(test_client):
    """Test standard health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

@patch("api_server.pool")
def test_ready(mock_pool, test_client):
    """Test readiness check endpoint."""
    import api_server
    api_server.pool = MagicMock()
    api_server.pool.close = AsyncMock()
    
    mock_conn = AsyncMock()
    mock_conn.execute.return_value = "SELECT 1"
    
    api_server.pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    api_server.pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    
    response = test_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

@patch("src.server.mcp.list_tools")
def test_get_mcp_tools(mock_list_tools, test_client):
    """Test /mcp/tools endpoint."""
    # Mocking Tool objects from FastMCP
    mock_tool = MagicMock()
    mock_tool.name = "store_memory"
    mock_tool.description = "Store a memory"
    mock_tool.inputSchema = {"properties": {}}
    
    mock_list_tools.return_value = [mock_tool]
    
    response = test_client.get("/mcp/tools")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "store_memory"
    assert response.json()[0]["description"] == "Store a memory"

@patch("src.server.mcp.call_tool")
def test_execute_mcp_tool(mock_call_tool, test_client):
    """Test /mcp/call endpoint."""
    mock_response = MagicMock()
    mock_response.model_dump.return_value = {"type": "text", "text": "Successfully stored memory"}
    
    # FastMCP returns a tuple of (result_list, extra_dict)
    mock_call_tool.return_value = ([mock_response], {"result": "success"})
    
    response = test_client.post("/mcp/call", json={"name": "store_memory", "arguments": {"content": "hello"}})
    assert response.status_code == 200
    assert response.json() == {"result": [{"type": "text", "text": "Successfully stored memory"}]}
