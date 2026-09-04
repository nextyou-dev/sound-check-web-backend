"""
config.py — Centralised env-var loading for sound-check-web server.
All secrets and tunable constants are read from .env via python-dotenv.
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv(override=True)

# ─── Logger ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("soundcheck")

# ─── MongoDB ─────────────────────────────────────────────────────────────────
MONGO_URI: str     = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "soundcheck")

# ─── JWT ─────────────────────────────────────────────────────────────────────
JWT_SECRET: str       = os.getenv("JWT_SECRET", "change-me")
JWT_ALGORITHM: str    = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRES_DAYS: int = int(os.getenv("JWT_EXPIRES_DAYS", "7"))

# ─── Resend ──────────────────────────────────────────────────────────────────
RESEND_API_KEY: str = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM: str     = os.getenv("EMAIL_FROM", "onboarding@resend.dev")

# ─── Rate limiting ──────────────────────────────────────────────────────────
RATE_LIMIT_MAX: int      = int(os.getenv("RATE_LIMIT_MAX", "3"))
RATE_LIMIT_WINDOW_H: int = int(os.getenv("RATE_LIMIT_WINDOW_H", "48"))

# MAX_TRIES — alias for RATE_LIMIT_MAX. Set this env var to control how many
# analyses a user can run per 48-hour window. Defaults to RATE_LIMIT_MAX.
MAX_TRIES: int = RATE_LIMIT_MAX

# ─── ML / VAD ────────────────────────────────────────────────────────────────
GUEST_VAD_THRESHOLD: float = float(os.getenv("GUEST_VAD_THRESHOLD", "0.50"))

# ─── ML Population baselines (M/18-35 default used for guest) ────────────────
POPULATION_BASELINES = {
    ("F", "18-35"): {
        "F0semitoneFrom27.5Hz_sma3nz_amean":      (38.5, 3.2),
        "F0semitoneFrom27.5Hz_sma3nz_stddevNorm":  (0.18, 0.05),
        "jitterLocal_sma3nz_amean":                (0.025, 0.012),
        "shimmerLocaldB_sma3nz_amean":             (1.10, 0.35),
        "HNRdBACF_sma3nz_amean":                   (8.5, 2.1),
        "loudness_sma3_amean":                     (0.42, 0.15),
        "VoicedSegmentsPerSec":                    (3.6, 0.9),
        "logRelF0-H1-H2_sma3nz_amean":             (10.5, 3.5),
    },
    ("M", "18-35"): {
        "F0semitoneFrom27.5Hz_sma3nz_amean":      (26.3, 2.8),
        "F0semitoneFrom27.5Hz_sma3nz_stddevNorm":  (0.16, 0.05),
        "jitterLocal_sma3nz_amean":                (0.024, 0.011),
        "shimmerLocaldB_sma3nz_amean":             (1.05, 0.33),
        "HNRdBACF_sma3nz_amean":                   (9.0, 2.0),
        "loudness_sma3_amean":                     (0.45, 0.16),
        "VoicedSegmentsPerSec":                    (3.5, 0.9),
        "logRelF0-H1-H2_sma3nz_amean":             (7.8, 3.0),
    },
}

MODELS_DIR = os.getenv('MODELS_DIR', '/gcs/nuo-app-assets/model-weights')
# ─── ML pipeline constants ───────────────────────────────────────────────────────

MIN_AUDIO_DURATION_SEC = 10.0

# 30 recordings before personal baseline + learned intervention bonus kick in.
MIN_RECORDS_PERSONAL = 30

# Acoustic stress feature weights (positive contributors, sum ≈ 0.88)
ACOUSTIC_STRESS_FEATS = {
    "F0semitoneFrom27.5Hz_sma3nz_amean":      0.187,
    "jitterLocal_sma3nz_amean":               0.187,
    "shimmerLocaldB_sma3nz_amean":            0.169,
    "F0semitoneFrom27.5Hz_sma3nz_stddevNorm": 0.131,
    "loudness_sma3_amean":                    0.112,
    "VoicedSegmentsPerSec":                   0.094,
}

# Negative contributors — higher value = LOWER stress
HNR_WEIGHT_STRESS  = -0.06
H1H2_WEIGHT_STRESS = -0.06

# Stress component weights (sum = 1.0)
STRESS_WEIGHTS = {
    "acoustic":    0.40,
    "affective":   0.25,
    "categorical": 0.15,
    "context":     0.20,
}

# Recovery component weights (sum = 1.0)
RECOVERY_WEIGHTS = {
    "hnr_clarity": 0.20,
    "affective":   0.20,
    "trend":       0.20,
    "sleep":       0.20,
    "calendar":    0.20,
}

# SenseVoice emotion → stress load mapping
EMOTION_STRESS_LOAD = {
    "ANGRY":      0.90,
    "ANXIOUS":    0.85,
    "FRUSTRATED": 0.80,
    "DISGUSTED":  0.75,
    "SAD":        0.65,
    "TIRED":      0.60,
    "FEARFUL":    0.85,
    "SURPRISED":  0.45,
    "EXCITED":    0.40,
    "NEUTRAL":    0.35,
    "CONTENT":    0.20,
    "HAPPY":      0.15,
    "CALM":       0.10,
}

# eGeMAPS features tracked for baselines and z-score highlights
TRACKED_FEATURES = [
    "F0semitoneFrom27.5Hz_sma3nz_amean",
    "F0semitoneFrom27.5Hz_sma3nz_stddevNorm",
    "jitterLocal_sma3nz_amean",
    "shimmerLocaldB_sma3nz_amean",
    "HNRdBACF_sma3nz_amean",
    "loudness_sma3_amean",
    "VoicedSegmentsPerSec",
    "logRelF0-H1-H2_sma3nz_amean",
]

# Population baselines (mean, std) by sex × age_band
POPULATION_BASELINES = {
    ("F", "18-35"): {
        "F0semitoneFrom27.5Hz_sma3nz_amean":      (38.5, 3.2),
        "F0semitoneFrom27.5Hz_sma3nz_stddevNorm":  (0.18, 0.05),
        "jitterLocal_sma3nz_amean":                (0.025, 0.012),
        "shimmerLocaldB_sma3nz_amean":             (1.10, 0.35),
        "HNRdBACF_sma3nz_amean":                   (8.5, 2.1),
        "loudness_sma3_amean":                     (0.42, 0.15),
        "VoicedSegmentsPerSec":                    (3.6, 0.9),
        "logRelF0-H1-H2_sma3nz_amean":                      (10.5, 3.5),
    },
    ("F", "36-55"): {
        "F0semitoneFrom27.5Hz_sma3nz_amean":      (37.2, 3.0),
        "F0semitoneFrom27.5Hz_sma3nz_stddevNorm":  (0.17, 0.05),
        "jitterLocal_sma3nz_amean":                (0.028, 0.013),
        "shimmerLocaldB_sma3nz_amean":             (1.18, 0.38),
        "HNRdBACF_sma3nz_amean":                   (8.1, 2.2),
        "loudness_sma3_amean":                     (0.40, 0.14),
        "VoicedSegmentsPerSec":                    (3.4, 0.9),
        "logRelF0-H1-H2_sma3nz_amean":                      (9.8, 3.3),
    },
    ("M", "18-35"): {
        "F0semitoneFrom27.5Hz_sma3nz_amean":      (26.3, 2.8),
        "F0semitoneFrom27.5Hz_sma3nz_stddevNorm":  (0.16, 0.05),
        "jitterLocal_sma3nz_amean":                (0.024, 0.011),
        "shimmerLocaldB_sma3nz_amean":             (1.05, 0.33),
        "HNRdBACF_sma3nz_amean":                   (9.0, 2.0),
        "loudness_sma3_amean":                     (0.45, 0.16),
        "VoicedSegmentsPerSec":                    (3.5, 0.9),
        "logRelF0-H1-H2_sma3nz_amean":                      (7.8, 3.0),
    },
    ("M", "36-55"): {
        "F0semitoneFrom27.5Hz_sma3nz_amean":      (25.5, 2.7),
        "F0semitoneFrom27.5Hz_sma3nz_stddevNorm":  (0.15, 0.05),
        "jitterLocal_sma3nz_amean":                (0.027, 0.012),
        "shimmerLocaldB_sma3nz_amean":             (1.12, 0.36),
        "HNRdBACF_sma3nz_amean":                   (8.6, 2.1),
        "loudness_sma3_amean":                     (0.43, 0.15),
        "VoicedSegmentsPerSec":                    (3.3, 0.8),
        "logRelF0-H1-H2_sma3nz_amean":                      (7.2, 2.8),
    },
}
