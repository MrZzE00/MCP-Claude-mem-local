"""
Tests for MCP-Claude-mem-local MCP Server
"""

import pytest
import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock

# Set test environment
os.environ["PG_HOST"] = "localhost"
os.environ["PG_PORT"] = "5432"
os.environ["PG_DATABASE"] = "synaptic_test"
os.environ["PG_USER"] = "synaptic"
os.environ["PG_PASSWORD"] = "test_password"
os.environ["OLLAMA_HOST"] = "http://localhost:11434"


class TestEmbeddings:
    """Test embedding generation."""

    @pytest.mark.asyncio
    async def test_format_embedding(self):
        """Test embedding formatting for pgvector."""
        # Import here to avoid import errors before env is set
        import sys
        sys.path.insert(0, "src")
        from server import format_embedding
        
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]
        result = format_embedding(embedding)
        
        assert result == "[0.1,0.2,0.3,0.4,0.5]"
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_format_embedding_empty(self):
        """Test formatting empty embedding."""
        import sys
        sys.path.insert(0, "src")
        from server import format_embedding
        
        embedding = []
        result = format_embedding(embedding)
        
        assert result == "[]"

    @pytest.mark.asyncio
    async def test_format_embedding_large(self):
        """Test formatting large embedding (768 dimensions)."""
        import sys
        sys.path.insert(0, "src")
        from server import format_embedding
        
        embedding = [0.001 * i for i in range(768)]
        result = format_embedding(embedding)
        
        assert result.startswith("[")
        assert result.endswith("]")
        assert len(result.split(",")) == 768


class TestStoreMemory:
    """Test memory storage."""

    @pytest.mark.asyncio
    async def test_store_memory_success(self):
        """Test storing a memory successfully."""
        import sys
        sys.path.insert(0, "src")
        from server import store_memory
        
        # Mock dependencies
        with patch("server.get_embedding") as mock_embed, \
             patch("server.get_pool") as mock_pool:
            
            # Setup mocks
            mock_embed.return_value = [0.1] * 768
            
            mock_conn = AsyncMock()
            mock_conn.fetchrow.return_value = {"id": "test-uuid-1234"}
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            # Execute
            result = await store_memory(
                content="Test bug fix for authentication",
                category="bugfix",
                summary="Auth bug fix",
                tags=["auth", "security"],
                importance=0.8,
                project="test-project"
            )
            
            # Assert
            assert "Memory stored with ID:" in result
            assert "test-uuid-1234" in result
            mock_embed.assert_called_once()

    @pytest.mark.asyncio
    async def test_store_memory_auto_summary(self):
        """Test auto-generating summary when not provided."""
        import sys
        sys.path.insert(0, "src")
        from server import store_memory
        
        with patch("server.get_embedding") as mock_embed, \
             patch("server.get_pool") as mock_pool:
            
            mock_embed.return_value = [0.1] * 768
            mock_conn = AsyncMock()
            mock_conn.fetchrow.return_value = {"id": "test-uuid"}
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            # Long content without summary
            long_content = "A" * 200
            result = await store_memory(
                content=long_content,
                category="discovery"
            )
            
            assert "Memory stored with ID:" in result

    @pytest.mark.asyncio
    async def test_store_memory_error_handling(self):
        """Test error handling when storage fails."""
        import sys
        sys.path.insert(0, "src")
        from server import store_memory
        
        with patch("server.get_embedding") as mock_embed:
            mock_embed.side_effect = Exception("Ollama connection failed")
            
            result = await store_memory(
                content="Test content",
                category="bugfix"
            )
            
            assert "Error:" in result
            assert "Ollama connection failed" in result


