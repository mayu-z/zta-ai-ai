from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

class IntentLLMClient(Protocol):
    def semantic_match_score(self, query_text: str, candidate: dict) -> float:
        ...


class ResolverSettings(Protocol):
    intent_auto_select_threshold: float
    intent_clarification_threshold: float
    intent_margin_threshold: float


@dataclass
class CandidateScores:
    semantic_score: float
    rule_score: float
    context_score: float


@dataclass
class IntentCandidate:
    agent_id: str
    matched_intent: str
    semantic_score: float
    rule_score: float
    context_score: float
    final_score: float
    decision_reason: str
    risk_rank: int


@dataclass
class IntentResolutionResult:
    decision: str
    selected_agent_id: str | None = None
    clarification_question: str | None = None
    candidates: list[IntentCandidate] = field(default_factory=list)


class IntentResolver:
    def __init__(self, settings: ResolverSettings, llm_client: IntentLLMClient | None = None) -> None:
        self.settings = settings
        self.llm_client = llm_client

    def resolve(
        self,
        query_text: str,
        tenant_id: str,
        persona_context: dict,
        candidates: list[dict],
    ) -> IntentResolutionResult:
        scored_candidates: list[IntentCandidate] = []
        for candidate in candidates:
            scores = self._score_candidate(query_text, candidate, persona_context)
            final_score = self._weighted_final(scores)
            scored_candidates.append(
                IntentCandidate(
                    agent_id=candidate["agent_id"],
                    matched_intent=candidate.get("name", candidate["agent_id"]),
                    semantic_score=round(scores.semantic_score, 4),
                    rule_score=round(scores.rule_score, 4),
                    context_score=round(scores.context_score, 4),
                    final_score=round(final_score, 4),
                    decision_reason="weighted(semantic=0.55,rule=0.30,context=0.15)",
                    risk_rank=int(candidate.get("risk_rank", 50)),
                )
            )

        scored_candidates.sort(
            key=lambda c: (c.final_score, c.semantic_score, -c.risk_rank, c.agent_id),
            reverse=True,
        )

        if not scored_candidates:
            return IntentResolutionResult(
                decision="fallback",
                clarification_question=None,
                candidates=[],
            )

        top = scored_candidates[0]
        second = scored_candidates[1] if len(scored_candidates) > 1 else None
        margin = top.final_score - (second.final_score if second else 0.0)

        if (
            top.final_score >= self.settings.intent_auto_select_threshold
            and margin >= self.settings.intent_margin_threshold
        ):
            return IntentResolutionResult(
                decision="auto_select",
                selected_agent_id=top.agent_id,
                candidates=scored_candidates,
            )

        if top.final_score >= self.settings.intent_clarification_threshold:
            question = self._build_clarification_question(scored_candidates[:3])
            return IntentResolutionResult(
                decision="clarification",
                clarification_question=question,
                candidates=scored_candidates,
            )

        return IntentResolutionResult(
            decision="fallback",
            clarification_question="I could not map this to a safe registered agent. Please rephrase.",
            candidates=scored_candidates,
        )

    def _score_candidate(
        self,
        query_text: str,
        candidate: dict,
        persona_context: dict,
    ) -> CandidateScores:
        semantic_score = self._semantic_score(query_text, candidate)
        rule_score = self._rule_score(query_text, candidate.get("keywords", []))
        context_score = self._context_score(candidate, persona_context)
        return CandidateScores(
            semantic_score=semantic_score,
            rule_score=rule_score,
            context_score=context_score,
        )

    def _semantic_score(self, query_text: str, candidate: dict) -> float:
        if self.llm_client is not None:
            return max(0.0, min(1.0, self.llm_client.semantic_match_score(query_text, candidate)))

        candidate_text = f"{candidate.get('name', '')} {candidate.get('description', '')}".lower()
        query_tokens = set(query_text.lower().split())
        cand_tokens = set(candidate_text.split())
        if not query_tokens or not cand_tokens:
            return 0.0
        overlap = len(query_tokens & cand_tokens)
        return overlap / len(query_tokens | cand_tokens)

    @staticmethod
    def _rule_score(query_text: str, keywords: list[str]) -> float:
        if not keywords:
            return 0.0
        query = query_text.lower()
        matched = sum(1 for kw in keywords if kw.lower() in query)
        return min(1.0, matched / max(1, len(keywords)))

    @staticmethod
    def _context_score(candidate: dict, persona_context: dict) -> float:
        score = 0.4

        persona = persona_context.get("persona")
        allowed_personas = persona_context.get("allowed_personas_by_agent", {}).get(
            candidate["agent_id"],
            [],
        )
        if allowed_personas and persona in allowed_personas:
            score += 0.35

        historical_hits = persona_context.get("historical_intent_hits", {}).get(candidate["agent_id"], 0)
        if historical_hits > 0:
            score += min(0.25, historical_hits * 0.05)

        return min(1.0, score)

    @staticmethod
    def _weighted_final(scores: CandidateScores) -> float:
        return 0.55 * scores.semantic_score + 0.30 * scores.rule_score + 0.15 * scores.context_score

    @staticmethod
    def _build_clarification_question(candidates: list[IntentCandidate]) -> str:
        labels = ", ".join(candidate.agent_id for candidate in candidates)
        return f"I found multiple possible agents: {labels}. Which one should I use?"
