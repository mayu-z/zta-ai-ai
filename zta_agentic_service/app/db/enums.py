from enum import StrEnum


class AgentDefinitionStatus(StrEnum):
    ACTIVE = "active"
    BETA = "beta"
    DEPRECATED = "deprecated"


class TriggerType(StrEnum):
    USER_QUERY = "user_query"
    SCHEDULED = "scheduled"
    EVENT = "event"
    CHAIN = "chain"
    THRESHOLD = "threshold"
    CONTINUOUS = "continuous"


class ExecutionStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    PENDING_APPROVAL = "pending_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionState(StrEnum):
    INIT = "INIT"
    VALIDATED = "VALIDATED"
    RUNNING = "RUNNING"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RESUMED = "RESUMED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PublishStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class PublishAction(StrEnum):
    PUBLISH = "publish"
    ROLLBACK = "rollback"
    CANARY_PUBLISH = "canary_publish"


class StepAttemptStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class PluginStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    DEPRECATED = "deprecated"
