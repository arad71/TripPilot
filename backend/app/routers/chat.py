from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agent.llm import LLMClient, LLMError
from app.db import get_db
from app.deps import device_id, llm_client
from app.schemas import ChatIn, ChatOut
from app.services.chat_service import get_or_create_session, handle_message

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatOut)
async def chat(
    body: ChatIn,
    device: str = Depends(device_id),
    db: Session = Depends(get_db),
    llm: LLMClient = Depends(llm_client),
) -> ChatOut:
    session = get_or_create_session(db, device, body.session_id)
    try:
        result = await handle_message(db, llm, device, body.message.strip(), session)
    except LLMError as e:
        db.rollback()
        raise HTTPException(502, "The AI service is unavailable. Please try again.") from e
    return ChatOut(reply=result.reply, session_id=session.id, cards=result.cards)
