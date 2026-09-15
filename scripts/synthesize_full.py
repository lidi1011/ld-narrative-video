#!/usr/bin/env python3
"""Synthesize one complete narration with the configured Doubao endpoint.

The module intentionally uses only Python's standard library.  It does not
look for credentials or split a script: a credential source and the request
limit must be supplied by the project configuration.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import stat
import tempfile
import uuid
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import wave


class TTSUserError(Exception):
    """An expected, safe-to-display user/configuration error."""


class TTSRequestError(TTSUserError):
    """A provider request failed without exposing response contents."""


class NoRedirectError(TTSRequestError):
    """The endpoint attempted to redirect the request."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise NoRedirectError("provider redirect refused; use the configured endpoint directly")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def project_path(project_root: Path, value: str, description: str, *, must_exist: bool = False) -> Path:
    """Resolve a project-relative path and reject paths outside the project."""

    root = project_root.expanduser().resolve()
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise TTSUserError(f"{description} must be inside --project-root") from exc
    if must_exist and not candidate.is_file():
        raise TTSUserError(f"{description} does not exist: {value}")
    return candidate


def relative_project_path(project_root: Path, path: Path) -> str:
    return path.resolve().relative_to(project_root.expanduser().resolve()).as_posix()


def load_json(path: Path, description: str) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError as exc:
        raise TTSUserError(f"{description} does not exist") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TTSUserError(f"could not read {description} as JSON") from exc
    if not isinstance(value, dict):
        raise TTSUserError(f"{description} must contain a JSON object")
    return value


