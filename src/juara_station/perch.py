from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import subprocess
import sys

from .config import PerchConfig
from .storage import SoundDetection


PERCH_SOURCE = "perch"

PERCH_CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "bird": ("bird", "aves", "macaw", "parrot", "owl", "ibis", "finch", "hornero", "kiskadee"),
    "frog": ("frog", "toad", "amphibian"),
    "mammal": ("mammal", "monkey", "primate", "bat"),
    "insect": ("insect", "cricket", "cicada", "katydid"),
    "vehicle": ("vehicle", "car", "truck", "motorcycle", "engine"),
    "rain": ("rain", "thunder", "storm"),
    "wind": ("wind",),
    "human": ("human", "speech", "voice"),
}


@dataclass(frozen=True)
class PerchSummary:
    detections: list[SoundDetection]
    category_scores: dict[str, float]


class PerchRunner:
    def __init__(self, config: PerchConfig):
        self.config = config

    def analyze_audio(self, audio_path: Path) -> PerchSummary:
        if not self.config.enabled:
            return PerchSummary([], {})
        model_path = Path(self.config.model_path).expanduser() if self.config.model_path else None
        if model_path is None or not model_path.exists():
            raise RuntimeError("Perch model_path is not configured or does not exist")
        label_path = Path(self.config.label_path).expanduser() if self.config.label_path else None
        if label_path is None or not label_path.exists():
            raise RuntimeError("Perch label_path is not configured or does not exist")

        command = [
            str(Path(self.config.python or sys.executable).expanduser()),
            "-m",
            "juara_station.perch_worker",
            "--audio",
            str(audio_path),
            "--model",
            str(model_path),
            "--labels",
            str(label_path),
            "--ffmpeg",
            self.config.ffmpeg_command,
            "--min-confidence",
            str(self.config.min_confidence),
            "--top-k",
            str(self.config.top_k),
            "--sample-rate",
            str(self.config.sample_rate),
            "--window-seconds",
            str(self.config.window_seconds),
            "--max-audio-seconds",
            str(self.config.max_audio_seconds),
        ]
        env = os.environ.copy()
        source_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = source_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(30, int(self.config.subprocess_timeout_seconds)),
            env=env,
        )
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or f"Perch subprocess exited {proc.returncode}").strip()
            raise RuntimeError(message)
        payload = json.loads(proc.stdout)
        detections = [
            SoundDetection(item["label"], float(item["score"]), source=PERCH_SOURCE, category=item.get("category"))
            for item in payload.get("detections", [])
        ]
        return PerchSummary(detections=detections, category_scores=category_scores(detections))


class MockPerchRunner(PerchRunner):
    def __init__(self) -> None:
        super().__init__(PerchConfig(enabled=True))

    def analyze_audio(self, audio_path: Path) -> PerchSummary:
        detections = [
            SoundDetection("Hyacinth macaw", 0.72, source=PERCH_SOURCE, category="bird"),
            SoundDetection("Blue-and-yellow macaw", 0.22, source=PERCH_SOURCE, category="bird"),
            SoundDetection("frog", 0.18, source=PERCH_SOURCE, category="frog"),
        ]
        return PerchSummary(detections=detections, category_scores=category_scores(detections))


def category_scores(detections: list[SoundDetection]) -> dict[str, float]:
    scores = {category: 0.0 for category in PERCH_CATEGORY_TERMS}
    for detection in detections:
        label = detection.label.casefold()
        for category, terms in PERCH_CATEGORY_TERMS.items():
            if detection.category == category or any(term in label for term in terms):
                scores[category] = max(scores[category], float(detection.score or 0.0))
    return scores
