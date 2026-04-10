"""构建 4 路向量知识库：DDL Schema + Few-shot 示例 + 业务文档 + 表关系。"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.embeddings import ZhipuAIEmbeddings
from pymilvus import MilvusClient, DataType

load_dotenv()

MILVUS_URI = "http://localhost:19530"
BATCH_SIZE = 64
KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# 4 个 collection 配置
COLLECTIONS = {
    "text2sql_examples": {
        "file": "examples.json",
        "text_field": "text",       # embedding 用的文本字段
        "build_text": lambda item: f"问题: {item['question']}\nSQL: {item['sql']}",
        "fields": [
            ("question", DataType.VARCHAR, 2048),
            ("sql", DataType.VARCHAR, 8192),
        ],
        "build_data": lambda item, vec: {
            "question": item["question"],
            "sql": item["sql"],
            "text": f"问题: {item['question']}\nSQL: {item['sql']}",
            "vector": vec,
        },
    },
    "text2sql_business_docs": {
        "file": "business_docs.json",
        "text_field": "text",
        "build_text": lambda item: f"{item['title']}\n{item['content']}",
        "fields": [
            ("title", DataType.VARCHAR, 512),
            ("content", DataType.VARCHAR, 8192),
        ],
        "build_data": lambda item, vec: {
            "title": item["title"],
            "content": item["content"],
            "text": f"{item['title']}\n{item['content']}",
            "vector": vec,
        },
    },
    "text2sql_table_relations": {
        "file": "table_relations.json",
        "text_field": "text",
        "build_text": lambda item: f"{item['title']}\n{item['content']}",
        "fields": [
            ("title", DataType.VARCHAR, 512),
            ("content", DataType.VARCHAR, 8192),
        ],
        "build_data": lambda item, vec: {
            "title": item["title"],
            "content": item["content"],
            "text": f"{item['title']}\n{item['content']}",
            "vector": vec,
        },
    },
}


def _build_collection(client: MilvusClient, embeddings: ZhipuAIEmbeddings,
                       collection_name: str, config: dict):
    """构建单个 collection。"""
    file_path = KNOWLEDGE_DIR / config["file"]
    with open(file_path, "r", encoding="utf-8") as f:
        items = json.load(f)
    print(f"\n{'=' * 50}")
    print(f"构建 {collection_name}（共 {len(items)} 条）")

    # 构建 embedding 文本
    texts = [config["build_text"](item) for item in items]

    # 获取向量维度
    sample_vec = embeddings.embed_query(texts[0])
    dim = len(sample_vec)

    # 删除旧 collection
    if client.has_collection(collection_name):
        client.drop_collection(collection_name)

    # 创建 schema
    schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("text", DataType.VARCHAR, max_length=16384)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
    for field_name, field_type, max_length in config["fields"]:
        schema.add_field(field_name, field_type, max_length=max_length)

    # 创建索引
    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", metric_type="COSINE", index_type="HNSW")

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )

    # 分批 embedding + 插入
    total = 0
    for i in range(0, len(items), BATCH_SIZE):
        batch_items = items[i:i + BATCH_SIZE]
        batch_texts = texts[i:i + BATCH_SIZE]
        batch_vectors = embeddings.embed_documents(batch_texts)
        data = [
            config["build_data"](item, vec)
            for item, vec in zip(batch_items, batch_vectors)
        ]
        client.insert(collection_name=collection_name, data=data)
        total += len(data)
        print(f"  已插入第 {i // BATCH_SIZE + 1} 批，共 {len(data)} 条")

    client.flush(collection_name)
    print(f"  完成！共 {total} 条")


def build_all():
    """构建全部 4 个知识库（DDL Schema 用原有脚本，这里构建另外 3 个）。"""
    embeddings = ZhipuAIEmbeddings(model="embedding-3")
    client = MilvusClient(uri=MILVUS_URI)

    # 构建 DDL Schema 知识库（复用原有逻辑）
    print("=" * 50)
    print("构建 DDL Schema 知识库...")
    from app.text2sql.schema_build import build as build_schema
    build_schema()

    # 构建 Few-shot / 业务文档 / 表关系 三个知识库
    for collection_name, config in COLLECTIONS.items():
        _build_collection(client, embeddings, collection_name, config)

    print(f"\n{'=' * 50}")
    print("全部 4 个知识库构建完成！")
    print("  - text2sql_schema (DDL)")
    print("  - text2sql_examples (Few-shot)")
    print("  - text2sql_business_docs (业务文档)")
    print("  - text2sql_table_relations (表关系)")


if __name__ == "__main__":
    build_all()
