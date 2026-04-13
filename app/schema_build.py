"""读取 MySQL 全部表的 Schema，embedding 后存入 Milvus，供 Text2SQL Schema 检索使用。"""

from dotenv import load_dotenv
from langchain_community.embeddings import ZhipuAIEmbeddings
from pymilvus import MilvusClient, DataType

from app.sql_executor import get_all_tables, get_table_schema

load_dotenv()

MILVUS_URI = "http://localhost:19530"
COLLECTION_NAME = "text2sql_schema"
BATCH_SIZE = 64


def _build_table_description(table_name: str, table_comment: str, create_sql: str) -> str:
    """将表名、注释、建表语句拼成一段用于 embedding 的文本。"""
    comment_part = f"（{table_comment}）" if table_comment else ""
    return f"表名: {table_name}{comment_part}\n{create_sql}"


def build():
    """全量构建 Schema 向量库。"""
    print("[1/4] 读取所有表信息...")
    tables = get_all_tables()
    print(f"  共 {len(tables)} 张表")

    print("[2/4] 获取每张表的 CREATE TABLE 语句...")
    table_names = [t["TABLE_NAME"] for t in tables]
    table_comments = {t["TABLE_NAME"]: (t["TABLE_COMMENT"] or "") for t in tables}

    # 逐表获取 CREATE TABLE（避免单次查询过多）
    docs: list[dict] = []
    for name in table_names:
        create_sql = get_table_schema([name])
        if not create_sql:
            continue
        desc = _build_table_description(name, table_comments[name], create_sql)
        docs.append({
            "table_name": name,
            "table_comment": table_comments[name],
            "create_sql": create_sql,
            "description": desc,
        })
    print(f"  成功获取 {len(docs)} 张表的建表语句")

    print("[3/4] Embedding + 创建 Milvus collection...")
    embeddings = ZhipuAIEmbeddings(model="embedding-3")
    client = MilvusClient(uri=MILVUS_URI)

    if client.has_collection(COLLECTION_NAME):
        client.drop_collection(COLLECTION_NAME)

    # 向量维度
    dim = 2048

    schema = client.create_schema(auto_id=True, enable_dynamic_field=True)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("table_name", DataType.VARCHAR, max_length=256)
    schema.add_field("table_comment", DataType.VARCHAR, max_length=1024)
    schema.add_field("create_sql", DataType.VARCHAR, max_length=65535)
    schema.add_field("description", DataType.VARCHAR, max_length=65535)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)

    index_params = client.prepare_index_params()
    index_params.add_index(field_name="vector", metric_type="COSINE", index_type="HNSW")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        schema=schema,
        index_params=index_params,
    )

    print("[4/4] 分批插入 Milvus...")
    descriptions = [d["description"] for d in docs]
    total = 0
    for i in range(0, len(docs), BATCH_SIZE):
        batch_docs = docs[i:i + BATCH_SIZE]
        batch_descs = descriptions[i:i + BATCH_SIZE]
        batch_vectors = embeddings.embed_documents(batch_descs)
        data = [
            {
                "table_name": d["table_name"],
                "table_comment": d["table_comment"],
                "create_sql": d["create_sql"],
                "description": d["description"],
                "vector": v,
            }
            for d, v in zip(batch_docs, batch_vectors)
        ]
        client.insert(collection_name=COLLECTION_NAME, data=data)
        total += len(data)
        print(f"  已插入第 {i // BATCH_SIZE + 1} 批，共 {len(data)} 条")

    client.flush(COLLECTION_NAME)
    print(f"完成！共插入 {total} 张表的 Schema 到 Milvus collection: {COLLECTION_NAME}")


if __name__ == "__main__":
    build()
