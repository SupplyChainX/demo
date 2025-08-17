"""
Notification Service for multi-channel messaging
"""
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from flask import current_app, render_template
from flask_mail import Message
from app import db, mail, socketio
from app.models import Notification, User, Alert, Recommendation, Role, UserWorkspaceRole

logger = logging.getLogger(__name__)

class NotificationService:
    """Handle notifications across multiple channels."""
    
    def __init__(self):
        self.channels = {
            'email': self._send_email,
            'sms': self._send_sms,
            'in_app': self._send_in_app,
            'push': self._send_push
        }
    
    def send_notification(self, user_id: int, notification_type: str,
                         subject: str, message: str, 
                         channels: List[str] = None,
                         data: Dict[str, Any] = None) -> bool:
        """Send notification through specified channels."""
        if channels is None:
            channels = ['in_app']  # Default to in-app only
        
        success = True
        
        for channel in channels:
            if channel in self.channels:
                try:
                    # Create notification record
                    notification = Notification(
                        workspace_id=1,  # Default workspace
                        user_id=user_id,
                        type=channel,
                        channel=notification_type,
                        subject=subject,
                        message=message,
                        data=data or {},
                        status='pending'
                    )
                    db.session.add(notification)
                    db.session.flush()
                    
                    # Send through channel
                    if self.channels[channel](notification):
                        notification.status = 'sent'
                        notification.sent_at = datetime.utcnow()
                    else:
                        notification.status = 'failed'
                        success = False
                    
                except Exception as e:
                    logger.error(f"Error sending {channel} notification: {e}")
                    success = False
        
        db.session.commit()
        return success
    
    def _send_email(self, notification: Notification) -> bool:
        """Send email notification."""
        try:
            user = db.session.get(User, notification.user_id)
            if not user or not user.email:
                return False
            
            msg = Message(
                subject=notification.subject,
                recipients=[user.email],
                body=notification.message,
                html=render_template(
                    'emails/notification.html',
                    subject=notification.subject,
                    message=notification.message,
                    user=user,
                    data=notification.data
                )
            )
            
            mail.send(msg)
            logger.info(f"Email sent to {user.email}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False
    
    def _send_sms(self, notification: Notification) -> bool:
        """Send SMS notification."""
        try:
            user = db.session.get(User, notification.user_id)
            if not user or not user.phone:
                return False
            
            # Twilio integration
            if current_app.config.get('TWILIO_ACCOUNT_SID'):
                from twilio.rest import Client
                
                client = Client(
                    current_app.config['TWILIO_ACCOUNT_SID'],
                    current_app.config['TWILIO_AUTH_TOKEN']
                )
                
                message = client.messages.create(
                    body=f"{notification.subject}: {notification.message}",
                    from_=current_app.config['TWILIO_PHONE_NUMBER'],
                    to=user.phone
                )
                
                logger.info(f"SMS sent to {user.phone}: {message.sid}")
                return True
            
            logger.warning("Twilio not configured")
            return False
            
        except Exception as e:
            logger.error(f"Error sending SMS: {e}")
            return False
    
    def _send_in_app(self, notification: Notification) -> bool:
        """Send in-app notification."""
        try:
            # Emit WebSocket event
            socketio.emit(
                'notification',
                {
                    'id': notification.id,
                    'type': notification.channel,
                    'subject': notification.subject,
                    'message': notification.message,
                    'data': notification.data,
                    'timestamp': datetime.utcnow().isoformat()
                },
                room=f"user_{notification.user_id}"
            )
            
            logger.info(f"In-app notification sent to user {notification.user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending in-app notification: {e}")
            return False
    
    def _send_push(self, notification: Notification) -> bool:
        """Send push notification."""
        # For MVP, just log it
        logger.info(f"Push notification would be sent: {notification.subject}")
        return True
    
    def send_alert_notification(self, alert_id: int, user_ids: List[int]):
        """Send notification for new alert."""
        from app.models import Alert
        alert = db.session.get(Alert, alert_id)
        if not alert:
            return

        subject = f"New {alert.severity.value} severity alert: {alert.title}"
        message = alert.description[:200]

        for user_id in user_ids:
            self.send_notification(
                user_id=user_id,
                notification_type='alert',
                subject=subject,
                message=message,
                channels=['in_app', 'email'],
                data={
                    'alert_id': alert_id,
                    'severity': alert.severity.value,
                    'type': alert.type
                }
            )
    
    def send_approval_request(self, recommendation_id: int, 
                            approver_roles: List[str]):
        """Send approval request notifications."""
        from app.models import Recommendation, UserWorkspaceRole
        recommendation = db.session.get(Recommendation, recommendation_id)
        if not recommendation:
            return

        # Get users with approver roles
        user_roles = UserWorkspaceRole.query.filter(
            UserWorkspaceRole.workspace_id == recommendation.workspace_id,
            UserWorkspaceRole.role_id.in_(
                db.session.query(Role.id).filter(Role.name.in_(approver_roles))
            )
        ).all()

        subject = f"Approval Required: {recommendation.title}"
        message = f"Please review and approve: {recommendation.description[:150]}..."

        for user_role in user_roles:
            self.send_notification(
                user_id=user_role.user_id,
                notification_type='approval',
                subject=subject,
                message=message,
                channels=['in_app', 'email'],
                data={
                    'recommendation_id': recommendation_id,
                    'type': recommendation.type.value,
                    'severity': recommendation.severity.value
                }
            )
    
    def send_escalation(self, alert_id: int, title: str, severity: str):
        """Send escalation notification."""
        # Get escalation recipients based on severity
        if severity == 'critical':
            roles = ['operations_director', 'cto']
        elif severity == 'high':
            roles = ['operations_manager', 'logistics_manager']
        else:
            roles = ['team_lead']
        
        # Get users with these roles
        from app.models import Role, UserWorkspaceRole
        
        user_roles = UserWorkspaceRole.query.join(Role).filter(
            Role.name.in_(roles),
            UserWorkspaceRole.workspace_id == 1  # Default workspace
        ).all()
        
        for user_role in user_roles:
            self.send_notification(
                user_id=user_role.user_id,
                notification_type='escalation',
                subject=f"ESCALATION: {title}",
                message=f"Alert {alert_id} has been escalated due to SLA breach",
                channels=['in_app', 'email', 'sms'],
                data={
                    'alert_id': alert_id,
                    'severity': severity,
                    'escalation_reason': 'sla_breach'
                }
            )
    
    def send_status_update(self, object_type: str, object_id: int,
                          old_status: str, new_status: str,
                          affected_users: List[int]):
        """Send status update notifications."""
        subject = f"{object_type.title()} Status Update"
        message = f"Status changed from {old_status} to {new_status}"
        
        for user_id in affected_users:
            self.send_notification(
                user_id=user_id,
                notification_type='status_update',
                subject=subject,
                message=message,
                channels=['in_app'],
                data={
                    'object_type': object_type,
                    'object_id': object_id,
                    'old_status': old_status,
                    'new_status': new_status
                }
            )
    
    def mark_as_read(self, notification_id: int, user_id: int) -> bool:
        """Mark notification as read."""
        try:
            notification = Notification.query.filter_by(
                id=notification_id,
                user_id=user_id
            ).first()
            
            if notification:
                notification.status = 'read'
                notification.read_at = datetime.utcnow()
                db.session.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error marking notification as read: {e}")
            db.session.rollback()
        
        return False
    
    def get_unread_count(self, user_id: int) -> int:
        """Get count of unread notifications."""
        return Notification.query.filter_by(
            user_id=user_id,
            status='sent'
        ).count()
