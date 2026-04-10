"""Schema 感知（B+C 混合方案）：向量粗筛 + LLM 精选 + 常驻公共表。"""

import os
import re

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.text2sql.prompts import TABLE_SELECTION_PROMPT
from app.text2sql.sql_executor import get_table_schema

load_dotenv()
MODEL = os.environ["MODEL_ID"]

# 常驻公共表：每次查询自动带上，不依赖检索
PUBLIC_TABLES = ["sys_static", "sys_city"]


def _clean_llm_output(text: str) -> str:
    """清理 LLM 输出中的思考标签、markdown 等干扰内容。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```[a-z]*\n?", "", text)
    return text.strip()


def _extract_key_columns(create_sql: str) -> str:
    """从 CREATE TABLE 语句中提取关键字段摘要（字段名+注释）。"""
    columns = []
    for line in create_sql.split("\n"):
        line = line.strip()
        if not line.startswith("`") or line.startswith("PRIMARY") or line.startswith("KEY"):
            continue
        col_match = re.match(r"`(\w+)`", line)
        if not col_match:
            continue
        col_name = col_match.group(1)
        if col_name in ("id", "token", "add_time", "update_time", "is_deleted", "add_by"):
            continue
        comment_match = re.search(r"COMMENT\s+'([^']*)'", line)
        comment = comment_match.group(1) if comment_match else ""
        columns.append(f"{col_name}({comment})" if comment else col_name)
    return ", ".join(columns[:8])


def llm_select_tables(question: str, candidates: list[dict]) -> list[str]:
    """LLM 从候选表中精选出真正需要的表（带关键字段信息）。"""
    table_list = "\n".join(
        f"- {c['table_name']}: {c['table_comment'] or '无注释'} | 关键字段: {_extract_key_columns(c['create_sql'])}"
        for c in candidates
    )
    valid_names = {c["table_name"] for c in candidates}

    llm = ChatOpenAI(model=MODEL, temperature=0)
    prompt = TABLE_SELECTION_PROMPT.format(table_list=table_list, question=question)
    resp = llm.invoke(prompt)
    content = _clean_llm_output(resp.content or "")

    selected = [
        name.strip()
        for name in content.split(",")
        if name.strip() in valid_names
    ]
    return selected


def build_schema(question: str, schema_candidates: list[dict]) -> tuple[str, list[str]]:
    """从向量检索候选中经 LLM 精选，合并常驻表，返回最终 Schema。"""
    if not schema_candidates:
        return "", []

    # LLM 精选
    selected_names = llm_select_tables(question, schema_candidates)
    if not selected_names:
        selected_names = [c["table_name"] for c in schema_candidates[:5]]

    # 合并常驻公共表（去重）
    all_names = list(dict.fromkeys(selected_names + PUBLIC_TABLES))

    # 从候选中取 CREATE TABLE，候选中没有的（常驻表）从数据库实时获取
    candidate_map = {c["table_name"]: c["create_sql"] for c in schema_candidates}
    schemas = []
    for name in all_names:
        if name in candidate_map:
            schemas.append(candidate_map[name])
        else:
            sql = get_table_schema([name])
            if sql:
                schemas.append(sql)

    print(f"  向量候选 top-3: {[c['table_name'] for c in schema_candidates[:3]]}")
    print(f"  LLM 精选: {selected_names}")
    print(f"  最终表（含常驻）: {all_names}")

    return "\n\n".join(schemas), all_names
