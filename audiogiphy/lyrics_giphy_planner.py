"""
Lyrics GIPHY Planner Module.

This module handles planning GIPHY GIF overlays based on lyric segments
with gif_query keywords from LLM output.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List

from audiogiphy.giphy_client import GiphyClient

__all__ = ["plan_giphy_segments"]

logger = logging.getLogger("audiogiphy.lyrics_giphy_planner")


def plan_giphy_segments(
    segments_json_path: str,
    giphy_client: GiphyClient,
) -> Dict[int, Dict[str, any]]:
    """
    Plan GIPHY GIF overlays for lyric segments.
    
    This function:
    1. Loads LLM-generated JSON with segments and gif_query keywords
    2. Deduplicates gif_query strings
    3. Calls GIPHY API once per unique query (cached by client)
    4. Builds a mapping of segment_id -> gif_query and gif_urls
    
    Args:
        segments_json_path: Path to JSON file with segments structure:
            {
              "segments": [
                {"id": 1, "start": 0.0, "end": 4.0, "gif_query": "club dance floor"},
                {"id": 2, "start": 4.0, "end": 8.0, "gif_query": "money raining"},
                ...
              ]
            }
        giphy_client: Initialized GiphyClient instance
        
    Returns:
        Dictionary mapping segment_id -> {
            "gif_query": str,
            "gif_urls": List[str]
        }
        Example:
        {
            1: {"gif_query": "club dance floor", "gif_urls": ["url1", "url2", ...]},
            2: {"gif_query": "money raining", "gif_urls": ["url3", "url4", ...]},
        }
        
    Raises:
        FileNotFoundError: If segments_json_path doesn't exist
        ValueError: If JSON structure is invalid
    """
    path = Path(segments_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Segments JSON file not found: {segments_json_path}")
    
    # Load JSON
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in segments file: {e}") from e
    
    # Validate structure
    if not isinstance(data, dict) or "segments" not in data:
        raise ValueError("Segments JSON must have a 'segments' key")
    
    segments = data["segments"]
    if not isinstance(segments, list):
        raise ValueError("Segments must be a list")
    
    logger.info(f"Loaded {len(segments)} segments from {segments_json_path}")
    
    # Extract all gif_query strings and deduplicate
    unique_queries: set[str] = set()
    segment_queries: Dict[int, str] = {}  # segment_id -> gif_query
    
    for segment in segments:
        if not isinstance(segment, dict):
            logger.warning(f"Skipping invalid segment (not a dict): {segment}")
            continue
        
        segment_id = segment.get("id")
        gif_query = segment.get("gif_query", "").strip()
        
        if segment_id is None:
            logger.warning(f"Skipping segment without id: {segment}")
            continue
        
        if not gif_query:
            logger.debug(f"Segment {segment_id} has no gif_query, skipping GIPHY lookup")
            continue
        
        unique_queries.add(gif_query)
        segment_queries[segment_id] = gif_query
    
    logger.info(f"Found {len(unique_queries)} unique gif_query strings: {list(unique_queries)}")
    
    # Call GIPHY API for each unique query (caching handled by client)
    query_to_urls: Dict[str, List[str]] = {}
    for query in unique_queries:
        logger.info(f"Fetching GIPHY results for query: '{query}'")
        urls = giphy_client.search_gifs(query, limit=25)
        query_to_urls[query] = urls
        logger.info(f"Got {len(urls)} GIF URLs for query '{query}'")
    
    # Build final mapping: segment_id -> {gif_query, gif_urls, start, end}
    result: Dict[int, Dict[str, any]] = {}
    for segment in segments:
        segment_id = segment.get("id")
        if segment_id is None or segment_id not in segment_queries:
            continue
        
        gif_query = segment_queries[segment_id]
        gif_urls = query_to_urls.get(gif_query, [])
        result[segment_id] = {
            "gif_query": gif_query,
            "gif_urls": gif_urls,
            "start": segment.get("start", 0.0),
            "end": segment.get("end", 0.0),
        }
        logger.debug(f"Segment {segment_id}: query='{gif_query}', {len(gif_urls)} URLs, time={result[segment_id]['start']:.1f}-{result[segment_id]['end']:.1f}s")
    
    logger.info(f"Built GIPHY plan for {len(result)} segments")
    return result

