"""
GIPHY API Client Module.

This module provides a client for interacting with the GIPHY Search API.
It handles API key management, request caching, and error handling.
"""

import os
import logging
from typing import List

try:
    import requests
except ImportError:
    requests = None

__all__ = ["GiphyClient", "search_gifs"]

logger = logging.getLogger("audiogiphy.giphy_client")


class GiphyClient:
    """
    Client for GIPHY Search API.
    
    Handles API authentication, request caching, and error handling.
    API key is read from GIPHY_API_KEY environment variable.
    """
    
    def __init__(self, api_key: str | None = None):
        """
        Initialize GIPHY client.
        
        Args:
            api_key: GIPHY API key. If None, reads from GIPHY_API_KEY env var.
                    If still None, client operates in placeholder mode.
        """
        if api_key is None:
            api_key = os.getenv("GIPHY_API_KEY")
        
        self.api_key = api_key
        self.placeholder_mode = api_key is None or api_key == ""
        self._cache: dict[str, List[str]] = {}  # query -> list of URLs
        
        if requests is None:
            logger.warning("requests library not installed. GIPHY client will operate in placeholder mode.")
            self.placeholder_mode = True
        
        if self.placeholder_mode:
            logger.info("GiphyClient is in placeholder mode (no API key provided)")
        else:
            # Only log partial key for debugging (first 8 chars)
            logger.info(f"GiphyClient initialized with API key: {api_key[:8]}...")
    
    def search_gifs(self, query: str, limit: int = 25, rating: str = "g", lang: str = "en") -> List[str]:
        """
        Search for GIFs using GIPHY Search API.
        
        Results are cached in memory for the duration of the client instance.
        Repeated calls with the same query return cached results.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return (default: 25)
            rating: Content rating (default: "g" for general audience)
            lang: Language code (default: "en")
            
        Returns:
            List of MP4 URLs from GIPHY. Empty list if:
            - Client is in placeholder mode
            - API request fails
            - No results found
        """
        if self.placeholder_mode:
            logger.debug(f"Placeholder mode: would search for '{query}' (limit={limit})")
            return []
        
        if requests is None:
            logger.warning("requests library not available, cannot make GIPHY API calls")
            return []
        
        # Normalize query for cache key (lowercase, stripped)
        cache_key = query.lower().strip()
        
        # Check cache first
        if cache_key in self._cache:
            logger.debug(f"Cache hit for query: '{query}'")
            return self._cache[cache_key]
        
        # Make API request
        try:
            url = "https://api.giphy.com/v1/gifs/search"
            params = {
                "api_key": self.api_key,
                "q": query,
                "limit": limit,
                "rating": rating,
                "lang": lang,
            }
            
            logger.info(f"Searching GIPHY for: '{query}' (limit={limit})")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # Parse response
            data = response.json()
            gifs = data.get("data", [])
            
            # Extract MP4 URLs (prefer original.mp4, fallback to other formats)
            mp4_urls: List[str] = []
            for gif_data in gifs:
                images = gif_data.get("images", {})
                # Try original.mp4 first
                if "original" in images and "mp4" in images["original"]:
                    mp4_url = images["original"]["mp4"]
                    if mp4_url:
                        mp4_urls.append(mp4_url)
                # Fallback to fixed_height.mp4
                elif "fixed_height" in images and "mp4" in images["fixed_height"]:
                    mp4_url = images["fixed_height"]["mp4"]
                    if mp4_url:
                        mp4_urls.append(mp4_url)
            
            # Cache results
            self._cache[cache_key] = mp4_urls
            
            logger.info(f"Found {len(mp4_urls)} GIFs for query '{query}'")
            return mp4_urls
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"GIPHY API request failed for query '{query}': {e}")
            return []
        except (KeyError, ValueError, TypeError) as e:
            logger.warning(f"Failed to parse GIPHY API response for query '{query}': {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error during GIPHY search for query '{query}': {e}", exc_info=True)
            return []


def search_gifs(query: str, limit: int = 25) -> List[str]:
    """
    Convenience function to search GIPHY GIFs.
    
    Creates a GiphyClient instance and searches for the given query.
    Note: This creates a new client each time, so caching is not shared
    across calls. For better performance, create a GiphyClient instance
    and reuse it.
    
    Args:
        query: Search query string
        limit: Maximum number of results to return
        
    Returns:
        List of MP4 URLs from GIPHY
    """
    client = GiphyClient()
    return client.search_gifs(query, limit=limit)

