"""MySQL 数据库连接与 SQL 执行。"""

import os

import pymysql
from dotenv import load_dotenv

load_dotenv()

QUERY_TIMEOUT = 30  # 秒
MAX_ROWS = 500


def _get_connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.environ["MYSQL_HOST"],
        port=int(os.environ["MYSQL_PORT"]),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DATABASE"],
        charset="utf8mb4",
        read_timeout=QUERY_TIMEOUT,
        cursorclass=pymysql.cursors.DictCursor,
    )


def execute_sql(sql: str) -> tuple[list[dict], list[str]]:
    """执行 SQL 并返回 (结果行列表, 列名列表)。"""
    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchmany(MAX_ROWS)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            return rows, columns
    finally:
        conn.close()


def get_all_tables() -> list[dict]:
    """获取数据库中所有表名和表注释。"""
    sql = """
        SELECT TABLE_NAME, TABLE_COMMENT
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, (os.environ["MYSQL_DATABASE"],))
            return cursor.fetchall()
    finally:
        conn.close()


def get_table_schema(table_names: list[str]) -> str:
    """获取指定表的 CREATE TABLE 语句（含字段注释）。"""
    conn = _get_connection()
    schemas = []
    try:
        with conn.cursor() as cursor:
            for name in table_names:
                cursor.execute(f"SHOW CREATE TABLE `{name}`")
                row = cursor.fetchone()
                if row:
                    schemas.append(row.get("Create Table", ""))
        return "\n\n".join(schemas)
    finally:
        conn.close()
