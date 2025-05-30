from tavily import TavilyClient
from anthropic import Anthropic
import os
from typing import Literal
from pydantic import BaseModel, Field
from llm.prompt_templates import history_based_prompt
from llm import claude_3_7 as claude
from llm.vector_search import (
    title_collection,
    content_collection,
    description_collection,
    get_rrf,
    filter_results,
)

client = Anthropic()
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))


class Category(BaseModel):
    nationality: str = Field(description="예: 한국, 중국, 일본")
    period: str = Field(
        description="예: 신라, 고려, 조선. 단, 통일신라는 '신라'로 표기"
    )
    genre: Literal[
        "건축",
        "조각(불상)",
        "조각(불상 외)",
        "공예",
        "회화",
        "서예",
        "장신구",
        "복식",
        "과학기술",
        "기타",
    ]


tools = [
    {
        "name": "search_relics_by_period_and_genre",
        "description": "'시대'와 '전시물'로 검색 요청하는 경우에 한해 사용할 것",
        "input_schema": Category.model_json_schema(),
    },
    {
        "name": "search_relics_without_period_and_genre",
        "description": "search_relics_by_period_and_genre 이외의 모든 검색 조건에 해당하는 경우 사용할 것",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "사용자 질의",
                },
            },
        },
    },
    {
        "name": "search_historical_facts",
        "description": "역사적 사실에 대한 사용자의 질문에 답히기 위해 사용",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "웹 검색에 입력할 키워드를 3개 이내로 만들 것",
                },
            },
        },
    },
]


def search_relics_by_period_and_genre(search_condition: dict, database: dict):
    results = {}
    for relic_id, relic_data in database.items():
        relic_category: dict = relic_data["category"]
        if relic_category == search_condition:
            results[relic_id] = relic_data
            results[relic_id]["is_presented"] = False
    message = (
        f"요청하신 전시물이 {len(results)}점 검색되었습니다. [다음] 버튼을 클릭해주세요."
        if len(results) > 0
        else "요청하신 전시물의 검색 결과가 없습니다."
    )
    return results, message


def search_relics_without_period_and_genre(
    query: str, database: dict, user_message: str
):
    title_similarities = title_collection.query(query, top_k=5)
    description_similarities = description_collection.query(query, top_k=30)
    content_similarities = content_collection.query(query, top_k=30)
    desc_cntn_similarities = get_rrf(
        [description_similarities, content_similarities], weights=[0.6, 0.4]
    )[:3]
    similarities = title_similarities + desc_cntn_similarities
    filtered_similarities = filter_results(similarities, user_message)
    results = {}
    for similarity in filtered_similarities:
        results[similarity.id] = database[similarity.id]
        results[similarity.id]["is_presented"] = False
    message = (
        f"요청하신 전시물이 {len(results)}점 검색되었습니다. [다음] 버튼을 클릭해주세요."
        if len(results) > 0
        else "요청하신 전시물의 검색 결과가 없습니다. 조금 더 구체적으로 말씀해주세요!"
    )
    return results, message


def search_historical_facts(query):
    tavily_response = tavily.search(
        query=query,
        include_domains=["ko.wikipedia.org", "encykorea.aks.ac.kr"],
        max_results=10,
        search_depth="advanced",
        include_answer="advanced",
    )
    print("tavily_response:\n", tavily_response)
    return history_based_prompt.format(history_facts=tavily_response["answer"])


def use_tools(messages: list, database: dict):
    # messages.append({"role": "user", "content": tool_use_guide})
    response = claude.create_tool_response(messages=messages)
    if response.stop_reason != "tool_use":
        return None, None
    tool_content = next(
        content for content in response.content if content.type == "tool_use"
    )
    searched_database, message_dict = None, None
    if tool_content.name == "search_relics_by_period_and_genre":
        searched_database, message = search_relics_by_period_and_genre(
            tool_content.input, database
        )
        message_dict = {"role": "assistant", "content": message}
    elif tool_content.name == "search_relics_without_period_and_genre":
        searched_database, message = search_relics_without_period_and_genre(
            tool_content.input["query"], database, messages[-1]
        )
        message_dict = {"role": "assistant", "content": message}
    elif tool_content.name == "search_historical_facts":
        message = search_historical_facts(tool_content.input["query"])
        message_dict = {"role": "user", "content": message}
    return searched_database, message_dict
