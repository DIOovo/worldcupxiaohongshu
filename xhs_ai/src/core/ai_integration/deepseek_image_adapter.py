"""DeepSeek 风格的 OpenAI Images 兼容网关适配器。

DeepSeek 官方 API 当前没有文生图端点。本适配器只用于支持
`/images/generations` 的第三方 DeepSeek 兼容图片网关。
"""

from __future__ import annotations

from typing import Any, Dict

from src.core.ai_integration.custom_image_adapter import CustomImageAdapter


class DeepSeekImageAdapter(CustomImageAdapter):
    """调用第三方 DeepSeek 风格图片网关。"""

    def __init__(self, api_key: str, endpoint: str):
        normalized = str(endpoint or "").strip()
        if self._is_official_endpoint(normalized):
            raise RuntimeError(
                "DeepSeek 官方 API 当前不提供文生图端点。"
                "请填写支持 /images/generations 的第三方 DeepSeek 图片网关"
            )
        super().__init__(api_key, normalized)

    def generate_image(
        self,
        prompt: str,
        model: str = "",
        size: str = "1024x1024",
    ) -> Dict[str, Any]:
        if not str(model or "").strip():
            return {
                "success": False,
                "error": "DeepSeek 图片网关的模型名称不能为空",
            }
        return super().generate_image(prompt, model=model, size=size)

    @staticmethod
    def _is_official_endpoint(endpoint: str) -> bool:
        value = str(endpoint or "").strip().lower()
        return (
            "api.deepseek.com" in value
            or "platform.deepseek.com" in value
        )
