"""
ml/pipeline.py — Object-Oriented Voice Analysis Pipeline.
Orchestrates feature extraction, scoring, and VAD chunking.
"""
import math
import numpy as np
import soundfile as sf
import torch
import librosa

from ml.engine import ModelEngine
from config import log, ACOUSTIC_STRESS_FEATS, HNR_WEIGHT_STRESS, H1H2_WEIGHT_STRESS, STRESS_WEIGHTS, EMOTION_STRESS_LOAD


class FeatureExtractionError(Exception):
    pass


class VoiceAnalyzer:
    """
    Core ML pipeline for voice stress analysis.
    Uses the provided ModelEngine to evaluate audio chunks and compute stress scores.
    """
    def __init__(self, engine: ModelEngine):
        self.engine = engine

    def process_chunk(self, chunk_wav_path: str, chunk_array: np.ndarray, sleep_debt_hrs: float) -> dict:
        """
        Processes a single 30s chunk and returns its metrics.
        (Guest version: baseline and history omitted for simplicity)
        """
        features = self._extract_acoustic_features(chunk_wav_path)
        emotion, _ = self._run_sense_voice(chunk_array)
        valence, arousal, _, _ = self._run_valence_arousal_from_array(chunk_array)
        
        stress_score, _ = self._calculate_stress_score(
            features, emotion, valence, arousal, sleep_debt_hrs
        )
        composure_score = 100 - stress_score
        
        if valence > 0.1:
            tone = "POSITIVE"
        elif valence < -0.1:
            tone = "NEGATIVE"
        else:
            tone = "NEUTRAL"
            
        pace = features.get("VoicedSegmentsPerSec", 0.0)
        jitter = features.get("jitterLocal_sma3nz_amean", 0.0)
        jitter_pct = jitter * 100
        
        pitch_semitones = features.get("F0semitoneFrom27.5Hz_sma3nz_amean", 0.0)
        loudness = features.get("loudness_sma3_amean", 0.0)
        
        return {
            "stress_score": stress_score,
            "composure_score": composure_score,
            "mood": emotion,
            "tone": tone,
            "pace": round(pace, 3),
            "jitter": round(jitter_pct, 3),
            "pitch_semitones": pitch_semitones,
            "loudness": loudness,
            "raw_valence": valence,
            "raw_arousal": arousal
        }

    def _extract_acoustic_features(self, path: str) -> dict:
        if not self.engine.smile:
            raise RuntimeError("openSMILE model not loaded.")
        try:
            df = self.engine.smile.process_file(path)
            return df.iloc[0].to_dict()
        except Exception as exc:
            log.warning(f"[ml] Feature extraction failed: {exc}")
            raise FeatureExtractionError("Extraction failed", attempts=1)

    def _run_sense_voice(self, audio_array: np.ndarray) -> tuple:
        if not self.engine.sense_voice:
            return "NEUTRAL", ""
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = self.engine.sense_voice.generate(
                    input=audio_array,
                    cache={},
                    language="en",
                    use_itn=True,
                    batch_size_s=60,
                )
            if not res or len(res) == 0:
                return "NEUTRAL", ""
                
            text = res[0].get("text", "")
            emo_tags = {"<|HAPPY|>": "HAPPY", "<|SAD|>": "SAD", "<|ANGRY|>": "ANGRY", "<|NEUTRAL|>": "NEUTRAL"}
            detected_emo = "NEUTRAL"
            for tag, clean_emo in emo_tags.items():
                if tag in text:
                    detected_emo = clean_emo
                    text = text.replace(tag, "").strip()
            return detected_emo, text
        except Exception as exc:
            log.warning(f"[ml] SenseVoice inference failed: {exc}")
            return "NEUTRAL", ""

    def _run_valence_arousal_from_array(self, waveform: np.ndarray) -> tuple:
        if not self.engine.va_model or not self.engine.va_processor:
            return 0.0, 0.0, 0.0, 0.0
        try:
            inputs = self.engine.va_processor(
                waveform, sampling_rate=16000, return_tensors="pt", padding=True
            )
            input_values = inputs.input_values.to(self.engine.device)
            with torch.no_grad():
                logits = self.engine.va_model(input_values).logits
            scores = logits[0].cpu().numpy().tolist()
            if len(scores) >= 3:
                return scores[0], scores[1], scores[2], 0.0
            return 0.0, 0.0, 0.0, 0.0
        except Exception as exc:
            log.warning(f"[ml] Wav2Vec2 inference failed: {exc}")
            return 0.0, 0.0, 0.0, 0.0

    def _calculate_stress_score(
        self,
        features: dict,
        emotion: str,
        valence: float,
        arousal: float,
        sleep_debt_hrs: float
    ) -> tuple[int, dict]:
        """Calculates 1-100 stress score based on weighted components."""
        acoustic   = self._acoustic_stress_component(features)
        affective  = self._affective_component(valence, arousal)
        categorical= self._categorical_component(emotion)
        
        # Simplified sleep stress load (no full calendar/history)
        sleep_load = min(1.0, max(0.0, sleep_debt_hrs / 10.0))

        raw = (
            acoustic    * STRESS_WEIGHTS["acoustic"] +
            affective   * STRESS_WEIGHTS["affective"] +
            categorical * STRESS_WEIGHTS["categorical"] +
            sleep_load  * STRESS_WEIGHTS["context"]
        )

        final = int(round(min(1.0, max(0.0, raw)) * 100))
        return final, {
            "acoustic": acoustic,
            "affective": affective,
            "categorical": categorical,
            "context": sleep_load
        }

    def _acoustic_stress_component(self, features: dict) -> float:
        s = 0.0
        for feat, weight in ACOUSTIC_STRESS_FEATS.items():
            val = features.get(feat, 0.0)
            s += min(1.0, max(0.0, val / 100.0)) * weight
        hnr = features.get("HNRdBACF_sma3nz_amean", 0.0)
        h1h2 = features.get("logRelF0-H1-H2_sma3nz_amean", 0.0)
        s += min(1.0, max(0.0, hnr / 20.0)) * HNR_WEIGHT_STRESS
        s += min(1.0, max(0.0, h1h2 / 20.0)) * H1H2_WEIGHT_STRESS
        return min(1.0, max(0.0, s))

    def _affective_component(self, valence: float, arousal: float) -> float:
        # High arousal + low valence = high stress
        return min(1.0, max(0.0, (arousal - valence + 1) / 2))

    def _categorical_component(self, emotion: str) -> float:
        return EMOTION_STRESS_LOAD.get(emotion.upper(), 0.35)
