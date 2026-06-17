"""世界杯预测图文前端页面。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.agents.worldcup_workflow_agent import WorldCupWorkflowAgent
from src.core.alert import TipWindow
from src.core.ui.qt_font import get_ui_text_font_family_css


class WorldCupBuildThread(QThread):
    """在后台生成世界杯文案和封面，避免阻塞 GUI。"""

    finished = pyqtSignal(dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, options: Dict[str, Any]):
        super().__init__()
        self.options = dict(options or {})

    def run(self) -> None:
        try:
            self.progress.emit("正在读取并校验世界杯报告...")
            api_key = str(self.options.pop("image_api_key", "") or "").strip()
            if api_key:
                # 只写入当前进程环境，不持久化到 settings.json 或源码。
                os.environ["XHS_IMAGE_API_KEY"] = api_key
            self.progress.emit("正在审核文案并生成封面...")
            payload = WorldCupWorkflowAgent().build_publish_payload(
                **self.options
            )
            self.progress.emit("生成完成")
            self.finished.emit(payload)
        except Exception as exc:
            self.error.emit(str(exc))


class WorldCupPage(QWidget):
    """在工具箱中生成世界杯小红书内容。"""

    providers = [
        ("OpenAI", "openai"),
        ("Kimi", "kimi"),
        ("自定义 OpenAI 兼容", "custom"),
        ("Anthropic 兼容网关", "anthropic"),
        ("DeepSeek 图片网关", "deepseek"),
        ("通义万相", "qwen"),
    ]

    def __init__(self, app_window=None, parent=None):
        super().__init__(parent)
        self.app_window = app_window
        self.build_thread = None
        self.current_payload: Dict[str, Any] = {}
        self.setup_ui()
        self.refresh_reports()

    def setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #f8f9fa; }")
        root.addWidget(scroll)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 18, 24, 24)
        layout.setSpacing(14)
        scroll.setWidget(body)

        title = QLabel("世界杯预测 → 小红书")
        title.setStyleSheet(
            f"font-family: {get_ui_text_font_family_css()};"
            "font-size: 20pt; font-weight: bold; color: #1f2937;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "选择真实预测报告，生成一张封面和完整文字分析。"
            "默认只构建，不会自动发布。"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #6b7280; font-size: 11pt;")
        layout.addWidget(subtitle)

        config_frame = QFrame()
        config_frame.setStyleSheet(
            "QFrame { background: white; border: 1px solid #e5e7eb;"
            " border-radius: 10px; padding: 12px; }"
            "QLabel { border: none; }"
            "QLineEdit, QComboBox { min-height: 30px; padding: 3px 8px; }"
        )
        form = QFormLayout(config_frame)
        form.setSpacing(10)

        report_row = QWidget()
        report_layout = QHBoxLayout(report_row)
        report_layout.setContentsMargins(0, 0, 0, 0)
        self.report_combo = QComboBox()
        self.report_combo.setMinimumWidth(520)
        report_layout.addWidget(self.report_combo, 1)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_reports)
        report_layout.addWidget(refresh_btn)
        browse_btn = QPushButton("选择 JSON")
        browse_btn.clicked.connect(self.browse_report)
        report_layout.addWidget(browse_btn)
        form.addRow("预测报告", report_row)

        self.image_mode_combo = QComboBox()
        self.image_mode_combo.addItem("本地模板封面（无需 API）", "template")
        self.image_mode_combo.addItem("AI 生成封面", "ai")
        self.image_mode_combo.currentIndexChanged.connect(
            self.update_image_options
        )
        form.addRow("封面模式", self.image_mode_combo)

        self.provider_combo = QComboBox()
        for label, value in self.providers:
            self.provider_combo.addItem(label, value)
        self.provider_combo.currentIndexChanged.connect(
            self.update_provider_defaults
        )
        form.addRow("图片提供商", self.provider_combo)

        self.endpoint_input = QLineEdit()
        self.endpoint_input.setPlaceholderText(
            "官方 OpenAI 可留空；中转站填写 https://example.com/v1"
        )
        form.addRow("图片接口", self.endpoint_input)

        self.model_input = QLineEdit("gpt-image-1")
        form.addRow("图片模型", self.model_input)

        self.size_combo = QComboBox()
        self.size_combo.setEditable(True)
        self.size_combo.addItems(["1024x1024", "1024x1536", "1536x1024"])
        form.addRow("模型尺寸", self.size_combo)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText(
            "仅用于本次应用进程，不写入配置文件；也可使用环境变量"
        )
        form.addRow("图片 API Key", self.api_key_input)
        layout.addWidget(config_frame)

        action_row = QHBoxLayout()
        self.build_btn = QPushButton("生成世界杯小红书内容")
        self.build_btn.setMinimumHeight(42)
        self.build_btn.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; border: none;"
            " border-radius: 9px; padding: 8px 20px; font-weight: bold; }"
            "QPushButton:hover { background: #1d4ed8; }"
            "QPushButton:disabled { background: #93c5fd; }"
        )
        self.build_btn.clicked.connect(self.build_content)
        action_row.addWidget(self.build_btn)

        self.send_home_btn = QPushButton("送到主页预览")
        self.send_home_btn.setMinimumHeight(42)
        self.send_home_btn.setEnabled(False)
        self.send_home_btn.clicked.connect(self.send_to_home)
        action_row.addWidget(self.send_home_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.status_label = QLabel("请选择报告后开始生成")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #4b5563; font-size: 11pt;")
        layout.addWidget(self.status_label)

        result_frame = QFrame()
        result_frame.setStyleSheet(
            "QFrame { background: white; border: 1px solid #e5e7eb;"
            " border-radius: 10px; padding: 12px; }"
            "QLabel, QTextEdit { border: none; }"
        )
        result_layout = QHBoxLayout(result_frame)

        self.cover_label = QLabel("封面预览")
        self.cover_label.setAlignment(Qt.AlignCenter)
        self.cover_label.setFixedSize(320, 420)
        self.cover_label.setStyleSheet(
            "background: #f3f4f6; color: #9ca3af; border-radius: 8px;"
        )
        result_layout.addWidget(self.cover_label)

        text_column = QVBoxLayout()
        self.result_title = QLineEdit()
        self.result_title.setReadOnly(True)
        self.result_title.setPlaceholderText("生成后的标题")
        text_column.addWidget(self.result_title)
        self.result_content = QTextEdit()
        self.result_content.setReadOnly(True)
        self.result_content.setPlaceholderText("生成后的完整文字分析")
        self.result_content.setMinimumHeight(390)
        text_column.addWidget(self.result_content)
        result_layout.addLayout(text_column, 1)
        layout.addWidget(result_frame)
        self.update_image_options()

    @staticmethod
    def reports_directory() -> Path:
        project_root = Path(__file__).resolve().parents[3]
        return (
            project_root.parent
            / "worldcup"
            / "data"
            / "reports"
            / "world_cup_2026"
        )

    @classmethod
    def discover_reports(cls) -> List[Path]:
        directory = cls.reports_directory()
        if not directory.exists():
            return []
        return sorted(directory.glob("*.json"), reverse=True)

    def refresh_reports(self) -> None:
        current = str(self.report_combo.currentData() or "")
        reports = self.discover_reports()
        self.report_combo.clear()
        for path in reports:
            self.report_combo.addItem(path.stem.replace("_", " "), str(path))
        if current:
            index = self.report_combo.findData(current)
            if index >= 0:
                self.report_combo.setCurrentIndex(index)
        if reports:
            self.status_label.setText(f"已发现 {len(reports)} 份报告，默认选择最新一份")
        else:
            self.status_label.setText("未自动发现报告，可点击“选择 JSON”手动指定")

    def browse_report(self) -> None:
        start = str(self.reports_directory())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择世界杯预测报告",
            start,
            "JSON 文件 (*.json)",
        )
        if not path:
            return
        existing = self.report_combo.findData(path)
        if existing < 0:
            self.report_combo.insertItem(0, Path(path).stem, path)
            existing = 0
        self.report_combo.setCurrentIndex(existing)

    def update_image_options(self) -> None:
        enabled = self.image_mode_combo.currentData() == "ai"
        for widget in (
            self.provider_combo,
            self.endpoint_input,
            self.model_input,
            self.size_combo,
            self.api_key_input,
        ):
            widget.setEnabled(enabled)

    def update_provider_defaults(self) -> None:
        provider = str(self.provider_combo.currentData() or "")
        defaults = {
            "openai": ("", "gpt-image-1"),
            "kimi": ("", "kimi-image"),
            "qwen": ("", "wanx-v1"),
            "custom": ("", ""),
            "anthropic": ("", ""),
            "deepseek": ("", ""),
        }
        endpoint, model = defaults.get(provider, ("", ""))
        self.endpoint_input.setText(endpoint)
        self.model_input.setText(model)

    def build_options(self) -> Dict[str, Any]:
        report = str(self.report_combo.currentData() or "").strip()
        if not report:
            raise ValueError("请选择世界杯预测报告")
        report_path = Path(report).expanduser().resolve()
        output_path = (
            Path(__file__).resolve().parents[3]
            / "output"
            / f"{report_path.stem}_publish.json"
        )
        image_mode = str(self.image_mode_combo.currentData() or "template")
        return {
            "report_path": report_path,
            "page_count": 1,
            "image_mode": image_mode,
            "image_provider": (
                str(self.provider_combo.currentData() or "")
                if image_mode == "ai"
                else ""
            ),
            "image_endpoint": (
                self.endpoint_input.text().strip() if image_mode == "ai" else ""
            ),
            "image_model": (
                self.model_input.text().strip() if image_mode == "ai" else ""
            ),
            "image_size": (
                self.size_combo.currentText().strip() if image_mode == "ai" else ""
            ),
            "image_api_key": (
                self.api_key_input.text().strip() if image_mode == "ai" else ""
            ),
            "output_path": output_path,
        }

    def build_content(self) -> None:
        try:
            options = self.build_options()
        except Exception as exc:
            QMessageBox.warning(self, "无法生成", str(exc))
            return
        self.build_btn.setEnabled(False)
        self.send_home_btn.setEnabled(False)
        self.status_label.setText("正在启动世界杯工作流...")
        self.build_thread = WorldCupBuildThread(options)
        self.build_thread.progress.connect(self.status_label.setText)
        self.build_thread.finished.connect(self.handle_build_result)
        self.build_thread.error.connect(self.handle_build_error)
        self.build_thread.start()

    def handle_build_result(self, payload: Dict[str, Any]) -> None:
        self.build_btn.setEnabled(True)
        self.current_payload = dict(payload or {})
        self.result_title.setText(str(payload.get("title") or ""))
        self.result_content.setPlainText(str(payload.get("content") or ""))
        images = list(payload.get("images") or [])
        if images:
            pixmap = QPixmap(str(images[0]))
            if not pixmap.isNull():
                self.cover_label.setPixmap(
                    pixmap.scaled(
                        self.cover_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
        output = str(
            Path(self.build_thread.options.get("output_path")).expanduser().resolve()
        )
        self.status_label.setText(
            f"生成完成：{len(images)} 张封面\n输出：{output}"
        )
        self.send_home_btn.setEnabled(bool(images))
        TipWindow(self.app_window or self, "世界杯内容生成完成").show()

    def handle_build_error(self, message: str) -> None:
        self.build_btn.setEnabled(True)
        self.send_home_btn.setEnabled(False)
        self.status_label.setText(f"生成失败：{message}")
        QMessageBox.warning(self, "世界杯内容生成失败", str(message))

    def send_to_home(self) -> None:
        if not self.current_payload:
            return
        home_page = getattr(self.app_window, "home_page", None)
        if home_page is None:
            QMessageBox.warning(self, "无法预览", "未找到主页实例")
            return
        if hasattr(self.app_window, "switch_page"):
            self.app_window.switch_page(0)
        if hasattr(home_page, "generate_from_worldcup_payload"):
            home_page.generate_from_worldcup_payload(self.current_payload)
            TipWindow(self.app_window, "已送到主页并开始二次生成").show()
        else:
            home_page.load_publish_payload(self.current_payload)
            TipWindow(self.app_window, "已送到主页，可登录后预览发布").show()
