"""
Unit tests for RAG Poisoning strategies.
"""

import pytest
import json
import gzip
from unittest.mock import Mock, MagicMock
from agent_chaos_sdk.proxy.strategies.rag import (
    ResponseMutationStrategy,
    PhantomDocumentStrategy
)


class TestResponseMutationStrategy:
    """Test the base ResponseMutationStrategy class."""
    
    @pytest.mark.asyncio
    async def test_intercept_requires_response(self, mock_flow):
        """Test that strategy only applies to responses."""
        # Create a concrete implementation for testing
        class TestStrategy(ResponseMutationStrategy):
            async def _mutate_response(self, body_data, flow):
                return True
        
        strategy = TestStrategy("test")
        result = await strategy.intercept(mock_flow)
        assert result is False  # No response in mock_flow
    
    @pytest.mark.asyncio
    async def test_intercept_skips_non_json(self, mock_flow_with_response):
        """Test that strategy skips non-JSON responses."""
        class TestStrategy(ResponseMutationStrategy):
            async def _mutate_response(self, body_data, flow):
                return True
        
        mock_flow_with_response.response.headers[b"Content-Type"] = b"text/plain"
        strategy = TestStrategy("test")
        result = await strategy.intercept(mock_flow_with_response)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_decode_gzip_response(self, mock_flow_with_response):
        """Test decoding gzip-compressed responses."""
        class TestStrategy(ResponseMutationStrategy):
            async def _mutate_response(self, body_data, flow):
                return True
        
        # Create gzip-compressed JSON
        original_data = {"test": "data"}
        original_text = json.dumps(original_data)
        compressed = gzip.compress(original_text.encode('utf-8'))
        
        mock_flow_with_response.response.content = compressed
        mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
        mock_flow_with_response.response.headers[b"Content-Encoding"] = b"gzip"
        
        strategy = TestStrategy("test")
        result = await strategy.intercept(mock_flow_with_response)
        assert result is True


