"""
email/service.py — Thin wrapper around the Resend SDK.

All email-sending logic lives here so that the auth service
never has a direct dependency on Resend internals.
"""
import resend

from config import RESEND_API_KEY, EMAIL_FROM, log

resend.api_key = RESEND_API_KEY


def send_otp_email(to: str, otp: str) -> None:
    """Send the 6-digit OTP to the user."""
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto">
      <h2 style="color:#1a1a2e">Your Sound Check verification code</h2>
      <p style="font-size:15px;color:#444">
        Use the code below to verify your email address. It expires in <strong>15 minutes</strong>.
      </p>
      <div style="font-size:42px;font-weight:700;letter-spacing:12px;
                  text-align:center;padding:24px 0;color:#6c47ff">
        {otp}
      </div>
      <p style="font-size:13px;color:#888">
        If you did not request this, please ignore this email.
      </p>
    </div>
    """
    try:
        result = resend.Emails.send({
            "from":    EMAIL_FROM,
            "to":      to,
            "subject": f"{otp} is your Sound Check verification code",
            "html":    html,
        })
        log.info(f"[email] OTP sent to {to} — id={result.get('id')}")
    except Exception as exc:
        log.error(f"[email] Failed to send OTP to {to}: {exc}")
        raise
