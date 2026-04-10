"""SQL 安全校验。"""

import re

FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
    "CREATE", "REPLACE", "RENAME", "GRANT", "REVOKE",
]


def validate_sql(sql: str) -> tuple[bool, str]:
    """校验 SQL 安全性。返回 (是否通过, 错误信息)。"""
    normalized = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)  # 去掉行注释
    normalized = re.sub(r"/\*.*?\*/", "", normalized, flags=re.DOTALL)  # 去掉块注释
    normalized = normalized.strip().upper()

    if not normalized.startswith("SELECT") and not normalized.startswith("WITH"):
        return False, "只允许 SELECT / WITH 查询语句"

    for kw in FORBIDDEN_KEYWORDS:
        pattern = rf"\b{kw}\b"
        if re.search(pattern, normalized):
            return False, f"禁止使用 {kw} 语句"

    if normalized.count("SELECT") > 5:
        return False, "子查询嵌套过深（超过 5 层）"

    return True, ""
