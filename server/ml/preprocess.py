"""
ml/preprocess.py — Object-Oriented RNNoise-based audio preprocessing.
"""
import os
import tempfile
import time
import numpy as np
import soundfile as sf
from pyrnnoise import RNNoise

from config import log


class AudioPreprocessor:
    """
    Handles noise suppression and loudness normalization of raw audio
    using RNNoise before ML feature extraction.
    """
    def __init__(self, sample_rate: int = 48000, target_dbfs: float = -23.0, min_snr_db: float = 8.0):
        self.sample_rate = sample_rate
        self.target_dbfs = target_dbfs
        self.min_snr_db = min_snr_db

    def process(self, audio_path: str) -> str:
        """
        Full RNNoise preprocessing pipeline.
        Returns the path to the cleaned temp WAV file.
        The caller is responsible for deleting the temp file when done.
        """
        t0 = time.perf_counter()

        raw_audio, sr = self._load_and_resample(audio_path)
        denoised_audio, mean_speech_prob = self._denoise_audio(raw_audio)
        normalized_audio = self._normalize_loudness(denoised_audio)
        snr_db = self._estimate_snr_db(raw_audio, denoised_audio)
        
        low_confidence = (snr_db < self.min_snr_db) or (mean_speech_prob < 0.5)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if low_confidence:
            log.warning(
                f"[rnnoise] Low confidence audio: SNR={snr_db:.1f}dB, "
                f"speech_prob={mean_speech_prob:.3f} — proceeding anyway"
            )

        log.info(
            f"[rnnoise] Preprocessed {len(raw_audio)/sr:.1f}s audio in {elapsed_ms:.0f}ms | "
            f"SNR={snr_db:.1f}dB, speech_prob={mean_speech_prob:.3f}"
        )

        fd, cleaned_path = tempfile.mkstemp(suffix="_rnnoise.wav")
        os.close(fd)
        sf.write(cleaned_path, normalized_audio, sr, subtype="PCM_16")

        return cleaned_path

    def _load_and_resample(self, audio_path: str) -> tuple[np.ndarray, int]:
        """Load input audio, force mono, resample to target rate."""
        import librosa
        audio, sr = librosa.load(audio_path, sr=None, mono=True)
        if sr != self.sample_rate:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=self.sample_rate)
        return audio.astype(np.float32), self.sample_rate

    def _denoise_audio(self, audio_f32: np.ndarray) -> tuple[np.ndarray, float]:
        """Run RNNoise over the full signal."""
        denoiser = RNNoise(sample_rate=self.sample_rate)
        denoised_chunks = []
        speech_probs = []
        
        for speech_prob, denoised_frame in denoiser.process_chunk(audio_f32, last=True):
            denoised_chunks.append(denoised_frame)
            speech_probs.append(np.mean(speech_prob))

        if not denoised_chunks:
            return audio_f32, 0.0

        denoised_f32 = np.concatenate(denoised_chunks, axis=0).flatten()
        mean_speech_prob = float(np.mean(speech_probs)) if speech_probs else 0.0
        return denoised_f32, mean_speech_prob

    def _normalize_loudness(self, audio: np.ndarray) -> np.ndarray:
        """RMS-based loudness normalization to fixed dBFS target."""
        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 1e-9:
            return audio
        current_dbfs = 20 * np.log10(rms)
        gain_db = self.target_dbfs - current_dbfs
        gain_linear = 10 ** (gain_db / 20)
        normalized = audio * gain_linear
        return np.clip(normalized, -1.0, 1.0)

    def _estimate_snr_db(self, original: np.ndarray, denoised: np.ndarray) -> float:
        """Rough SNR proxy: treat (original − denoised) as estimated noise floor."""
        min_len = min(len(original), len(denoised))
        orig_matched = original[:min_len]
        denoised_matched = denoised[:min_len]

        noise_estimate = orig_matched - denoised_matched
        signal_power = np.mean(denoised_matched ** 2)
        noise_power = np.mean(noise_estimate ** 2)

        if noise_power < 1e-12:
            return 99.0

        return float(10 * np.log10(signal_power / noise_power))
