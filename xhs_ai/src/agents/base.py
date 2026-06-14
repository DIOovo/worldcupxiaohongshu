"""
Agent 基础类型。

这一层只描述 Agent 的输入、执行步骤和结果，不绑定 PyQt、数据库或浏览器。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AgentContext:
    """一次 Agent 执行的上下文。"""

    user_id: Optional[int] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentStep:
    """可持久化/可展示的 Agent 执行步骤。"""

    agent: str
    action: str
    status: str
    detail: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "action": self.action,
            "status": self.status,
            "detail": self.detail,
            "data": dict(self.data or {}),
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class AgentRunResult:
    """通用 Agent 执行结果。"""

    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    steps: List[AgentStep] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": dict(self.output or {}),
            "steps": [step.to_dict() for step in self.steps],
            "error": self.error,
        }
