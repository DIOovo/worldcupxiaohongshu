from src.agents.worldcup_copy_agent import WorldCupCopyAgent


class FakeLLMService:
    def __init__(self):
        self.calls = []

    def generate_text(self, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        return "这场比赛可以先看中场，主队状态更稳，但客队反击同样值得注意。"


def test_copy_agent_uses_editor_prompt_and_returns_plain_chinese():
    service = FakeLLMService()
    result = WorldCupCopyAgent(llm_service=service).rewrite_analysis(
        "比利时",
        "埃及",
        ["比利时近期状态更稳定"],
    )
    assert len(service.calls) == 1
    assert "把自己当成一个小编" in service.calls[0][0]
    assert "不要太死板" in service.calls[0][1]
    assert "这场比赛可以先看中场" in result
