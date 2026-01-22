"""Long-term memory engine for Jarvis AI Agent.

This module provides persistent key-value storage for user preferences,
habits, personal details, and configuration. Memory survives system restarts
and is stored in a JSON file.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import asyncio
from threading import Lock


logger = logging.getLogger("jarvis.memory_engine")

MEMORY_FILE_PATH = "data/memory.json"
MEMORY_LOCK = Lock()


def _ensure_data_directory():
    """Ensure the data directory exists."""
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)


def _load_memory_from_disk() -> Dict[str, Any]:
    """Load memory from disk. Returns empty dict if file doesn't exist."""
    _ensure_data_directory()
    
    if not os.path.exists(MEMORY_FILE_PATH):
        return {}
    
    try:
        with open(MEMORY_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                logger.error(f"Memory file contains invalid data type: {type(data)}")
                return {}
            return data
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse memory file: {exc!r}")
        return {}
    except Exception as exc:
        logger.error(f"Failed to load memory from disk: {exc!r}")
        return {}


def _save_memory_to_disk(memory: Dict[str, Any]) -> bool:
    """Save memory to disk. Returns True on success."""
    _ensure_data_directory()
    
    try:
        with open(MEMORY_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:
        logger.error(f"Failed to save memory to disk: {exc!r}")
        return False


async def save_memory(key: str, value: str) -> Dict[str, Any]:
    """Save a memory entry with key-value pair.
    
    This function writes a key-value pair to persistent storage. If the key
    exists, it updates the value. Prevents storing duplicates, empty values,
    or invalid data.
    
    Args:
        key: Memory key (e.g., "email_preference", "assistant_name")
        value: Memory value (e.g., "short emails", "David")
    
    Returns:
        {
            "success": True,
            "message": "Memory saved successfully",
            "key": "email_preference",
            "value": "short emails"
        }
    """
    # Validate inputs
    if not key or not isinstance(key, str):
        return {
            "success": False,
            "error": "INVALID_KEY",
            "message": "Memory key must be a non-empty string"
        }
    
    if not value or not isinstance(value, str):
        return {
            "success": False,
            "error": "INVALID_VALUE",
            "message": "Memory value must be a non-empty string"
        }
    
    key = key.strip()
    value = value.strip()
    
    if not key or not value:
        return {
            "success": False,
            "error": "EMPTY_DATA",
            "message": "Key and value cannot be empty"
        }
    
    try:
        with MEMORY_LOCK:
            memory = _load_memory_from_disk()
            
            # Check if updating existing key
            is_update = key in memory
            
            # Store with metadata
            memory[key] = {
                "value": value,
                "created_at": memory.get(key, {}).get("created_at", datetime.now().isoformat()),
                "updated_at": datetime.now().isoformat()
            }
            
            success = _save_memory_to_disk(memory)
            
            if not success:
                return {
                    "success": False,
                    "error": "SAVE_FAILED",
                    "message": "Failed to save memory to disk"
                }
            
            action = "updated" if is_update else "saved"
            logger.info(f"Memory {action}: {key} = {value}")
            
            return {
                "success": True,
                "message": f"Memory {action} successfully",
                "key": key,
                "value": value,
                "is_update": is_update
            }
    
    except Exception as exc:
        logger.error(f"Error saving memory: {exc!r}")
        return {
            "success": False,
            "error": f"SAVE_ERROR: {exc!r}",
            "message": "An error occurred while saving memory"
        }


async def load_memory() -> Dict[str, Any]:
    """Load all memory entries from persistent storage.
    
    Returns all stored memory as a list of key-value pairs. This function
    NEVER fails silently - it always returns a valid response.
    
    Returns:
        {
            "success": True,
            "memory": [
                {"key": "email_preference", "value": "short emails"},
                {"key": "assistant_name", "value": "David"}
            ],
            "count": 2
        }
    """
    try:
        with MEMORY_LOCK:
            memory = _load_memory_from_disk()
            
            # Convert to list format
            memory_list = []
            for key, data in memory.items():
                if isinstance(data, dict) and "value" in data:
                    memory_list.append({
                        "key": key,
                        "value": data["value"],
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at")
                    })
                else:
                    # Handle legacy format (direct string values)
                    memory_list.append({
                        "key": key,
                        "value": str(data)
                    })
            
            logger.info(f"Loaded {len(memory_list)} memory entries")
            
            return {
                "success": True,
                "memory": memory_list,
                "count": len(memory_list)
            }
    
    except Exception as exc:
        logger.error(f"Error loading memory: {exc!r}")
        return {
            "success": False,
            "error": f"LOAD_ERROR: {exc!r}",
            "message": "An error occurred while loading memory",
            "memory": [],
            "count": 0
        }


async def delete_memory(key: str) -> Dict[str, Any]:
    """Delete a memory entry by key.
    
    Removes a memory entry from persistent storage. Returns an error if
    the key doesn't exist.
    
    Args:
        key: Memory key to delete
    
    Returns:
        {
            "success": True,
            "message": "Memory deleted successfully",
            "key": "email_preference"
        }
    """
    if not key or not isinstance(key, str):
        return {
            "success": False,
            "error": "INVALID_KEY",
            "message": "Memory key must be a non-empty string"
        }
    
    key = key.strip()
    
    if not key:
        return {
            "success": False,
            "error": "EMPTY_KEY",
            "message": "Key cannot be empty"
        }
    
    try:
        with MEMORY_LOCK:
            memory = _load_memory_from_disk()
            
            if key not in memory:
                return {
                    "success": False,
                    "error": "KEY_NOT_FOUND",
                    "message": f"Memory key '{key}' does not exist"
                }
            
            deleted_value = memory[key]
            del memory[key]
            
            success = _save_memory_to_disk(memory)
            
            if not success:
                return {
                    "success": False,
                    "error": "DELETE_FAILED",
                    "message": "Failed to delete memory from disk"
                }
            
            logger.info(f"Memory deleted: {key}")
            
            return {
                "success": True,
                "message": "Memory deleted successfully",
                "key": key,
                "deleted_value": deleted_value.get("value") if isinstance(deleted_value, dict) else str(deleted_value)
            }
    
    except Exception as exc:
        logger.error(f"Error deleting memory: {exc!r}")
        return {
            "success": False,
            "error": f"DELETE_ERROR: {exc!r}",
            "message": "An error occurred while deleting memory"
        }


async def list_memory() -> Dict[str, Any]:
    """List all memory keys.
    
    Returns a list of all stored memory keys without their values.
    Useful for discovering what's stored in memory.
    
    Returns:
        {
            "success": True,
            "keys": ["email_preference", "assistant_name"],
            "count": 2
        }
    """
    try:
        with MEMORY_LOCK:
            memory = _load_memory_from_disk()
            keys = list(memory.keys())
            
            logger.info(f"Listed {len(keys)} memory keys")
            
            return {
                "success": True,
                "keys": keys,
                "count": len(keys)
            }
    
    except Exception as exc:
        logger.error(f"Error listing memory: {exc!r}")
        return {
            "success": False,
            "error": f"LIST_ERROR: {exc!r}",
            "message": "An error occurred while listing memory",
            "keys": [],
            "count": 0
        }


async def search_memory(query: str) -> Dict[str, Any]:
    """Search memory by keyword in keys or values.
    
    Args:
        query: Search query string
    
    Returns:
        {
            "success": True,
            "results": [
                {"key": "email_preference", "value": "short emails"}
            ],
            "count": 1
        }
    """
    if not query or not isinstance(query, str):
        return {
            "success": False,
            "error": "INVALID_QUERY",
            "message": "Search query must be a non-empty string"
        }
    
    query = query.strip().lower()
    
    if not query:
        return {
            "success": False,
            "error": "EMPTY_QUERY",
            "message": "Search query cannot be empty"
        }
    
    try:
        with MEMORY_LOCK:
            memory = _load_memory_from_disk()
            results = []
            
            for key, data in memory.items():
                value = data.get("value") if isinstance(data, dict) else str(data)
                
                # Search in key or value
                if query in key.lower() or query in value.lower():
                    results.append({
                        "key": key,
                        "value": value
                    })
            
            logger.info(f"Search '{query}' found {len(results)} results")
            
            return {
                "success": True,
                "results": results,
                "count": len(results),
                "query": query
            }
    
    except Exception as exc:
        logger.error(f"Error searching memory: {exc!r}")
        return {
            "success": False,
            "error": f"SEARCH_ERROR: {exc!r}",
            "message": "An error occurred while searching memory",
            "results": [],
            "count": 0
        }


def inject_memory_context(memory_list: List[Dict[str, str]], max_entries: int = 10) -> str:
    """Inject memory context into LLM prompt.
    
    This function formats memory entries into a clean string that can be
    injected into the LLM context. It filters out irrelevant memory and
    provides only the most important facts.
    
    Args:
        memory_list: List of memory entries from load_memory()
        max_entries: Maximum number of entries to include (default: 10)
    
    Returns:
        Formatted memory context string
    """
    if not memory_list:
        return ""
    
    # Limit to max_entries
    memory_list = memory_list[:max_entries]
    
    lines = ["LONG-TERM MEMORY:"]
    for entry in memory_list:
        key = entry.get("key", "")
        value = entry.get("value", "")
        if key and value:
            lines.append(f"- {key}: {value}")
    
    if len(lines) == 1:
        return ""
    
    return "\n".join(lines)


async def classify_memory(user_message: str) -> Dict[str, Any]:
    """Classify whether a user message should be stored in long-term memory.
    
    This function analyzes user messages and determines if they contain
    information worth storing permanently (preferences, habits, personal
    details, goals, configuration).
    
    Args:
        user_message: The user's message to analyze
    
    Returns:
        {
            "should_store": True,
            "key": "email_preference",
            "value": "short emails",
            "reason": "User preference detected"
        }
    """
    if not user_message or not isinstance(user_message, str):
        return {
            "should_store": False,
            "reason": "Invalid message"
        }
    
    message_lower = user_message.lower().strip()
    
    # Keywords that indicate storable information
    preference_keywords = [
        "i prefer", "i like", "i want", "i need", "i always",
        "my preference", "please remember", "remember that",
        "from now on", "always", "never", "every time",
        "my assistant", "my manager", "my team", "my colleague"
    ]
    
    # Keywords that indicate temporary information (DO NOT STORE)
    temporary_keywords = [
        "right now", "today", "tomorrow", "this week",
        "can you", "please", "could you", "schedule",
        "create a task", "send an email", "what time"
    ]
    
    # Check for temporary indicators first
    for keyword in temporary_keywords:
        if keyword in message_lower:
            return {
                "should_store": False,
                "reason": "Temporary instruction detected"
            }
    
    # Check for preference indicators
    for keyword in preference_keywords:
        if keyword in message_lower:
            # Try to extract key-value pair
            # Simple heuristic: look for patterns like "I prefer X" or "my Y is Z"
            
            if "i prefer" in message_lower:
                parts = message_lower.split("i prefer", 1)
                if len(parts) == 2:
                    value = parts[1].strip()
                    return {
                        "should_store": True,
                        "key": "preference",
                        "value": value,
                        "reason": "User preference detected"
                    }
            
            if "my" in message_lower and "is" in message_lower:
                # Pattern: "my X is Y"
                parts = message_lower.split("my", 1)
                if len(parts) == 2:
                    rest = parts[1].strip()
                    if " is " in rest:
                        key_value = rest.split(" is ", 1)
                        if len(key_value) == 2:
                            key = key_value[0].strip().replace(" ", "_")
                            value = key_value[1].strip()
                            return {
                                "should_store": True,
                                "key": key,
                                "value": value,
                                "reason": "Personal detail detected"
                            }
            
            if "remember" in message_lower:
                # Pattern: "remember that X" or "please remember X"
                if "remember that" in message_lower:
                    parts = message_lower.split("remember that", 1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        return {
                            "should_store": True,
                            "key": "note",
                            "value": value,
                            "reason": "Explicit memory request"
                        }
                elif "remember" in message_lower:
                    parts = message_lower.split("remember", 1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        return {
                            "should_store": True,
                            "key": "note",
                            "value": value,
                            "reason": "Explicit memory request"
                        }
            
            # Generic preference storage
            return {
                "should_store": True,
                "key": "user_preference",
                "value": user_message,
                "reason": "Preference keyword detected"
            }
    
    # No storable information detected
    return {
        "should_store": False,
        "reason": "No storable information detected"
    }
