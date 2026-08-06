import logging

from sqlalchemy.orm import Session

from app.email_service import send_notification_email
from app.models import Notification, User, default_notification_preferences

logger = logging.getLogger(__name__)


def preferences_for(user: User) -> dict[str, bool]:
    return {**default_notification_preferences(), **(user.notification_preferences or {})}


def create_notification(db: Session, *, user_id: str, organization_id: str | None,
                        type_: str, title: str, message: str, action_url: str | None = None,
                        email_category: str | None = None) -> Notification:
    notification = Notification(user_id=user_id, organization_id=organization_id, type=type_,
                                title=title, message=message, action_url=action_url)
    db.add(notification)
    recipient = db.get(User, user_id)
    if recipient and recipient.email_verified and email_category and preferences_for(recipient).get(email_category, False):
        try:
            send_notification_email(recipient, title, message, action_url)
        except Exception:
            logger.exception("Notification email delivery failed for user %s", user_id)
    return notification
