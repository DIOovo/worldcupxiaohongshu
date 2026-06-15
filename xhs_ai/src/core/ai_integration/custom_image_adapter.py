"""OpenAI Images 兼容的自定义图片接口适配器。"""

from __future__ import annotations

from typing import Any, Dict

import requests


class CustomImageAdapter:
    """调用用户提供的 OpenAI Images 兼容接口。"""

    def __init__(self, api_key: str, endpoint: str):
        self.api_key = str(api_key or "").strip()
        self.endpoint = self._normalize_endpoint(endpoint)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate_image(
        self,
        prompt: str,
        model: str = "",
        size: str = "1024x1024",
    ) -> Dict[str, Any]:
        """生成图片，兼容 URL 和 base64 两种响应。"""

        payload: Dict[str, Any] = {
            "prompt": str(prompt or "").strip(),
            "n": 1,
            "size": str(size or "1024x1024").strip(),
        }
        if str(model or "").strip():
            payload["model"] = str(model).strip()

        try:
            response = requests.post(
                self.endpoint,
                headers=self.headers,
                json=payload,
                timeout=120,
            )
        except requests.Timeout:
            return {"success": False, "error": "自定义图片接口请求超时"}
        except requests.RequestException as exc:
            return {"success": False, "error": f"自定义图片接口网络错误：{exc}"}

        if response.status_code < 200 or response.status_code >= 300:
            return {
                "success": False,
                "error": f"自定义图片接口错误：{response.status_code} - {response.text}",
            }
        try:
            data = response.json()
        except ValueError:
            return {"success": False, "error": "自定义图片接口未返回有效 JSON"}

        items = data.get("data") if isinstance(data, dict) else None
        item = items[0] if isinstance(items, list) and items else None
        if not isinstance(item, dict):
            return {"success": False, "error": "自定义图片接口响应缺少 data[0]"}
        image_url = str(item.get("url") or "").strip()
        image_base64 = str(item.get("b64_json") or "").strip()
        if image_url:
            return {
                "success": True,
                "url": image_url,
                "revised_prompt": str(item.get("revised_prompt") or ""),
            }
        if image_base64:
            return {
                "success": True,
                "b64_json": image_base64,
                "revised_prompt": str(item.get("revised_prompt") or ""),
            }
        return {
            "success": False,
            "error": "自定义图片接口响应缺少 url 或 b64_json",
        }

    @staticmethod
    def _normalize_endpoint(endpoint: str) -> str:
        value = str(endpoint or "").strip().rstrip("/")
        if not value:
            raise RuntimeError(
                "自定义图片接口地址未配置，请设置 --image-endpoint "
                "或 XHS_IMAGE_ENDPOINT"
            )
        if value.endswith("/images/generations"):
            return value
        return f"{value}/images/generations"
