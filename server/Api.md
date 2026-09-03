# Sound Check Web — API Documentation

This document describes all exposed endpoints, authentication flows, rate limiting rules, and error schemas.

## Base URL
All routes are exposed on the FastAPI server root (default `http://localhost:8001`).

---

## 1. Authentication

The authentication flow is completely passwordless and relies on Resend email OTPs.

### `POST /auth/request-otp`
Sends a 6-digit OTP to the user's email address.

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Responses:**
- `200 OK`
  ```json
  {
    "message": "OTP sent successfully."
  }
  ```
- `422 Unprocessable Entity`: Invalid email format.
- `500 Internal Server Error`: `MAILER_ERROR|...` if Resend fails.

### `POST /auth/verify-otp`
Validates the OTP and returns a signed JWT.

**Request Body:**
```json
{
  "email": "user@example.com",
  "otp": "123456"
}
```

**Responses:**
- `200 OK`
  ```json
  {
    "access_token": "eyJhbG...",
    "token_type": "bearer"
  }
  ```
- `401 Unauthorized`:
  ```json
  {
    "detail": "OTP has expired. Please request a new one."
  }
  ```
  *(Other messages include "Incorrect OTP." or "No OTP pending...")*

---

## 2. Voice Analysis

These endpoints require a valid JWT passed in the `Authorization: Bearer <token>` header.

### Rate Limiting Policy
Users are limited to **3 analyses per 48 hours**. This limit is tracked using a combination of the user's `email` and their `IP address` to prevent abuse.

### `POST /analysis/voice`
Analyzes a short voice recording (minimum 10 seconds).

**Headers:**
- `Authorization`: `Bearer <jwt_token>`

**Form Data (multipart/form-data):**
- `file`: The audio file (WAV, MP3, M4A, etc.)
- `sleep_3d_avg` (optional, float): The user's average sleep hours over the last 3 days. Defaults to `0.0`.

**Responses:**
- `200 OK`
  ```json
  {
    "overall": {
      "stress_score": 45,
      "composure_score": 55,
      "pitch": "Medium",
      "pace": 3.2,
      "jitter": "Low",
      "raw_jitter_percentage": 0.05,
      "loudness": "High",
      "mood": "NEUTRAL",
      "tone": "NEUTRAL",
      "stress_label": "Adaptive",
      "composure_label": "Stabilised",
      "sleep_3d_avg": 7.5,
      "sleep_debt_hrs": 1.5
    },
    "segments": [ ... ],
    "speech_ratio": 0.85,
    "audio_duration_sec": 30.5,
    "ml_version": "v3.1.0_oop",
    "event_id": "64f9b8c7e4b0a1a2b3c4d5e6"
  }
  ```
- `429 Too Many Requests`: (Rate Limit Exceeded)
  ```json
  {
    "detail": "RATE_LIMIT_EXCEEDED|You have reached the maximum of 3 analyses per 48 hours."
  }
  ```
- `400 Bad Request`: (Validation / Processing Errors)
  ```json
  {
    "detail": "INSUFFICIENT_SPEECH|Only 12% of the recording contained voice. Please ensure you are speaking clearly and try again."
  }
  ```
  *(Other messages: "NO_SEGMENTS|Audio too short to analyse. Please record at least 10 seconds.", "PROCESSING_ERROR|...")*
- `401 Unauthorized`: Invalid, expired, or missing JWT.

---

## 3. Engagement Tracking

These endpoints track when a user interacts with their analysis results. They are idempotent.

### `PATCH /analysis/{event_id}/viewed`
Marks the analysis result as viewed by the user.

**Headers:**
- `Authorization`: `Bearer <jwt_token>`

**Responses:**
- `200 OK`
  ```json
  {
    "status": "success",
    "message": "View recorded"
  }
  ```
- `404 Not Found`:
  ```json
  {
    "detail": "Analysis event not found or does not belong to you."
  }
  ```

### `PATCH /analysis/{event_id}/downloaded`
Marks the analysis result as downloaded/saved by the user.

**Headers:**
- `Authorization`: `Bearer <jwt_token>`

**Responses:**
- `200 OK`
  ```json
  {
    "status": "success",
    "message": "Download recorded"
  }
  ```
- `404 Not Found`: Same as above.

---

## General Error Response Schema

Whenever a non-200 error occurs, the API will respond with a JSON object following this schema:

```json
{
  "detail": "<ERROR_CODE>|<Human readable description>"
}
```

The frontend should split the `detail` string by the `|` character. The first part is an enum-like error code, and the second part is a human-readable message safe to display directly to the user. If no `|` is present, treat the entire string as the human-readable message.
