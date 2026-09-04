"""
analysis/service.py — Core voice-analysis business logic.

Uses the Object-Oriented ML pipeline classes from the ml/ package.
No HTTP or DB code lives here — purely transformation logic.
"""
import math
import os
import subprocess
import tempfile
import time
import soundfile as sf

from config import POPULATION_BASELINES, GUEST_VAD_THRESHOLD, log





def _sanitise(obj):
    """Recursively replace NaN/Inf floats with None for safe JSON serialisation."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitise(v) for v in obj]
    return obj


def _get_category(val: float, feat_name: str, baseline: dict, raw_val=None) -> str:
    """Z-score category against population baseline."""
    mean, sd = baseline.get(feat_name, (0.0, 1.0))
    if feat_name == "jitterLocal_sma3nz_amean" and raw_val is not None:
        return "High" if raw_val >= 33.0 else "Low"
    z = (val - mean) / max(sd, 1e-6)
    if feat_name == "loudness_sma3_amean":
        return "High" if z >= 0 else "Low"
    if feat_name == "F0semitoneFrom27.5Hz_sma3nz_amean":
        if z >= 0.79:  return "High"
        if z <= -0.79: return "Low"
        return "Medium"
    return "High" if z >= 0 else "Low"



def scan_safety(transcript: str, engine) -> tuple[bool, str | None, str | None]:
    if not transcript or not transcript.strip():
        return False, None, None
    if not engine.distilbart_pipeline:
        return False, None, None
    
    candidate_labels = ["suicide or self harm", "violence", "safe", "normal statement"]
    result = engine.distilbart_pipeline(
        transcript.strip(), 
        candidate_labels=candidate_labels, 
        multi_label=True
    )
    for label, score in zip(result['labels'], result['scores']):
        if label in ["suicide or self harm", "violence"] and score >= 0.75:
            category = "self_harm" if label == "suicide or self harm" else "harm_others"
            return True, f"{label} ({score*100:.1f}%)", category
    return False, None, None

class AnalysisError(Exception):

    """Raised on unrecoverable ML pipeline failures."""


def run_voice_analysis(audio_bytes: bytes, filename: str, sleep_3d_avg: float) -> dict:
    """
    Full guest-style voice analysis pipeline using OOP ML classes.
    """
    from ml.engine import ModelEngine
    from ml.preprocess import AudioPreprocessor
    from ml.pipeline import VoiceAnalyzer, FeatureExtractionError

    # Instantiate services
    engine = ModelEngine.get_instance()
    preprocessor = AudioPreprocessor()
    analyzer = VoiceAnalyzer(engine)

    baseline = POPULATION_BASELINES.get(("M", "18-35"), {})

    tmp_upload = tmp_rnnoise = tmp_wav = None
    try:
        log.info(f"[analysis] Step 1: Writing upload to disk ({filename})")
        # 1. Write upload to disk
        ext = os.path.splitext(filename)[-1] or ".wav"
        fd, tmp_upload = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        with open(tmp_upload, "wb") as f:
            f.write(audio_bytes)

        log.info("[analysis] Step 2: Running RNNoise denoising")
        # 2. RNNoise denoising
        tmp_rnnoise = preprocessor.process(tmp_upload)

        log.info("[analysis] Step 3: Downsampling to 16kHz mono via ffmpeg")
        # 3. Downsample to 16kHz mono
        fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        res = subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_rnnoise,
             "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp_wav],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if res.returncode != 0:
            raise AnalysisError(f"FFmpeg failed: {res.stderr.decode('utf-8', errors='ignore')}")

        log.info("[analysis] Step 4: Loading audio into memory")
        # 4. Load audio
        wf, sr = sf.read(tmp_wav)
        if len(wf.shape) > 1:
            wf = wf.mean(axis=1)
        audio_duration_sec = len(wf) / sr
        
        log.info("[analysis] Step 5: Running VAD gate")
        # 5. VAD gate (energy fallback only for simplicity in guest if Silero fails)
        speech_ratio = _speech_ratio_vad(wf, sr, engine)
        log.info(f"[analysis] VAD speech_ratio={speech_ratio:.1%} threshold={GUEST_VAD_THRESHOLD:.1%}")
        if speech_ratio < GUEST_VAD_THRESHOLD:
            raise AnalysisError(
                f"INSUFFICIENT_SPEECH|Only {speech_ratio:.0%} of the recording contained voice. "
                "Please ensure you are speaking clearly and try again."
            )

        log.info("[analysis] Step 6: Starting chunked ML processing")
        # 6. Chunked processing (30-second windows)
        chunk_length = 30 * sr
        segments     = []
        comp_start   = time.perf_counter()

        for i in range(0, len(wf), chunk_length):
            chunk = wf[i:i + chunk_length]
            if len(chunk) < sr:       # skip < 1 s tail
                continue

            fd, tmp_chunk = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            sf.write(tmp_chunk, chunk, sr)
            
            try:
                raw = analyzer.process_chunk(tmp_chunk, chunk, sleep_3d_avg)
                
                pitch_cat    = _get_category(raw.get("pitch_semitones", 0),   "F0semitoneFrom27.5Hz_sma3nz_amean", baseline)
                loudness_cat = _get_category(raw.get("loudness", 0),           "loudness_sma3_amean",               baseline)
                jitter_cat   = _get_category(raw.get("jitter", 0) / 100.0,    "jitterLocal_sma3nz_amean",          baseline, raw_val=raw.get("jitter", 0))

                segments.append({
                    "start_time":            round(i / sr, 2),
                    "end_time":              round(min((i + chunk_length) / sr, audio_duration_sec), 2),
                    "stress_score":          raw.get("stress_score"),
                    "composure_score":       raw.get("composure_score"),
                    "mood":                  raw.get("mood"),
                    "tone":                  raw.get("tone"),
                    "pace":                  raw.get("pace", 0.0),
                    "pitch":                 pitch_cat,
                    "jitter":                jitter_cat,
                    "raw_jitter":            raw.get("jitter", 0),
                    "loudness":              loudness_cat,
                })
            except FeatureExtractionError:
                pass   # skip bad chunk, keep going
            finally:
                if os.path.exists(tmp_chunk):
                    os.remove(tmp_chunk)

        if not segments:
            raise AnalysisError("NO_SEGMENTS|Audio too short to analyse. Please record at least 10 seconds.")

        log.info("[analysis] Step 7: Aggregating chunk metrics into overall scores")
        # 7. Aggregate overall
        n             = len(segments)
        stress_mean   = int(round(sum(s.get("stress_score",   50) for s in segments) / n))
        comp_mean     = int(round(sum(s.get("composure_score", 50) for s in segments) / n))
        pace_mean     = round(sum(s.get("pace",            0.0) for s in segments) / n, 3)
        jitter_mean   = sum(s.get("raw_jitter",       0)   for s in segments) / n

        comp_mean = 100 - stress_mean

        if comp_mean > 85:
            stress_label = "Resilient"
            comp_label = "Resilient"
        elif comp_mean >= 66:
            stress_label = "Adaptive"
            comp_label = "Adaptive"
        elif comp_mean >= 33:
            stress_label = "Stabilised"
            comp_label = "Stabilised"
        else:
            stress_label = "Dysregulated"
            comp_label = "Dysregulated" 

        sleep_debt_hrs = max(0.0, round((8.0 - sleep_3d_avg) * 3, 2)) if sleep_3d_avg > 0 else None

        overall = {
            "stress_score":          stress_mean,
            "composure_score":       comp_mean,
            "pitch":                 segments[-1]["pitch"],
            "pace":                  pace_mean,
            "jitter":                segments[-1]["jitter"],
            "raw_jitter_percentage": round(jitter_mean, 3),
            "loudness":              segments[-1]["loudness"],
            "mood":                  segments[-1]["mood"],
            "tone":                  segments[-1]["tone"],
            "stress_label":          stress_label,
            "composure_label":       comp_label,
            "sleep_3d_avg":          sleep_3d_avg if sleep_3d_avg > 0 else None,
            "sleep_debt_hrs":        sleep_debt_hrs,
            "summary":               summary_text,
        }

        compute_ms = round((time.perf_counter() - comp_start) * 1000)
        log.info(f"[analysis] Done in {compute_ms}ms, speech={speech_ratio:.1%}")

        return _sanitise({
            "overall":            overall,
            "segments":           segments,
            "speech_ratio":       round(speech_ratio, 3),
            "audio_duration_sec": round(audio_duration_sec, 2),
            "sleep_3d_avg":       sleep_3d_avg if sleep_3d_avg > 0 else None,
            "ml_version":         "v3.1.0_oop",
        })

    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError(f"PROCESSING_ERROR|{exc}") from exc
    finally:
        for p in (tmp_upload, tmp_rnnoise, tmp_wav):
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

def _speech_ratio_vad(wf, sr, engine) -> float:
    """VAD with Silero fallback."""
    import numpy as np
    try:
        import torch
        if engine.silero_vad_model and engine.silero_vad_get_timestamps:
            wav_t = torch.from_numpy(wf).float()
            if wav_t.dim() == 1:
                wav_t = wav_t.unsqueeze(0)
            timestamps = engine.silero_vad_get_timestamps(
                wav_t, engine.silero_vad_model, sampling_rate=sr, threshold=0.4
            )
            voiced = sum(ts["end"] - ts["start"] for ts in timestamps)
            return float(voiced / max(len(wf), 1))
    except Exception as exc:
        log.warning(f"[vad] Silero failed ({exc}), falling back to energy VAD")

    frame_len   = int(sr * 0.02)
    frames      = [wf[i:i + frame_len] for i in range(0, len(wf) - frame_len, frame_len)]
    if not frames:
        return 0.0
    energies    = [float(np.sqrt(np.mean(f ** 2))) for f in frames]
    noise_floor = sorted(energies)[max(0, int(len(energies) * 0.05))]
    threshold   = noise_floor * 3.0
    voiced      = sum(1 for e in energies if e > threshold)
    return voiced / len(energies)
