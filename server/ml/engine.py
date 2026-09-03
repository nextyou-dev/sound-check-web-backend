"""
ml/engine.py — Core ML Model Engine.

Provides the `ModelEngine` singleton class to encapsulate device detection
and loading of all PyTorch and ONNX models (openSMILE, SenseVoice, Wav2Vec2, Silero VAD).
"""
import json
import os
import torch
import opensmile
from typing import Optional

from funasr import AutoModel
from transformers import (
    Wav2Vec2FeatureExtractor,
    AutoModelForAudioClassification,
    Wav2Vec2Config,
)

from config import log, MODELS_DIR

class ModelEngine:
    """
    Singleton wrapper for all ML models.
    Ensures models are loaded exactly once and provides centralized access.
    """
    _instance: Optional["ModelEngine"] = None

    def __init__(self):
        if ModelEngine._instance is not None:
            raise RuntimeError("ModelEngine is a singleton. Use ModelEngine.get_instance().")
        
        self.device = self._detect_device()
        self.smile: Optional[opensmile.Smile] = None
        self.sense_voice: Optional[AutoModel] = None
        self.va_processor: Optional[Wav2Vec2FeatureExtractor] = None
        self.va_model: Optional[AutoModelForAudioClassification] = None
        self.silero_vad_model = None
        self.silero_vad_get_timestamps = None
        
        ModelEngine._instance = self

    @classmethod
    def get_instance(cls) -> "ModelEngine":
        """Returns the singleton instance of ModelEngine."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _detect_device(self) -> torch.device:
        """Detect best available compute backend."""
        if torch.cuda.is_available():
            dev = torch.device("cuda")
            log.info(f"[device] CUDA — {torch.cuda.get_device_name(0)}")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            dev = torch.device("mps")
            log.info("[device] Apple MPS")
        else:
            dev = torch.device("cpu")
            log.info("[device] CPU")
        return dev

    def load_all(self) -> None:
        """Loads all required models into memory."""
        log.info("[startup] Loading openSMILE eGeMAPS...")
        self.smile = opensmile.Smile(
            feature_set=opensmile.FeatureSet.eGeMAPSv02,
            feature_level=opensmile.FeatureLevel.Functionals,
        )

        log.info("[startup] Loading SenseVoice...")
        sv_model_path = os.path.join(MODELS_DIR, "sensevoice")
        has_onnx = os.path.exists(os.path.join(sv_model_path, "model.onnx"))
        
        sv_kwargs = {
            "model": sv_model_path,
            "model_type": "SenseVoiceSmall",
            "trust_remote_code": True,
            "disable_update": True,
            "device": str(self.device),
        }

        if has_onnx:
            log.info("[startup] SenseVoice: Auto-detected ONNX graph, switching backend.")
            sv_kwargs["backend"] = "onnx"
            
        self.sense_voice = AutoModel(**sv_kwargs)

        log.info("[startup] Loading Silero VAD...")
        silero_dir = os.path.join(MODELS_DIR, "silero-vad", "snakers4_silero-vad_master")
        try:
            import sys
            silero_src = os.path.join(silero_dir, "src")
            if silero_src not in sys.path:
                sys.path.insert(0, silero_src)
            
            jit_path = os.path.join(silero_src, "silero_vad", "data", "silero_vad.jit")
            vad_model = torch.jit.load(jit_path, map_location="cpu")
            vad_model.eval()
            
            from silero_vad.utils_vad import get_speech_timestamps
            self.silero_vad_model = vad_model
            self.silero_vad_get_timestamps = get_speech_timestamps
            log.info(f"[startup] Silero VAD loaded from {jit_path}")
        except Exception as exc:
            log.warning(f"[startup] Silero VAD failed to load: {exc} — VAD will be skipped")
            self.silero_vad_model = None
            self.silero_vad_get_timestamps = None

        log.info("[startup] Loading Wav2Vec2 V/A/D model...")
        va_path = os.path.join(MODELS_DIR, "wav2vec2-emotion")

        config_path = os.path.join(va_path, "config.json")
        with open(config_path) as f:
            config_dict = json.load(f)
            
        if config_dict.get("vocab_size") is None:
            config_dict["vocab_size"] = 32
        config_dict["classifier_proj_size"] = 1024

        config = Wav2Vec2Config.from_dict(config_dict)
        self.va_processor = Wav2Vec2FeatureExtractor.from_pretrained(va_path)
        self.va_model = AutoModelForAudioClassification.from_config(config)

        weights_path = os.path.join(va_path, "pytorch_model.bin")
        state_dict = torch.load(weights_path, map_location="cpu", weights_only=True)

        if "classifier.dense.weight" in state_dict:
            state_dict["projector.weight"] = state_dict.pop("classifier.dense.weight")
            state_dict["projector.bias"]   = state_dict.pop("classifier.dense.bias")
            state_dict["classifier.weight"]= state_dict.pop("classifier.out_proj.weight")
            state_dict["classifier.bias"]  = state_dict.pop("classifier.out_proj.bias")

        self.va_model.load_state_dict(state_dict, strict=False)
        self.va_model.to(self.device).eval()

        log.info(f"[startup] All models ready ✓ (device: {self.device})")