class TestRetrieveMemories:
    """Test memory retrieval."""

    @pytest.mark.asyncio
    async def test_retrieve_memories_success(self):
        """Test retrieving memories successfully."""
        import sys
        sys.path.insert(0, "src")
        from server import retrieve_memories
        
        with patch("server.get_embedding") as mock_embed, \
             patch("server.get_pool") as mock_pool:
            
            mock_embed.return_value = [0.1] * 768
            
            mock_conn = AsyncMock()
            mock_conn.fetch.return_value = [
                {
                    "id": "uuid-1",
                    "content": "Bug fix content",
                    "summary": "Bug fix",
                    "category": "bugfix",
                    "tags": ["auth"],
                    "importance_score": 0.8,
                    "similarity": 0.95
                }
            ]
            mock_conn.execute = AsyncMock()
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            result = await retrieve_memories(
                query="authentication bug",
                max_results=5
            )
            
            assert "1 memory(ies) found" in result
            assert "bugfix" in result
            assert "0.95" in result

    @pytest.mark.asyncio
    async def test_retrieve_memories_no_results(self):
        """Test retrieving when no memories match."""
        import sys
        sys.path.insert(0, "src")
        from server import retrieve_memories
        
        with patch("server.get_embedding") as mock_embed, \
             patch("server.get_pool") as mock_pool:
            
            mock_embed.return_value = [0.1] * 768
            mock_conn = AsyncMock()
            mock_conn.fetch.return_value = []
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            result = await retrieve_memories(query="nonexistent topic")
            
            assert "No relevant memories found" in result

    @pytest.mark.asyncio
    async def test_retrieve_memories_with_category_filter(self):
        """Test retrieving with category filter."""
        import sys
        sys.path.insert(0, "src")
        from server import retrieve_memories
        
        with patch("server.get_embedding") as mock_embed, \
             patch("server.get_pool") as mock_pool:
            
            mock_embed.return_value = [0.1] * 768
            mock_conn = AsyncMock()
            mock_conn.fetch.return_value = []
            mock_conn.execute = AsyncMock()
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            await retrieve_memories(
                query="test",
                category="decision"
            )
            
            # Verify the query included category filter
            call_args = mock_conn.fetch.call_args
            assert "category = $4" in call_args[0][0]


class TestListMemories:
    """Test memory listing."""

    @pytest.mark.asyncio
    async def test_list_memories_success(self):
        """Test listing memories."""
        import sys
        sys.path.insert(0, "src")
        from server import list_memories
        
        with patch("server.get_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.fetch.return_value = [
                {
                    "id": "uuid-1",
                    "summary": "Test summary",
                    "category": "bugfix",
                    "tags": ["test"],
                    "importance_score": 0.7,
                    "created_at": None,
                    "access_count": 5
                }
            ]
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            result = await list_memories(limit=10)
            
            assert "1 memory(ies)" in result
            assert "bugfix" in result

    @pytest.mark.asyncio
    async def test_list_memories_empty(self):
        """Test listing when no memories exist."""
        import sys
        sys.path.insert(0, "src")
        from server import list_memories
        
        with patch("server.get_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.fetch.return_value = []
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            result = await list_memories()
            
            assert "No memories stored" in result


class TestMemoryStats:
    """Test memory statistics."""

    @pytest.mark.asyncio
    async def test_memory_stats_success(self):
        """Test getting memory statistics."""
        import sys
        sys.path.insert(0, "src")
        from server import memory_stats
        
        with patch("server.get_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.fetchval.side_effect = [100, 10]  # total, recent
            mock_conn.fetch.side_effect = [
                [{"category": "bugfix", "count": 50}, {"category": "feature", "count": 30}],
                [{"summary": "Top memory", "access_count": 20}]
            ]
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            result = await memory_stats()
            
            assert "100 memories" in result
            assert "10 new" in result
            assert "bugfix: 50" in result


class TestDeleteMemory:
    """Test memory deletion."""

    @pytest.mark.asyncio
    async def test_delete_memory_success(self):
        """Test deleting a memory."""
        import sys
        sys.path.insert(0, "src")
        from server import delete_memory
        
        with patch("server.get_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.execute.return_value = "DELETE 1"
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            result = await delete_memory("550e8400-e29b-41d4-a716-446655440000")
            
            assert "deleted" in result

    @pytest.mark.asyncio
    async def test_delete_memory_not_found(self):
        """Test deleting non-existent memory."""
        import sys
        sys.path.insert(0, "src")
        from server import delete_memory
        
        with patch("server.get_pool") as mock_pool:
            mock_conn = AsyncMock()
            mock_conn.execute.return_value = "DELETE 0"
            mock_pool.return_value.acquire.return_value.__aenter__.return_value = mock_conn
            
            result = await delete_memory("550e8400-e29b-41d4-a716-446655440000")
            
            assert "not found" in result


class TestIntegration:
    """Integration tests (require running services)."""

    @pytest.mark.skip(reason="Requires running PostgreSQL and Ollama")
    @pytest.mark.asyncio
    async def test_full_workflow(self):
        """Test complete store -> retrieve -> delete workflow."""
        import sys
        sys.path.insert(0, "src")
        from server import store_memory, retrieve_memories, delete_memory
        
        # Store
        store_result = await store_memory(
            content="Integration test memory",
            category="discovery",
            summary="Integration test"
        )
        assert "Memory stored with ID:" in store_result
        
        # Extract ID
        memory_id = store_result.split(": ")[1]
        
        # Retrieve
        retrieve_result = await retrieve_memories(query="integration test")
        assert "Integration test" in retrieve_result
        
        # Delete
        delete_result = await delete_memory(memory_id)
        assert "deleted" in delete_result