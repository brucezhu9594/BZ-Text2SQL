"""Schema 精简（当前未启用，保留为扩展点）。"""


def simplify_create_table(create_sql: str) -> str:
    """直接返回原始 CREATE TABLE，不做任何精简。"""
    return create_sql
