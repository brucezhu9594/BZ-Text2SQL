"""表关系图谱 + 业务语义标注。

提供给 SQL 生成 Prompt，帮助 LLM 正确写 JOIN 条件和理解字段含义。
"""

# 字典表使用说明
DICT_TABLE_GUIDE = """\
【字典表 sys_static 使用规则】
sys_static 是通用字典表，结构：code(字典类型), value(编码值), label(显示文字)。
关联方式固定为：JOIN sys_static AS s ON s.value = 源表.字段 AND s.code = '字典类型'
务必加条件：s.is_deleted = 0

常用字典 code 对照：
- gb_company_scale: 公司规模（1=20人以下, 2=20-99人, 3=100-499人, 4=500-999人, 5=1000-9999人, 6=10000人以上）
- gb_company_type: 公司性质（1=民营, 2=外资, 3=合资, 4=国营, 5=上市公司, 6=合资公司, 7=事业/事业单位）
- gb_company_stage: 发展阶段（1=初创/天使轮, 3=A轮, 4=B轮, 5=C轮, 6=D轮及以上, 8=不需要融资）
- gb_industry: 行业类别（10000=医药, 10001=化妆品/美妆, ...）
- gb_education: 学历（1=初中, 2=高中, 3=中专, 4=大专, 5=本科, 6=硕士, 7=博士）
- gb_sex: 性别（1=男, 2=女）
- gb_work_time: 工作经验
- gb_salary_scope: 薪资范围
- gb_jd_type: 职位类型"""

# 核心表关系图谱
TABLE_RELATIONS = """\
【表关系图谱（JOIN 条件参考）】
gb_company（公司主表）:
  → gb_company_industry ON gb_company_industry.company_id = gb_company.id（公司行业，一对多）
  → gb_company_industry.industry_id 关联字典: JOIN sys_static ON sys_static.value = gb_company_industry.industry_id AND sys_static.code = 'gb_industry'
  → gb_company.scale 关联字典: JOIN sys_static ON sys_static.value = gb_company.scale AND sys_static.code = 'gb_company_scale'
  → gb_company.type 关联字典: JOIN sys_static ON sys_static.value = gb_company.type AND sys_static.code = 'gb_company_type'
  → gb_company.stage 关联字典: JOIN sys_static ON sys_static.value = gb_company.stage AND sys_static.code = 'gb_company_stage'
  → gb_company.city_id 关联城市: JOIN sys_city ON sys_city.id = gb_company.city_id

gb_jd（职位主表）:
  → gb_company ON gb_company.id = gb_jd.company_id（所属公司）
  → gb_jd_address ON gb_jd_address.jd_id = gb_jd.id（工作地址，一对多）
  → gb_jd_benefit ON gb_jd_benefit.jd_id = gb_jd.id（职位福利，一对多）
  → gb_jd.education 关联字典: JOIN sys_static ON sys_static.value = gb_jd.education AND sys_static.code = 'gb_jd_education'
  → gb_jd.type 关联字典: JOIN sys_static ON sys_static.value = gb_jd.type AND sys_static.code = 'gb_jd_type'

gb_profile_basic（候选人主表）:
  → gb_profile_edu ON gb_profile_edu.profile_id = gb_profile_basic.id（教育经历，一对多）
  → gb_profile_job ON gb_profile_job.profile_id = gb_profile_basic.id（工作经历，一对多）
  → gb_profile_intent ON gb_profile_intent.profile_id = gb_profile_basic.id（求职意向）
  → gb_profile_skill ON gb_profile_skill.profile_id = gb_profile_basic.id（技能）
  → gb_profile_basic.sex 关联字典: JOIN sys_static ON sys_static.value = gb_profile_basic.sex AND sys_static.code = 'gb_sex'
  → gb_profile_basic.education 关联字典: JOIN sys_static ON sys_static.value = gb_profile_basic.education AND sys_static.code = 'gb_education'

gb_jd_profile（投递记录表）:
  → gb_jd ON gb_jd.id = gb_jd_profile.jd_id（关联职位）
  → gb_profile_basic ON gb_profile_basic.id = gb_jd_profile.profile_id（关联候选人）
  → gb_company ON gb_company.id = gb_jd_profile.company_id（关联公司）

gb_user_hh（B端用户/HR表）:
  → gb_user_company ON gb_user_company.user_id = gb_user_hh.id（关联用户公司）
  → gb_company ON gb_company.id = gb_user_company.company_id（关联公司）

sys_city（城市表）:
  层级关系：p_id=0 为省份，p_id=省份id 为城市，p_id=城市id 为区县"""

# 业务语义标注
BUSINESS_NOTES = """\
【业务语义标注】
- 时间字段：大部分表用 int(10) 存 Unix 时间戳，查询时用 FROM_UNIXTIME() 转换；少部分表用 datetime
- 软删除：所有表查询时务必加 is_deleted = 0
- WHERE 条件原则：除了 is_deleted = 0 是必加的，其他过滤条件（status、is_open、is_show、is_recommend、is_new、is_virtual 等）只有在用户问题明确涉及时才加，不要自行添加用户未提及的过滤条件
- 一对多 JOIN 去重：当主表与子表是一对多关系时（如一个公司有多个行业），如果用户要求按主表实体计数或排序，必须用 GROUP BY 主表主键，子表字段用 GROUP_CONCAT() 聚合
- gb_company.status: 1=上线, 2=待审核, 3=猎企合作关系待审核
- gb_jd.status: 1=在线, 2=暂停, 3=关闭
- gb_jd_profile.status: 投递状态，不同值代表不同流程阶段
- gb_company.is_virtual: 1=虚拟公司, 0=真实公司"""


def get_relation_context() -> str:
    """返回拼接好的关系图谱 + 字典说明 + 业务标注，供 SQL 生成 prompt 使用。"""
    return f"{DICT_TABLE_GUIDE}\n\n{TABLE_RELATIONS}\n\n{BUSINESS_NOTES}"
