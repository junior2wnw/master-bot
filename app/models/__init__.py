"""All models imported here for Alembic autogenerate to discover them."""

from app.models.ai import AIRequestLog, PromptTemplate
from app.models.approval import ApprovalRequest
from app.models.audit import AuditLog
from app.models.catalog import (
    Profession,
    ServiceGroup,
    ServiceItem,
    ServiceSubgroup,
    SharedOperation,
)
from app.models.coefficient import Coefficient
from app.models.discount import DiscountRequest
from app.models.estimate import Estimate, EstimateDiscount, EstimateLineItem, EstimateVersion
from app.models.feature_flag import FeatureFlag, SystemSetting
from app.models.hierarchy import Branch, BranchMember
from app.models.invite import Invite, InviteActivation
from app.models.master_profile import MasterProfile
from app.models.notification import Notification, NotificationTemplate
from app.models.order import Order, OrderStatusHistory
from app.models.payment import CommissionPolicy, CommissionRecord, Payment
from app.models.project_suggestion import ProjectSuggestion
from app.models.staffing import StaffingAction
from app.models.superapp import JobPost, JobPostResponse, MasterReview, PublicMasterProfile, WorkspaceLayout
from app.models.user import User, UserRole

__all__ = [
    "User", "UserRole",
    "Branch", "BranchMember",
    "Invite", "InviteActivation",
    "Profession", "ServiceGroup", "ServiceSubgroup", "ServiceItem", "SharedOperation",
    "Coefficient",
    "Estimate", "EstimateVersion", "EstimateLineItem", "EstimateDiscount",
    "MasterProfile",
    "DiscountRequest",
    "Order", "OrderStatusHistory",
    "Payment", "CommissionPolicy", "CommissionRecord",
    "Notification", "NotificationTemplate",
    "ProjectSuggestion",
    "ApprovalRequest",
    "StaffingAction",
    "JobPost", "JobPostResponse", "MasterReview", "PublicMasterProfile", "WorkspaceLayout",
    "AuditLog",
    "FeatureFlag", "SystemSetting",
    "PromptTemplate", "AIRequestLog",
]
