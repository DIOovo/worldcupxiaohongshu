import base64
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from src.agents.cover_agent import CoverAgent
from src.core.services.ai_image_service import AIImageService
from src.core.ai_integration.custom_image_adapter import CustomImageAdapter
from src.core.ai_integration.anthropic_image_adapter import AnthropicImageAdapter
from src.core.ai_integration.deepseek_image_adapter import DeepSeekImageAdapter
from src.core.ai_integration.kimi_adapter import KimiAdapter


class FakeAIImageService:
    def __init__(self, images):
        self.images = images
        self.calls = []

    def generate_backgrounds(self, prompts, **kwargs):
        self.calls.append((prompts, kwargs))
        return list(self.images)


def test_ai_prompts_do_not_ask_model_to_draw_protected_text():
    prompts = CoverAgent._build_ai_background_prompts(
        title="Belgium vs Egypt",
        topic="世界杯预测",
        pages=["比分", "概率", "分析"],
    )
    assert len(prompts) == 4
    assert all("不要文字" in prompt for prompt in prompts)
    assert all("不要数字" in prompt for prompt in prompts)


def test_ai_image_service_rejects_unknown_provider():
    with pytest.raises(RuntimeError, match="不支持"):
        AIImageService().generate_backgrounds(["test"], provider="unknown")


def test_custom_endpoint_appends_images_path():
    adapter = CustomImageAdapter("test-key", "https://example.com/v1")
    assert adapter.endpoint == "https://example.com/v1/images/generations"


def test_anthropic_endpoint_appends_messages_path():
    adapter = AnthropicImageAdapter("test-key", "https://example.com")
    assert adapter.endpoint == "https://example.com/v1/messages"


def test_deepseek_rejects_official_endpoint():
    with pytest.raises(RuntimeError, match="官方 API"):
        DeepSeekImageAdapter("test-key", "https://api.deepseek.com/v1")


def test_deepseek_accepts_third_party_image_gateway():
    adapter = DeepSeekImageAdapter("test-key", "https://example.com/v1")
    assert adapter.endpoint == "https://example.com/v1/images/generations"


def test_kimi_accepts_relay_base_endpoint():
    adapter = KimiAdapter("test-key", endpoint="https://relay.example.com/v1")
    assert adapter.base_url == "https://relay.example.com/v1"


def test_kimi_accepts_relay_full_images_endpoint():
    adapter = KimiAdapter(
        "test-key",
        endpoint="https://relay.example.com/v1/images/generations",
    )
    assert adapter.base_url == "https://relay.example.com/v1"


@patch("src.core.ai_integration.custom_image_adapter.requests.post")
def test_custom_adapter_accepts_url_response(mock_post):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{"url": "https://example.com/image.png"}]}
    mock_post.return_value = response

    result = CustomImageAdapter(
        "test-key",
        "https://example.com/v1/images/generations",
    ).generate_image("football", model="image-model")

    assert result["success"] is True
    assert result["url"] == "https://example.com/image.png"
    assert mock_post.call_args.kwargs["json"]["model"] == "image-model"


@patch("src.core.ai_integration.custom_image_adapter.requests.post")
def test_custom_adapter_accepts_base64_response(mock_post):
    encoded = base64.b64encode(b"image-bytes").decode()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"data": [{"b64_json": encoded}]}
    mock_post.return_value = response

    result = CustomImageAdapter(
        "test-key",
        "https://example.com/v1",
    ).generate_image("football")

    assert result["success"] is True
    assert result["b64_json"] == encoded


@patch("src.core.ai_integration.anthropic_image_adapter.requests.post")
def test_anthropic_adapter_accepts_image_block(mock_post):
    encoded = base64.b64encode(b"image-bytes").decode()
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": encoded,
                },
            }
        ]
    }
    mock_post.return_value = response

    result = AnthropicImageAdapter(
        "test-key",
        "https://example.com/v1/messages",
    ).generate_image("football", model="image-model")

    assert result["success"] is True
    assert result["b64_json"] == encoded
    assert mock_post.call_args.kwargs["headers"]["anthropic-version"] == "2023-06-01"


@patch("src.core.ai_integration.anthropic_image_adapter.requests.post")
def test_anthropic_adapter_accepts_text_url(mock_post):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "content": [
            {
                "type": "text",
                "text": '{"url":"https://example.com/image.png"}',
            }
        ]
    }
    mock_post.return_value = response

    result = AnthropicImageAdapter(
        "test-key",
        "https://example.com/v1",
    ).generate_image("football", model="image-model")

    assert result["success"] is True
    assert result["url"] == "https://example.com/image.png"


