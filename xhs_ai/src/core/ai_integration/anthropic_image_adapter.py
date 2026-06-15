"""Anthropic Messages 兼容的自定义图片接口适配器。

Anthropic 官方 Claude 不提供原生文生图。本适配器面向使用 Anthropic
Messages 请求格式、但能够返回图片块的第三方模型网关。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

import requests


class AnthropicImageAdapter:
    """调用 Anthropic Messages 兼容的图片模型网关。"""

    def __init__(self, api_key: str, endpoint: str):
        self.api_key = str(api_key or "").strip()
        self.endpoint = self._normalize_endpoint(endpoint)
        self.headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def generate_image(
        self,
        prompt: str,
        model: str = "",
        size: str = "1024x1024",
    ) -> Dict[str, Any]:
        """发送 Messages 请求并解析图片块、URL 或 base64。"""

        if not str(model or "").strip():
            return {"success": False, "error": "Anthropic 图片模型名称不能为空"}
        payload = {
            "model": str(model).strip(),
            "max_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"{str(prompt or '').strip()}\n"
                                f"目标图片尺寸：{str(size or '1024x1024').strip()}。"
                                "请返回生成后的图片，不要只返回图片描述。"
                            ),
                        }
                    ],
                }
            ],
        }
        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload,
                timeout=120,
            )
        except requests.Timeout:
            return {"success": False, "error": "Anthropic 图片接口请求超时"}
        except requests.RequestException as exc:
            return {"success": False, "error": f"Anthropic 图片接口网络错误：{exc}"}

        if response.status_code < 200 or response.status_code >= 300:
            return {
                "success": False,
                "error": f"Anthropic 图片接口错误：{response.status_code} - {response.text}",
            }
        try:
            data = response.json()
        except ValueError:
            return {"success": False, "error": "Anthropic 图片接口未返回有效 JSON"}
        result = self._extract_image(data)
        if result:
            return {"success": True, **result}
        return {
            "success": False,
            "error": (
                "Anthropic 响应中没有图片。官方 Claude 只支持图片理解，"
                "请使用能返回图片块的 Anthropic 兼容模型网关"
            ),
        }

    @classmethod
    def _extract_image(cls, data: Any) -> Dict[str, str]:
        if not isinstance(data, dict):
            return {}
        content = data.get("content")
        if not isinstance(content, list):
            return {}
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip()
            source = block.get("source")
            if block_type == "image" and isinstance(source, dict):
                source_type = str(source.get("type") or "").strip()
                if source_type == "base64" and source.get("data"):
                    return {"b64_json": str(source["data"])}
                if source_type == "url" and source.get("url"):
                    return {"url": str(source["url"])}
            if block_type in {"image_url", "image"} and block.get("url"):
                return {"url": str(block["url"])}
            if block_type == "text":
                parsed = cls._extract_from_text(str(block.get("text") or ""))
                if parsed:
                    return parsed
        return {}

    @staticmethod
    def _extract_from_text(text: str) -> Dict[str, str]:
        raw = str(text or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                if parsed.get("url"):
                    return {"url": str(parsed["url"])}
                if parsed.get("b64_json"):
                    return {"b64_json": str(parsed["b64_json"])}
        except ValueError:
            pass
        data_url = re.search(
            r"data:image/[a-zA-Z0-9.+-]+;base64,([A-Za-z0-9+/=\s]+)",
            raw,
        )
        if data_url:
            return {"b64_json": re.sub(r"\s+", "", data_url.group(1))}
        markdown_url = re.search(r"!\[[^\]]*]\((https?://[^)\s]+)\)", raw)
        if markdown_url:
            return {"url": markdown_url.group(1)}
        plain_url = re.search(r"https?://[^\s\"'<>]+", raw)
        if plain_url:
            return {"url": plain_url.group(0).rstrip(".,;，。；")}
        return {}

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        value = str(endpoint or "").strip().rstrip("/")
        if not value:
            raise RuntimeError(
                "Anthropic 图片接口地址未配置，请设置 --image-endpoint "
                "或 XHS_IMAGE_ENDPOINT"
            )
        if value.endswith("/messages"):
            return value
        if value.endswith("/v1"):
            return f"{value}/messages"
        return f"{value}/v1/messages"
