"""4 路向量知识检索：DDL Schema + Few-shot 示例 + 业务文档 + 表关系。"""

import os

from dotenv import load_dotenv
from langchain_community.embeddings import ZhipuAIEmbeddings
from pymilvus import MilvusClient

load_dotenv()
MILVUS_URI = "http://localhost:19530"

# 各知识库检索参数
SCHEMA_TOP_K = 15       # DDL Schema 候选数
EXAMPLE_TOP_K = 3        # Few-shot 示例数
BUSINESS_DOC_TOP_K = 5   # 业务文档数
RELATION_TOP_K = 5       # 表关系数

_embeddings = None
_client = None


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = ZhipuAIEmbeddings(model="embedding-3")
    return _embeddings


def _get_client():
    global _client
    if _client is None:
        _client = MilvusClient(uri=MILVUS_URI)
    return _client


def _search(collection_name: str, query_vector: list[float],
            top_k: int, output_fields: list[str]) -> list[dict]:
    """通用向量检索。"""
    client = _get_client()
    results = client.search(
        collection_name=collection_name,
        data=[query_vector],
        anns_field="vector",
        limit=top_k,
        output_fields=output_fields,
    )[0]
    return [r["entity"] for r in results]


def retrieve_all(question: str) -> dict:
    """对用户问题进行 4 路并行检索，返回各知识源的检索结果。

    Returns:
        {
            "schema_candidates": [...],   # DDL Schema 候选表
            "examples": [...],            # Few-shot Q&A 示例
            "business_docs": [...],       # 业务文档
            "table_relations": [...],     # 表关系
        }
    """
    embeddings = _get_embeddings()
    query_vector = embeddings.embed_query(question)

    # 4 路检索（共用同一个 query_vector，不需要重复 embed）
    schema_candidates = _search(
        "text2sql_schema", query_vector, SCHEMA_TOP_K,
        ["table_name", "table_comment", "create_sql"],
    )

    examples = _search(
        "text2sql_examples", query_vector, EXAMPLE_TOP_K,
        ["question", "sql"],
    )

    business_docs = _search(
        "text2sql_business_docs", query_vector, BUSINESS_DOC_TOP_K,
        ["title", "content"],
    )

    table_relations = _search(
        "text2sql_table_relations", query_vector, RELATION_TOP_K,
        ["title", "content"],
    )

    return {
        "schema_candidates": schema_candidates,
        "examples": examples,
        "business_docs": business_docs,
        "table_relations": table_relations,
    }
