import json
import hashlib
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class DoclingCache:
    """
    Disk-based cache for Docling parsing results.
    Uses SHA256 hash of file content as cache key for reliability.
    """
    
    def __init__(self, cache_dir: str = "docling_cache"):
        """
        Initialize cache manager.
        
        Args:
            cache_dir: Directory to store cache files (relative to project root)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        logger.info(f"Cache directory initialized: {self.cache_dir.absolute()}")
    
    def _calculate_hash(self, file_bytes: bytes) -> str:
        """Calculate SHA256 hash of file content."""
        return hashlib.sha256(file_bytes).hexdigest()
    
    def _get_cache_path(self, file_hash: str) -> Path:
        """Get cache file path for a given hash."""
        return self.cache_dir / f"{file_hash}.json"
    
    def get(self, file_bytes: bytes, source_name: str = "document.pdf") -> Optional[Dict[str, Any]]:
        """
        Retrieve cached parsing result if available.
        
        Args:
            file_bytes: PDF file content as bytes
            source_name: Original filename (for metadata verification)
            
        Returns:
            Parsed document dict if cache hit, None otherwise
        """
        file_hash = self._calculate_hash(file_bytes)
        cache_path = self._get_cache_path(file_hash)
        
        if not cache_path.exists():
            logger.debug(f"Cache miss for {source_name} (hash: {file_hash[:8]}...)")
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
            
            # Verify metadata matches (safety check)
            metadata = cached_data.get("metadata", {})
            cached_hash = metadata.get("file_hash")
            
            if cached_hash != file_hash:
                logger.warning(f"Cache hash mismatch for {source_name}. Invalidating cache.")
                cache_path.unlink()
                return None
            
            logger.info(f"Cache hit for {source_name} (hash: {file_hash[:8]}...)")
            
            # Return data in same format as DoclingParser.parse_pdf()
            return cached_data["data"]
            
        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.error(f"Error reading cache file {cache_path}: {e}. Invalidating cache.")
            try:
                cache_path.unlink()
            except:
                pass
            return None
    
    def set(self, file_bytes: bytes, parsed_data: Dict[str, Any], source_name: str = "document.pdf") -> bool:
        """
        Store parsing result in cache.
        
        Args:
            file_bytes: PDF file content as bytes
            parsed_data: Result from DoclingParser.parse_pdf()
            source_name: Original filename
            
        Returns:
            True if successful, False otherwise
        """
        file_hash = self._calculate_hash(file_bytes)
        cache_path = self._get_cache_path(file_hash)
        
        # Prepare cache entry
        cache_entry = {
            "metadata": {
                "source_file": source_name,
                "cached_at": datetime.utcnow().isoformat(),
                "file_hash": file_hash,
                "file_size_bytes": len(file_bytes)
            },
            "data": self._serialize_data(parsed_data)
        }
        
        try:
            # Atomic write: write to temp file first, then rename
            temp_path = cache_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(cache_entry, f, ensure_ascii=False, indent=2)
            
            # Atomic rename (works on most filesystems)
            temp_path.replace(cache_path)
            
            logger.info(f"Cached parsing result for {source_name} (hash: {file_hash[:8]}...)")
            return True
            
        except (IOError, OSError, TypeError) as e:
            logger.error(f"Error writing cache file {cache_path}: {e}")
            # Clean up temp file if it exists
            try:
                temp_path.unlink(missing_ok=True)
            except:
                pass
            return False
    
    def _serialize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert parsed data to JSON-serializable format.
        Handles pandas DataFrames in tables.
        """
        serialized = {
            "text": data.get("text", ""),
            "chunks": data.get("chunks", [])
        }
        
        # Serialize tables (convert DataFrames to dict format)
        tables = []
        for table in data.get("tables", []):
            table_dict = {
                "id": table.get("id"),
                "page": table.get("page", -1),
                "columns": table.get("columns", []),
                "content": table.get("content", [])  # Already a list of dicts
            }
            tables.append(table_dict)
        
        serialized["tables"] = tables
        return serialized
    
    def clear(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache entries.
        
        Args:
            pattern: Optional filename pattern to match (e.g., "*.json")
                    If None, clears all cache entries.
                    
        Returns:
            Number of files deleted
        """
        deleted = 0
        try:
            if pattern:
                for cache_file in self.cache_dir.glob(pattern):
                    if cache_file.is_file():
                        cache_file.unlink()
                        deleted += 1
            else:
                for cache_file in self.cache_dir.glob("*.json"):
                    if cache_file.is_file():
                        cache_file.unlink()
                        deleted += 1
                # Also clean up temp files
                for temp_file in self.cache_dir.glob("*.tmp"):
                    temp_file.unlink(missing_ok=True)
            
            logger.info(f"Cleared {deleted} cache entries")
            return deleted
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return deleted
    
    def get_cache_size(self) -> int:
        """Get total cache size in bytes."""
        total_size = 0
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                if cache_file.is_file():
                    total_size += cache_file.stat().st_size
        except Exception as e:
            logger.error(f"Error calculating cache size: {e}")
        return total_size
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        cache_files = list(self.cache_dir.glob("*.json"))
        return {
            "cache_dir": str(self.cache_dir.absolute()),
            "total_files": len(cache_files),
            "total_size_bytes": self.get_cache_size(),
            "total_size_mb": round(self.get_cache_size() / (1024 * 1024), 2)
        }


