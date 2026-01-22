"""
Gmail Agentic Session Management

This module provides session state management for Gmail agentic interactions,
including pagination, email caching, and user interaction tracking.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
import json

logger = logging.getLogger("jarvis.gmail_session")

# Default chunk size: 2 pages (~100 emails)
DEFAULT_CHUNK_PAGES = 2
# Session expiration: 30 minutes of inactivity
SESSION_EXPIRY_MINUTES = 30

@dataclass
class GmailEmailMetadata:
    """Lightweight metadata for an email in the current session"""
    id: str
    thread_id: str
    subject: str
    from_email: str
    date: str
    snippet: str
    labels: List[str] = field(default_factory=list)
    index: int = 0  # Position in the current displayed list

@dataclass
class GmailSearchSession:
    """Session state for a Gmail search interaction"""
    user_id: int
    query: str
    message_ids: List[str] = field(default_factory=list)
    metadata_cache: Dict[str, GmailEmailMetadata] = field(default_factory=dict)
    current_page_token: Optional[str] = None
    next_page_token: Optional[str] = None
    displayed_indices: List[int] = field(default_factory=list)  # Indices shown to user
    total_fetched: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    
    def is_expired(self) -> bool:
        """Check if session has expired due to inactivity"""
        return datetime.now() - self.last_activity > timedelta(minutes=SESSION_EXPIRY_MINUTES)
    
    def update_activity(self):
        """Update the last activity timestamp"""
        self.last_activity = datetime.now()
    
    def add_emails(self, message_ids: List[str], metadata_list: List[GmailEmailMetadata], next_token: Optional[str] = None):
        """Add new emails to the session"""
        start_index = len(self.message_ids)
        self.message_ids.extend(message_ids)
        
        for i, (msg_id, metadata) in enumerate(zip(message_ids, metadata_list)):
            metadata.index = start_index + i + 1  # 1-based indexing for user display
            self.metadata_cache[msg_id] = metadata
        
        self.next_page_token = next_token
        self.total_fetched += len(message_ids)
        self.update_activity()
    
    def get_displayed_emails(self) -> List[GmailEmailMetadata]:
        """Get emails currently displayed to user"""
        return [self.metadata_cache[msg_id] for msg_id in self.message_ids if self.metadata_cache[msg_id].index in self.displayed_indices]
    
    def get_email_by_index(self, index: int) -> Optional[GmailEmailMetadata]:
        """Get email by user-facing index (1-based)"""
        for metadata in self.metadata_cache.values():
            if metadata.index == index:
                return metadata
        return None
    
    def get_message_id_by_index(self, index: int) -> Optional[str]:
        """Get message ID by user-facing index (1-based)"""
        email = self.get_email_by_index(index)
        return email.id if email else None

class GmailSessionManager:
    """Manages Gmail search sessions across users"""
    
    def __init__(self):
        self.sessions: Dict[int, GmailSearchSession] = {}
    
    def create_session(self, user_id: int, query: str) -> GmailSearchSession:
        """Create a new Gmail search session"""
        # Clean up any existing expired session for this user
        self.cleanup_expired_sessions(user_id)
        
        session = GmailSearchSession(user_id=user_id, query=query)
        self.sessions[user_id] = session
        logger.info(f"Created new Gmail session for user {user_id} with query: {query}")
        return session
    
    def get_session(self, user_id: int) -> Optional[GmailSearchSession]:
        """Get existing session for user"""
        session = self.sessions.get(user_id)
        if session and session.is_expired():
            logger.info(f"Session expired for user {user_id}")
            del self.sessions[user_id]
            return None
        return session
    
    def update_session(self, session: GmailSearchSession):
        """Update session in storage"""
        session.update_activity()
        self.sessions[session.user_id] = session
    
    def cleanup_expired_sessions(self, user_id: Optional[int] = None):
        """Remove expired sessions"""
        if user_id:
            session = self.sessions.get(user_id)
            if session and session.is_expired():
                del self.sessions[user_id]
        else:
            expired_users = [uid for uid, sess in self.sessions.items() if sess.is_expired()]
            for uid in expired_users:
                del self.sessions[uid]
    
    def clear_session(self, user_id: int):
        """Clear session for user"""
        if user_id in self.sessions:
            del self.sessions[user_id]
            logger.info(f"Cleared Gmail session for user {user_id}")

# Global session manager instance
gmail_session_manager = GmailSessionManager()

def format_email_list(metadata_list: List[GmailEmailMetadata], show_continue: bool = True) -> str:
    """Format email metadata list for user display"""
    if not metadata_list:
        return "No emails found."
    
    lines = []
    for email in metadata_list:
        # Truncate subject if too long
        subject = email.subject[:60] + "..." if len(email.subject) > 60 else email.subject
        # Truncate snippet if too long
        snippet = email.snippet[:80] + "..." if len(email.snippet) > 80 else email.snippet
        
        lines.append(f"{email.index}. {subject}")
        lines.append(f"   From: {email.from_email} | Date: {email.date}")
        lines.append(f"   {snippet}")
        lines.append("")  # Empty line for readability
    
    if show_continue:
        lines.append("Type 'continue' to see more emails, or 'open email #N' to read a specific email.")
    
    return "\n".join(lines)

def parse_open_email_command(text: str) -> Optional[int]:
    """Parse 'open email #N' command and return the index N"""
    import re
    match = re.search(r'open\s+email\s+#?(\d+)', text.lower().strip())
    if match:
        return int(match.group(1))
    return None

def is_continue_command(text: str) -> bool:
    """Check if user wants to continue pagination"""
    return text.lower().strip() in ['continue', 'more', 'next', 'yes', 'y']
