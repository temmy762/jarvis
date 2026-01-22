"""Response formatter middleware for Jarvis AI Agent.

This module ensures all outputs are clean, professional, and free of
Markdown artifacts, emojis, and formatting symbols per Saara's requirements.
"""

import re
from typing import Any, Dict


def strip_markdown(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'~~(.+?)~~', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'\[([^\]]+?)\]\((https?://[^\s)]+)\)', r'\1: \2', text)
    text = re.sub(r'\[([^\]]+?)\]\(([^\s)]+)\)', r'\1', text)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    return text


def strip_emojis(text: str) -> str:
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub('', text)


def normalize_whitespace(text: str) -> str:
    text = re.sub(r'\r\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    text = text.strip()
    return text


def strip_urls_for_voice(text: str) -> str:
    text = re.sub(r'http[s]?://\S+', '', text)
    text = re.sub(r'www\.\S+', '', text)
    return text


def strip_link_ctas_for_voice(text: str) -> str:
    text = re.sub(r'\burl\s*:\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bview\s+task\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bview\s+card\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bview\s+event\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bview\s+email\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bview\s+message\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bopen\s+link\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bclick\s+here\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\btap\s+here\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhere\s+is\s+the\s+link\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bhere\s+are\s+the\s+links\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b\[link\]\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\(\s*link\s*\)', '', text, flags=re.IGNORECASE)
    return text


def strip_metadata_for_voice(text: str) -> str:
    text = re.sub(r'\[.*?attachment.*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?file.*?\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?image.*?\]', '', text, flags=re.IGNORECASE)
    return text


def clean_response_for_text(response: str) -> str:
    response = strip_markdown(response)
    response = strip_emojis(response)
    response = normalize_whitespace(response)
    return response


def clean_response_for_voice(response: str) -> str:
    had_url = bool(re.search(r'(https?://\S+|www\.\S+|\[[^\]]+\]\(https?://[^)]+\))', response or ""))
    response = strip_markdown(response)
    response = strip_emojis(response)
    response = strip_urls_for_voice(response)
    response = strip_link_ctas_for_voice(response)
    response = strip_metadata_for_voice(response)
    response = normalize_whitespace(response)
    if had_url:
        if response:
            response = f"{response} I sent the link in a text message."
        else:
            response = "I sent the details in a text message."
    return response


def format_agent_response(response: str, is_voice: bool = False) -> str:
    response_mode = "voice" if is_voice else "text"
    if response_mode == "voice":
        return clean_response_for_voice(response)
    return clean_response_for_text(response)


def strip_system_commentary(text: str) -> str:
    patterns = [
        r"I have sent (the|your) email",
        r"I've sent (the|your) email",
        r"Email sent successfully",
        r"Here is (the|your) email",
        r"I've composed (the|your) email",
        r"I have composed (the|your) email",
    ]
    
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    text = normalize_whitespace(text)
    return text
