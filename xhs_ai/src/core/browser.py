from PyQt5.QtCore import QThread, pyqtSignal
import asyncio
import os
import sys
from functools import partial

from src.agents.workflow_agent import ContentWorkflowAgent
from src.core.write_xiaohongshu import XiaohongshuPoster


class BrowserThread(QThread):
    # 添加信号
    login_status_changed = pyqtSignal(str, bool)  # 用于更新登录按钮状态
    preview_status_changed = pyqtSignal(str, bool)  # 用于更新预览按钮状态
    login_success = pyqtSignal(object)  # 用于传递poster对象
    login_error = pyqtSignal(str)  # 用于传递错误信息
    preview_success = pyqtSignal()  # 用于通知预览成功
    preview_error = pyqtSignal(str)  # 用于传递预览错误信息
    scheduled_task_result = pyqtSignal(str, bool, str)  # (task_id, success, error_msg)

    def __init__(self):
        super().__init__()
        self.poster = None
        self.action_queue = []
        self.is_running = True
        self.loop = None

    def run(self):
        # 创建新的事件循环
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        # 在事件循环中运行主循环
        self.loop.run_until_complete(self.async_run())
        
        # 关闭事件循环
        self.loop.close()
        
    async def async_run(self):
        """异步主循环"""
        while self.is_running:
            if self.action_queue:
                action = self.action_queue.pop(0)
                try:
                    if action['type'] == 'login':
                        phone = (action.get('phone') or "").strip()
                        country_code = str(action.get('country_code') or "+86").strip() or "+86"
                        if not phone:
                            raise ValueError("手机号不能为空")

                        # 根据手机号匹配/创建用户，并作为当前用户
                        try:
                            from src.core.services.user_service import user_service
                        except Exception:
                            user_service = None

                        current_user = None
                        if user_service:
                            current_user = user_service.get_user_by_phone(phone)
                            if current_user:
                                user_service.switch_user(current_user.id)
                            else:
                                normalized_phone = "".join([c for c in phone if c.isdigit()]) or phone
                                username_base = f"user_{normalized_phone}"
                                username = username_base
                                suffix = 1
                                while user_service.get_user_by_username(username):
                                    username = f"{username_base}_{suffix}"
                                    suffix += 1
                                current_user = user_service.create_user(
                                    username=username,
                                    phone=phone,
                                    display_name=phone,
                                    set_current=True,
                                )

                        # 如果已存在浏览器会话，先关闭避免残留进程导致“偶发启动失败”
                        if self.poster:
                            try:
                                await self.poster.close(force=True)
                            except Exception:
                                pass
                            self.poster = None

                        # 读取当前用户的默认环境（代理/指纹）
                        browser_env = None
                        try:
                            from src.core.services.browser_environment_service import browser_environment_service

                            if current_user:
                                browser_env = browser_environment_service.get_default_environment(current_user.id)
                                if not browser_env:
                                    browser_environment_service.create_preset_environments(current_user.id)
                                    browser_env = browser_environment_service.get_default_environment(current_user.id)

                                # 若默认环境与当前系统不匹配，优先选择同用户下更贴近当前系统的环境（仅本次会话，不修改默认设置）
                                if browser_env and sys.platform == "darwin":
                                    ua = (browser_env.user_agent or "")
                                    platform = (browser_env.platform or "")
                                    if "Windows NT" in ua or platform == "Win32":
                                        browser_environment_service.create_preset_environments(current_user.id)
                                        envs = browser_environment_service.get_user_environments(current_user.id, active_only=True) or []
                                        for env in envs:
                                            if (env.platform or "") == "MacIntel" or "Macintosh" in (env.user_agent or ""):
                                                print(f"检测到 macOS 系统，默认环境为 Windows 指纹；本次登录临时切换到环境: {env.name}")
                                                browser_env = env
                                                break
                                elif browser_env and sys.platform == "win32":
                                    ua = (browser_env.user_agent or "")
                                    platform = (browser_env.platform or "")
                                    if "Macintosh" in ua or platform == "MacIntel":
                                        browser_environment_service.create_preset_environments(current_user.id)
                                        envs = browser_environment_service.get_user_environments(current_user.id, active_only=True) or []
                                        for env in envs:
                                            if (env.platform or "") == "Win32" or "Windows NT" in (env.user_agent or ""):
                                                print(f"检测到 Windows 系统，默认环境为 Mac 指纹；本次登录临时切换到环境: {env.name}")
                                                browser_env = env
                                                break
                        except Exception:
                            browser_env = None

                        self.poster = XiaohongshuPoster(
                            user_id=(current_user.id if current_user else None),
                            browser_environment=browser_env,
                        )
                        await self.poster.initialize()
                        await self.poster.login(phone, country_code=country_code)

                        if user_service and current_user:
                            user_service.update_login_status(current_user.id, True)

                        self.login_success.emit(self.poster)
                    elif action['type'] == 'preview' and self.poster:
                        auto_publish = bool(action.get("auto_publish", False))
                        await ContentWorkflowAgent().publish_payload(
                            self.poster,
                            {
                                "title": action['title'],
                                "content": action['content'],
                                "images": action['images'],
                            },
                            auto_publish=auto_publish,
                            record_analytics=False,
                        )
                        self.preview_success.emit()
                    elif action['type'] == 'scheduled_publish':
                        await self._run_scheduled_publish(action)
                except Exception as e:
                    if action['type'] == 'login':
                        # 登录阶段失败时，尽量释放浏览器资源，避免后续启动不稳定
                        try:
                            if self.poster:
                                await self.poster.close(force=True)
                        except Exception:
                            pass
                        finally:
                            self.poster = None

                        # 登录失败：更新数据库状态（不影响错误上报）
                        try:
                            from src.core.services.user_service import user_service

                            phone = (action.get('phone') or "").strip()
                            if phone:
                                u = user_service.get_user_by_phone(phone)
                                if u:
                                    user_service.update_login_status(u.id, False)
                        except Exception:
                            pass

                        msg = str(e)
                        if "Executable doesn't exist" in msg:
                            msg += "\n\n可能原因：Playwright 浏览器未安装/被杀毒清理。"
                            msg += "\n解决："
                            msg += "\n  - macOS/Linux："
                            msg += "\n    PLAYWRIGHT_BROWSERS_PATH=\"$HOME/.xhs_system/ms-playwright\" python -m playwright install chromium"
                            msg += "\n  - Windows（PowerShell）："
                            msg += "\n    $env:PLAYWRIGHT_BROWSERS_PATH=\"$HOME\\.xhs_system\\ms-playwright\"; python -m playwright install chromium"
                        self.login_error.emit(msg)
                    elif action['type'] == 'preview':
                        self.preview_error.emit(str(e))
                    elif action['type'] == 'scheduled_publish':
                        task_id = str(action.get('task_id') or "")
                        self.scheduled_task_result.emit(task_id, False, str(e))
            # 使用异步sleep而不是QThread.msleep
            await asyncio.sleep(0.1)  # 避免CPU占用过高

    async def _run_scheduled_publish(self, action: dict):
        """执行定时发布（无人值守，自动点击发布）。"""
        task_id = str(action.get("task_id") or "")
        user_id = action.get("user_id")
        task_type = str(action.get("task_type") or "fixed").strip() or "fixed"
        title = str(action.get("title") or "")
        content = str(action.get("content") or "")
        images = action.get("images") or []
        payload = {}

        if isinstance(images, (list, tuple)):
            images = [p for p in images if isinstance(p, str) and p and os.path.isfile(p)]
        else:
            images = []

        if task_type == "hotspot":
            loop = asyncio.get_running_loop()
            payload = await loop.run_in_executor(None, partial(self._build_hotspot_payload_sync, action))
            title = str(payload.get("title") or "").strip()
            content = str(payload.get("content") or "").strip()
            images = payload.get("images") or []
            if isinstance(images, (list, tuple)):
                images = [p for p in images if isinstance(p, str) and p and os.path.isfile(p)]
            else:
                images = []

            if not title and not content:
                raise RuntimeError("热点任务生成文案失败：标题/内容为空")
            if not images:
                raise RuntimeError("热点任务生成图片失败：图片为空")
        else:
            if not title and not content:
                raise RuntimeError("发布失败：标题/正文为空")

            # 固定内容任务：若未提供图片，则到点自动生成模板图/占位图
            if not images:
                cover_template_id = str(action.get("cover_template_id") or "").strip()
                try:
                    page_count = int(action.get("page_count") or 3)
                except Exception:
                    page_count = 3
                page_count = max(1, page_count)
                images = self._generate_images_for_text(title=title, content=content, cover_template_id=cover_template_id, page_count=page_count)
                if isinstance(images, (list, tuple)):
                    images = [p for p in images if isinstance(p, str) and p and os.path.isfile(p)]
                else:
                    images = []
            payload = {
                "schema": "xhs_ai.publish_payload.v1",
                "platform": str(action.get("platform") or "xiaohongshu").strip() or "xiaohongshu",
                "user_id": user_id,
                "title": title,
                "content": content,
                "images": images,
                "tags": ContentWorkflowAgent._extract_tags(content),
                "agent_steps": [],
            }

        # 默认使用当前用户
        if not user_id:
            try:
                from src.core.services.user_service import user_service

                current_user = user_service.get_current_user()
                user_id = current_user.id if current_user else None
            except Exception:
                user_id = None

        # 读取该用户默认浏览器环境（代理/指纹）
        browser_env = None
        try:
            from src.core.services.browser_environment_service import browser_environment_service

            if user_id:
                browser_env = browser_environment_service.get_default_environment(int(user_id))
                if not browser_env:
                    browser_environment_service.create_preset_environments(int(user_id))
                    browser_env = browser_environment_service.get_default_environment(int(user_id))

                # 定时任务同样优先使用与当前系统匹配的环境（避免 UA/platform 与 OS 不一致触发风控）
                if browser_env and sys.platform == "darwin":
                    ua = (browser_env.user_agent or "")
                    platform = (browser_env.platform or "")
                    if "Windows NT" in ua or platform == "Win32":
                        browser_environment_service.create_preset_environments(int(user_id))
                        envs = browser_environment_service.get_user_environments(int(user_id), active_only=True) or []
                        for env in envs:
                            if (env.platform or "") == "MacIntel" or "Macintosh" in (env.user_agent or ""):
                                browser_env = env
                                break
                elif browser_env and sys.platform == "win32":
                    ua = (browser_env.user_agent or "")
                    platform = (browser_env.platform or "")
                    if "Macintosh" in ua or platform == "MacIntel":
                        browser_environment_service.create_preset_environments(int(user_id))
                        envs = browser_environment_service.get_user_environments(int(user_id), active_only=True) or []
                        for env in envs:
                            if (env.platform or "") == "Win32" or "Windows NT" in (env.user_agent or ""):
                                browser_env = env
                                break
        except Exception:
            browser_env = None

        if not images:
            raise RuntimeError("发布失败：缺少图片（小红书图文发布需要图片）")

        poster = None
        poster_is_ephemeral = False
        try:
            target_uid = int(user_id) if user_id else None

            # 优先复用当前线程已登录的 poster，避免 persistent profile 目录被同时打开导致启动失败。
            if self.poster and getattr(self.poster, "user_id", None) == target_uid:
                poster = self.poster
            else:
                poster = XiaohongshuPoster(user_id=target_uid, browser_environment=browser_env)
                poster_is_ephemeral = True

            await poster.initialize()
            payload.update({"title": title, "content": content, "images": images, "user_id": target_uid})
            await ContentWorkflowAgent().publish_payload(
                poster,
                payload,
                auto_publish=True,
                record_analytics=self._bool_action_flag(action.get("record_analytics", True), default=True),
            )
            self.scheduled_task_result.emit(task_id, True, "")
        except Exception as e:
            self.scheduled_task_result.emit(task_id, False, str(e))
        finally:
            try:
                if poster and poster_is_ephemeral:
                    await poster.close(force=True)
            except Exception:
                pass

    @classmethod
    def _generate_images_for_text(cls, *, title: str, content: str, cover_template_id: str = "", page_count: int = 3):
        """为固定内容任务生成图片（优先系统模板，失败则回退占位图）。"""
        from src.agents.cover_agent import CoverAgent

        result = CoverAgent().generate_for_post(
            title=title,
            content=content,
            topic=title or content,
            cover_template_id=cover_template_id,
            page_count=page_count,
        )
        return list(result.images or [])

    @classmethod
    def _build_hotspot_payload_sync(cls, action: dict) -> dict:
        """生成热点定时任务的标题/内容/图片（同步，便于放入线程池执行）。"""
        workflow = ContentWorkflowAgent()
        request = ContentWorkflowAgent.request_from_action(action)
        return workflow.build_hotspot_payload(request)

    @staticmethod
    def _bool_action_flag(value, *, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            text = value.strip().lower()
            if not text:
                return default
            return text not in {"0", "false", "no", "n", "off"}
        return bool(value)

    def stop(self):
        self.is_running = False
        # 确保浏览器资源被释放
        if self.poster and self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.poster.close(force=True), self.loop)
