from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv
import subprocess

from .config import YamNetConfig
from .storage import SoundDetection


YAMNET_SOURCE = "yamnet"

YAMNET_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "bird": ("bird", "chirp", "tweet", "squawk", "caw", "hoot", "coo"),
    "frog": ("frog", "croak"),
    "primate": ("monkey", "primate"),
    "vehicle": ("vehicle", "car", "truck", "bus", "motor vehicle", "traffic"),
    "motorcycle": ("motorcycle",),
    "chainsaw": ("chainsaw",),
    "wind": ("wind",),
    "rain": ("rain", "thunderstorm", "waterfall"),
    "human": ("speech", "conversation", "shout", "yell", "human voice", "laughter"),
    "insect": ("insect", "cricket", "cicada"),
}


@dataclass(frozen=True)
class YamNetSummary:
    detections: list[SoundDetection]
    category_scores: dict[str, float]


class YamNetRunner:
    def __init__(self, config: YamNetConfig):
        self.config = config
        self._labels: list[str] | None = None
        self._saved_model = None
        self._tflite_interpreter = None
        self._tflite_input_index: int | None = None
        self._tflite_output_index: int | None = None

    def analyze_audio(self, audio_path: Path) -> YamNetSummary:
        if not self.config.enabled:
            return YamNetSummary([], {})
        model_path = Path(self.config.model_path).expanduser() if self.config.model_path else None
        if model_path is None or not model_path.exists():
            raise RuntimeError("YAMNet model_path is not configured or does not exist")

        labels = self._class_labels()
        waveform = _load_audio_as_16khz_float32(audio_path, self.config.ffmpeg_command)
        if model_path.suffix == ".tflite":
            scores = self._analyze_tflite(model_path, waveform)
        else:
            scores = self._analyze_saved_model(model_path, waveform)
        detections = _scores_to_detections(scores, labels, self.config)
        categories = category_scores(detections)
        return YamNetSummary(detections=detections, category_scores=categories)

    def _class_labels(self) -> list[str]:
        if self._labels is not None:
            return self._labels
        if not self.config.class_map_path:
            raise RuntimeError("YAMNet class_map_path is not configured")
        path = Path(self.config.class_map_path).expanduser()
        if not path.exists():
            raise RuntimeError(f"YAMNet class map does not exist: {path}")
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        labels = []
        for row in sorted(rows, key=lambda item: int(item.get("index") or len(labels))):
            labels.append(row.get("display_name") or row.get("label") or row.get("name") or "")
        self._labels = labels
        return labels

    def _analyze_saved_model(self, model_path: Path, waveform):
        import numpy as np
        import tensorflow as tf

        if self._saved_model is None:
            self._saved_model = tf.saved_model.load(str(model_path))
        scores, _embeddings, _spectrogram = self._saved_model(waveform)
        array = scores.numpy() if hasattr(scores, "numpy") else np.asarray(scores)
        if array.ndim == 1:
            return array
        return array.max(axis=0)

    def _analyze_tflite(self, model_path: Path, waveform):
        import numpy as np

        if self._tflite_interpreter is None:
            try:
                from tflite_runtime.interpreter import Interpreter
            except ImportError:
                from tensorflow.lite import Interpreter

            interpreter = Interpreter(model_path=str(model_path))
            input_details = interpreter.get_input_details()
            waveform = np.asarray(waveform, dtype=np.float32)
            target_shape = list(input_details[0]["shape"])
            if -1 in target_shape or target_shape != list(waveform.shape):
                try:
                    interpreter.resize_tensor_input(input_details[0]["index"], waveform.shape, strict=False)
                except TypeError:
                    interpreter.resize_tensor_input(input_details[0]["index"], waveform.shape)
            interpreter.allocate_tensors()
            output_details = interpreter.get_output_details()
            self._tflite_interpreter = interpreter
            self._tflite_input_index = input_details[0]["index"]
            self._tflite_output_index = output_details[0]["index"]

        interpreter = self._tflite_interpreter
        interpreter.set_tensor(self._tflite_input_index, waveform)
        interpreter.invoke()
        scores = interpreter.get_tensor(self._tflite_output_index)
        if scores.ndim == 1:
            return scores
        return scores.max(axis=0)


class MockYamNetRunner(YamNetRunner):
    def __init__(self) -> None:
        super().__init__(YamNetConfig(enabled=True))

    def analyze_audio(self, audio_path: Path) -> YamNetSummary:
        detections = [
            SoundDetection("Bird vocalization, bird call, bird song", 0.81, source=YAMNET_SOURCE, category="bird"),
            SoundDetection("Frog", 0.32, source=YAMNET_SOURCE, category="frog"),
        ]
        return YamNetSummary(detections=detections, category_scores=category_scores(detections))


def category_scores(detections: list[SoundDetection]) -> dict[str, float]:
    scores = {category: 0.0 for category in YAMNET_CATEGORY_TERMS}
    for detection in detections:
        label = detection.label.casefold()
        for category, terms in YAMNET_CATEGORY_TERMS.items():
            if any(term in label for term in terms):
                scores[category] = max(scores[category], float(detection.score or 0.0))
    return scores


def _scores_to_detections(scores, labels: list[str], config: YamNetConfig) -> list[SoundDetection]:
    import numpy as np

    values = np.asarray(scores, dtype=float)
    top_k = max(1, int(config.top_k))
    min_score = max(0.0, float(config.min_confidence))
    ranked = sorted(enumerate(values.tolist()), key=lambda item: (-item[1], item[0]))
    detections: list[SoundDetection] = []
    for index, score in ranked:
        if score < min_score:
            continue
        label = labels[index] if index < len(labels) and labels[index] else f"class_{index}"
        detections.append(SoundDetection(label, score, source=YAMNET_SOURCE, category=_category_for_label(label)))
        if len(detections) >= top_k:
            break
    return detections


def _category_for_label(label: str) -> str | None:
    lower = label.casefold()
    for category, terms in YAMNET_CATEGORY_TERMS.items():
        if any(term in lower for term in terms):
            return category
    return None


def _load_audio_as_16khz_float32(audio_path: Path, ffmpeg_command: str):
    import numpy as np

    proc = subprocess.run(
        [
            ffmpeg_command,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(audio_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "-",
        ],
        check=False,
        capture_output=True,
        timeout=300,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr.decode(errors="ignore") or f"ffmpeg exited {proc.returncode}").strip())
    waveform = np.frombuffer(proc.stdout, dtype=np.float32)
    if waveform.size == 0:
        raise RuntimeError(f"YAMNet audio decode produced no samples: {audio_path}")
    return waveform
