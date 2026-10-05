"""Notification module - event-driven notifications for document changes."""

from grunt.notification.service import NotificationService

notification_service = NotificationService()

__all__ = ["NotificationService", "notification_service"]
