from __future__ import annotations

from dataclasses import dataclass


class SafetyPolicyError(PermissionError):
    pass


@dataclass
class TokenizationResult:
    tokenized_payload: dict
    token_map: dict[str, str]


class TokenizationLayer:
    def tokenize_payload(self, payload: dict) -> TokenizationResult:
        token_map: dict[str, str] = {}
        tokenized = {}
        slot_index = 1
        for key, value in payload.items():
            if isinstance(value, (int, float, str)) and key not in {"intent", "query"}:
                token = f"[SLOT_{slot_index}]"
                token_map[token] = str(value)
                tokenized[key] = token
                slot_index += 1
            else:
                tokenized[key] = value
        return TokenizationResult(tokenized_payload=tokenized, token_map=token_map)

    @staticmethod
    def detokenize_output(text: str, token_map: dict[str, str]) -> str:
        output = text
        for token, raw_value in token_map.items():
            output = output.replace(token, raw_value)
        return output


class PolicyEnforcementLayer:
    def validate_pre_llm(self, tenant_id: str, allowed_candidates: list[str], proposed_candidates: list[str]) -> None:
        if not tenant_id:
            raise SafetyPolicyError("Missing tenant_id in pre-LLM validation")
        for candidate in proposed_candidates:
            if candidate not in allowed_candidates:
                raise SafetyPolicyError(f"Candidate {candidate} is not in allowed registry set")

    def validate_post_llm(self, selected_agent: str, allowed_candidates: list[str]) -> None:
        if selected_agent not in allowed_candidates:
            raise SafetyPolicyError("LLM selected an unauthorized agent")


class OutputValidationLayer:
    def validate_output(self, rendered_text: str, allowed_channels: list[str], requested_channel: str) -> None:
        if requested_channel not in allowed_channels:
            raise SafetyPolicyError("Output channel is not allowed by agent policy")
        if "http://" in rendered_text or "https://" in rendered_text:
            # URL generation should be explicit in configured steps.
            raise SafetyPolicyError("Unexpected URL in rendered output")
