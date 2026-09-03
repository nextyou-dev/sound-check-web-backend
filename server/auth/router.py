"""
auth/router.py — HTTP layer for authentication endpoints.

POST /auth/send-otp   — generates and emails a 6-digit OTP
POST /auth/verify-otp — validates OTP, returns signed JWT
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from auth.service import OTPError, create_and_store_otp, verify_otp_and_issue_token
from mailer.service import send_otp_email

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─── Request schemas ─────────────────────────────────────────────────────────

class SendOtpRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp:   str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/send-otp", summary="Send a 6-digit OTP to the user's email")
def send_otp(body: SendOtpRequest):
    try:
        otp = create_and_store_otp(body.email)
        send_otp_email(body.email, otp)
        return {"success": True, "message": "OTP sent to your email."}
    except Exception as exc:
        return JSONResponse(status_code=500, content={"detail": f"MAILER_ERROR|{str(exc)}"})


@router.post("/verify-otp", summary="Verify OTP and receive a JWT")
def verify_otp(body: VerifyOtpRequest):
    try:
        token = verify_otp_and_issue_token(body.email, body.otp)
        return {"access_token": token, "token_type": "bearer"}
    except OTPError as exc:
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc)},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={"detail": f"AUTH_ERROR|{str(exc)}"}
        )
