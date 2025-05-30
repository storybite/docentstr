from anthropic import Anthropic
import json
from pathlib import Path
from llm.prompt_templates import (
    guide_instruction,
    revisit_instruction,
    guide_program_prompt,
)
from utils import get_base64_data
from llm import claude_3_7 as claude
from llm.tools import use_tools

client = Anthropic()


class Relics:

    def __init__(self, database=None):
        if database is None:
            self._load_database()
            self.original = self
        else:
            self.database = database
            self.original = None
        self.index = -1

    def _load_database(self):
        try:
            file_path = Path("data") / "database" / "relic_index.json"
            with open(file_path, "r", encoding="utf-8") as f:
                self.database: dict = json.load(f)
                for key, value in self.database.items():
                    value["img_path"] = str(
                        Path("data", "database", key, Path(value["img"]).name)
                    )
                    value["title"] = f"{value['label']['명칭']} ({key})"
                    value["is_presented"] = False
                    value["is_cached"] = False
                self.ids = list(self.database.keys())
        except Exception as e:
            import traceback

            msg = f"Error loading relic_index.json: {traceback.format_exc()}"
            print(msg)
            raise e

    @property
    def current_id(self):
        return self.ids[self.index]

    @property
    def current(self):
        current_relic = self.database[self.current_id]
        return current_relic

    def next(self):
        self.index += 1
        return self.current

    def previous(self):
        if self.index == 0:
            raise ValueError("첫 번째 작품입니다.")
        else:
            self.index -= 1
        return self.current

    @property
    def original_database(self):
        return self.database

    @property
    def header(self):
        prefix = "검색된 작품" if isinstance(self, SearchedRelics) else ""
        return f"{prefix} {len(self.database)}점 중 {self.index + 1}번째 전시물입니다."

    def set_presented(self, is_presented: bool):
        self.database[self.current_id]["is_presented"] = is_presented

    def current_to_card(self):
        return {
            "header": self.header,
            "img_path": self.current["img_path"],
            "title": self.current["title"],
        }


class SearchedRelics(Relics):

    def __init__(self, searched_database: dict, original: Relics):
        super().__init__(searched_database)
        self.original = original
        self.ids = list(self.database.keys())

    @property
    def original_database(self):
        return self.original.database


class InstructionHandler:

    first_present_index = 1

    def __init__(self):
        self.last_guide_id = ""

    def add_guide_program(self, messages: list):
        try:
            file_path = Path("data") / "guide_program.json"
            with open(file_path, "r", encoding="utf-8") as f:
                _guide_program_prompt = guide_program_prompt.format(
                    guide_program=json.load(f)
                )
                messages.append(
                    {
                        "role": "user",
                        "content": _guide_program_prompt,
                    }
                )
        except Exception as e:
            import traceback

            msg = f"Error loading guide_program.json: {traceback.format_exc()}"
            print(msg)
            raise e

    def add_guide(self, relics: Relics, messages: list):

        self._remove_before_guide(messages)

        guide_instruction_prompt = guide_instruction.format(
            label=relics.current["label"],
            content=relics.current["content"],
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": get_base64_data(relics.current["img_path"]),
                        },
                    },
                    {"type": "text", "text": guide_instruction_prompt},
                ],
            }
        )
        self.last_guide_id = relics.current_id
        if len(messages) == self.first_present_index + 1:
            messages[self.first_present_index]["content"][1]["cache_control"] = {
                "type": "ephemeral"
            }

    def _remove_before_guide(self, messages: list):
        for idx in reversed(range(len(messages))):
            if not isinstance(messages[idx]["content"], list):
                continue
            text_message: str = messages[idx]["content"][1]["text"]
            if "<relic_information>" in text_message:
                messages.pop(idx)
                break

    def check_and_add(self, relics: Relics, messages: list):
        if self.last_guide_id == relics.current_id:
            return
        self.add_guide(relics, messages)
        messages.append({"role": "user", "content": revisit_instruction})


class ExceptionHandler:

    @staticmethod
    def overflow(messages: list, relics: Relics):
        if isinstance(relics, SearchedRelics):
            messages.append(
                {
                    "role": "assistant",
                    "content": "검색된 전시물을 모두 소개했습니다. 다음 전시물을 소개하겠습니다.",
                }
            )
            relics.original.index += 1
            return relics.original
        else:
            messages.append(
                {
                    "role": "assistant",
                    "content": "준비한 전시물을 모두 소개했습니다. 오늘 유익한 시간 되었기를 바랍니다. 감사합니다.",
                }
            )
            return relics

    @staticmethod
    def underflow(messages: list, relics: Relics):
        messages.append({"role": "assistant", "content": "첫 번째 작품입니다."})
        relics.index = 0


class DocentBot:

    def __init__(self):
        self.messages = []
        self.relics = Relics()
        self.instruction = InstructionHandler()
        self.instruction.add_guide_program(self.messages)

    def _present_relic(self):
        self.instruction.add_guide(self.relics, self.messages)
        response_message = claude.create_response_text(messages=self.messages)
        # response_message = "test...."
        self.messages.append({"role": "assistant", "content": response_message})
        self.relics.set_presented(True)

    def move(self, is_next: bool):
        if is_next:
            try:
                self.relics.next()
            except IndexError:
                self.relics = ExceptionHandler.overflow(self.messages, self.relics)
        else:
            try:
                self.relics.previous()
            except ValueError:
                ExceptionHandler.underflow(self.messages, self.relics)

        if not self.relics.current["is_presented"]:
            self._present_relic()

    def answer(self, user_input: str) -> str:
        self.instruction.check_and_add(self.relics, self.messages)
        self.messages.append({"role": "user", "content": user_input})
        searched_database, message_dict = use_tools(
            self.get_conversation(),
            self.relics.original_database,
        )
        if searched_database is not None:
            if len(searched_database) > 0:
                self.relics = SearchedRelics(searched_database, self.relics.original)
            self.messages.append(message_dict)
            response_message = message_dict["content"]
        elif message_dict:
            self.messages.append(message_dict)
            response_message = claude.create_response_text(messages=self.messages)
            self.messages.append({"role": "assistant", "content": response_message})
        else:
            response_message = claude.create_response_text(messages=self.messages)
            self.messages.append({"role": "assistant", "content": response_message})
        return response_message

    def get_conversation(self):
        conversation = []
        for message in self.messages:
            if isinstance(message["content"], list):
                text_message: str = message["content"][1]["text"]
            else:
                text_message = message["content"]
            text_message = text_message.strip()
            if text_message.startswith("<system_command>"):
                continue
            conversation.append({"role": message["role"], "content": text_message})
        return conversation
