from dataclasses import dataclass
import numpy as np
import os
from utils import project_root
from openai import OpenAI
from .llm import claude_3_7 as claude
from .prompt_templates import search_result_filter
import json
import re
import streamlit as st

print(
    "upstage=============================================>",
    os.getenv("UPSTAGE_API_KEY"),
)
print(
    "anthropic=============================================>",
    os.getenv("ANTHROPIC_API_KEY"),
)
print(
    "slack_bot_token=============================================>",
    os.getenv("slack_bot_token"),
)
print(
    "ANTHROPIC_API_KEY-2=============================================>",
    st.secrets["ANTHROPIC_API_KEY"],
)
print(
    "UPSTAGE_API_KEY=============================================>",
    st.secrets["UPSTAGE_API_KEY"],
)

upstage = OpenAI(api_key=os.getenv("UPSTAGE_API_KEY"),
                 base_url="https://api.upstage.ai/v1")


@dataclass(slots=True)
class DocEmbedding:
    id: str
    doc: str
    embedding: list[float] | None = None


@dataclass(slots=True)
class Similarity:
    id: str
    doc: str
    score: float = 0
    collection_name: str = ""


class Collecton:

    _instances = {}

    def __new__(cls, name: str):
        if name not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[name] = instance
        return cls._instances[name]

    def __init__(self, name: str):
        if getattr(self, "_initialized", False):
            return

        self.name = name
        self.file_path = project_root / "data" / "vector_store" / f"{name}"
        self.index: dict[str, DocEmbedding] = {}
        self._initialized = True

    def load(self) -> "Collecton":
        with open(f"{self.file_path}_meta.json", "r", encoding="utf-8") as f:
            docs_list = json.load(f)

        embeddings_array = np.load(f"{self.file_path}_embeddings.npy")

        for doc, embedding in zip(docs_list, embeddings_array):
            self.index[doc["id"]] = DocEmbedding(id=doc["id"],
                                                 doc=doc["doc"],
                                                 embedding=embedding.tolist())

        return self

    def add_doc(self, id: str, doc: str):
        self.index[id] = DocEmbedding(id=id, doc=doc)

    def build(self):
        doc_embeddings_all = list(self.index.values())
        doc_embeddings_chunks = [
            doc_embeddings_all[i:i + 100]
            for i in range(0, len(doc_embeddings_all), 100)
        ]

        doc_all_list = []
        embedding_all_list = []
        for doc_embeddings in doc_embeddings_chunks:
            docs = [doc_embedding.doc for doc_embedding in doc_embeddings]
            embeddings = self._get_embeddings(docs)
            for doc_embedding, embedding in zip(doc_embeddings, embeddings):
                doc_embedding.embedding = embedding
                doc_all_list.append({
                    "id": doc_embedding.id,
                    "doc": doc_embedding.doc
                })
                embedding_all_list.append(embedding)

        embedding_np_array = np.array(embedding_all_list)
        np.save(f"{self.file_path}_embeddings.npy", embedding_np_array)

        with open(f"{self.file_path}_meta.json", "w", encoding="utf-8") as f:
            json.dump(doc_all_list, f, ensure_ascii=False, indent=2)

    def query(self,
              query: str,
              cutoff=0.4,
              top_k: int = 60) -> dict[int, Similarity]:
        query_embedding = self._get_embeddings(query)[0]
        similarities: list[Similarity] = []
        for doc_embedding in self.index.values():
            score = np.dot(query_embedding, doc_embedding.embedding) / (
                np.linalg.norm(query_embedding) *
                np.linalg.norm(doc_embedding.embedding))
            if score < cutoff:
                continue
            similarities.append(
                Similarity(
                    id=doc_embedding.id,
                    doc=doc_embedding.doc,
                    score=float(score),
                    collection_name=self.name,
                ))

        similarities = sorted(similarities,
                              key=lambda x: x.score,
                              reverse=True)[:top_k]
        return similarities

    def _get_embeddings(self, texts: list[str]) -> list[float]:
        embeddings = upstage.embeddings.create(input=texts,
                                               model="embedding-query")
        return [embedding_data.embedding for embedding_data in embeddings.data]

    def __len__(self) -> int:
        return len(self.index)


def get_rrf(
    ranked_lists: list[list[Similarity]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[Similarity]:

    weights = weights or [1 / len(ranked_lists)] * len(ranked_lists)
    # rrf_scores = defaultdict(float)
    rrf_sim_dict: dict[str, Similarity] = {}

    for w, ranked in zip(weights, ranked_lists):
        for rank, sim in enumerate(ranked, start=1):
            score = w / (k + rank)
            if sim.id in rrf_sim_dict:
                rrf_sim_dict[sim.id].score += score
                rrf_sim_dict[sim.id].doc += "\n" + sim.doc
            else:
                rrf_sim = Similarity(
                    id=sim.id,
                    doc=sim.doc,
                    score=score,
                )
                rrf_sim_dict[sim.id] = rrf_sim

    return sorted(rrf_sim_dict.values(), key=lambda x: x.score, reverse=True)


def filter_results(similarities: list[Similarity], query: str):

    sim_dict: dict[str, Similarity] = {}
    for sim in similarities:
        if sim.id in sim_dict:
            sim_dict[sim.id].doc += "\n" + sim.doc
        else:
            sim_dict[sim.id] = sim

    # rrf와 제목의 id가 겹치면 엎어질 수 있으므로 rrf와 마찬가지로 loop 돌면서 새로 구성
    # search_doc_results = {sim.id: sim.doc for sim in similarities}
    search_doc_results = {sim.id: sim.doc for sim in sim_dict.values()}
    response_json_str = claude.create_response_text(
        messages=[
            {
                "role":
                "user",
                "content":
                search_result_filter.format(user_query=query,
                                            search_results=search_doc_results),
            },
            {
                "role": "assistant",
                "content": "<json>"
            },
        ],
        stop_sequences=["</json>"],
    )
    filtered_similarities: list[Similarity] = []
    search_sim_results = {sim.id: sim for sim in similarities}
    response_json: dict[str, bool] = json.loads(response_json_str)
    for id, is_valid in response_json.items():
        if is_valid:
            filtered_similarities.append(search_sim_results[id])

    return filtered_similarities


HANJA_RE = re.compile(r"["
                      r"\u4E00-\u9FFF"  # 기본
                      r"\u3400-\u4DBF"  # 확장 A
                      r"\uF900-\uFAFF"  # 호환 한자
                      r"\U00020000-\U0002A6DF"  # 확장 B
                      r"\U0002A700-\U0002B73F"  # 확장 C–D
                      r"\U0002B740-\U0002B81F"  # 확장 E
                      r"]+")


def clean_text(text: str, replace_with: str = "") -> str:
    text = re.sub(r"\([^)]*\)|,", "", text)
    text = HANJA_RE.sub(replace_with, text)
    return text


title_collection = Collecton("title").load()
content_collection = Collecton("content").load()
description_collection = Collecton("description").load()
