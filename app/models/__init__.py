"""All models imported here for Alembic autogenerate to discover them."""

from app.models.user import User, UserRole
from app.models.hierarchy import Branch, BranchMember
from app.models.invite import Invite, InviteActivation
from app.models.catalog import Profession, ServiceGroup, ServiceSubgroup, ServiceItem, SharedOperation
from app.models.coefficient import Coefficient
from app.models.estimate import Estimate, EstimateVersion, EstimateLineItem, EstimateDiscount
from app.models.discount import DiscountRequest
from app.models.order import Order, OrderStatusHistory
from app.models.payment import Payment, CommissionPolicy, CommissionRecord
from app.models.notification import Notification, NotificationTemplate
from app.models.approval import ApprovalRequest
from app.models.staffing import StaffingAction
from app.models.audit import AuditLog
from app.models.feature_flag import FeatureFlag, SystemSetting
from app.models.ai import PromptTemplate, AIRequestLog

__all__ = [
    "User", "UserRole",
    "Branch", "BranchMember",
    "Invite", "InviteActivation",
    "Profession", "ServiceGroup", "ServiceSubgroup", "ServiceItem", "SharedOperation",
    "Coefficient",
    "Estimate", "EstimateVersion", "EstimateLineItem", "EstimateDiscount",
    "DiscountRequest",
    "Order", "OrderStatusHistory",
    "Payment", "CommissionPolicy", "CommissionRecord",
    "Notification", "NotificationTemplate",
    "ApprovalRequest",
    "StaffingAction",
    "AuditLog",
    "FeatureFlag", "SystemSetting",
    "PromptTemplate", "AIRequestLog",
]
