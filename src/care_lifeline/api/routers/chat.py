import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from care_lifeline.graph.builder import build_graph
from care_lifeline.graph.state import AgentState
from care_lifeline.llm.mock_provider import MockProvider

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _initial_state(message: str) -> AgentState:
    return {
        "messages": [HumanMessage(message)],
        "patient_id": None,
        "intent": "",
        "risk_level": "routine",
        "citations": [],
        "draft": "",
        "qc_result": None,  # type: ignore[arg-type]
        "hitl_required": False,
    }


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    if not req.message.strip():

        async def error_stream() -> AsyncIterator[str]:
            yield _sse("error", {"code": "INVALID", "message": "消息不能为空"})

        return StreamingResponse(error_stream(), media_type="text/event-stream")

    async def generate() -> AsyncIterator[str]:
        graph = build_graph(MockProvider())
        state = graph.invoke(_initial_state(req.message))

        yield _sse(
            "meta",
            {
                "session_id": req.session_id,
                "intent": state["intent"],
                "risk_level": state["risk_level"],
            },
        )
        for chunk in state["draft"].split("，"):
            yield _sse("token", {"text": chunk})
        for citation in state["citations"]:
            yield _sse(
                "citation",
                {
                    "index": citation.index,
                    "source": citation.source,
                    "snippet": citation.snippet,
                },
            )
        qc = state["qc_result"]
        yield _sse(
            "qc",
            {
                "status": qc.status,
                "risk_score": qc.risk_score,
                "violations": qc.violations,
            },
        )
        yield _sse(
            "done",
            {
                "final": state["draft"],
                "citations": [c.model_dump() for c in state["citations"]],
            },
        )

    return StreamingResponse(generate(), media_type="text/event-stream")
