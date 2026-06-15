"""大模型图片生成服务。

模型负责生成视觉背景，受保护的球队、比分和概率仍由本地排版引擎叠加，
避免图片模型改错事实。
"""

from __future__ import annotations

import base64
import binascii
import os
from pathlib import Path
from typing import Any, List, Sequence
import uuid

import requests


class AIImageService:
    """统一调用现有图片模型适配器并保存图片。"""

    provider_aliases = {
        "qwen": "qwen",
        "通义": "qwen",
        "通义千问": "qwen",
        "阿里云": "qwen",
        "kimi": "kimi",
        "月之暗面": "kimi",
        "custom": "custom",
        "自定义": "custom",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "deepseek": "deepseek",
        "深度求索": "deepseek",
        "openai": "openai",
        "gpt-image": "openai",
    }

    def generate_backgrounds(
        self,
        prompts: Sequence[str],
        *,
        provider: str = "",
        model: str = "",
        size: str = "",
        endpoint: str = "",
        output_dir: str | Path = "",
    ) -> List[str]:
        """逐页生成并下载背景图；任一页失败即抛出异常。"""

        normalized_provider = self._normalize_provider(
            provider or os.environ.get("XHS_IMAGE_PROVIDER", "")
        )
        api_key = self._resolve_api_key(normalized_provider)
        resolved_endpoint = str(
            endpoint or os.environ.get("XHS_IMAGE_ENDPOINT", "")
        ).strip()
        adapter = self._create_adapter(
            normalized_provider,
            api_key,
            endpoint=resolved_endpoint,
        )
        resolved_model = str(
            model
            or os.environ.get("XHS_IMAGE_MODEL", "")
            or self._default_model(normalized_provider)
        ).strip()
        resolved_size = str(
            size
            or os.environ.get("XHS_IMAGE_SIZE", "")
            or ("1024*1024" if normalized_provider == "qwen" else "1024x1024")
        ).strip()
        directory = (
            Path(output_dir).expanduser().resolve()
            if output_dir
            else Path(os.path.expanduser("~"))
            / ".xhs_system"
            / "generated_imgs"
            / "ai"
        )
        directory.mkdir(parents=True, exist_ok=True)

        images: List[str] = []
        for index, prompt in enumerate(prompts, 1):
            result = adapter.generate_image(
                str(prompt or "").strip(),
                model=resolved_model,
                size=resolved_size,
            )
            if not isinstance(result, dict) or not result.get("success"):
                error = (
                    result.get("error")
                    if isinstance(result, dict)
                    else "模型未返回有效结果"
                )
                raise RuntimeError(f"AI 图片第 {index} 页生成失败：{error}")
            image_url = str(result.get("url") or "").strip()
            target = directory / f"worldcup_ai_{index}_{uuid.uuid4().hex[:10]}.png"
            image_base64 = str(result.get("b64_json") or "").strip()
            if image_url:
                self._download_image(image_url, target)
            elif image_base64:
                self._write_base64_image(image_base64, target)
            else:
                raise RuntimeError(
                    f"AI 图片第 {index} 页生成失败：返回结果缺少 URL 或 base64"
                )
            images.append(str(target))
        return images

    @classmethod
    def _normalize_provider(cls, provider: str) -> str:
        raw = str(provider or "").strip().lower()
        for alias, normalized in cls.provider_aliases.items():
            if alias in raw:
                return normalized
        raise RuntimeError(
            "AI 图片提供商未配置或不支持，请使用 "
            "--image-provider qwen、kimi、custom、anthropic、deepseek 或 openai"
        )

    @staticmethod
    def _create_adapter(
        provider: str,
        api_key: str,
        *,
        endpoint: str = "",
    ) -> Any:
        if provider == "kimi" and endpoint:
            from src.core.ai_integration.kimi_adapter import KimiAdapter

            return KimiAdapter(api_key, endpoint=endpoint)
        if provider in {"custom", "openai"}:
            from src.core.ai_integration.custom_image_adapter import (
                CustomImageAdapter,
            )

            resolved_endpoint = endpoint
            if provider == "openai" and not resolved_endpoint:
                resolved_endpoint = "https://api.openai.com/v1"
            return CustomImageAdapter(api_key, resolved_endpoint)
        if provider == "anthropic":
            from src.core.ai_integration.anthropic_image_adapter import (
                AnthropicImageAdapter,
            )

            return AnthropicImageAdapter(api_key, endpoint)
        if provider == "deepseek":
            from src.core.ai_integration.deepseek_image_adapter import (
                DeepSeekImageAdapter,
            )

            return DeepSeekImageAdapter(api_key, endpoint)
        from src.core.ai_integration.ai_provider_factory import AIProviderFactory

        return AIProviderFactory.create_provider(provider, api_key)

    @staticmethod
    def _resolve_api_key(provider: str) -> str:
        if provider == "qwen":
            env_names = ["XHS_IMAGE_API_KEY", "DASHSCOPE_API_KEY", "QWEN_API_KEY"]
        elif provider == "kimi":
            env_names = ["XHS_IMAGE_API_KEY", "MOONSHOT_API_KEY", "KIMI_API_KEY"]
        elif provider == "custom":
            env_names = ["XHS_IMAGE_API_KEY"]
        elif provider == "openai":
            env_names = ["XHS_IMAGE_API_KEY", "OPENAI_API_KEY"]
        elif provider == "anthropic":
            env_names = [
                "XHS_IMAGE_API_KEY",
                "ANTHROPIC_API_KEY",
                "ANTHROPIC_AUTH_TOKEN",
            ]
        else:
            env_names = [
                "XHS_IMAGE_API_KEY",
                "DEEPSEEK_API_KEY",
            ]
        for name in env_names:
            value = str(os.environ.get(name) or "").strip()
            if value:
                return value

        try:
            from src.core.ai_integration.api_key_manager import api_key_manager

            if provider == "qwen":
                provider_names = ["阿里云（通义千问）", "Qwen3", "qwen"]
            elif provider == "kimi":
                provider_names = ["月之暗面（Kimi）", "Kimi2", "kimi"]
            elif provider == "custom":
                provider_names = ["自定义图片接口", "custom"]
            elif provider == "openai":
                provider_names = ["OpenAI", "OpenAI GPT-4", "openai"]
            elif provider == "anthropic":
                provider_names = ["Anthropic（Claude）", "Claude 3.5", "anthropic"]
            else:
                provider_names = ["DeepSeek", "deepseek"]
            for provider_name in provider_names:
                value = api_key_manager.get_key(provider_name, "default")
                if value:
                    return value.strip()
        except Exception:
            pass
        raise RuntimeError(
            "AI 图片 API Key 未配置。请设置 XHS_IMAGE_API_KEY，"
            "或在后台配置对应提供商的 default 密钥"
        )

    @staticmethod
    def _default_model(provider: str) -> str:
        if provider == "qwen":
            return "wanx-v1"
        if provider == "kimi":
            return "kimi-image"
        if provider == "openai":
            return "gpt-image-1"
        return ""

    @staticmethod
    def _download_image(url: str, target: Path) -> None:
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"下载 AI 图片失败：{exc}") from exc
        content_type = str(response.headers.get("Content-Type") or "").lower()
        if content_type and not content_type.startswith("image/"):
            raise RuntimeError(f"下载 AI 图片失败：响应类型不是图片（{content_type}）")
        if not response.content:
            raise RuntimeError("下载 AI 图片失败：响应内容为空")
        target.write_bytes(response.content)

    @staticmethod
    def _write_base64_image(value: str, target: Path) -> None:
        raw = str(value or "").strip()
        if raw.startswith("data:") and "," in raw:
            raw = raw.split(",", 1)[1]
        try:
            content = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise RuntimeError("保存 AI 图片失败：base64 数据无效") from exc
        if not content:
            raise RuntimeError("保存 AI 图片失败：base64 内容为空")
        target.write_bytes(content)


ai_image_service = AIImageService()
