"""Concrete registry-driven agent handlers."""

from app.agents.handlers.bulk_notification import BulkNotificationHandler
from app.agents.handlers.email_draft_send import EmailDraftSendHandler
from app.agents.handlers.fee_reminder import FeeReminderHandler
from app.agents.handlers.leave_approval import LeaveApprovalHandler
from app.agents.handlers.leave_balance import LeaveBalanceHandler
from app.agents.handlers.meeting_scheduler import MeetingSchedulerHandler
from app.agents.handlers.payroll_query import PayrollQueryHandler
from app.agents.handlers.refund_processing import RefundProcessingHandler
from app.agents.handlers.result_notification import ResultNotificationHandler
from app.agents.handlers.sensitive_field_monitor import SensitiveFieldMonitorHandler
from app.agents.handlers.upi_payment import UpiPaymentHandler

HANDLER_REGISTRY = {
    "ResultNotificationHandler": ResultNotificationHandler,
    "FeeReminderHandler": FeeReminderHandler,
    "UpiPaymentHandler": UpiPaymentHandler,
    "RefundProcessingHandler": RefundProcessingHandler,
    "EmailDraftSendHandler": EmailDraftSendHandler,
    "BulkNotificationHandler": BulkNotificationHandler,
    "LeaveApprovalHandler": LeaveApprovalHandler,
    "MeetingSchedulerHandler": MeetingSchedulerHandler,
    "PayrollQueryHandler": PayrollQueryHandler,
    "LeaveBalanceHandler": LeaveBalanceHandler,
    "SensitiveFieldMonitorHandler": SensitiveFieldMonitorHandler,
}

__all__ = [
    "HANDLER_REGISTRY",
    "ResultNotificationHandler",
    "FeeReminderHandler",
    "UpiPaymentHandler",
    "RefundProcessingHandler",
    "EmailDraftSendHandler",
    "BulkNotificationHandler",
    "LeaveApprovalHandler",
    "MeetingSchedulerHandler",
    "PayrollQueryHandler",
    "LeaveBalanceHandler",
    "SensitiveFieldMonitorHandler",
]
