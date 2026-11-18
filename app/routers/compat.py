from __future__ import annotations

from fastapi import APIRouter

from app.schemas import OpenAIModel, OpenAIModelList

router = APIRouter(tags=["compatibility"])

MODEL_ID = "money-machine-smc-v1"


@router.get("/v1/models", response_model=OpenAIModelList)
async def list_models() -> OpenAIModelList:
    """OpenAI-style discovery endpoint.

    A few tools probe ``/v1/models`` before using an HTTP API. Money Machine is
    a trading bot rather than an LLM server, so the list contains the strategy
    engine itself. This keeps discovery clients from treating the whole app as
    unavailable while still making the non-LLM nature explicit in the docs.
    """
    return OpenAIModelList(
        data=[
            OpenAIModel(
                id=MODEL_ID,
                owned_by="money-machine",
            )
        ]
    )
