from __future__ import annotations

from pathlib import Path
import argparse
import csv
import json
import subprocess
import sys

from .perch import PERCH_CATEGORY_TERMS
from .taxonomy import resolve_taxon


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Perch/Perch-v2 inference on an audio file.")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--min-confidence", type=float, default=0.15)
    parser.add_argument("--top-k", type=int, default=8)
    parser.add_argument("--sample-rate", type=int, default=32000)
    parser.add_argument("--window-seconds", type=float, default=5.0)
    parser.add_argument("--max-audio-seconds", type=int, default=300)
    args = parser.parse_args(argv)

    labels = _load_labels(Path(args.labels))
    waveform = _load_audio(
        Path(args.audio),
        args.ffmpeg,
        sample_rate=max(1, args.sample_rate),
        max_audio_seconds=args.max_audio_seconds,
    )
    scores = _run_model(
        Path(args.model),
        waveform,
        label_count=len(labels),
        sample_rate=max(1, args.sample_rate),
        window_seconds=max(0.1, args.window_seconds),
    )
    detections = _scores_to_detections(scores, labels, args.min_confidence, args.top_k)
    print(json.dumps({"detections": detections}, separators=(",", ":")))
    return 0


def _load_labels(path: Path) -> list[str]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        labels = []
        for row in rows:
            labels.append(
                row.get("display_name")
                or row.get("common_name")
                or row.get("label")
                or row.get("name")
                or _join_scientific_common(row.get("scientific_name"), row.get("common"))
                or _join_scientific_common(row.get("scientific_name"), row.get("common_name"))
                or ""
            )
        return labels
    return [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]


def _join_scientific_common(scientific: str | None, common: str | None) -> str:
    scientific = (scientific or "").strip()
    common = (common or "").strip()
    if scientific and common:
        return f"{scientific}_{common}"
    return scientific or common


def _load_audio(path: Path, ffmpeg: str, sample_rate: int, max_audio_seconds: int):
    import numpy as np

    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
    ]
    if max_audio_seconds and max_audio_seconds > 0:
        command.extend(["-t", str(max_audio_seconds)])
    command.extend(["-f", "f32le", "-"])
    proc = subprocess.run(command, check=False, capture_output=True, timeout=max(300, max_audio_seconds + 120))
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr.decode(errors="ignore") or f"ffmpeg exited {proc.returncode}").strip())
    waveform = np.frombuffer(proc.stdout, dtype=np.float32)
    if waveform.size == 0:
        raise RuntimeError(f"Perch audio decode produced no samples: {path}")
    return waveform


def _run_model(model_path: Path, waveform, label_count: int, sample_rate: int, window_seconds: float):
    if model_path.suffix.lower() == ".tflite":
        return _run_tflite_model(model_path, waveform, label_count, sample_rate, window_seconds)
    return _run_saved_model(model_path, waveform, label_count, sample_rate, window_seconds)


def _run_tflite_model(model_path: Path, waveform, label_count: int, sample_rate: int, window_seconds: float):
    import numpy as np

    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            from tensorflow.lite import Interpreter

    interpreter = Interpreter(model_path=str(model_path), num_threads=1)
    input_details = interpreter.get_input_details()
    input_detail = input_details[0]
    expected_samples = _expected_samples(input_detail, sample_rate, window_seconds)
    input_shape = [int(value) for value in input_detail.get("shape")]
    if not expected_samples:
        expected_samples = int(sample_rate * window_seconds)
        _resize_input(interpreter, input_detail["index"], input_shape, expected_samples)
    interpreter.allocate_tensors()
    output_details = interpreter.get_output_details()
    output_index = _score_output_index(output_details, label_count)

    frame_scores = []
    input_details = interpreter.get_input_details()
    input_shape = [int(value) for value in input_details[0].get("shape")]
    for frame in _fixed_frames(waveform, expected_samples):
        tensor = _reshape_frame(frame, input_shape)
        interpreter.set_tensor(input_details[0]["index"], tensor)
        interpreter.invoke()
        frame_scores.append(interpreter.get_tensor(output_index))
    return _collapse_scores(frame_scores, label_count)


