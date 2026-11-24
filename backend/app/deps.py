"""Shared FastAPI dependencies."""
import re

from fastapi import Header, HTTPException

from app.agent.llm import LLMClient, LLMNotConfigured, get_llm

DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


def device_id(x_device_id: str = Header(default="")) -> str:
    """Anonymous per-browser id (the web app stores a random UUID in localStorage)."""
    if not DEVICE_ID_RE.match(x_device_id):
        raise HTTPException(400, "Missing or invalid X-Device-Id header")
    return x_device_id


def llm_client() -> LLMClient:
    try:
        return get_llm()
    except LLMNotConfigured as e:
        raise HTTPException(503, str(e)) from e


def optional_llm_client() -> LLMClient | None:
    try:
        return get_llm()
    except LLMNotConfigured:
        return None
