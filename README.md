# BZ-Text2SQL

自然语言转 SQL 查询 Agent，基于 **4 路向量知识检索 + LLM** 架构，将用户的中文问题自动转换为 SQL 并执行，直接返回结构化查询结果。

## 系统架构

```
用户问题: "查询最新入驻的10家公司的名称和行业"
        |
        v  embed 一次，共用 query_vector
  +---------------------------------------------+
  |           4 路并行向量检索 (Milvus)            |
  +----------+----------+-----------+-----------+
  | DDL      | Few-shot | 业务文档    | 表关系     |
  | Schema   | 示例      |           |           |
  | top-15   | top-3    | top-5     | top-5     |
  +----+-----+----+-----+-----+-----+-----+----+
       |          |           |           |
       v          v           v           v
  LLM 精选表   注入 Prompt   注入 Prompt  注入 Prompt
  + 常驻公共表
       |
       v
  SQL 生成 (LLM，参考示例写法 + 业务规则 + JOIN 条件)
       |
       v
  安全校验 -> 执行 -> 失败则自愈重试(最多3次)
       |
       v
  格式化表格输出 (原样返回全部查询结果)
```

## 技术栈

| 组件 | 技术选型 |
|------|---------|
| LLM | MiniMax-M2.7 (OpenAI 兼容接口) |
| Embedding | 智谱 embedding-3 (2048 维) |
| 向量数据库 | Milvus (HNSW 索引, COSINE 相似度) |
| 业务数据库 | MySQL 8.0 (retail_2_0，257 张表) |
| Python 框架 | LangChain |

## 项目结构

```
BZ-Text2SQL/
|-- .env                          # 环境变量 (LLM / Embedding / MySQL 配置)
|-- requirements.txt              # Python 依赖
|-- app/
    |-- text2sql/
        |-- agent.py              # 主流程 (4 步编排 + 结果格式化)
        |-- prompts.py            # 3 套 Prompt 模板 (表选择/SQL生成/SQL修正)
        |-- knowledge_build.py    # 一键构建全部 4 个向量知识库
        |-- knowledge_retriever.py# 4 路向量检索 (统一入口)
        |-- schema_build.py       # DDL Schema 入库
        |-- schema_retriever.py   # LLM 精选表 (B+C 混合方案)
        |-- sql_executor.py       # MySQL 连接与执行
        |-- sql_validator.py      # SQL 安全校验
        |-- knowledge/
            |-- examples.json     # 25 条 Few-shot Q&A 示例
            |-- business_docs.json# 16 条业务语义文档
            |-- table_relations.json # 18 条表关系定义
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

编辑 `.env` 文件：

```env
# LLM (OpenAI 兼容接口)
OPENAI_API_KEY=你的API Key
OPENAI_BASE_URL=https://api.minimaxi.com/v1
MODEL_ID=MiniMax-M2.7

# 智谱 Embedding
ZHIPUAI_API_KEY=你的智谱API Key

# MySQL
MYSQL_HOST=数据库地址
MYSQL_PORT=端口
MYSQL_USER=用户名
MYSQL_PASSWORD=密码
MYSQL_DATABASE=retail_2_0
```

### 3. 启动 Milvus

确保 Milvus 服务运行在 `localhost:19530`。

### 4. 构建知识库 (首次运行)

```bash
python -m app.text2sql.knowledge_build
```

该命令一键构建 4 个向量知识库：

| 知识库 | Collection 名称 | 数据来源 | 条目数 |
|-------|----------------|---------|-------|
| DDL Schema | text2sql_schema | MySQL INFORMATION_SCHEMA | 257 (每表一条) |
| Few-shot 示例 | text2sql_examples | knowledge/examples.json | 25 |
| 业务文档 | text2sql_business_docs | knowledge/business_docs.json | 16 |
| 表关系 | text2sql_table_relations | knowledge/table_relations.json | 18 |

### 5. 运行 Agent

```bash
python -m app.text2sql.agent
```

## 执行流程详解

以"查询最新入驻的10家公司的名称和行业"为例：

### Step 1 - 4 路向量知识检索

对用户问题做一次 embedding，同时查询 4 个 Milvus collection：

- **DDL Schema**: 召回 15 张候选表 (gb_company, gb_company_industry, ...)
- **Few-shot 示例**: 召回 3 条相似的历史 Q&A 对
- **业务文档**: 召回 5 条相关的业务规则 (字典关联方式、去重规则等)
- **表关系**: 召回 5 条 JOIN 条件定义

### Step 2 - Schema 感知 (B+C 混合方案)

1. **方案 B (向量粗筛)**: 从 Step 1 的 15 张候选表中提取表名 + 注释 + 关键字段
2. **方案 C (LLM 精选)**: LLM 从候选中选出真正需要的表 (gb_company, gb_company_industry)
3. **常驻表合并**: 自动追加 sys_static (字典表)、sys_city (城市表)
4. 获取选中表的完整 CREATE TABLE 语句

### Step 3 - SQL 生成

将 4 路知识全部注入 Prompt，LLM 参考 Few-shot 示例的写法生成 SQL：

```sql
SELECT c.name AS 公司名称, GROUP_CONCAT(DISTINCT s.label) AS 行业
FROM gb_company c
LEFT JOIN gb_company_industry ci ON ci.company_id = c.id AND ci.is_deleted = 0
LEFT JOIN sys_static s ON s.value = ci.industry_id AND s.code = 'gb_industry' AND s.is_deleted = 0
WHERE c.is_deleted = 0
GROUP BY c.id, c.name
ORDER BY c.add_time DESC
LIMIT 10
```

### Step 4 - 校验 + 执行 (含自愈)

1. **安全校验**: 只允许 SELECT/WITH，禁止 DROP/DELETE/UPDATE 等
2. **执行查询**: 连接 MySQL 执行
3. **自愈重试**: 若执行报错，将错误信息反馈给 LLM 修正 SQL，最多重试 3 次

### Step 5 - 格式化结果

将查询结果原样格式化为对齐的表格输出，不经过 LLM 二次加工，确保数据完整准确：

```
共 10 条结果:

公司名称                          | 行业
----------------------------------+--------------------------
南昌择仕人力资源有限公司            |
南京水杯子科技股份有限公司          |
有详细地点的公司                    | 奢侈品
没有地点的公司                      | 其他, 珠宝/精品
五八五八就五八                      | 箱包, 珠宝/精品, 化妆品/彩妆
```

## 4 路知识库说明

### DDL Schema

从 MySQL `INFORMATION_SCHEMA` 读取所有表的 `CREATE TABLE` 语句，包含字段名、类型、注释，embedding 后存入向量库。用于根据用户问题找到相关的表结构。

### Few-shot 示例 (examples.json)

人工编写的高质量 Q&A 对，覆盖常见查询模式：

- 公司查询 (规模、行业、性质、融资阶段)
- 职位查询 (学历要求、薪资、城市分布)
- 候选人查询 (注册、学历统计)
- 投递/招聘统计
- 聚合统计 (GROUP BY、COUNT)

**作用**: LLM 直接模仿正确示例的写法，不需要自己推理 JOIN 条件和字典关联方式。这是提升准确率最有效的手段。

**扩展方式**: 遇到 LLM 生成错误的 SQL 时，人工修正后追加到 `examples.json`，重新执行 `knowledge_build` 即可。

### 业务文档 (business_docs.json)

记录 CREATE TABLE 中无法表达的业务知识：

- sys_static 字典表的固定关联方式 (`value` + `code`，不是 `id`)
- 各字典 code 与取值的对照表
- 时间字段处理规则 (Unix 时间戳)
- 软删除规则 (所有表加 `is_deleted = 0`)
- WHERE 条件原则 (只加用户明确提及的过滤条件)
- 一对多 JOIN 去重规则 (GROUP BY + GROUP_CONCAT)
- 核心主表说明 (区分主表与派生表)

### 表关系 (table_relations.json)

精确定义表与表之间的 JOIN 条件：

```
gb_company_industry.industry_id
  -> sys_static.value (WHERE code = 'gb_industry')

gb_company.scale
  -> sys_static.value (WHERE code = 'gb_company_scale')

gb_jd.company_id -> gb_company.id
```

避免 LLM 猜测 JOIN 条件导致查询错误。

## SQL 安全机制

- **只读**: 仅允许 SELECT / WITH 语句
- **黑名单**: 禁止 DROP、DELETE、UPDATE、INSERT、ALTER、TRUNCATE、CREATE、REPLACE、RENAME、GRANT、REVOKE
- **嵌套限制**: 子查询不超过 5 层
- **查询超时**: 30 秒
- **行数限制**: 最多返回 500 行
- **注释清理**: 校验前移除 SQL 注释，防止注释内绕过检测

## 设计决策

### 为什么用 4 路向量检索而不是把规则硬编码在 Prompt 中？

1. **可扩展**: 新增业务规则只需编辑 JSON 文件 + 重建知识库，无需改代码
2. **精准召回**: 257 张表不可能全塞进 Prompt，向量检索只召回相关内容
3. **token 节省**: 只注入与当前问题相关的知识，而非全部规则

### 为什么 Schema 检索用 B+C 混合方案？

- **方案 B (向量检索)**: 解决用户语言与表名之间的词汇鸿沟 ("公司数量" -> gb_company)
- **方案 C (LLM 精选)**: 理解跨表关联 ("公司和行业" -> 需要 gb_company + gb_company_industry)
- **常驻公共表**: sys_static 等字典表与用户问题语义无关，向量检索永远召回不到，必须自动带上

### 为什么 Few-shot 示例是提升效果最大的手段？

LLM 不需要"理解"业务规则，直接**模仿**正确示例。JOIN 条件、WHERE 条件、GROUP BY 写法都在示例里，LLM 照着来。积累越多示例，覆盖面越广，准确率持续上升。

## 持续优化

当遇到 LLM 生成错误的 SQL 时：

1. 手动修正 SQL
2. 将正确的 Q&A 对追加到 `knowledge/examples.json`
3. 如涉及新的业务规则，追加到 `knowledge/business_docs.json`
4. 如涉及新的表关系，追加到 `knowledge/table_relations.json`
5. 重新执行 `python -m app.text2sql.knowledge_build`

这样形成**持续学习的飞轮**，系统越用越准。