@patch("src.core.ai_integration.anthropic_image_adapter.requests.post")
def test_anthropic_adapter_rejects_text_only_response(mock_post):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "content": [{"type": "text", "text": "这是一张足球海报的描述"}]
    }
    mock_post.return_value = response

    result = AnthropicImageAdapter(
        "test-key",
        "https://api.anthropic.com/v1/messages",
    ).generate_image("football", model="claude-model")

    assert result["success"] is False
    assert "官方 Claude" in result["error"]


@patch("src.core.ai_integration.custom_image_adapter.requests.post")
def test_deepseek_gateway_accepts_image_response(mock_post):
    response = Mock()
    response.status_code = 200
    response.json.return_value = {
        "data": [{"url": "https://example.com/deepseek-image.png"}]
    }
    mock_post.return_value = response

    result = DeepSeekImageAdapter(
        "test-key",
        "https://example.com/v1",
    ).generate_image("football", model="deepseek-image-model")

    assert result["success"] is True
    assert result["url"] == "https://example.com/deepseek-image.png"
    assert mock_post.call_args.kwargs["json"]["model"] == "deepseek-image-model"


def test_ai_image_service_writes_base64_result(tmp_path, monkeypatch):
    encoded = base64.b64encode(b"image-bytes").decode()

    class FakeAdapter:
        def generate_image(self, prompt, model="", size=""):
            return {"success": True, "b64_json": encoded}

    monkeypatch.setenv("XHS_IMAGE_API_KEY", "test-key")
    service = AIImageService()
    monkeypatch.setattr(
        service,
        "_create_adapter",
        lambda provider, api_key, endpoint="": FakeAdapter(),
    )
    images = service.generate_backgrounds(
        ["football"],
        provider="custom",
        endpoint="https://example.com/v1",
        output_dir=tmp_path,
    )
    assert Path(images[0]).read_bytes() == b"image-bytes"


def test_openai_uses_official_endpoint_by_default(monkeypatch):
    monkeypatch.setenv("XHS_IMAGE_API_KEY", "test-key")
    service = AIImageService()
    adapter = service._create_adapter("openai", "test-key", endpoint="")
    assert adapter.endpoint == "https://api.openai.com/v1/images/generations"


def test_openai_accepts_relay_endpoint(monkeypatch):
    monkeypatch.setenv("XHS_IMAGE_API_KEY", "test-key")
    service = AIImageService()
    adapter = service._create_adapter(
        "openai",
        "test-key",
        endpoint="https://relay.example.com/v1",
    )
    assert adapter.endpoint == "https://relay.example.com/v1/images/generations"


def test_ai_mode_does_not_fall_back_when_background_count_is_short():
    service = FakeAIImageService(["only-cover.png"])
    agent = CoverAgent(ai_image_service=service)
    with pytest.raises(RuntimeError, match="数量不足"):
        agent.generate_for_post(
            title="Belgium vs Egypt",
            content="content",
            topic="世界杯预测",
            page_count=3,
            content_pages=["one", "two", "three"],
            image_mode="ai",
            image_provider="qwen",
        )


def test_ai_backgrounds_render_into_four_publish_images(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    backgrounds = []
    for index in range(4):
        path = tmp_path / f"background-{index}.png"
        Image.new("RGB", (1024, 1024), (20 + index * 20, 40, 80)).save(path)
        backgrounds.append(str(path))

    service = FakeAIImageService(backgrounds)
    result = CoverAgent(ai_image_service=service).generate_for_post(
        title="Belgium vs Egypt",
        content="世界杯预测正文",
        topic="Belgium vs Egypt 世界杯预测",
        page_count=3,
        content_pages=[
            "# 预测结论\n预测比分：Belgium 2-0 Egypt",
            "# 胜平负概率\n主胜概率：74.614%\n平局概率：15.6723%\n客胜概率：9.7136%",
            "# 分析依据\n1. 历史数据支持主队占优\n风险提示：理性参考",
        ],
        image_mode="ai",
        image_provider="qwen",
    )
    assert result.source == "ai_generated"
    assert len(result.images) == 4
    assert all(Path(path).is_file() for path in result.images)


def test_ai_cover_only_generates_one_background_and_one_image(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("HOME", str(tmp_path))
    background = tmp_path / "cover-background.png"
    Image.new("RGB", (1024, 1024), (20, 40, 80)).save(background)
    service = FakeAIImageService([str(background)])

    result = CoverAgent(ai_image_service=service).generate_for_post(
        title="Belgium vs Egypt",
        content="完整分析放在正文",
        topic="Belgium vs Egypt 世界杯预测",
        page_count=1,
        content_pages=[],
        cover_only=True,
        image_mode="ai",
        image_provider="openai",
    )

    assert result.source == "ai_generated"
    assert len(result.images) == 1
    assert len(service.calls[0][0]) == 1
    assert Path(result.images[0]).is_file()
