from pydantic import BaseModel, Field


class IntentCandidate(BaseModel):
    agent_id: str
    matched_intent: str
    semantic_score: float = Field(ge=0.0, le=1.0)
    rule_score: float = Field(ge=0.0, le=1.0)
    context_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    decision_reason: str
    risk_rank: int = Field(ge=0, le=100, default=50)


class IntentResolutionResult(BaseModel):
    decision: str
    selected_agent_id: str | None = None
    clarification_question: str | None = None
    candidates: list[IntentCandidate]