def load_text(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise TTSUserError("could not read the narration text as UTF-8") from exc
    if not text.strip():
        raise TTSUserError("narration text is empty")
    return text


def _positive_int(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TTSUserError(f"config field {field} must be a positive integer")
    return value


def validate_config(raw: dict) -> dict:
    """Validate the non-secret TTS project configuration."""

    if raw.get("provider") != "doubao":
        raise TTSUserError("config provider must be 'doubao'")
    endpoint = raw.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise TTSUserError("config endpoint is required")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise TTSUserError("config endpoint must be an HTTPS URL without query or fragment")
    if parsed.scheme == "http":
        host = (parsed.hostname or "").lower()
        if not raw.get("allow_insecure_localhost") or host not in {"127.0.0.1", "localhost", "::1"}:
            raise TTSUserError("HTTP is allowed only for an explicitly enabled loopback mock endpoint")

    max_text_chars = _positive_int(raw["max_text_chars"], "max_text_chars") if "max_text_chars" in raw else None
    max_text_bytes = _positive_int(raw["max_text_bytes"], "max_text_bytes") if "max_text_bytes" in raw else None
    if max_text_chars is None and max_text_bytes is None:
        raise TTSUserError("config requires max_text_chars or max_text_bytes")
    timeout_seconds = raw.get("timeout_seconds", 60)
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or timeout_seconds <= 0:
        raise TTSUserError("config field timeout_seconds must be positive")
    sample_rate = _positive_int(raw.get("sample_rate", 24000), "sample_rate")
    audio_format = raw.get("audio_format", "pcm")
    if audio_format not in {"wav", "pcm", "mp3", "ogg_opus"}:
        raise TTSUserError("config audio_format must be wav, pcm, mp3, or ogg_opus")
    output_container = raw.get("output_container", "wav")
    if output_container != "wav":
        raise TTSUserError("this tool writes and validates a WAV output container")
    pcm_channels = _positive_int(raw.get("pcm_channels", 1), "pcm_channels")
    pcm_sample_width = _positive_int(raw.get("pcm_sample_width", 2), "pcm_sample_width")
    speaker = raw.get("speaker")
    if not isinstance(speaker, str) or not speaker.strip():
        raise TTSUserError("config speaker is required")
    uid = raw.get("uid", "narrative-video")
    if not isinstance(uid, str) or not uid:
        raise TTSUserError("config uid must be a non-empty string")

    auth_mode = raw.get("auth_mode", "bearer_semicolon")
    allowed_auth = {"bearer_semicolon", "bearer_space", "api_key", "legacy_headers"}
    if auth_mode not in allowed_auth:
        raise TTSUserError(f"config auth_mode must be one of: {', '.join(sorted(allowed_auth))}")
    credential_file = raw.get("credentials_file")
    if credential_file is not None and (not isinstance(credential_file, str) or not credential_file):
        raise TTSUserError("config credentials_file must be an explicit path")
    credential_file_env = raw.get("credentials_file_env")
    if credential_file_env is not None and (not isinstance(credential_file_env, str) or not credential_file_env):
        raise TTSUserError("config credentials_file_env must be a non-empty environment variable name")
    token_env = raw.get("access_token_env", raw.get("token_env"))
    if token_env is None and (credential_file or credential_file_env):
        token_env = ""
    if not isinstance(token_env, str) or (not token_env and not (credential_file or credential_file_env)):
        raise TTSUserError("config access_token_env or an explicit credentials_file is required; do not put a token in this file")
    appid_env = raw.get("appid_env")
    if appid_env is not None and (not isinstance(appid_env, str) or not appid_env):
        raise TTSUserError("config appid_env must be a non-empty environment variable name")
    credential_key = raw.get("credential_key", "VOLCENGINE_API_KEY")
    if not isinstance(credential_key, str) or not credential_key:
        raise TTSUserError("config credential_key must be a non-empty string")

    resource_id = raw.get("resource_id")
    if resource_id is not None and (not isinstance(resource_id, str) or not resource_id):
        raise TTSUserError("config resource_id must be a non-empty string")
    resource_header = raw.get("resource_header", "X-Api-Resource-Id")
    if not isinstance(resource_header, str) or not resource_header:
        raise TTSUserError("config resource_header must be a non-empty string")
    appid_header = raw.get("appid_header")
    if appid_header is not None and (not isinstance(appid_header, str) or not appid_header):
        raise TTSUserError("config appid_header must be a non-empty string")
    token_header = raw.get("token_header")
    if token_header is not None and (not isinstance(token_header, str) or not token_header):
        raise TTSUserError("config token_header must be a non-empty string")

    extra = raw.get("extra_req_params", {})
    if not isinstance(extra, dict):
        raise TTSUserError("config extra_req_params must be an object")
    return {
        "provider": "doubao",
        "endpoint": endpoint,
        "resource_id": resource_id,
        "resource_header": resource_header,
        "speaker": speaker,
        "uid": uid,
        "model": raw.get("model"),
        "audio_format": audio_format,
        "output_container": output_container,
        "pcm_channels": pcm_channels,
        "pcm_sample_width": pcm_sample_width,
        "sample_rate": sample_rate,
        "max_text_bytes": max_text_bytes,
        "max_text_chars": max_text_chars,
        "timeout_seconds": float(timeout_seconds),
        "auth_mode": auth_mode,
        "access_token_env": token_env,
        "appid_env": appid_env,
        "credentials_file": credential_file,
        "credentials_file_env": credential_file_env,
        "credential_key": credential_key,
        "appid_header": appid_header,
        "token_header": token_header,
        "extra_req_params": extra,
    }


def _read_explicit_credentials(path: Path, credential_key: str) -> tuple[str | None, str | None]:
    """Read only one explicitly configured JSON or shell-env credential file."""

    try:
        if os.name == "nt":
            raise TTSUserError("On Windows use explicit access_token_env; POSIX file modes cannot verify Windows ACLs")
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            raise TTSUserError("the explicitly configured credentials file must not be group/world readable")
        raw = path.read_text(encoding="utf-8")
    except TTSUserError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise TTSUserError("could not read the explicitly configured credentials file") from exc
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TTSUserError("could not parse the explicitly configured credentials file") from exc
    else:
        data = {}
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                parts = shlex.split(stripped, comments=True)
            except ValueError as exc:
                raise TTSUserError("could not parse the explicitly configured credentials file") from exc
            if parts and parts[0] == "export":
                parts = parts[1:]
            if len(parts) == 1 and "=" in parts[0]:
                name, value = parts[0].split("=", 1)
                data[name] = value
    if not isinstance(data, dict):
        raise TTSUserError("the explicitly configured credentials file must contain an object")
    appid = data.get("appid", data.get("app_id"))
    token = data.get("access_token", data.get("token", data.get(credential_key)))
    if appid is not None and not isinstance(appid, str):
        raise TTSUserError("the configured credentials file has an invalid app id")
    if token is not None and not isinstance(token, str):
        raise TTSUserError("the configured credentials file has an invalid access token")
    return appid, token


def resolve_credentials(config: dict, project_root: Path, *, required: bool) -> tuple[str | None, str | None]:
    """Resolve only named environment variables or one explicitly named file."""

    appid = os.environ.get(config.get("appid_env")) if config.get("appid_env") else None
    token = os.environ.get(config.get("access_token_env")) if config.get("access_token_env") else None

    credential_file = config.get("credentials_file")
    credential_file_env = config.get("credentials_file_env")
    if credential_file_env:
        credential_file = os.environ.get(credential_file_env)
        if required and not credential_file:
            raise TTSUserError(f"credential file unavailable; set configured environment variable {credential_file_env}")
    if credential_file:
        file_path = Path(credential_file).expanduser()
        if not file_path.is_absolute():
            file_path = project_root / file_path
        file_appid, file_token = _read_explicit_credentials(file_path.resolve(), config["credential_key"])
        appid = appid or file_appid
        token = token or file_token

    if required:
        if not token:
            raise TTSUserError(f"credential unavailable; set configured environment variable {config['access_token_env']}")
        if config.get("appid_env") and not appid:
            raise TTSUserError(f"app id unavailable; set configured environment variable {config['appid_env']}")
    return appid, token


def build_payload(config: dict, text: str, request_id: str) -> dict:
    req_params = dict(config["extra_req_params"])
    req_params["text"] = text
    req_params["speaker"] = config["speaker"]
    audio_params = dict(req_params.get("audio_params", {}))
    audio_params["format"] = config["audio_format"]
    audio_params["sample_rate"] = config["sample_rate"]
    req_params["audio_params"] = audio_params
    if config.get("model"):
        req_params["model"] = config["model"]
    payload = {
        "user": {"uid": config["uid"]},
        "req_params": req_params,
    }
    return payload


def request_fingerprint(config: dict, payload: dict) -> str:
    """Hash request semantics without including credentials or volatile IDs."""

    stable = {
        "endpoint": config["endpoint"],
        "resource_id": config.get("resource_id"),
        "payload": dict(payload),
    }
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded)


def _extract_base64_audio(value) -> bytes | None:
    if isinstance(value, str):
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, base64.binascii.Error):
            return None
        return decoded or None
    if isinstance(value, list) and all(isinstance(item, int) and 0 <= item <= 255 for item in value):
        return bytes(value)
    return None


