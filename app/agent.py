"""Text2SQL Agent 主流程（4 路向量知识检索版）。"""

import os
import re
import time

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from app.prompts import (
    SQL_GENERATION_PROMPT,
    SQL_FIX_PROMPT,
)
from app.knowledge_retriever import retrieve_all
from app.schema_retriever import build_schema
from app.sql_validator import validate_sql
from app.sql_executor import execute_sql

load_dotenv()
MODEL = os.environ["MODEL_ID"]
MAX_RETRIES = 3


def _clean_llm_output(text: str) -> str:
    """清理 LLM 输出中的思考标签、markdown 代码块等干扰内容。"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```\s*", "", text)
    return text.strip()


def _format_examples(examples: list[dict]) -> str:
    """将 Few-shot 示例格式化为 Prompt 文本。"""
    if not examples:
        return "无相似示例"
    parts = []
    for i, ex in enumerate(examples, 1):
        parts.append(f"示例{i}:\n  问题: {ex['question']}\n  SQL: {ex['sql']}")
    return "\n\n".join(parts)


def _format_docs(docs: list[dict]) -> str:
    """将业务文档格式化为 Prompt 文本。"""
    if not docs:
        return "无相关业务知识"
    return "\n\n".join(f"- {d['content']}" for d in docs)


def _format_relations(relations: list[dict]) -> str:
    """将表关系格式化为 Prompt 文本。"""
    if not relations:
        return "无相关表关系"
    return "\n\n".join(f"- {r['content']}" for r in relations)


def _generate_sql(question: str, schema: str, examples: str,
                   business_docs: str, table_relations: str) -> str:
    """LLM 生成 SQL。"""
    llm = ChatOpenAI(model=MODEL, temperature=0)
    prompt = SQL_GENERATION_PROMPT.format(
        schema=schema, examples=examples,
        business_docs=business_docs, table_relations=table_relations,
        question=question,
    )
    resp = llm.invoke(prompt)
    return _clean_llm_output(resp.content or "")


def _fix_sql(question: str, schema: str, examples: str,
              business_docs: str, table_relations: str,
              sql: str, error: str) -> str:
    """LLM 根据错误信息修正 SQL。"""
    llm = ChatOpenAI(model=MODEL, temperature=0)
    prompt = SQL_FIX_PROMPT.format(
        schema=schema, examples=examples,
        business_docs=business_docs, table_relations=table_relations,
        sql=sql, error=error, question=question,
    )
    resp = llm.invoke(prompt)
    return _clean_llm_output(resp.content or "")


def _format_result(rows: list[dict], columns: list[str]) -> str:
    """将查询结果格式化为表格文本，原样返回所有数据。"""
    if not rows:
        return "查询结果为空，没有匹配的数据。"

    # 计算每列最大宽度（考虑中文字符占 2 个宽度）
    def _display_width(s: str) -> int:
        w = 0
        for c in s:
            w += 2 if '\u4e00' <= c <= '\u9fff' or '\u3000' <= c <= '\u303f' else 1
        return w

    def _pad(s: str, width: int) -> str:
        return s + " " * (width - _display_width(s))

    str_rows = []
    for row in rows:
        str_rows.append([str(row.get(c, "") or "") for c in columns])

    col_widths = [max(_display_width(c), *((_display_width(r[i]) for r in str_rows))) for i, c in enumerate(columns)]

    header = " | ".join(_pad(c, col_widths[i]) for i, c in enumerate(columns))
    separator = "-+-".join("-" * w for w in col_widths)
    lines = [header, separator]
    for r in str_rows:
        lines.append(" | ".join(_pad(r[i], col_widths[i]) for i in range(len(columns))))

    return f"共 {len(rows)} 条结果:\n\n" + "\n".join(lines)


def run(question: str) -> str:
    """Text2SQL Agent 完整流程。"""
    total_start = time.time()

    # 第 1 步：4 路向量知识检索
    print("[1/5] 4 路向量知识检索...")
    t0 = time.time()
    knowledge = retrieve_all(question)
    print(f"  耗时: {time.time() - t0:.2f}s")
    print(f"  Schema 候选: {len(knowledge['schema_candidates'])} 张表")
    print(f"  Few-shot 示例: {len(knowledge['examples'])} 条")
    print(f"  业务文档: {len(knowledge['business_docs'])} 条")
    print(f"  表关系: {len(knowledge['table_relations'])} 条")

    # 第 2 步：Schema 感知（LLM 精选 + 常驻表）
    print("[2/5] Schema 感知：LLM 精选表...")
    t0 = time.time()
    schema, table_names = build_schema(question, knowledge["schema_candidates"])
    print(f"  耗时: {time.time() - t0:.2f}s")
    if not schema:
        return "无法识别与问题相关的数据库表，请换一种方式提问。"
    print(f"  选中表: {', '.join(table_names)}")

    # 格式化知识上下文
    examples_text = _format_examples(knowledge["examples"])
    business_docs_text = _format_docs(knowledge["business_docs"])
    relations_text = _format_relations(knowledge["table_relations"])

    # 第 3 步：生成 SQL
    print("[3/5] 生成 SQL...")
    t0 = time.time()
    sql = _generate_sql(question, schema, examples_text, business_docs_text, relations_text)
    print(f"  耗时: {time.time() - t0:.2f}s")
    print(f"  SQL: {sql}")

    # 第 4 步：校验 + 执行 SQL（含自愈重试）
    print("[4/5] 校验 + 执行 SQL...")
    t0 = time.time()
    passed, err_msg = validate_sql(sql)
    if not passed:
        return f"生成的 SQL 未通过安全校验：{err_msg}"

    last_error = ""
    for attempt in range(MAX_RETRIES):
        try:
            rows, columns = execute_sql(sql)
            break
        except Exception as e:
            last_error = str(e)
            print(f"  执行失败 (第{attempt + 1}次): {last_error}")
            if attempt < MAX_RETRIES - 1:
                print("  尝试修正 SQL...")
                sql = _fix_sql(question, schema, examples_text,
                               business_docs_text, relations_text,
                               sql, last_error)
                print(f"  修正后 SQL: {sql}")
                passed, err_msg = validate_sql(sql)
                if not passed:
                    return f"修正后的 SQL 未通过安全校验：{err_msg}"
    else:
        return f"SQL 执行失败，已重试 {MAX_RETRIES} 次。最后错误：{last_error}"
    print(f"  耗时: {time.time() - t0:.2f}s")

    # 第 5 步：格式化结果
    print("[5/5] 格式化结果...")
    answer = _format_result(rows, columns)

    print(f"\n总耗时: {time.time() - total_start:.2f}s")
    return answer


def main():
    print("Text2SQL Agent (输入 'exit' 退出)")
    print("=" * 50)
    while True:
        question = input("\n请输入问题: ").strip()
        if question.lower() == "exit":
            print("再见！")
            break
        if not question:
            print("请输入内容，不能为空")
            continue

        print()
        answer = run(question)
        print(f"\n回答: {answer}")


if __name__ == "__main__":
    main()
