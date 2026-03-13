"""
INBXR — Email Sending
SMTP-based transactional email for verification, password resets, and alerts.
Configure via environment variables:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@inbxr.com")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")


def is_configured():
    """Check if SMTP credentials are set."""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS)


def _send(to_email, subject, html_body, text_body=None):
    """Send an email via SMTP. Returns True on success, False on failure."""
    if not is_configured():
        print(f"[MAILER] SMTP not configured. Would send to {to_email}: {subject}")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            if SMTP_PORT != 25:
                server.starttls()
                server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[MAILER] Failed to send to {to_email}: {e}")
        return False


def send_verification_email(to_email, token):
    """Send email verification link after signup."""
    verify_url = f"{BASE_URL}/verify-email/{token}"
    subject = "Verify your INBXR account"
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
      <h2 style="color:#0c1a3a;margin:0 0 8px;">Welcome to INBXR</h2>
      <p style="color:#334155;font-size:15px;line-height:1.6;">
        Click the button below to verify your email and activate your account.
      </p>
      <a href="{verify_url}"
         style="display:inline-block;background:#16a34a;color:#fff;padding:12px 28px;
                border-radius:999px;text-decoration:none;font-weight:600;font-size:15px;
                margin:20px 0;">
        Verify Email
      </a>
      <p style="color:#64748b;font-size:13px;line-height:1.5;margin-top:24px;">
        Or copy this link:<br>
        <a href="{verify_url}" style="color:#16a34a;word-break:break-all;">{verify_url}</a>
      </p>
      <p style="color:#94a3b8;font-size:12px;margin-top:32px;">
        If you didn't create an INBXR account, ignore this email.
      </p>
    </div>
    """
    text = f"Welcome to INBXR.\n\nVerify your email: {verify_url}\n\nIf you didn't sign up, ignore this."
    return _send(to_email, subject, html, text)


def send_password_reset_email(to_email, token):
    """Send password reset link."""
    reset_url = f"{BASE_URL}/reset-password/{token}"
    subject = "Reset your INBXR password"
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
      <h2 style="color:#0c1a3a;margin:0 0 8px;">Password Reset</h2>
      <p style="color:#334155;font-size:15px;line-height:1.6;">
        Someone requested a password reset for your INBXR account.
        Click the button below to set a new password. This link expires in 1 hour.
      </p>
      <a href="{reset_url}"
         style="display:inline-block;background:#16a34a;color:#fff;padding:12px 28px;
                border-radius:999px;text-decoration:none;font-weight:600;font-size:15px;
                margin:20px 0;">
        Reset Password
      </a>
      <p style="color:#64748b;font-size:13px;line-height:1.5;margin-top:24px;">
        Or copy this link:<br>
        <a href="{reset_url}" style="color:#16a34a;word-break:break-all;">{reset_url}</a>
      </p>
      <p style="color:#94a3b8;font-size:12px;margin-top:32px;">
        If you didn't request this, ignore this email. Your password won't change.
      </p>
    </div>
    """
    text = f"Reset your INBXR password: {reset_url}\n\nThis link expires in 1 hour.\nIf you didn't request this, ignore this email."
    return _send(to_email, subject, html, text)


def send_welcome_email(to_email, display_name=None):
    """Send a welcome email after verification (optional, called after verify)."""
    name = display_name or to_email.split("@")[0]
    subject = "You're in — welcome to INBXR"
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
      <h2 style="color:#0c1a3a;margin:0 0 8px;">Hey {name},</h2>
      <p style="color:#334155;font-size:15px;line-height:1.6;">
        Your INBXR account is verified and ready. Here's what you can do:
      </p>
      <ul style="color:#334155;font-size:14px;line-height:1.8;padding-left:20px;">
        <li><strong>50 checks/day</strong> across all tools (up from 3 as a guest)</li>
        <li><strong>Full email test</strong> — send a real email, get a full checkup</li>
        <li><strong>Domain checkup</strong> — auth, blocklists, DNS fixes</li>
        <li><strong>Dashboard</strong> — track your inbox scores</li>
      </ul>
      <a href="{BASE_URL}/"
         style="display:inline-block;background:#16a34a;color:#fff;padding:12px 28px;
                border-radius:999px;text-decoration:none;font-weight:600;font-size:15px;
                margin:20px 0;">
        Run Your First Checkup
      </a>
      <p style="color:#94a3b8;font-size:12px;margin-top:32px;">
        INBXR — Free email deliverability tools.
      </p>
    </div>
    """
    text = f"Hey {name},\n\nYour INBXR account is ready.\n\nRun your first checkup: {BASE_URL}/\n\nINBXR — Free email deliverability tools."
    return _send(to_email, subject, html, text)


def send_admin_email(to_email, subject, body_html, body_text=None):
    """Send an arbitrary email from admin. Returns True on success."""
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;">
      {body_html}
      <p style="color:#94a3b8;font-size:12px;margin-top:32px;border-top:1px solid #e2e8f0;padding-top:16px;">
        INBXR &mdash; Email Intelligence Platform
      </p>
    </div>
    """
    return _send(to_email, subject, html, body_text)


def send_team_invite_email(to_email, team_name, inviter_name, token):
    """Send a team invite email with accept link."""
    accept_url = f"{BASE_URL}/team/invite/{token}"
    subject = f"{inviter_name} invited you to join {team_name} on INBXR"
    html = f"""
    <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;">
      <h2 style="color:#0c1a3a;margin:0 0 8px;">Team Invite</h2>
      <p style="color:#334155;font-size:15px;line-height:1.6;">
        <strong>{inviter_name}</strong> has invited you to join
        <strong>{team_name}</strong> on INBXR.
      </p>
      <p style="color:#334155;font-size:14px;line-height:1.6;">
        As a team member you'll share monitored domains, check history,
        bulk verification jobs, and alerts.
      </p>
      <a href="{accept_url}"
         style="display:inline-block;background:#16a34a;color:#fff;padding:12px 28px;
                border-radius:999px;text-decoration:none;font-weight:600;font-size:15px;
                margin:20px 0;">
        Accept Invite
      </a>
      <p style="color:#64748b;font-size:13px;line-height:1.5;margin-top:24px;">
        Or copy this link:<br>
        <a href="{accept_url}" style="color:#16a34a;word-break:break-all;">{accept_url}</a>
      </p>
      <p style="color:#94a3b8;font-size:12px;margin-top:32px;">
        This invite expires in 7 days. If you don't have an INBXR account,
        you'll be asked to sign up first.
      </p>
    </div>
    """
    text = f"{inviter_name} invited you to join {team_name} on INBXR.\n\nAccept: {accept_url}\n\nThis invite expires in 7 days."
    return _send(to_email, subject, html, text)
