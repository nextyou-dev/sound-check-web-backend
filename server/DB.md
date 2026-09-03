# Database Architecture & Schemas

The NextYou `sound-check-web` backend uses **MongoDB** as its primary datastore. We adhere to the Repository pattern to ensure the database layer is fully decoupled from the business logic and HTTP controllers.

## Core Optimization & Uniqueness

As requested, **the user's Email is treated as the true global unique identifier**.
- This is enforced at the database level using a `unique: True` index on the `users` collection.
- Foreign documents (such as analysis events) store the `user_id` (ObjectId) for efficient joins, but also embed the `email` directly to optimize for simple read queries without requiring $lookup operations.

All performance-critical queries are covered by appropriate indexes, including TTL (Time-To-Live) indexes for auto-expiring rate limits.

---

## 1. `users` Collection

Stores authentication state and OTP hashes.

### Schema
```json
{
  "_id": ObjectId("..."),             // Internal Mongo ID
  "email": "user@example.com",        // (String, UNIQUE INDEX) Primary User Identifier
  "otp_hash": "$2b$12$...",           // (String) bcrypt hashed current OTP
  "otp_expires_at": ISODate("..."),   // (Date) Expiration time of the current OTP
  "is_verified": true,                // (Boolean) Has the user ever completed an OTP verification?
  "created_at": ISODate("..."),       // (Date)
  "updated_at": ISODate("...")        // (Date)
}
```

### Operation
- **Upserting OTPs**: When a user requests an OTP, the system performs a `find_one_and_update` with `upsert=True` matching exactly on the lowercased `email`. This guarantees exactly one document per email.
- **Verification**: If the user submits the correct OTP before `otp_expires_at`, the `otp_hash` field is cleared (`null`), and a JWT is issued using both the `_id` (as the `sub`) and the `email`.

---

## 2. `analysis_events` Collection

Stores the results of every successful voice analysis, alongside engagement tracking flags.

### Schema
```json
{
  "_id": ObjectId("..."),             // Internal Mongo ID
  "user_id": ObjectId("..."),         // (ObjectId, INDEXED) Reference to the `users` collection
  "email": "user@example.com",        // (String) Denormalized for fast filtering
  "ip": "192.168.1.1",                // (String) Client IP (useful for rate-limiting context)
  
  // ML Output Payload
  "overall": {
    "stress_score": 45,
    "composure_score": 55,
    "stress_label": "Adaptive",
    "composure_label": "Stabilised",
    "sleep_3d_avg": 7.5,
    "sleep_debt_hrs": 1.5,
    // ... pitch, pace, jitter, loudness, mood, tone
  },
  "segments": [ ... ],                // Array of 30-second chunk results
  "speech_ratio": 0.85,               // (Float) VAD ratio
  "audio_duration_sec": 30.5,         // (Float) Length of audio file
  "ml_version": "v3.1.0_oop",         // (String) ML Pipeline version tracking
  
  // Engagement Flags
  "has_viewed_result": false,         // (Boolean)
  "viewed_at": null,                  // (Date | Null)
  "has_clicked_download": false,      // (Boolean)
  "downloaded_at": null,              // (Date | Null)

  "created_at": ISODate("...")        // (Date)
}
```

### Operation
- **Insertion**: Happens asynchronously in the background *after* the HTTP response is sent, keeping the user's wait time to an absolute minimum.
- **Engagement Updates**: When the frontend hits the `/analysis/{id}/viewed` or `/downloaded` routes, we perform an idempotent `update_one` matching the `_id` AND the `user_id` from the JWT. This guarantees users can only modify their own analysis records.

---

## 3. `rate_limits` Collection

A specialized tracking collection used exclusively to enforce the 3 analyses per 48 hours policy.

### Schema
```json
{
  "_id": ObjectId("..."),
  "key": "rl:voice:user@example.com", // (String, UNIQUE INDEX) The composite limit key
  "count": 3,                         // (Integer) Number of requests made
  "expires_at": ISODate("...")        // (Date, TTL INDEX) Automatic deletion timestamp
}
```

### Operation
- **Atomic Increments**: Uses MongoDB's `$inc` operator to increment the `count` in a thread-safe way.
- **Auto Cleanup**: The `expires_at` field has a MongoDB TTL (Time-To-Live) index attached (`expireAfterSeconds=0`). Exactly 48 hours after the *first* request in a window, MongoDB's background sweeper automatically deletes the document. This resets the rate limit without requiring any manual cron jobs.
