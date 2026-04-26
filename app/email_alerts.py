"""
app/email_alerts.py

Resend-based email alerts for Evidentix Custody Monitoring.

Provides:
    send_upload_alert(...)        — fires when a new file is uploaded to a monitored matter
    send_chain_failure_alert(...) — fires when chain integrity check fails
    send_monthly_summary(...)     — monthly activity digest per monitored matter
"""

import os
import logging
from datetime import datetime

import resend

logger = logging.getLogger(__name__)

FROM_ADDRESS = "alerts@evidenceanalyzer.com"
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")


def _get_client():
    if not RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — email alerts disabled.")
        return None
    resend.api_key = RESEND_API_KEY
    return resend


def send_upload_alert(
    to_email: str,
    case_id: str,
    case_name: str,
    file_name: str,
    evidence_id: str,
    sha256: str,
    uploaded_by: str,
    base_url: str = "https://evidenceanalyzer.com",
):
    """Send an alert when a new file is uploaded to a monitored matter."""
    client = _get_client()
    if not client:
        return

    subject = f"Evidentix Alert — New File Uploaded to {case_name}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #5B2D8E; color: white; padding: 24px 28px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 20px;">Evidentix&#8482; Custody Monitoring</h1>
            <p style="margin: 4px 0 0 0; opacity: 0.8; font-size: 13px;">New File Upload Alert</p>
        </div>
        <div style="background: white; padding: 28px; border: 1px solid #e5e7eb; border-top: none;">
            <p style="margin-top: 0;">A new evidence file has been uploaded to a matter you are monitoring.</p>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; width: 40%; background: #faf8ff;">Case ID</td>
                    <td style="padding: 10px 12px;">{case_id}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Matter Name</td>
                    <td style="padding: 10px 12px;">{case_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">File Name</td>
                    <td style="padding: 10px 12px;">{file_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Evidence ID</td>
                    <td style="padding: 10px 12px; font-family: monospace; font-size: 12px;">{evidence_id}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">SHA-256</td>
                    <td style="padding: 10px 12px; font-family: monospace; font-size: 11px; word-break: break-all;">{sha256}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Uploaded By</td>
                    <td style="padding: 10px 12px;">{uploaded_by}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Timestamp (UTC)</td>
                    <td style="padding: 10px 12px;">{datetime.utcnow().strftime("%B %d, %Y at %H:%M:%S UTC")}</td>
                </tr>
            </table>
            <a href="{base_url}/cases/{case_id}" style="display: inline-block; background: #5B2D8E; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold;">View Case</a>
        </div>
        <div style="padding: 16px 28px; background: #f9f9f9; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px; font-size: 12px; color: #888;">
            Evidentix&#8482; Custody Monitoring &mdash; Evidence Analyzer, LLC &mdash; evidenceanalyzer.com
        </div>
    </div>
    """

    try:
        client.Emails.send({
            "from": FROM_ADDRESS,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        logger.info(f"Upload alert sent to {to_email} for {case_id}/{evidence_id}")
    except Exception as e:
        logger.error(f"Failed to send upload alert: {e}")


def send_chain_failure_alert(
    to_email: str,
    case_id: str,
    case_name: str,
    record_id: str,
    base_url: str = "https://evidenceanalyzer.com",
):
    """Send an alert when chain integrity verification fails."""
    client = _get_client()
    if not client:
        return

    subject = f"URGENT — Evidentix Chain Integrity Failure: {case_name}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #b71c1c; color: white; padding: 24px 28px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 20px;">&#9888; Chain Integrity Failure Detected</h1>
            <p style="margin: 4px 0 0 0; opacity: 0.8; font-size: 13px;">Evidentix&#8482; Custody Monitoring — Urgent Alert</p>
        </div>
        <div style="background: white; padding: 28px; border: 1px solid #e5e7eb; border-top: none;">
            <div style="background: #fdecea; border: 1px solid #f5c6cb; border-radius: 6px; padding: 14px 16px; margin-bottom: 20px;">
                <strong style="color: #b71c1c;">The custody log hash chain for the matter below has failed verification.</strong>
                This indicates that one or more custody log entries may have been altered after recording.
                This finding should be investigated immediately and disclosed to all parties as required.
            </div>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; width: 40%; background: #faf8ff;">Case ID</td>
                    <td style="padding: 10px 12px;">{case_id}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Matter Name</td>
                    <td style="padding: 10px 12px;">{case_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Custody Record ID</td>
                    <td style="padding: 10px 12px; font-family: monospace; font-size: 12px;">{record_id}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Detected At (UTC)</td>
                    <td style="padding: 10px 12px;">{datetime.utcnow().strftime("%B %d, %Y at %H:%M:%S UTC")}</td>
                </tr>
            </table>
            <a href="{base_url}/verify-custody/{record_id}" style="display: inline-block; background: #b71c1c; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold;">View Custody Record</a>
        </div>
        <div style="padding: 16px 28px; background: #f9f9f9; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px; font-size: 12px; color: #888;">
            Evidentix&#8482; Custody Monitoring &mdash; Evidence Analyzer, LLC &mdash; evidenceanalyzer.com
        </div>
    </div>
    """

    try:
        client.Emails.send({
            "from": FROM_ADDRESS,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        logger.info(f"Chain failure alert sent to {to_email} for {case_id}")
    except Exception as e:
        logger.error(f"Failed to send chain failure alert: {e}")


def send_monthly_summary(
    to_email: str,
    case_id: str,
    case_name: str,
    file_count: int,
    tier_limit: int,
    event_count: int,
    chain_verified: bool,
    period: str,
    base_url: str = "https://evidenceanalyzer.com",
):
    """Send a monthly activity summary for a monitored matter."""
    client = _get_client()
    if not client:
        return

    chain_status = "VERIFIED ✓" if chain_verified else "FAILED ✗"
    chain_color = "#1e7e34" if chain_verified else "#b71c1c"
    subject = f"Evidentix Monthly Summary — {case_name} — {period}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: #5B2D8E; color: white; padding: 24px 28px; border-radius: 8px 8px 0 0;">
            <h1 style="margin: 0; font-size: 20px;">Evidentix&#8482; Monthly Summary</h1>
            <p style="margin: 4px 0 0 0; opacity: 0.8; font-size: 13px;">{period}</p>
        </div>
        <div style="background: white; padding: 28px; border: 1px solid #e5e7eb; border-top: none;">
            <p style="margin-top: 0;">Here is your monthly custody monitoring summary for the matter below.</p>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; width: 40%; background: #faf8ff;">Case ID</td>
                    <td style="padding: 10px 12px;">{case_id}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Matter Name</td>
                    <td style="padding: 10px 12px;">{case_name}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Files on Platform</td>
                    <td style="padding: 10px 12px;">{file_count} of {tier_limit}</td>
                </tr>
                <tr style="border-bottom: 1px solid #e5e7eb;">
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Custody Events This Period</td>
                    <td style="padding: 10px 12px;">{event_count}</td>
                </tr>
                <tr>
                    <td style="padding: 10px 12px; font-weight: bold; color: #555; background: #faf8ff;">Chain Integrity</td>
                    <td style="padding: 10px 12px; font-weight: bold; color: {chain_color};">{chain_status}</td>
                </tr>
            </table>
            <a href="{base_url}/cases/{case_id}" style="display: inline-block; background: #5B2D8E; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold;">View Case</a>
        </div>
        <div style="padding: 16px 28px; background: #f9f9f9; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 8px 8px; font-size: 12px; color: #888;">
            Evidentix&#8482; Custody Monitoring &mdash; Evidence Analyzer, LLC &mdash; evidenceanalyzer.com
        </div>
    </div>
    """

    try:
        client.Emails.send({
            "from": FROM_ADDRESS,
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        logger.info(f"Monthly summary sent to {to_email} for {case_id}")
    except Exception as e:
        logger.error(f"Failed to send monthly summary: {e}")