def extract_audio_body(body: bytes, content_type: str) -> bytes:
    """Accept a direct audio body or a JSON response containing base64 audio."""

    if body[:4] == b"RIFF" and body[8:12] == b"WAVE":
        return body
    if "json" in content_type.lower() or "text/plain" in content_type.lower() or body[:1] in {b"{", b"["}:
        try:
            stream_text = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TTSRequestError("provider returned invalid JSON") from exc
        records = []
        decoder = json.JSONDecoder()
        cursor = 0
        while cursor < len(stream_text):
            while cursor < len(stream_text) and stream_text[cursor].isspace():
                cursor += 1
            if cursor >= len(stream_text):
                break
            # SSE servers prefix each JSON record with ``data:``; discard only
            # that protocol marker, never arbitrary response text.
            if stream_text.startswith("data:", cursor):
                cursor += len("data:")
                while cursor < len(stream_text) and stream_text[cursor].isspace():
                    cursor += 1
            try:
                record, end = decoder.raw_decode(stream_text, cursor)
            except json.JSONDecodeError as exc:
                raise TTSRequestError("provider returned invalid JSON") from exc
            records.append(record)
            cursor = end
            if cursor < len(stream_text) and stream_text[cursor] == "\n":
                cursor += 1
        if not records:
            raise TTSRequestError("provider returned an empty response")
        candidates = []
        saw_error = False
        for data in records:
            if isinstance(data, dict):
                code = data.get("code", data.get("status_code", data.get("status")))
                if code not in (None, 0, "0", 200, "200", 3000, "3000", "success", "SUCCESS"):
                    saw_error = True
                for key in ("data", "audio", "audio_data", "audio_base64", "audioContent"):
                    if key in data:
                        candidates.append(data[key])
                nested = data.get("result")
                if isinstance(nested, dict):
                    for key in ("data", "audio", "audio_data", "audio_base64", "audioContent"):
                        if key in nested:
                            candidates.append(nested[key])
        chunks = []
        for candidate in candidates:
            audio = _extract_base64_audio(candidate)
            if audio:
                chunks.append(audio)
        if chunks:
            return b"".join(chunks)
        if saw_error:
            raise TTSRequestError("provider rejected the synthesis request")
        raise TTSRequestError("provider response did not contain audio")
    if not body:
        raise TTSRequestError("provider returned an empty audio response")
    return body


