#!/usr/bin/env python3
"""Create an honest, project-relative narration alignment JSON artifact.

The standard-library ``python`` backend validates WAV data and accepts
manually measured phrase timestamps.  Without measured timestamps it emits a
single coarse full-audio segment and records that no internal boundary was
measured.  The ``asr`` backend consumes an explicit ASR JSON artifact and
maps its measured utterance/word intervals back to the original script; it
never treats ASR text as the original script.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unicodedata
import wave


class AlignmentError(Exception):
    """An alignment input cannot be mapped without inventing timing."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def project_path(project_root: Path, value: str, description: str, *, must_exist: bool = False) -> Path:
    root = project_root.expanduser().resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AlignmentError(f"{description} must be inside --project-root") from exc
    if must_exist and not candidate.is_file():
        raise AlignmentError(f"{description} does not exist: {value}")
    return candidate


def relative_project_path(project_root: Path, path: Path) -> str:
    return path.resolve().relative_to(project_root.expanduser().resolve()).as_posix()


def read_json(path: Path, description: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AlignmentError(f"{description} does not exist") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlignmentError(f"could not read {description} as JSON") from exc


def read_script(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AlignmentError("could not read --text as UTF-8") from exc
    if not text:
        raise AlignmentError("the narration text is empty")
    return text


def inspect_wav(path: Path) -> dict:
    """Fully read PCM frames so timing is based on verified audio, not a guess."""

    try:
        with wave.open(str(path), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            if wav_file.getcomptype() != "NONE":
                raise AlignmentError("audio must be an uncompressed PCM WAV")
            if channels <= 0 or sample_width <= 0 or sample_rate <= 0 or frame_count <= 0:
                raise AlignmentError("audio WAV has invalid or empty parameters")
            frames = wav_file.readframes(frame_count)
            expected = channels * sample_width * frame_count
            if len(frames) != expected:
                raise AlignmentError("audio WAV could not be fully decoded")
    except AlignmentError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise AlignmentError("audio is not a readable WAV file") from exc
    return {
        "channels": channels,
        "sample_width": sample_width,
        "sample_rate": sample_rate,
        "frames": frame_count,
        "duration_ms": (frame_count * 1000 + sample_rate // 2) // sample_rate,
        "sha256": sha256_file(path),
    }


def normalize_text(value: str) -> str:
    """Normalize only for locating a phrase; never replace stored source text."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(
        char
        for char in normalized
        if not unicodedata.category(char).startswith(("P", "S", "Z"))
        and not char.isspace()
    )


def _normalized_with_indices(value: str) -> tuple[str, list[int]]:
    output = []
    indices = []
    for index, char in enumerate(value):
        normalized = normalize_text(char)
        for item in normalized:
            output.append(item)
            indices.append(index)
    return "".join(output), indices


def locate_phrase(source: str, phrase: str, source_cursor: int) -> tuple[int, int, bool]:
    """Locate a timestamp phrase after the prior phrase in source order."""

    if not isinstance(phrase, str) or not phrase.strip():
        raise AlignmentError("timestamp entry text must be non-empty")
    direct = source.find(phrase, source_cursor)
    if direct >= 0:
        return direct, direct + len(phrase), False

    source_normalized, source_indices = _normalized_with_indices(source)
    phrase_normalized = normalize_text(phrase)
    if not phrase_normalized:
        raise AlignmentError("timestamp entry text contains no matchable characters")
    normalized_cursor = 0
    for index, original_index in enumerate(source_indices):
        if original_index >= source_cursor:
            normalized_cursor = index
            break
    else:
        normalized_cursor = len(source_normalized)
    found = source_normalized.find(phrase_normalized, normalized_cursor)
    if found < 0:
        raise AlignmentError("timestamp text cannot be mapped in source order")
    end_index = found + len(phrase_normalized) - 1
    return source_indices[found], source_indices[end_index] + 1, True


def _number(value, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AlignmentError(f"timestamp field {field} must be numeric")
    return float(value)


def parse_time_pair(entry: dict, *, asr: bool = False) -> tuple[int, int]:
    """Parse explicit milliseconds first; ASR start/end values are seconds."""

    if "start_ms" in entry and "end_ms" in entry:
        start = _number(entry["start_ms"], "start_ms")
        end = _number(entry["end_ms"], "end_ms")
    elif "begin_ms" in entry and "end_ms" in entry:
        start = _number(entry["begin_ms"], "begin_ms")
        end = _number(entry["end_ms"], "end_ms")
    elif "begin_time" in entry and "end_time" in entry:
        start = _number(entry["begin_time"], "begin_time")
        end = _number(entry["end_time"], "end_time")
    elif "start_time" in entry and "end_time" in entry:
        start = _number(entry["start_time"], "start_time")
        end = _number(entry["end_time"], "end_time")
    elif "start" in entry and "end" in entry:
        start = _number(entry["start"], "start") * 1000
        end = _number(entry["end"], "end") * 1000
    elif "begin" in entry and "end" in entry:
        start = _number(entry["begin"], "begin") * 1000
        end = _number(entry["end"], "end") * 1000
    else:
        raise AlignmentError("timestamp entry needs start_ms/end_ms or start/end")
    start_ms = int(round(start))
    end_ms = int(round(end))
    if start_ms < 0 or end_ms <= start_ms:
        raise AlignmentError("timestamp entries must have start_ms < end_ms and non-negative times")
    return start_ms, end_ms


def _entry_text(entry: dict) -> str:
    for key in ("text", "word", "transcript"):
        if isinstance(entry.get(key), str):
            return entry[key]
    raise AlignmentError("timestamp entry needs text")


def extract_entries(data, *, asr: bool) -> list[dict]:
    """Accept a small stable shape plus common ASR utterance containers."""

    if isinstance(data, list):
        raw_entries = data
    elif isinstance(data, dict) and isinstance(data.get("segments"), list):
        raw_entries = data["segments"]
    elif asr and isinstance(data, dict):
        result = data.get("result") if isinstance(data.get("result"), dict) else data
        if isinstance(result.get("utterances"), list):
            raw_entries = result["utterances"]
        elif isinstance(result.get("segments"), list):
            raw_entries = result["segments"]
        elif isinstance(result.get("words"), list):
            raw_entries = result["words"]
        else:
            raise AlignmentError("ASR JSON has no segments, utterances, or words list")
    else:
        raise AlignmentError("timestamps JSON must be a list or an object with segments")

    entries = []
    previous_end = -1
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            raise AlignmentError(f"timestamp entry {index + 1} must be an object")
        text = _entry_text(raw_entry)
        start_ms, end_ms = parse_time_pair(raw_entry, asr=asr)
        if start_ms < previous_end:
            raise AlignmentError("timestamp entries overlap or are out of time order")
        previous_end = end_ms
        entries.append({"text": text, "start_ms": start_ms, "end_ms": end_ms, "index": index})
    if not entries:
        raise AlignmentError("timestamp JSON contains no entries")
    return entries


def _issue(code: str, message: str, **fields) -> dict:
    result = {"code": code, "message": message}
    result.update(fields)
    return result


def _is_format_only(value: str) -> bool:
    """Return true for spaces/punctuation/symbols with no spoken content."""

    return not normalize_text(value)


def _append_to_last_timed_segment(segments: list[dict], value: str) -> bool:
    for segment in reversed(segments):
        if segment.get("start_ms") is not None:
            segment["text"] += value
            return True
    return False


def map_measured_entries(source: str, entries: list[dict], duration_ms: int, *, method: str) -> tuple[list[dict], list[dict]]:
    """Map measured phrases to exact source slices while preserving gaps."""

    segments = []
    issues = []
    source_cursor = 0
    leading_format_gap = ""
    for entry in entries:
        start_ms = entry["start_ms"]
        end_ms = entry["end_ms"]
        if end_ms > duration_ms:
            raise AlignmentError("timestamp exceeds decoded audio duration")
        try:
            start, end, normalized_match = locate_phrase(source, entry["text"], source_cursor)
        except AlignmentError:
            if method.startswith("asr-"):
                # An ASR word can be genuinely different from the final
                # script. Keep the source unmapped and report the measured
                # ASR interval rather than assigning it to a guessed phrase.
                issues.append(
                    _issue(
                        "ASR_WORD_DIFFERENCE",
                        "ASR text could not be mapped to the original script",
                        entry_index=entry["index"],
                        asr_start_ms=start_ms,
                        asr_end_ms=end_ms,
                    )
                )
                continue
            raise
        if start < source_cursor:
            raise AlignmentError("timestamp text is out of source order")
        if start > source_cursor:
            gap = source[source_cursor:start]
            if _is_format_only(gap) and _append_to_last_timed_segment(segments, gap):
                pass
            elif _is_format_only(gap):
                leading_format_gap += gap
            else:
                segments.append({"text": gap, "start_ms": None, "end_ms": None})
                issues.append(
                    _issue(
                        "UNALIGNED_SOURCE_GAP",
                        "source text between measured phrases has no measured timing",
                        source_start=source_cursor,
                        source_end=start,
                    )
                )
        source_slice = leading_format_gap + source[start:end]
        leading_format_gap = ""
        segments.append({"text": source_slice, "start_ms": start_ms, "end_ms": end_ms})
        if normalized_match or source_slice != entry["text"]:
            code = "TEXT_FORMAT_DIFFERENCE" if normalize_text(source_slice) == normalize_text(entry["text"]) else "TEXT_CONTENT_DIFFERENCE"
            issues.append(
                _issue(
                    code,
                    "measured text differs only in punctuation, spacing, case, or Unicode normalization"
                    if code == "TEXT_FORMAT_DIFFERENCE"
                    else "measured text differs in spoken content",
                    source_start=start,
                    source_end=end,
                    entry_index=entry["index"],
                )
            )
        source_cursor = end
    if source_cursor < len(source):
        tail = source[source_cursor:]
        if _is_format_only(tail) and _append_to_last_timed_segment(segments, tail):
            pass
        else:
            segments.append({"text": tail, "start_ms": None, "end_ms": None})
            issues.append(
                _issue(
                    "UNALIGNED_SOURCE_TAIL",
                    "source text after the final measured phrase has no measured timing",
                    source_start=source_cursor,
                    source_end=len(source),
                )
            )
    return segments, issues


def align_python(source: str, duration_ms: int, timestamps_path: Path | None = None) -> tuple[str, list[dict], list[dict]]:
    if timestamps_path is None:
        return (
            "python-coarse",
            [{"text": source, "start_ms": 0, "end_ms": duration_ms}],
            [
                _issue(
                    "NO_INTERNAL_BOUNDARIES",
                    "no measured phrase timestamps were supplied; the full audio span is coarse and not word timing",
                )
            ],
        )
    entries = extract_entries(read_json(timestamps_path, "--timestamps"), asr=False)
    segments, issues = map_measured_entries(source, entries, duration_ms, method="known-text-manual")
    return "known-text-manual", segments, issues


def align_asr(source: str, duration_ms: int, asr_path: Path) -> tuple[str, list[dict], list[dict]]:
    entries = extract_entries(read_json(asr_path, "--asr-json"), asr=True)
    segments, issues = map_measured_entries(source, entries, duration_ms, method="asr-transcript-mapped")
    return "asr-transcript-mapped", segments, issues


def validate_segments(source: str, segments: list[dict], duration_ms: int) -> list[dict]:
    if not segments:
        raise AlignmentError("alignment produced no segments")
    if "".join(segment.get("text", "") for segment in segments) != source:
        raise AlignmentError("alignment segments do not preserve the complete original text")
    previous_end = -1
    normalized = []
    for index, segment in enumerate(segments, start=1):
        text = segment.get("text")
        start = segment.get("start_ms")
        end = segment.get("end_ms")
        if not isinstance(text, str) or not text:
            raise AlignmentError(f"segment {index} has empty or invalid text")
        if (start is None) != (end is None):
            raise AlignmentError(f"segment {index} must have both times or neither")
        if start is not None:
            if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
                raise AlignmentError(f"segment {index} times must be integer milliseconds")
            if start < 0 or end <= start or end > duration_ms:
                raise AlignmentError(f"segment {index} is outside decoded audio")
            if previous_end >= 0 and start < previous_end:
                raise AlignmentError(f"segment {index} overlaps an earlier measured segment")
            previous_end = end
        normalized.append({"id": f"seg-{index:03d}", "text": text, "start_ms": start, "end_ms": end})
    return normalized


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, mode="w", encoding="utf-8", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def run_alignment(
    *,
    project_root: Path,
    text_path: str,
    audio_path: str,
    output_path: str,
    backend: str = "python",
    timestamps_path: str | None = None,
    asr_json_path: str | None = None,
) -> dict:
    root = project_root.expanduser().resolve()
    if not root.is_dir():
        raise AlignmentError("--project-root must be an existing directory")
    text_file = project_path(root, text_path, "--text", must_exist=True)
    audio_file = project_path(root, audio_path, "--audio", must_exist=True)
    output_file = project_path(root, output_path, "--output")
    if output_file.resolve() == audio_file.resolve():
        raise AlignmentError("--output must differ from --audio")
    source = read_script(text_file)
    audio_info = inspect_wav(audio_file)
    timestamps_file = project_path(root, timestamps_path, "--timestamps", must_exist=True) if timestamps_path else None
    asr_file = project_path(root, asr_json_path, "--asr-json", must_exist=True) if asr_json_path else None
    if backend == "python":
        if asr_file:
            raise AlignmentError("--asr-json requires --backend asr")
        method, segments, issues = align_python(source, audio_info["duration_ms"], timestamps_file)
    elif backend == "asr":
        if not asr_file:
            raise AlignmentError("--backend asr requires --asr-json")
        if timestamps_file:
            raise AlignmentError("use either --timestamps or --asr-json, not both")
        method, segments, issues = align_asr(source, audio_info["duration_ms"], asr_file)
    else:
        raise AlignmentError("--backend must be python or asr")
    output_segments = validate_segments(source, segments, audio_info["duration_ms"])
    result = {
        "version": 1,
        "audio_path": relative_project_path(root, audio_file),
        "audio_sha256": audio_info["sha256"],
        "text_sha256": sha256_text(source),
        "method": method,
        "reviewed": False,
        "segments": output_segments,
        "issues": issues,
    }
    atomic_write_json(output_file, result)
    return {
        "output_path": relative_project_path(root, output_file),
        "audio_path": result["audio_path"],
        "audio_sha256": result["audio_sha256"],
        "text_sha256": result["text_sha256"],
        "method": method,
        "segment_count": len(output_segments),
        "issue_count": len(issues),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Align narration without fabricating word timing")
    subparsers = parser.add_subparsers(dest="command", required=True)
    align = subparsers.add_parser("align", help="write alignment.json")
    align.add_argument("--project-root", required=True)
    align.add_argument("--text", required=True)
    align.add_argument("--audio", required=True)
    align.add_argument("--output", required=True)
    align.add_argument("--backend", choices=("python", "asr"), default="python")
    align.add_argument("--timestamps", help="JSON list of manually measured phrase intervals in milliseconds")
    align.add_argument("--asr-json", help="JSON ASR artifact; use with --backend asr")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "align":
            result = run_alignment(
                project_root=Path(args.project_root),
                text_path=args.text,
                audio_path=args.audio,
                output_path=args.output,
                backend=args.backend,
                timestamps_path=args.timestamps,
                asr_json_path=args.asr_json,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except AlignmentError as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