class TestPhantomDocumentStrategy:
    """Test the PhantomDocumentStrategy."""
    
    @pytest.mark.asyncio
    async def test_phantom_document_overwrite_mode(self, mock_flow_with_response):
        """Test overwrite mode injects fake information."""
        # Mock Pinecone-like response
        response_body = {
            "matches": [
                {
                    "id": "doc1",
                    "metadata": {
                        "text": "The capital of France is Paris."
                    },
                    "score": 0.95
                },
                {
                    "id": "doc2",
                    "metadata": {
                        "text": "Python is a programming language."
                    },
                    "score": 0.88
                }
            ]
        }
        
        response_text = json.dumps(response_body)
        mock_flow_with_response.response.content = response_text.encode('utf-8')
        mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
        
        strategy = PhantomDocumentStrategy(
            "test_phantom",
            target_json_path="$.matches[*].metadata.text",
            mode="overwrite",
            misinformation_source=["FAKE: The Earth is flat."],
            probability=1.0
        )
        
        result = await strategy.intercept(mock_flow_with_response)
        assert result is True
        
        # Verify mutation - decode response content (it's been updated)
        modified_content = mock_flow_with_response.response.content
        if isinstance(modified_content, bytes):
            modified_text = modified_content.decode('utf-8')
        else:
            modified_text = modified_content
        modified_body = json.loads(modified_text)
        
        # At least one field should be mutated
        assert any(
            "FAKE: The Earth is flat." in match["metadata"]["text"]
            for match in modified_body["matches"]
        )
    
    @pytest.mark.asyncio
    async def test_phantom_document_injection_mode(self, mock_flow_with_response):
        """Test injection mode appends conflicting information."""
        response_body = {
            "results": [
                {"snippet": "Original fact about Python."},
                {"snippet": "Another original fact."}
            ]
        }
        
        response_text = json.dumps(response_body)
        mock_flow_with_response.response.content = response_text.encode('utf-8')
        mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
        if not hasattr(mock_flow_with_response.response, 'text'):
            mock_flow_with_response.response.text = response_text
        
        strategy = PhantomDocumentStrategy(
            "test_phantom",
            target_json_path="$.results[*].snippet",
            mode="injection",
            misinformation_source=["CONFLICTING: This is false."],
            probability=1.0
        )
        
        result = await strategy.intercept(mock_flow_with_response)
        assert result is True
        
        # Verify injection - decode response content
        modified_content = mock_flow_with_response.response.content
        if isinstance(modified_content, bytes):
            modified_text = modified_content.decode('utf-8')
        else:
            modified_text = modified_content
        modified_body = json.loads(modified_text)
        
        # Should contain both original and conflicting info
        assert any(
            "Original fact" in result["snippet"] and "CONFLICTING" in result["snippet"]
            for result in modified_body["results"]
        )
    
    @pytest.mark.asyncio
    async def test_phantom_document_respects_probability(self, mock_flow_with_response):
        """Test that strategy respects probability setting."""
        response_body = {"results": [{"snippet": "Test"}]}
        response_text = json.dumps(response_body)
        mock_flow_with_response.response.content = response_text.encode('utf-8')
        mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
        
        # Use a very low probability and test multiple times, or mock random
        import random
        original_random = random.random
        
        # Force random to return high value (above probability threshold)
        def high_random():
            return 0.99
        
        random.random = high_random
        
        try:
            strategy = PhantomDocumentStrategy(
                "test_phantom",
                target_json_path="$.results[*].snippet",
                probability=0.5  # 50% probability
            )
            
            result = await strategy.intercept(mock_flow_with_response)
            # With random() = 0.99 and probability = 0.5, should skip (0.99 >= 0.5)
            assert result is False
        finally:
            random.random = original_random
    
    @pytest.mark.asyncio
    async def test_phantom_document_handles_weaviate_format(self, mock_flow_with_response):
        """Test strategy works with Weaviate response format."""
        response_body = {
            "data": {
                "Get": {
                    "Document": [
                        {
                            "content": "Original document content here.",
                            "title": "Document Title"
                        }
                    ]
                }
            }
        }
        
        response_text = json.dumps(response_body)
        mock_flow_with_response.response.content = response_text.encode('utf-8')
        mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
        if not hasattr(mock_flow_with_response.response, 'text'):
            mock_flow_with_response.response.text = response_text
        
        strategy = PhantomDocumentStrategy(
            "test_phantom",
            target_json_path="$.data.Get.Document[*].content",
            mode="overwrite",
            misinformation_source=["FAKE: Misinformation injected."],
            probability=1.0
        )
        
        result = await strategy.intercept(mock_flow_with_response)
        assert result is True
        
        # Decode response content
        modified_content = mock_flow_with_response.response.content
        if isinstance(modified_content, bytes):
            modified_text = modified_content.decode('utf-8')
        else:
            modified_text = modified_content
        modified_body = json.loads(modified_text)
        
        assert "FAKE: Misinformation injected." in modified_body["data"]["Get"]["Document"][0]["content"]
    
    @pytest.mark.asyncio
    async def test_phantom_document_skips_when_disabled(self, mock_flow_with_response):
        """Test that strategy skips when disabled."""
        response_body = {"results": [{"snippet": "Test"}]}
        response_text = json.dumps(response_body)
        mock_flow_with_response.response.content = response_text.encode('utf-8')
        mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
        
        strategy = PhantomDocumentStrategy(
            "test_phantom",
            enabled=False,
            target_json_path="$.results[*].snippet"
        )
        
        result = await strategy.intercept(mock_flow_with_response)
        assert result is False
    
    def test_phantom_document_loads_misinformation_from_list(self):
        """Test loading misinformation from a list."""
        facts = ["Fact 1", "Fact 2", "Fact 3"]
        strategy = PhantomDocumentStrategy(
            "test",
            misinformation_source=facts
        )
        assert len(strategy.misinformation) == 3
        assert "Fact 1" in strategy.misinformation
    
    def test_phantom_document_uses_default_misinformation(self):
        """Test that default misinformation is used when none provided."""
        strategy = PhantomDocumentStrategy("test")
        assert len(strategy.misinformation) > 0
        assert isinstance(strategy.misinformation, list)
    
    @pytest.mark.asyncio
    async def test_phantom_document_handles_missing_jsonpath(self, mock_flow_with_response):
        """Test that strategy handles missing JSONPath matches gracefully."""
        response_body = {"other": "data"}  # No matching path
        response_text = json.dumps(response_body)
        mock_flow_with_response.response.content = response_text.encode('utf-8')
        mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
        
        strategy = PhantomDocumentStrategy(
            "test_phantom",
            target_json_path="$.nonexistent[*].field",
            probability=1.0
        )
        
        result = await strategy.intercept(mock_flow_with_response)
        # Should return False (no matches found), not raise exception
        assert result is False
    
    @pytest.mark.asyncio
    async def test_phantom_document_handles_gzip_compression(self, mock_flow_with_response):
        """Test that strategy handles gzip-compressed responses."""
        response_body = {
            "matches": [
                {"metadata": {"text": "Original content"}}
            ]
        }
        response_text = json.dumps(response_body)
        compressed = gzip.compress(response_text.encode('utf-8'))
        
        mock_flow_with_response.response.content = compressed
        mock_flow_with_response.response.headers[b"Content-Type"] = b"application/json"
        mock_flow_with_response.response.headers[b"Content-Encoding"] = b"gzip"
        if not hasattr(mock_flow_with_response.response, 'text'):
            mock_flow_with_response.response.text = None
        
        strategy = PhantomDocumentStrategy(
            "test_phantom",
            target_json_path="$.matches[*].metadata.text",
            mode="overwrite",
            misinformation_source=["FAKE: Compressed content"],
            probability=1.0
        )
        
        result = await strategy.intercept(mock_flow_with_response)
        assert result is True
        
        # Verify response is still gzip-compressed
        assert b"Content-Encoding" in mock_flow_with_response.response.headers
        # Verify content was mutated - decompress and check
        decoded = gzip.decompress(mock_flow_with_response.response.content)
        decoded_text = decoded.decode('utf-8')
        decoded_body = json.loads(decoded_text)
        # Check if mutation was applied
        assert "FAKE: Compressed content" in decoded_body["matches"][0]["metadata"]["text"]

