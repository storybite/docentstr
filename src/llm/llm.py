from anthropic import Anthropic
from llm.prompt_templates import system_prompt, tool_system_prompt


class LLM:

    _instances: dict[str, "LLM"] = {}

    def __new__(cls, model_name: str, system_prompt: str, *args, **kwargs):
        if model_name not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[model_name] = instance
        return cls._instances[model_name]

    def __init__(self, model_name: str, system_prompt: str):
        if getattr(self, "_initialized", False):
            return

        self.client = Anthropic()
        self.model = model_name
        self.system_prompt = system_prompt
        self.tool_system_prompt = tool_system_prompt
        self._initialized = True  # 인스턴스 단위 초기화 완료 플래그

    def create_response(
        self,
        messages: list,
        temperature: float = 0,
        max_tokens: int = 2048,
        system_prompt: str | None = None,
        stop_sequences: list[str] = [],
    ):
        try:
            response = self.client.messages.create(
                max_tokens=max_tokens,
                temperature=temperature,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt or self.system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                messages=messages,
                model=self.model,
                stop_sequences=stop_sequences,
            )
            print(response.usage.model_dump_json())
            return response
        except Exception as e:
            print(f"[create_response error] {e}")
            raise e

    def create_response_text(
        self,
        messages: list,
        temperature: float = 0.5,
        max_tokens: int = 2048,
        system_prompt: str | None = None,
        stop_sequences: list[str] = [],
    ) -> str:
        response = self.create_response(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            stop_sequences=stop_sequences,
        )
        try:
            return response.content[0].text
        except Exception as e:
            print(f"[create_tool_response error] {response.model_dump_json()}")
            raise e

    def create_tool_response(
        self,
        messages: list,
        temperature: float = 0,
        max_tokens: int = 2048,
        tools: dict | None = None,
        tool_choice: dict[str, str] = {"type": "auto"},
        tool_system_prompt: str | None = None,
        stop_sequences: list[str] = [],
    ):
        if not tools:
            from src.llm.tools import tools as imported_tools

            tools = imported_tools
        try:
            response = self.client.messages.create(
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
                tool_choice=tool_choice,
                system=[
                    {
                        "type": "text",
                        "text": tool_system_prompt or self.tool_system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
                messages=messages,
                model=self.model,
                stop_sequences=stop_sequences,
            )
            print(response.usage.model_dump_json())
            return response
        except Exception as e:
            print(f"[LLM ERROR] {e}")
            raise e


# 모델별 싱글턴 인스턴스 생성
claude_3_7 = LLM(model_name="claude-3-7-sonnet-20250219", system_prompt=system_prompt)
claude_3_5 = LLM(model_name="claude-3-5-sonnet-20240620", system_prompt=system_prompt)
