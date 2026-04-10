"""Prompt 模板。"""

TABLE_SELECTION_PROMPT = """\
你是一个数据库专家。根据用户的问题，从下面的候选表中选出生成 SQL 需要用到的表。

【候选表】
{table_list}

【注意】
1. 字典表 sys_static、城市表 sys_city、职类表 gb_position 已自动包含，无需再选
2. 优先选主表（如 gb_company 是公司主表，gb_market_company 只是营销统计表）
3. 如果字段是编码值（如 scale、type），需要关联 sys_static 字典表翻译

【用户问题】
{question}

请只输出相关的表名，用英文逗号分隔，不要输出任何其他内容。
例如：gb_jd,gb_company,gb_profile_basic"""

SQL_GENERATION_PROMPT = """\
你是一个 MySQL 8.0 SQL 专家。根据下面提供的所有知识生成 SQL 查询。

【数据库 Schema】
{schema}

【相似查询示例（请参考这些示例的写法）】
{examples}

【业务知识】
{business_docs}

【表关系与 JOIN 条件】
{table_relations}

【规则】
1. 只生成一条 SELECT 语句
2. 使用表别名提高可读性
3. 查询必须带 LIMIT，默认 LIMIT 50
4. 时间字段是 Unix 时间戳（int(10)），用 FROM_UNIXTIME() 转换显示
5. 关联字典表时严格按【表关系与 JOIN 条件】中的写法，不要自己猜
6. 严格遵守【业务知识】中的所有规则
7. 优先参考【相似查询示例】中的 SQL 写法
8. 只输出 SQL，不要输出任何解释，不要用 markdown 代码块包裹

【用户问题】
{question}"""

SQL_FIX_PROMPT = """\
你是一个 MySQL 8.0 SQL 专家。上一次生成的 SQL 执行报错，请修正。

【数据库 Schema】
{schema}

【相似查询示例】
{examples}

【业务知识】
{business_docs}

【表关系与 JOIN 条件】
{table_relations}

【原始 SQL】
{sql}

【错误信息】
{error}

【规则】
1. 只生成修正后的 SELECT 语句
2. 必须带 LIMIT
3. 严格按【表关系与 JOIN 条件】和【相似查询示例】的写法
4. 只输出 SQL，不要输出任何解释，不要用 markdown 代码块包裹

【用户问题】
{question}"""

RESULT_INTERPRETATION_PROMPT = """\
你是一个数据分析助手。下面是用户问题和已执行的 SQL 查询结果，请直接基于查询结果回答。

【用户问题】
{question}

【查询结果】
{result}

【要求】
1. 直接基于上面的查询结果回答，不要编造数据
2. 用简洁的中文回答，将结果组织成易读的格式
3. 如果结果为空，说明没有查到匹配的数据
4. 不要提及 SQL、数据库、查询等技术细节"""
