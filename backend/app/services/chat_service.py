"""Shared chat logic used by the web API and the Telegram bot."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.agent import AgentResult, run_agent
from app.agent.llm import LLMClient
from app.agent.tools import ToolContext
from app.models import ChatSession


def get_or_create_session(db: Session, device_id: str, session_id: str | None) -> ChatSession:
    if session_id:
        s = db.get(ChatSession, session_id)
        if s and s.device_id == device_id:
            return s
    s = ChatSession(device_id=device_id, history=[])
    db.add(s)
    db.flush()
    return s


def latest_session(db: Session, device_id: str) -> ChatSession | None:
    return db.scalars(
        select(ChatSession)
        .where(ChatSession.device_id == device_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(1)
    ).first()


async def handle_message(
    db: Session, llm: LLMClient, device_id: str, message: str, session: ChatSession
) -> AgentResult:
    """Run the agent on a new user message and save the conversation. Commits on success;
    the caller should roll back if this raises."""
    history = list(session.history or [])
    history.append({"role": "user", "content": message})

    ctx = ToolContext(db=db, device_id=device_id, session_id=session.id)
    result = await run_agent(llm, history, ctx)

    session.history = result.history  # reassign so SQLAlchemy sees the JSON change
    db.commit()
    return result
