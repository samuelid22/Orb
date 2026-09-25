"""Orb AI API tests use a fake provider; they do not claim real model analysis."""

from __future__ import annotations

import importlib
import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image


api_module = importlib.import_module("prometheus.api.app")


class FakeAI:
    def image(self, operation, source):
        return {"prompt": f"{operation} prompt from pixels", "visual_analysis": {
            "subject_and_scene": "Blue square", "composition": "Centered",
            "lighting": "Even light"}, "refinements": ["Try softer light"]}

    def compose_video(self, analysis):
        assert analysis["frames"]
        return {"prompt": "Compose a moving blue square", "visual_analysis": {
            "motion_and_progression": "Moves across frame"}, "refinements": []}

    def enhance(self, prompt, output, style, detail):
        return f"Enhanced {output} prompt: {prompt} ({style}, {detail})"


def _png_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (32, 24), "blue").save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize("format_name,suffix", [("JPEG", "jpg"), ("PNG", "png"), ("WEBP", "webp")])
def test_all_supported_image_formats(tmp_path, monkeypatch, format_name, suffix):
    stream = io.BytesIO()
    Image.new("RGB", (32, 24), "blue").save(stream, format=format_name)
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/orb/decode/file", files={"file": (f"reference.{suffix}", stream.getvalue(), f"image/{suffix}")})
    assert response.status_code == 202
    assert _result(client, response.json()["job_id"])["image"]["width"] == 32


def test_image_extension_must_match_contents(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/api/orb/decode/file", files={"file": ("fake.jpg", _png_bytes(), "image/jpeg")})
    assert response.status_code == 422
    assert not list((tmp_path / "uploads").iterdir())


def _client(tmp_path, monkeypatch, service=None, *, local=True, key=True):
    monkeypatch.setenv("ORB_ENV", "local")
    monkeypatch.setenv("ORB_AI_LOCAL_TESTING", "1" if local else "0")
    if key:
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    else:
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("PROMETHEUS_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    return TestClient(api_module.create_app(
        provider="gemini", output_dir=tmp_path / "out", upload_dir=tmp_path / "uploads",
        require_payment=False, orb_ai_service=service or FakeAI(),
    ))


def _result(client, job_id):
    deadline = time.time() + 40
    while time.time() < deadline:
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["state"] != "processing":
            break
        time.sleep(.1)
    assert status["state"] == "complete", status
    response = client.get(f"/api/jobs/{job_id}/result")
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("operation", ["decode", "compose"])
def test_image_workflows_and_validation(tmp_path, monkeypatch, operation):
    client = _client(tmp_path, monkeypatch)
    response = client.post(f"/api/orb/{operation}/file", files={"file": ("reference.png", _png_bytes(), "image/png")})
    assert response.status_code == 202
    data = _result(client, response.json()["job_id"])
    assert data["operation"] == operation
    assert data["prompt"] == f"{operation} prompt from pixels"
    assert data["image"]["width"] == 32
    assert client.get(data["image"]["preview_url"]).status_code == 200
    assert client.post(f"/api/orb/{operation}/file", files={"file": ("bad.png", b"not image", "image/png")}).status_code == 422
    assert client.post(f"/api/orb/{operation}/file", files={"file": ("bad.gif", _png_bytes(), "image/gif")}).status_code == 400


def test_video_workflows_reuse_pipeline(tmp_path, monkeypatch, synthetic_video):
    from prometheus.analysis.analyzer import MockAnalyzer
    from prometheus.pipeline import PrometheusPipeline

    calls = []

    class FakePipeline:
        def __init__(self, config):
            self.pipeline = PrometheusPipeline(config=config, analyzer=MockAnalyzer())

        def run(self, source, progress=None):
            calls.append(source)
            return self.pipeline.run(source, progress=progress)

    monkeypatch.setattr(api_module, "PrometheusPipeline", FakePipeline)
    client = _client(tmp_path, monkeypatch)
    for operation in ("decode", "compose"):
        response = client.post(f"/api/orb/{operation}/file", files={"file": ("clip.mp4", synthetic_video.read_bytes(), "video/mp4")})
        assert response.status_code == 202
        data = _result(client, response.json()["job_id"])
        assert data["operation"] == operation
        assert data["video"]["duration"] > 0
        assert data["scenes"]
        assert data["prompt"]
        if operation == "decode":
            assert data["prompt"] == "No inferences available; connect a multimodal analyzer to generate a prompt."
            assert "Structured breakdown" not in data["prompt"]
    assert len(calls) == 2


def test_enhance_validation_and_error_sanitization(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {"prompt": "A red train crosses a bridge", "output": "video", "style": "cinematic", "detail": "balanced"}
    response = client.post("/api/orb/enhance", json=payload)
    assert response.status_code == 202
    data = _result(client, response.json()["job_id"])
    assert data["original_prompt"] == payload["prompt"]
    assert "red train" in data["prompt"]
    assert client.post("/api/orb/enhance", json={**payload, "prompt": "x"}).status_code == 422
    assert client.post("/api/orb/enhance", json={**payload, "output": "audio"}).status_code == 422

    class FailingAI(FakeAI):
        def enhance(self, *args):
            raise RuntimeError("private provider traceback secret")

    failed_client = _client(tmp_path / "failed", monkeypatch, FailingAI())
    failed = failed_client.post("/api/orb/enhance", json=payload)
    job_id = failed.json()["job_id"]
    deadline = time.time() + 10
    while time.time() < deadline:
        status = failed_client.get(f"/api/jobs/{job_id}").json()
        if status["state"] == "error":
            break
        time.sleep(.1)
    assert status["state"] == "error"
    assert "secret" not in status["error"]
    assert "secret" not in failed_client.get(f"/api/jobs/{job_id}/result").text


def test_payment_boundary_and_missing_provider(tmp_path, monkeypatch):
    production = _client(tmp_path / "production", monkeypatch, local=False)
    assert production.post("/api/orb/enhance", json={"prompt": "A blue sky"}).status_code == 402
    assert production.post("/api/orb/decode/file", files={"file": ("x.png", _png_bytes(), "image/png")}).status_code == 402
    assert production.post("/api/orb/compose/file", files={"file": ("x.png", _png_bytes(), "image/png")}).status_code == 402
    assert production.post("/api/analyze", files={"file": ("x.mp4", b"bad", "video/mp4")}).status_code == 402
    keyless = _client(tmp_path / "keyless", monkeypatch, key=False)
    assert keyless.post("/api/orb/enhance", json={"prompt": "A blue sky"}).status_code == 503
    local = _client(tmp_path / "forwarded", monkeypatch)
    assert local.post("/api/orb/enhance", json={"prompt": "A blue sky"}, headers={"X-Forwarded-For": "198.51.100.4"}).status_code == 402
    assert local.post("/api/orb/enhance", json={"prompt": "A blue sky"}, headers={"Host": "orb.example"}).status_code == 402
    monkeypatch.delenv("ORB_AI_LOCAL_TESTING")
    assert local.post("/api/orb/enhance", json={"prompt": "A blue sky"}).status_code == 402