def materialize_wav(audio_bytes: bytes, config: dict) -> bytes:
    """Convert a raw PCM response to the requested WAV delivery container."""

    if audio_bytes[:4] == b"RIFF" and audio_bytes[8:12] == b"WAVE":
        return audio_bytes
    if config["audio_format"] != "pcm":
        raise TTSUserError(
            f"provider returned {config['audio_format']} data; stdlib validation requires PCM/WAV output"
        )
    if len(audio_bytes) == 0:
        raise TTSUserError("provider returned empty PCM audio")
    if len(audio_bytes) % (config["pcm_channels"] * config["pcm_sample_width"]) != 0:
        raise TTSUserError("provider returned incomplete PCM frames")
    buffer = io.BytesIO()
    try:
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(config["pcm_channels"])
            wav_file.setsampwidth(config["pcm_sample_width"])
            wav_file.setframerate(config["sample_rate"])
            wav_file.writeframes(audio_bytes)
    except (OSError, wave.Error) as exc:
        raise TTSUserError("provider PCM data could not be wrapped as WAV") from exc
    return buffer.getvalue()


def inspect_wav_bytes(data: bytes) -> dict:
    """Read all PCM frames and return measured metadata."""

    try:
        handle = wave.open(io.BytesIO(data), "rb")
    except (wave.Error, EOFError) as exc:
        raise TTSUserError("synthesis output is not a readable WAV file") from exc
    with handle as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        compression = wav_file.getcomptype()
        if compression != "NONE":
            raise TTSUserError("synthesis output uses a compressed WAV encoding")
        if channels <= 0 or sample_width <= 0 or sample_rate <= 0 or frame_count <= 0:
            raise TTSUserError("synthesis output has invalid or empty WAV parameters")
        frames = wav_file.readframes(frame_count)
        expected = channels * sample_width * frame_count
        if len(frames) != expected:
            raise TTSUserError("synthesis output could not be fully decoded")
    duration_ms = (frame_count * 1000 + sample_rate // 2) // sample_rate
    return {
        "channels": channels,
        "sample_width": sample_width,
        "sample_rate": sample_rate,
        "frames": frame_count,
        "duration_ms": duration_ms,
    }


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def cache_metadata_path(output_path: Path) -> Path:
    return Path(f"{output_path}.meta.json")


def inspect_cache(output_path: Path, text_sha: str, request_sha: str) -> dict:
    meta_path = cache_metadata_path(output_path)
    if not output_path.is_file() or not meta_path.is_file():
        return {"hit": False, "reason": "missing output or metadata"}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {"hit": False, "reason": "invalid metadata"}
    if not isinstance(meta, dict) or meta.get("version") != 1:
        return {"hit": False, "reason": "unsupported metadata"}
    if meta.get("text_sha256") != text_sha or meta.get("request_sha256") != request_sha:
        return {"hit": False, "reason": "text or request changed"}
    try:
        audio = output_path.read_bytes()
        measured = inspect_wav_bytes(audio)
    except (OSError, TTSUserError):
        return {"hit": False, "reason": "audio failed validation"}
    audio_sha = sha256_bytes(audio)
    if meta.get("audio_sha256") != audio_sha:
        return {"hit": False, "reason": "audio hash changed"}
    if meta.get("duration_ms") != measured["duration_ms"]:
        return {"hit": False, "reason": "audio metadata changed"}
    return {"hit": True, "metadata": meta, "audio": measured}


def _request_headers(config: dict, appid: str | None, token: str, request_id: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "audio/wav, application/json, application/octet-stream",
        "X-Api-Request-Id": request_id,
    }
    if config.get("resource_id"):
        headers[config["resource_header"]] = config["resource_id"]
    mode = config["auth_mode"]
    if mode == "bearer_semicolon":
        headers["Authorization"] = f"Bearer; {token}"
    elif mode == "bearer_space":
        headers["Authorization"] = f"Bearer {token}"
    elif mode == "api_key":
        headers[config.get("token_header") or "X-Api-Key"] = token
    elif mode == "legacy_headers":
        if not appid or not config.get("appid_header") or not config.get("token_header"):
            raise TTSUserError("legacy_headers requires app id and configured app/token headers")
        headers[config["appid_header"]] = appid
        headers[config["token_header"]] = token
    if mode in {"bearer_semicolon", "bearer_space"} and appid and config.get("appid_header"):
        headers[config["appid_header"]] = appid
    return headers


def call_provider(config: dict, payload: dict, appid: str | None, token: str, request_id: str) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        config["endpoint"],
        data=body,
        headers=_request_headers(config, appid, token, request_id),
        method="POST",
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=config["timeout_seconds"]) as response:
            response_body = response.read()
            content_type = response.headers.get("Content-Type", "")
    except NoRedirectError:
        raise
    except urllib.error.HTTPError as exc:
        # Do not read or print the provider body: it can echo text or secrets.
        raise TTSRequestError(f"provider request failed with HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            raise TTSRequestError("provider request timed out") from None
        raise TTSRequestError("provider request could not be completed") from None
    except TimeoutError:
        raise TTSRequestError("provider request timed out") from None
    return extract_audio_body(response_body, content_type)


def run_tts(
    *,
    project_root: Path,
    text_path: str,
    config_path: str,
    output_path: str,
    dry_run: bool = False,
    force: bool = False,
    voice: str | None = None,
) -> dict:
    root = project_root.expanduser().resolve()
    if not root.is_dir():
        raise TTSUserError("--project-root must be an existing directory")
    text_file = project_path(root, text_path, "--text", must_exist=True)
    output_file = project_path(root, output_path, "--output")
    if output_file.suffix.lower() != ".wav":
        raise TTSUserError("--output must use a .wav extension")
    config_file = Path(config_path).expanduser()
    if not config_file.is_absolute():
        config_file = root / config_file
    raw = load_json(config_file.resolve(), "--config")
    if voice is not None:
        selected = raw.get("voices", {}).get(voice)
        if not isinstance(selected, dict):
            raise TTSUserError("requested voice is not configured")
        raw.update({key: selected[key] for key in ("speaker", "resource_id")})
    config = validate_config(raw)
    text = load_text(text_file)
    text_bytes = len(text.encode("utf-8"))
    if config["max_text_chars"] is not None and len(text) > config["max_text_chars"]:
        raise TTSUserError(f"narration is {len(text)} Unicode characters, over configured limit {config['max_text_chars']}; whole-text synthesis will not split it")
    if config["max_text_bytes"] is not None and text_bytes > config["max_text_bytes"]:
        raise TTSUserError(
            f"narration is {text_bytes} UTF-8 bytes, over configured interface limit "
            f"{config['max_text_bytes']}; whole-text synthesis will not split it"
        )
    request_id = str(uuid.uuid4())
    payload = build_payload(config, text, request_id)
    text_sha = sha256_bytes(text.encode("utf-8"))
    request_sha = request_fingerprint(config, payload)
    cache = inspect_cache(output_file, text_sha, request_sha)
    env_status = {
        "access_token_env": config["access_token_env"],
        "access_token_present": bool(config["access_token_env"] and os.environ.get(config["access_token_env"])),
        "appid_env": config.get("appid_env"),
        "appid_present": bool(os.environ.get(config["appid_env"])) if config.get("appid_env") else False,
        "credentials_file_env": config.get("credentials_file_env"),
        "credentials_file_present": bool(config.get("credentials_file_env") and os.environ.get(config["credentials_file_env"])),
    }
    plan = {
        "project_root": str(root),
        "text_path": relative_project_path(root, text_file),
        "output_path": relative_project_path(root, output_file),
        "text_bytes": text_bytes,
        "text_chars": len(text),
        "speaker": config["speaker"],
        "resource_id": config["resource_id"],
        "max_text_chars": config["max_text_chars"],
        "text_sha256": text_sha,
        "max_text_bytes": config["max_text_bytes"],
        "request_sha256": request_sha,
        "request_count": 1,
        "cache": {key: value for key, value in cache.items() if key != "metadata"},
        "credentials": env_status,
        "dry_run": dry_run,
    }
    if dry_run:
        return plan
    if cache.get("hit") and not force:
        return {
            **plan,
            "cache_hit": True,
            "audio_sha256": cache["metadata"]["audio_sha256"],
            "duration_ms": cache["audio"]["duration_ms"],
        }

    appid, token = resolve_credentials(config, root, required=True)
    audio_bytes = materialize_wav(call_provider(config, payload, appid, token or "", request_id), config)
    audio_info = inspect_wav_bytes(audio_bytes)
    audio_sha = sha256_bytes(audio_bytes)
    atomic_write(output_file, audio_bytes)
    metadata = {
        "version": 1,
        "text_sha256": text_sha,
        "request_sha256": request_sha,
        "audio_sha256": audio_sha,
        "duration_ms": audio_info["duration_ms"],
        "sample_rate": audio_info["sample_rate"],
        "channels": audio_info["channels"],
        "sample_width": audio_info["sample_width"],
        "frames": audio_info["frames"],
        "byte_size": len(audio_bytes),
    }
    atomic_write(
        cache_metadata_path(output_file),
        (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )
    # Validate the persisted file and cache record, not just the response bytes.
    persisted = inspect_cache(output_file, text_sha, request_sha)
    if not persisted.get("hit"):
        raise TTSUserError("written synthesis output failed cache validation")
    return {
        **plan,
        "cache_hit": False,
        "audio_sha256": audio_sha,
        "duration_ms": audio_info["duration_ms"],
        "sample_rate": audio_info["sample_rate"],
        "channels": audio_info["channels"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthesize one complete narration with Doubao TTS")
    subparsers = parser.add_subparsers(dest="command", required=True)
    tts = subparsers.add_parser("tts", help="send one whole-text request")
    tts.add_argument("--project-root", required=True)
    tts.add_argument("--text", required=True)
    tts.add_argument("--config", required=True)
    tts.add_argument("--output", required=True)
    tts.add_argument("--dry-run", action="store_true", help="validate and print the request plan without network or writes")
    tts.add_argument("--voice", choices=["male", "female"], help="select a configured default voice")
    tts.add_argument("--force", action="store_true", help="ignore a valid cache and make one new request")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "tts":
            result = run_tts(
                project_root=Path(args.project_root),
                text_path=args.text,
                config_path=args.config,
                output_path=args.output,
                dry_run=args.dry_run,
                force=args.force,
                voice=args.voice,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except TTSUserError as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
