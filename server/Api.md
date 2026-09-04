# Sound Check API — Documentation

**Base URL:** `https://sound-check-api.nextyou.app`  
**Protocol:** HTTPS only  
**Content-Type:** `application/json` for all JSON endpoints; `multipart/form-data` for file upload  
**Auth:** Bearer JWT in the `Authorization` header for all protected routes

---

## General Error Schema

All non-2xx responses return a JSON body with a `detail` field:

```json
{ "detail": "ERROR_CODE|Human-readable message" }
```

The frontend should split on `|`. The left part is a machine-readable error code; the right part is safe to display to the user. If no `|` is present, treat the entire string as the message.

---

## 1. Authentication

### `POST /auth/send-otp`

Sends a 6-digit OTP to the provided email address via Resend. Creates the user account if it doesn't exist yet.

**Auth required:** No

**Request Body:**
```json
{
  "email": "user@example.com"
}
```

**Responses:**

| Status | Body | Description |
|--------|------|-------------|
| `200` | `{ "success": true, "message": "OTP sent to your email." }` | OTP dispatched successfully |
| `422` | FastAPI validation error | Invalid email format |
| `500` | `{ "detail": "MAILER_ERROR\|..." }` | Resend failed to deliver the email |

---

### `POST /auth/verify-otp`

Validates the submitted OTP against the stored bcrypt hash. On success, returns a signed JWT valid for `JWT_EXPIRES_DAYS` days.

**Auth required:** No

**Request Body:**
```json
{
  "email": "user@example.com",
  "otp": "874254"
}
```

**Responses:**

| Status | Body | Description |
|--------|------|-------------|
| `200` | `{ "access_token": "eyJhbG...", "token_type": "bearer" }` | OTP verified; JWT issued |
| `401` | `{ "detail": "OTP has expired. Please request a new one." }` | OTP TTL elapsed |
| `401` | `{ "detail": "Incorrect OTP." }` | Wrong code |
| `401` | `{ "detail": "No OTP pending for this email. Please request one." }` | No pending OTP |
| `422` | FastAPI validation error | Missing or malformed fields |
| `500` | `{ "detail": "AUTH_ERROR\|..." }` | Unexpected server error |

---

## 2. Voice Analysis

### `POST /analysis/voice`

Analyzes a voice recording and returns a full stress/composure breakdown. Heavy ML inference is performed on the server (expect 15–60 s on CPU). DB logging and rate-limit counter increments happen in the background **after** the response is returned.

