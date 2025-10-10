import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions
import logging
import os
from typing import List, Dict, Any, Optional
import openai
from django.conf import settings


logger = logging.getLogger(__name__)


class ChromaDBClient:
    """Wrapper for ChromaDB operations with OpenAI embeddings"""
    
    def __init__(self):
        self.client = None
        self.embedding_function = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize ChromaDB client and embedding function"""
        try:
            # Initialize ChromaDB client with HTTP server connection
            chroma_host = getattr(settings, 'CHROMA_HOST', 'localhost')
            chroma_port = getattr(settings, 'CHROMA_PORT', 5000)
            
            self.client = chromadb.HttpClient(
                host=chroma_host,
                port=chroma_port,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Initialize OpenAI embedding function
            openai_api_key = os.getenv('OPENAI_API_KEY')
            if not openai_api_key:
                raise ValueError("OPENAI_API_KEY environment variable is required")
            
            self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
                api_key=openai_api_key,
                model_name="text-embedding-3-small"
            )
            
            logger.info("ChromaDB client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client: {e}")
            raise
    
    def get_or_create_collection(self, collection_name: str) -> chromadb.Collection:
        """Get or create a ChromaDB collection for a project"""
        try:
            collection = self.client.get_collection(
                name=collection_name,
                embedding_function=self.embedding_function
            )
            logger.debug(f"Retrieved existing collection: {collection_name}")
        except (ValueError, Exception):
            # Collection doesn't exist, create it
            collection = self.client.create_collection(
                name=collection_name,
                embedding_function=self.embedding_function,
                metadata={"description": f"Code embeddings for project {collection_name}"}
            )
            logger.info(f"Created new collection: {collection_name}")
        
        return collection
    
    def add_code_chunks(self, collection_name: str, chunks: List[Dict[str, Any]]) -> bool:
        """Add code chunks to ChromaDB collection"""
        try:
            if not chunks:
                logger.warning(f"No chunks provided to add to collection {collection_name}")
                return True  # Empty is success
            
            collection = self.get_or_create_collection(collection_name)
            
            # Prepare and validate data for ChromaDB
            documents = []
            metadatas = []
            ids = []
            
            for i, chunk in enumerate(chunks):
                # Validate chunk structure
                if not isinstance(chunk, dict) or 'content' not in chunk or 'metadata' not in chunk or 'id' not in chunk:
                    logger.error(f"Invalid chunk structure at index {i}: {chunk.keys() if isinstance(chunk, dict) else type(chunk)}")
                    continue
                
                content = chunk['content']

                # Skip empty content
                if not content or not content.strip():
                    logger.debug(f"Skipping chunk {chunk['id']} with empty content")
                    continue

                # Clean content of null bytes and other problematic characters
                content = content.replace('\x00', '').replace('\ufffd', '')

                # Validate content isn't too long - use token estimation
                # OpenAI's text-embedding-3-small has 8192 token limit
                # Conservative estimate: 1 token ≈ 2.5 characters for code
                # (actual ratio varies, but being conservative prevents errors)
                estimated_tokens = len(content) // 2.5
                max_tokens = 6000  # Leave significant buffer below 8192

                if estimated_tokens > max_tokens:
                    # Truncate to fit within token limit
                    max_chars = int(max_tokens * 2.5)
                    logger.warning(f"Truncating large chunk {chunk['id']} from ~{int(estimated_tokens)} tokens to ~{max_tokens} tokens")
                    content = content[:max_chars] + "\n\n# [Content truncated due to token limit]"

                if not content.strip():
                    logger.debug(f"Skipping chunk {chunk['id']} after cleaning - no valid content")
                    continue
                    
                documents.append(content)
                metadatas.append(chunk['metadata'])
                ids.append(str(chunk['id']))
            
            if not documents:
                logger.warning(f"No valid documents to add to collection {collection_name}")
                return True  # No valid content is not an error
            
            # Add documents to collection
            collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Added {len(documents)} chunks to collection {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add chunks to collection {collection_name}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False
    
    def query_similar_code(self, 
                          collection_name: str, 
                          query_texts: List[str], 
                          n_results: int = 10,
                          where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Query ChromaDB for similar code chunks"""
        try:
            collection = self.get_or_create_collection(collection_name)
            
            # Perform semantic search
            results = collection.query(
                query_texts=query_texts,
                n_results=n_results,
                where=where,
                include=['documents', 'metadatas', 'distances']
            )
            
            logger.debug(f"Query returned {len(results['documents'][0])} results from {collection_name}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to query collection {collection_name}: {e}")
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}
    
    def delete_collection(self, collection_name: str) -> bool:
        """Delete a ChromaDB collection"""
        try:
            self.client.delete_collection(name=collection_name)
            logger.info(f"Deleted collection: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete collection {collection_name}: {e}")
            return False
    
    def update_chunk(self, collection_name: str, chunk_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        """Update a specific chunk in ChromaDB"""
        try:
            collection = self.get_or_create_collection(collection_name)
            
            collection.update(
                ids=[chunk_id],
                documents=[content],
                metadatas=[metadata]
            )
            
            logger.debug(f"Updated chunk {chunk_id} in collection {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update chunk {chunk_id} in collection {collection_name}: {e}")
            return False
    
    def delete_chunks(self, collection_name: str, chunk_ids: List[str]) -> bool:
        """Delete specific chunks from ChromaDB collection"""
        try:
            collection = self.get_or_create_collection(collection_name)
            
            collection.delete(ids=chunk_ids)
            
            logger.info(f"Deleted {len(chunk_ids)} chunks from collection {collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete chunks from collection {collection_name}: {e}")
            return False
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Get statistics about a ChromaDB collection"""
        try:
            collection = self.get_or_create_collection(collection_name)
            
            # Get collection count
            count = collection.count()
            
            # Get some sample metadata for analysis
            sample_results = collection.peek(limit=10)
            
            stats = {
                'total_documents': count,
                'sample_metadata': sample_results.get('metadatas', []),
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get stats for collection {collection_name}: {e}")
            return {'total_documents': 0, 'sample_metadata': []}
    
    def health_check(self) -> bool:
        """Check if ChromaDB is accessible and functioning"""
        try:
            # Try to list collections
            collections = self.client.list_collections()
            logger.debug(f"ChromaDB health check passed. Found {len(collections)} collections")
            return True
        except Exception as e:
            logger.error(f"ChromaDB health check failed: {e}")
            return False


# Global client instance
_chroma_client = None


def get_chroma_client() -> ChromaDBClient:
    """Get singleton ChromaDB client instance"""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = ChromaDBClient()
    return _chroma_client


def reset_chroma_client():
    """Reset the global client (useful for testing)"""
    global _chroma_client
    _chroma_client = None