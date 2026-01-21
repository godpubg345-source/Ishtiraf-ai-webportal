"""
IshtirafAI - Notification Service
==================================
Email and SMS alerts for critical diagnoses.
"""

import os
from datetime import datetime
from typing import List, Optional
import logging

logger = logging.getLogger('IshtirafAI.Notifications')


class NotificationService:
    """Unified notification service for email and SMS."""
    
    def __init__(self, app=None):
        self.app = app
        self.email_enabled = False
        self.sms_enabled = False
        
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize with Flask app config."""
        self.app = app
        
        # Email configuration
        self.email_provider = app.config.get('NOTIFICATION_EMAIL_PROVIDER', 'smtp')
        self.sendgrid_key = app.config.get('SENDGRID_API_KEY')
        self.smtp_host = app.config.get('MAIL_SERVER', 'smtp.gmail.com')
        self.smtp_port = app.config.get('MAIL_PORT', 587)
        self.smtp_user = app.config.get('MAIL_USERNAME')
        self.smtp_pass = app.config.get('MAIL_PASSWORD')
        self.from_email = app.config.get('MAIL_DEFAULT_SENDER', 'alerts@ishtiraf.ai')
        
        # SMS configuration
        self.twilio_sid = app.config.get('TWILIO_ACCOUNT_SID')
        self.twilio_token = app.config.get('TWILIO_AUTH_TOKEN')
        self.twilio_number = app.config.get('TWILIO_FROM_NUMBER')
        
        self.email_enabled = bool(self.smtp_user or self.sendgrid_key)
        self.sms_enabled = bool(self.twilio_sid and self.twilio_token)
        
        logger.info(f"Notifications: Email={self.email_enabled}, SMS={self.sms_enabled}")
    
    def send_email(self, to: str, subject: str, body: str, html: str = None) -> bool:
        """Send email notification."""
        if not self.email_enabled:
            logger.warning("Email not configured")
            return False
        
        try:
            if self.email_provider == 'sendgrid' and self.sendgrid_key:
                return self._send_sendgrid(to, subject, body, html)
            else:
                return self._send_smtp(to, subject, body, html)
        except Exception as e:
            logger.error(f"Email send error: {e}")
            return False
    
    def _send_smtp(self, to: str, subject: str, body: str, html: str = None) -> bool:
        """Send via SMTP."""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.from_email
        msg['To'] = to
        
        msg.attach(MIMEText(body, 'plain'))
        if html:
            msg.attach(MIMEText(html, 'html'))
        
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            if self.smtp_user and self.smtp_pass:
                server.login(self.smtp_user, self.smtp_pass)
            server.send_message(msg)
        
        logger.info(f"Email sent to {to}")
        return True
    
    def _send_sendgrid(self, to: str, subject: str, body: str, html: str = None) -> bool:
        """Send via SendGrid API."""
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail
        except ImportError:
            logger.error("sendgrid package not installed")
            return False
        
        message = Mail(
            from_email=self.from_email,
            to_emails=to,
            subject=subject,
            plain_text_content=body,
            html_content=html
        )
        
        sg = SendGridAPIClient(self.sendgrid_key)
        response = sg.send(message)
        
        logger.info(f"SendGrid response: {response.status_code}")
        return response.status_code == 202
    
    def send_sms(self, to: str, message: str) -> bool:
        """Send SMS notification via Twilio."""
        if not self.sms_enabled:
            logger.warning("SMS not configured")
            return False
        
        try:
            from twilio.rest import Client
        except ImportError:
            logger.error("twilio package not installed")
            return False
        
        try:
            client = Client(self.twilio_sid, self.twilio_token)
            
            msg = client.messages.create(
                body=message[:160],  # SMS limit
                from_=self.twilio_number,
                to=to
            )
            
            logger.info(f"SMS sent: {msg.sid}")
            return True
        except Exception as e:
            logger.error(f"SMS error: {e}")
            return False
    
    def send_critical_alert(self, diagnosis, recipients: List[str]):
        """Send critical diagnosis alert to all recipients."""
        subject = f"⚠️ CRITICAL ALERT - Patient {diagnosis.patient.name}"
        
        body = f"""
CRITICAL DIAGNOSIS ALERT - IshtirafAI
=====================================

Patient: {diagnosis.patient.name}
Patient ID: PAT-{diagnosis.patient.id:04d}
Diagnosis: {diagnosis.diagnosis_result}
Risk Score: {diagnosis.risk_score}/10
Confidence: {diagnosis.confidence}%
Time: {diagnosis.timestamp}

IMMEDIATE ATTENTION REQUIRED

This is an automated alert from IshtirafAI Medical System.
        """
        
        html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
    <div style="background: #FF3B30; color: white; padding: 20px; text-align: center;">
        <h1>⚠️ CRITICAL ALERT</h1>
    </div>
    <div style="padding: 20px; background: #f5f5f5;">
        <h2>Patient: {diagnosis.patient.name}</h2>
        <table style="width: 100%; border-collapse: collapse;">
            <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Patient ID</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">PAT-{diagnosis.patient.id:04d}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Diagnosis</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd; color: red; font-weight: bold;">{diagnosis.diagnosis_result}</td></tr>
            <tr><td style="padding: 8px; border-bottom: 1px solid #ddd;"><strong>Risk Score</strong></td>
                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{diagnosis.risk_score}/10</td></tr>
            <tr><td style="padding: 8px;"><strong>Time</strong></td>
                <td style="padding: 8px;">{diagnosis.timestamp}</td></tr>
        </table>
        <p style="color: red; font-weight: bold; text-align: center; margin-top: 20px;">
            IMMEDIATE MEDICAL ATTENTION REQUIRED
        </p>
    </div>
    <div style="padding: 10px; background: #333; color: white; text-align: center; font-size: 12px;">
        IshtirafAI Medical Diagnostic System
    </div>
</div>
        """
        
        # Send to all recipients
        for email in recipients:
            self.send_email(email, subject, body, html)
        
        # If phone numbers available, send SMS too
        sms_msg = f"CRITICAL: Patient {diagnosis.patient.name} - {diagnosis.diagnosis_result} - Risk {diagnosis.risk_score}/10 - Immediate attention required"
        # self.send_sms(phone, sms_msg)


# Global instance
notifications = NotificationService()


def init_notifications(app):
    """Initialize notification service with app."""
    notifications.init_app(app)
    return notifications