def _run_saved_model(model_path: Path, waveform, label_count: int, sample_rate: int, window_seconds: float):
    import numpy as np
    import tensorflow as tf

    model = tf.saved_model.load(str(model_path))
    signature = model.signatures.get("serving_default") if hasattr(model, "signatures") else None
    expected_samples = int(sample_rate * window_seconds)
    frame_scores = []
    for frame in _fixed_frames(waveform, expected_samples):
        tensor = tf.convert_to_tensor(frame, dtype=tf.float32)
        if signature is not None:
            kwargs = _signature_kwargs(signature, tensor)
            result = signature(**kwargs)
        else:
            result = model(tensor)
        frame_scores.append(_extract_score_array(result, label_count))
    return _collapse_scores(frame_scores, label_count)


def _signature_kwargs(signature, tensor):
    input_items = list(signature.structured_input_signature[1].items())
    if not input_items:
        return {"inputs": tensor}
    name, spec = input_items[0]
    shape = list(spec.shape) if getattr(spec, "shape", None) is not None else []
    if len(shape) == 2:
        tensor = tensor[None, :]
    return {name: tensor}


def _extract_score_array(result, label_count: int):
    import numpy as np

    if isinstance(result, dict):
        arrays = [np.asarray(value) for value in result.values()]
    elif isinstance(result, (tuple, list)):
        arrays = [np.asarray(value) for value in result]
    else:
        arrays = [np.asarray(result)]
    return _select_score_array(arrays, label_count)


def _score_output_index(output_details, label_count: int) -> int:
    best = output_details[0]
    best_size = 0
    for detail in output_details:
        shape = [int(value) for value in detail.get("shape", [])]
        size = shape[-1] if shape else 0
        if label_count and size == label_count:
            return detail["index"]
        if size > best_size:
            best = detail
            best_size = size
    return best["index"]


def _select_score_array(arrays, label_count: int):
    best = arrays[0]
    best_size = 0
    for array in arrays:
        size = int(array.shape[-1]) if array.shape else 0
        if label_count and size == label_count:
            return array
        if size > best_size:
            best = array
            best_size = size
    return best


def _expected_samples(input_detail, sample_rate: int, window_seconds: float) -> int | None:
    shape = [int(value) for value in input_detail.get("shape", [])]
    if len(shape) == 1 and shape[0] > 0:
        return shape[0]
    if len(shape) == 2 and shape[1] > 0:
        return shape[1]
    return int(sample_rate * window_seconds)


def _resize_input(interpreter, input_index: int, input_shape: list[int], expected_samples: int) -> None:
    if len(input_shape) == 2:
        shape = [1, expected_samples]
    else:
        shape = [expected_samples]
    try:
        interpreter.resize_tensor_input(input_index, shape, strict=False)
    except TypeError:
        interpreter.resize_tensor_input(input_index, shape)


def _fixed_frames(waveform, expected_samples: int):
    import numpy as np

    waveform = np.asarray(waveform, dtype=np.float32)
    if waveform.size < expected_samples:
        yield np.pad(waveform, (0, expected_samples - waveform.size))
        return
    for start in range(0, waveform.size - expected_samples + 1, expected_samples):
        yield waveform[start : start + expected_samples]
    if waveform.size % expected_samples:
        yield waveform[-expected_samples:]


def _reshape_frame(frame, input_shape):
    if len(input_shape) == 2:
        return frame.reshape((1, frame.size))
    return frame


def _collapse_scores(frame_scores, label_count: int):
    import numpy as np

    scores = np.asarray([_select_score_array([score], label_count) for score in frame_scores])
    if scores.ndim == 1:
        return scores
    return scores.max(axis=tuple(range(scores.ndim - 1)))


def _scores_to_detections(scores, labels: list[str], min_confidence: float, top_k: int) -> list[dict]:
    import numpy as np

    values = np.asarray(scores, dtype=float).reshape(-1)
    ranked = sorted(enumerate(values.tolist()), key=lambda item: (-item[1], item[0]))
    detections = []
    for index, score in ranked:
        if score < min_confidence:
            continue
        label = labels[index] if index < len(labels) and labels[index] else f"class_{index}"
        detections.append({"label": label, "score": score, "category": _category_for_label(label)})
        if len(detections) >= max(1, top_k):
            break
    return detections


def _category_for_label(label: str) -> str | None:
    lower = label.casefold()
    taxon = resolve_taxon(_common_part(label))
    if taxon.family or taxon.order or taxon.genus:
        return "bird"
    for category, terms in PERCH_CATEGORY_TERMS.items():
        if any(term in lower for term in terms):
            return category
    return None


def _common_part(label: str) -> str:
    if "_" in label:
        return label.split("_", 1)[1].strip()
    return label.strip()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
