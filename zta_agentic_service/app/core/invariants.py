from dataclasses import dataclass
import logging

from app.core.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuntimeInvariants:
    llm_allowed_surfaces: tuple[str, ...] = ("intent_resolution", "template_personalization")
    requires_tenant_scope: bool = True
    submit_api_allowlist_required: bool = True
    default_fail_mode_closed: bool = True


def validate_startup_invariants(settings: Settings) -> None:
    errors: list[str] = []

    if settings.max_chain_depth > 3:
        errors.append("MAX_CHAIN_DEPTH must be <= 3")

    if not 0.0 < settings.intent_clarification_threshold < settings.intent_auto_select_threshold <= 1.0:
        errors.append("Intent thresholds are invalid")

    if settings.intent_margin_threshold <= 0:
        errors.append("INTENT_MARGIN_THRESHOLD must be > 0")

    if settings.tokenization_secret_key in {"", "change-me", "change-this-in-prod"}:
        errors.append("TOKENIZATION_SECRET_KEY must be set to a non-default value")

    if errors:
        logger.error("invariants.validation_failed", extra={"errors": errors})
        raise RuntimeError("Startup invariant check failed: " + "; ".join(errors))

    logger.info(
        "invariants.validation_passed",
        extra={
            "max_chain_depth": settings.max_chain_depth,
            "intent_auto_select_threshold": settings.intent_auto_select_threshold,
            "intent_clarification_threshold": settings.intent_clarification_threshold,
            "intent_margin_threshold": settings.intent_margin_threshold,
        },
    )
