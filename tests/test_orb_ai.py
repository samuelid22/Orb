"""Provider-adapter tests use fake SDK clients and real image bytes."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from PIL import Image

from prometheus.analysis.analyzer import GeminiAnalyzer, OpenAIAnalyzer
from prometheus.analysis.orb_ai import OrbAIService, video_generation_prompt
from prometheus.errors import PrometheusError


@pytest.fixture
def image_path(tmp_path):
    path = tmp_path / "reference.webp"
    Image.new("RGB", (8, 8), "blue").save(path, format="WEBP")
    return path


def _visual_json():
    return json.dumps({"prompt": "A blue square on a neutral background",
                       "visual_analysis": {"subject_and_scene": "Blue square",
                                           "composition": "Centered", "lighting": "Even"},
                       "refinements": ["Softer lighting"]})


@pytest.mark.parametrize("provider", ["gemini", "openai"])
def test_image_bytes_reach_provider(provider, image_path):
    calls = []
    if provider == "gemini":
        class Models:
            def generate_content(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(text=_visual_json())

        analyzer = GeminiAnalyzer(model="test-model", client=SimpleNamespace(models=Models()))
    else:
        class Completions:
            def create(self, **kwargs):
                calls.append(kwargs)
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=_visual_json()))])

        analyzer = OpenAIAnalyzer(model="test-model", client=SimpleNamespace(
            chat=SimpleNamespace(completions=Completions())))
    service = OrbAIService.__new__(OrbAIService)
    service.analyzer = analyzer
    service.provider = provider
    service.model = "test-model"
    result = service.image("decode", image_path)
    assert "blue square" in result["prompt"].lower()
    assert result["refinements"] == ["Softer lighting"]
    if provider == "gemini":
        assert calls[0]["contents"][1].inline_data.mime_type == "image/webp"
        assert calls[0]["contents"][1].inline_data.data == image_path.read_bytes()
    else:
        url = calls[0]["messages"][1]["content"][1]["image_url"]["url"]
        assert url.startswith("data:image/webp;base64,")


def test_enhance_rejects_empty_model_result():
    class Models:
        def generate_content(self, **kwargs):
            return SimpleNamespace(text=json.dumps({"enhanced_prompt": ""}))

    service = OrbAIService.__new__(OrbAIService)
    service.analyzer = GeminiAnalyzer(model="test-model", client=SimpleNamespace(models=Models()))
    service.provider = "gemini"
    service.model = "test-model"
    with pytest.raises(PrometheusError, match="usable enhanced_prompt"):
        service.enhance("A red train", "image", "", "balanced")


def test_video_generation_prompt_excludes_report_sections():
    report = (
        "# Video Reconstruction\n\n"
        "## Generation prompt\n\n"
        "Recreate a short video with these characteristics:\n\n"
        "**Subject:** A red ball moves across a field.\n\n"
        "## Structured breakdown\n\nInternal analysis\n"
    )
    assert video_generation_prompt(report) == (
        "Recreate a short video with these characteristics:\n\n"
        "Subject: A red ball moves across a field."
    )
    with pytest.raises(PrometheusError, match="did not produce a generation prompt"):
        video_generation_prompt("# No generation section")
