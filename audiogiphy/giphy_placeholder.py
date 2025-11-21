"""
GIPHY API Integration Placeholder.

This module provides a placeholder for future GIPHY API integration.
Currently, it returns empty results and logs that it's in placeholder mode.

Future implementation would:
1. Call GIPHY API search endpoint: https://api.giphy.com/v1/gifs/search
2. Download GIFs and convert to MP4
3. Return paths to downloaded files for use in visual_builder
"""

import logging
from typing import List

__all__ = ["GiphyClient"]

logger = logging.getLogger("audiogiphy.giphy_placeholder")


class GiphyClient:
    """
    Placeholder client for GIPHY API integration.
    
    In the future, this will:
    - Authenticate with GIPHY API using api_key
    - Search for GIFs based on query terms
    - Download and convert GIFs to MP4 format
    - Return file paths for use in the visual builder
    
    For now, it operates in placeholder mode and uses local video folder instead.
    """
    
    def __init__(self, api_key: str | None = None):
        """
        Initialize GIPHY client.
        
        Args:
            api_key: GIPHY API key (None for placeholder mode)
        """
        self.api_key = api_key
        self.placeholder_mode = api_key is None or api_key == ""
        
        if self.placeholder_mode:
            logger.info("GiphyClient is in placeholder mode, using local video folder instead")
        else:
            logger.info(f"GiphyClient initialized with API key: {api_key[:8]}...")
    
    def search_gifs(self, query: str, limit: int = 50) -> List[str]:
        """
        Search for GIFs using GIPHY API (placeholder implementation).
        
        Future implementation would:
        1. Make HTTP request to: https://api.giphy.com/v1/gifs/search
        2. Parameters: api_key, q=query, limit=limit
        3. Parse JSON response and extract GIF URLs
        4. Download GIFs and convert to MP4
        5. Return list of local file paths
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            
        Returns:
            List of file paths to downloaded/converted MP4 files
            (Empty list in placeholder mode)
        """
        if self.placeholder_mode:
            logger.info(f"Placeholder mode: would search for '{query}' (limit={limit})")
            logger.info("Using local video folder instead of GIPHY API")
            return []
        
        # Future implementation would go here:
        # import requests
        # response = requests.get(
        #     "https://api.giphy.com/v1/gifs/search",
        #     params={"api_key": self.api_key, "q": query, "limit": limit}
        # )
        # ... download and convert GIFs ...
        # return list_of_mp4_paths
        
        logger.info(f"API mode: searching for '{query}' (limit={limit})")
        return []

