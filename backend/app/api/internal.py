from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.agent import AgentTokenValidationResponse
from app.services.agent_service import AgentService

router = APIRouter(prefix="/internal", tags=["internal"])


def extract_bearer_token(authorization: str | None) -> str:
    """Extract a raw bearer token from an Authorization header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return token


@router.get("/agent-token/validate", response_model=AgentTokenValidationResponse)
async def validate_agent_token_get(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AgentTokenValidationResponse:
    """Validate a raw agent token from a GET request used by reverse proxies."""
    token = await AgentService.validate_raw_token(db, extract_bearer_token(authorization))
    return AgentTokenValidationResponse(valid=True, vm_id=token.vm_id)


@router.post("/agent-token/validate", response_model=AgentTokenValidationResponse)
async def validate_agent_token_post(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> AgentTokenValidationResponse:
    """Validate a raw agent token from a POST request used by reverse proxies."""
    token = await AgentService.validate_raw_token(db, extract_bearer_token(authorization))
    return AgentTokenValidationResponse(valid=True, vm_id=token.vm_id)