**Auth required:** Yes (`Authorization: Bearer <token>`)

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio_file` | File | ✅ | Voice recording. Accepts WAV, MP3, M4A, OGG, FLAC, or any ffmpeg-supported format |
| `session_id` | string | ✅ | Frontend-generated unique identifier for this session (used later for engagement tracking) |
| `sleep_3d_avg` | float | ❌ | User's average sleep hours over the last 3 days. Defaults to `0.0`. Pass `0` to omit |

**Success Response `200`:**
```json
{
  "overall": {
    "stress_score": 45,
    "composure_score": 55,
    "stress_label": "Adaptive",
    "composure_label": "Stabilised",
    "pitch": "Medium",
    "pace": 3.2,
    "jitter": "Low",
    "raw_jitter_percentage": 0.042,
    "loudness": "High",
    "mood": "NEUTRAL",
    "tone": "NEUTRAL",
    "sleep_3d_avg": 7.5,
    "sleep_debt_hrs": 1.5
  },
  "segments": [
    {
      "start_time": 0.0,
      "end_time": 30.0,
      "stress_score": 45,
      "composure_score": 55,
      "mood": "NEUTRAL",
      "tone": "NEUTRAL",
      "pace": 3.2,
      "pitch": "Medium",
      "jitter": "Low",
      "loudness": "High"
    }
  ],
  "speech_ratio": 0.85,
  "audio_duration_sec": 30.5,
  "ml_version": "v3.1.0_oop"
}
```

**Stress / Composure Label Logic:**

Labels are determined by the `composure_score` (`100 - stress_score`). Both labels are set to the same value based on the composure score.

| Composure Score | Stress Label | Composure Label |
|---|---|---|
| > 85 | Resilient | Resilient |
| 66 – 85 | Adaptive | Adaptive |
| 33 – 65 | Stabilised | Stabilised |
| 0 – 32 | Dysregulated | Dysregulated |

**Error Responses:**

| Status | `detail` | Cause |
|--------|----------|-------|
| `401` | `"Not authenticated"` | Missing or invalid JWT |
| `422` | `"INSUFFICIENT_SPEECH\|Only X% of the recording contained voice..."` | VAD found < 50% speech content |
| `422` | `"NO_SEGMENTS\|Audio too short to analyse..."` | Recording shorter than ~10 s of usable speech |
| `429` | `"RATE_LIMIT_EXCEEDED\|You have reached the limit of N analyses per 48 hours..."` | Per-account quota hit |
| `400` | `"INVALID_FILE\|Could not read the uploaded audio file."` | Corrupt or unreadable upload |
| `500` | `"PROCESSING_ERROR\|..."` | Unexpected ML pipeline failure |

---

### `GET /analysis/quota`

Returns the authenticated user's remaining analysis quota for the current 48-hour window.

**Auth required:** Yes (`Authorization: Bearer <token>`)

**Request Body:** None

**Success Response `200`:**
```json
{
  "max": 3,
  "used": 1,
  "remaining": 2,
  "window_hours": 48,
  "hours_remaining": 46.0
}
```

| Field | Type | Description |
|-------|------|-------------|
| `max` | int | Maximum analyses allowed per window (set via `RATE_LIMIT_MAX` env var) |
| `used` | int | How many analyses the user has run in the current window |
| `remaining` | int | How many analyses the user can still run (`max - used`) |
| `window_hours` | int | The rolling window size in hours (set via `RATE_LIMIT_WINDOW_H`, default `48`) |
| `hours_remaining` | float | Hours until the rate-limit window resets. `0.0` if no usage yet in this window |

**Error Responses:**

| Status | `detail` | Cause |
|--------|----------|-------|
| `401` | `"Not authenticated"` | Missing or invalid JWT |

---

## 3. Engagement Tracking

Both endpoints are **idempotent** — calling them multiple times has no side effect after the first call. They look up the analysis event by `session_id` and verify it belongs to the authenticated user.

---

### `PATCH /analysis/viewed`

Marks the analysis result as viewed by the user.

**Auth required:** Yes (`Authorization: Bearer <token>`)

**Request Body:**
```json
{
  "session_id": "frontend-generated-session-uuid"
}
```

**Success Response `200`:**
```json
{
  "success": true,
  "has_viewed_result": true
}
```

**Error Responses:**

| Status | `detail` | Cause |
|--------|----------|-------|
| `401` | `"Not authenticated"` | Missing or invalid JWT |
| `404` | `"Session not found or does not belong to you."` | Invalid `session_id` or belongs to a different user |

---

### `PATCH /analysis/downloaded`

Marks the analysis result as downloaded by the user.

**Auth required:** Yes (`Authorization: Bearer <token>`)

**Request Body:**
```json
{
  "session_id": "frontend-generated-session-uuid"
}
```

**Success Response `200`:**
```json
{
  "success": true,
  "has_clicked_download": true
}
```

**Error Responses:**

| Status | `detail` | Cause |
|--------|----------|-------|
| `401` | `"Not authenticated"` | Missing or invalid JWT |
| `404` | `"Session not found or does not belong to you."` | Invalid `session_id` or belongs to a different user |

---

## 4. Rate Limiting

| Dimension | Limit | Window |
|-----------|-------|--------|
| Per account (email) | `RATE_LIMIT_MAX` (env var, default `3`) | 48 hours rolling |

- The counter is incremented **after** a successful analysis only.
- Failed requests (bad audio, processing errors, etc.) do **not** count against the quota.
- The window resets automatically via a MongoDB TTL index — no cron job required.
- Use `GET /analysis/quota` before submitting audio to check remaining uses.

**Rate limit exceeded response `429`:**
```json
{
  "detail": "RATE_LIMIT_EXCEEDED|You have reached the limit of 3 voice analyses per 48 hours. Please try again later."
}
```

---

## 5. Authentication Flow (End-to-End)

```
1. POST /auth/send-otp    { email }          → OTP sent to inbox
2. POST /auth/verify-otp  { email, otp }     → { access_token, token_type }
3. Store token on client (localStorage / secure cookie)
4. Pass token on every protected request:
   Authorization: Bearer <access_token>
```

---

## 6. Frontend Integration Notes

- **`session_id`**: Generate this on the frontend when the user starts a recording session (e.g. `crypto.randomUUID()`). Store it locally so you can call `/analysis/viewed` and `/analysis/downloaded` later using the same ID.
- **Polling quota**: Call `GET /analysis/quota` on app load to decide whether to show/hide the record button.
- **Error handling**: Always split `detail` on `|`. Example:
  ```js
  const [code, message] = detail.includes('|')
    ? detail.split('|')
    : ['ERROR', detail];
  ```
