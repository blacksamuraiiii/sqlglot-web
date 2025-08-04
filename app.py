import os
import re
import streamlit as st
import sqlglot
from dotenv import load_dotenv
from openai import OpenAI

# 加载环境变量
load_dotenv(".env")

# 从环境变量中获取配置
base_url = os.getenv("base_url")
api_key = os.getenv("api_key")

# 支持的 SQL 方言列表
DIALECTS = [
    "athena",
    "bigquery",
    "clickhouse",
    "databricks",
    "doris",
    "drill",
    "druid",
    "duckdb",
    "dune",
    "hive",
    "materialize",
    "mysql",
    "oracle",
    "postgres",
    "presto",
    "prql",
    "redshift",
    "risingwave",
    "snowflake",
    "spark",
    "spark2",
    "sqlite",
    "starrocks",
    "tableau",
    "teradata",
    "trino",
    "tsql",
]

# 定义辅助函数
def transpile_single_sql(sql_statement, read_dialect, write_dialect, pretty):
    """
    辅助函数，用于转换单个SQL语句或返回SQL片段。
    会尝试转换，如果失败（例如因为是片段或错误），则返回原始语句（可能带错误注释）。
    """
    sql_statement = sql_statement.strip()
    if not sql_statement:
        return ""

    try:
        transpiled_list = sqlglot.transpile(sql_statement, read=read_dialect, write=write_dialect, pretty=pretty)
        return transpiled_list[0] if transpiled_list else "" # 确保列表不为空
    except sqlglot.errors.ParseError:
        # 对于无法单独解析的片段或实际的语法错误。
        return sql_statement # 按原样返回，可能后续由LLM处理或作为更大结构的一部分
    except sqlglot.errors.UnsupportedError as e:
        return f"-- 不支持的转换特性: {e}\n{sql_statement}"
    except Exception as e:
        # 其他转换错误
        return f"-- 转换错误: {e}\n{sql_statement}"

# 定义转换按钮点击的回调函数
def handle_conversion():
    """
    处理SQL转换按钮点击事件的回调函数。
    会读取输入框和下拉框的值，执行转换并更新session_state。
    """
    input_sql_val = st.session_state.input_sql_area
    from_dialect_val = st.session_state.from_dialect_select
    to_dialect_val = st.session_state.to_dialect_select

    if input_sql_val:
        # 调用转换函数
        converted_result = convert_sql(input_sql_val, from_dialect_val, to_dialect_val)
        # 更新 session state 中的输出结果
        st.session_state.output_sql_value = converted_result
    else:
        # 更新 session state 中的输出结果
        st.session_state.output_sql_value = "请输入SQL"

# sql转化函数
def convert_sql(sql_text, from_dialect, to_dialect, pretty=True):
    """
    使用 SQLGlot 和 LLM 增强实现SQL方言转换，处理复杂SQL结构。
    能够识别和处理普通SQL、PL/SQL块、ZTC_SQLZZ动态SQL、注释块内的SQL、行注释和空行。
    """

    plsql_pattern = re.compile(
        r"""
        ((CREATE\s+(OR\s+REPLACE\s+)?(PROCEDURE|FUNCTION)\s+[\s\S]*?END\s*([A-Za-z0-9_]+)?\s*;)| # CREATE PROCEDURE/FUNCTION
        (\bDECLARE\b[\s\S]*?END\s*;)| # DECLARE ... END;
        (\bBEGIN\b[\s\S]*?END\s*;)) # BEGIN ... END; (匿名块)
        """,
        re.IGNORECASE | re.VERBOSE
    )
    ztc_sqlzz_pattern = re.compile(r"ZTC_SQLZZ\s*\(\s*'([\s\S]*?)'\s*\)\s*;", re.IGNORECASE)
    comment_block_pattern = re.compile(r"/\*([\s\S]*?)\*/", re.IGNORECASE)

    # 新增的 Oracle PROCEDURE 转换特定模式 (用于 Oracle -> PostgreSQL 的 CREATE OR REPLACE PROCEDURE)
    # 该模式匹配完整的 "CREATE [OR REPLACE] PROCEDURE name IS [declarations] BEGIN [body] END name;" 结构
    oracle_procedure_specific_pattern = re.compile(
        r"""^\s*
            (CREATE\s+(OR\s+REPLACE\s+)?PROCEDURE\s+([a-zA-Z0-9_."]+)) # Group 1: Full "CREATE [OR REPLACE] PROCEDURE proc_name", Group 3: proc_name
            \s+IS\s+
            ([\s\S]*?)                                               # Group 4: Declarations (between IS and BEGIN)
            BEGIN\s+
            ([\s\S]+?)                                               # Group 5: Body (between BEGIN and END proc_name;)
            \s*END\s+\3\s*;                                          # Match "END proc_name;" using backreference to group 3
            \s*$""",
        re.IGNORECASE | re.VERBOSE | re.DOTALL
    )

    def process_plain_segment_with_comments_and_empty_lines(segment_text, read_dialect, write_dialect, pretty_format):
        """
        处理普通SQL片段，保留行注释和空行，并转换SQL语句。
        """
        parts = []
        lines = segment_text.splitlines(keepends=True)
        sql_batch = []

        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith('--'):
                if sql_batch:
                    parts.append(transpile_single_sql("".join(sql_batch), read_dialect, write_dialect, pretty_format))
                    sql_batch = []
                parts.append(line)
            elif not stripped_line:
                if sql_batch:
                    parts.append(transpile_single_sql("".join(sql_batch), read_dialect, write_dialect, pretty_format))
                    sql_batch = []
                parts.append(line)
            else:
                sql_batch.append(line)

        if sql_batch:
            parts.append(transpile_single_sql("".join(sql_batch), read_dialect, write_dialect, pretty_format))
        
        return "".join(parts)

    def process_comment_block_content(comment_inner_content, read_dialect, write_dialect, pretty_format):
        """
        处理注释块 /* ... */ 内部的内容。
        主要目标是转换内部的 ZTC_SQLZZ 语句，并保留其他注释内容。
        """
        processed_comment_parts = []
        current_comment_pos = 0
        
        internal_ztc_matches = sorted(list(ztc_sqlzz_pattern.finditer(comment_inner_content)), key=lambda m: m.start())

        if not internal_ztc_matches:
            return comment_inner_content 

        for ztc_match in internal_ztc_matches:
            processed_comment_parts.append(comment_inner_content[current_comment_pos:ztc_match.start()])
            
            ztc_block_text = ztc_match.group(0)
            ztc_inner_sql = ztc_match.group(1).strip()
            if ztc_inner_sql:
                transpiled_ztc_inner_sql = transpile_single_sql(ztc_inner_sql, read_dialect, write_dialect, pretty_format)
                processed_comment_parts.append(f"ZTC_SQLZZ('\n{transpiled_ztc_inner_sql}\n');")
            else:
                processed_comment_parts.append(ztc_block_text) 
            current_comment_pos = ztc_match.end()
            
        processed_comment_parts.append(comment_inner_content[current_comment_pos:])
        return "".join(processed_comment_parts)

    if not sql_text.strip():
        return ""

    if plsql_pattern.fullmatch(sql_text.strip()): # 整个输入是一个PL/SQL块
        # 首先处理 Oracle 到 PostgreSQL 的特定 PROCEDURE 转换 (代码内转换)
        if from_dialect == 'oracle' and to_dialect == 'postgres':
            specific_match = oracle_procedure_specific_pattern.fullmatch(sql_text.strip())
            if specific_match:
                # 提取 Oracle 过程的各个部分
                procedure_creation_statement = specific_match.group(1) # 例如 "CREATE OR REPLACE PROCEDURE P_TEST"
                declarations = specific_match.group(4).strip()         # IS 和 BEGIN 之间的声明
                body = specific_match.group(5).strip()                 # BEGIN 和 END name; 之间的过程体

                # 递归调用 convert_sql 转换过程体
                # 这确保了过程体内部的SQL、ZTC_SQLZZ、注释等能被正确处理
                converted_body = convert_sql(body, from_dialect, to_dialect, pretty)

                # 构建 PostgreSQL 过程的字符串列表
                pg_parts = [f"{procedure_creation_statement} LANGUAGE plpgsql AS $$\n"]
                if declarations: # 只有当声明部分不为空时才添加
                    pg_parts.append(f"{declarations}\n")
                pg_parts.append("BEGIN\n")
                pg_parts.append(converted_body) # 转换后的过程体
                pg_parts.append("\nEND;\n$$")
                
                return "".join(pg_parts) # 返回拼接后的PostgreSQL过程代码

            # 如果不是上述特定 PROCEDURE 结构，但仍是 Oracle->PostgreSQL 的 PL/SQL 块，则使用LLM
            # (例如 FUNCTION, DECLARE块, BEGIN块, 或不符合特定 PROCEDURE 格式的 PROCEDURE)
            upper_sql_text = sql_text.strip().upper()
            if upper_sql_text.startswith('CREATE OR REPLACE PROCEDURE') or upper_sql_text.startswith('CREATE PROCEDURE') \
               or upper_sql_text.startswith('CREATE OR REPLACE FUNCTION') or upper_sql_text.startswith('CREATE FUNCTION'):
                content_for_llm = f"将此 Oracle PL/SQL 过程或函数转换为 PostgreSQL 过程或函数 (例如 CREATE OR REPLACE PROCEDURE ... LANGUAGE plpgsql AS $$ BEGIN ... END; $$ 或 CREATE OR REPLACE FUNCTION ... RETURNS ... LANGUAGE plpgsql AS $$ BEGIN ... END; $$)。原始SQL是：\n{sql_text}"
                return call_xiyansql(base_url, api_key, sql_text, content=content_for_llm)
            elif upper_sql_text.startswith('DECLARE') or upper_sql_text.startswith('BEGIN'):
                content_for_llm = f"将此 Oracle PL/SQL 块 (DECLARE ... BEGIN ... END; 或 BEGIN ... END;) 转换为 PostgreSQL 的 PL/pgSQL 块 (DO $$ DECLARE ... BEGIN ... END $$;)。原始SQL是：\n{sql_text}"
                return call_xiyansql(base_url, api_key, sql_text, content=content_for_llm)
            else: # 其他 Oracle PL/SQL 块 (理论上不应到这里，因为 plsql_pattern.fullmatch 已经匹配，且上面条件未覆盖)
                  # 但为保险起见，提供一个通用转换提示
                content_for_llm = f"将此 {from_dialect} PL/SQL 块转换为 {to_dialect} PL/SQL 块。原始SQL是：\n{sql_text}"
                return call_xiyansql(base_url, api_key, sql_text, content=content_for_llm)

        # 对于其他方言的 PL/SQL 块 (非 Oracle->PostgreSQL)，或者源/目标方言不匹配上述条件
        content_for_llm = f"将此 {from_dialect} PL/SQL 块转换为 {to_dialect}。原始SQL是：\n{sql_text}"
        return call_xiyansql(base_url, api_key, sql_text, content=content_for_llm)

    processed_sql_parts = []
    current_position = 0
    
    all_found_matches = []
    for match in plsql_pattern.finditer(sql_text):
        all_found_matches.append({'type': 'plsql', 'match_obj': match, 'start': match.start(), 'end': match.end()})
    for match in ztc_sqlzz_pattern.finditer(sql_text):
        all_found_matches.append({'type': 'ztc', 'match_obj': match, 'start': match.start(), 'end': match.end()})
    for match in comment_block_pattern.finditer(sql_text):
        all_found_matches.append({'type': 'comment', 'match_obj': match, 'start': match.start(), 'end': match.end()})

    all_found_matches.sort(key=lambda x: (x['start'], -(x['end'] - x['start'])))

    unique_matches = []
    last_processed_end = -1
    for m_info in all_found_matches:
        if m_info['start'] >= last_processed_end:
            unique_matches.append(m_info)
            last_processed_end = m_info['end']
    
    unique_matches.sort(key=lambda x: x['start'])

    if not unique_matches:
        return process_plain_segment_with_comments_and_empty_lines(sql_text, from_dialect, to_dialect, pretty)

    for item_info in unique_matches:
        match_obj = item_info['match_obj']
        
        plain_sql_before = sql_text[current_position:match_obj.start()]
        if plain_sql_before:
            processed_sql_parts.append(process_plain_segment_with_comments_and_empty_lines(plain_sql_before, from_dialect, to_dialect, pretty))
        
        block_text = match_obj.group(0)
        if item_info['type'] == 'plsql':
            # 使用全局加载的 base_url 和 api_key
            content_for_llm = f"将此 {from_dialect} PL/SQL 块转换为 {to_dialect}"
            # 检查是否为 Oracle 到 PostgreSQL 的转换，并且是过程、函数、匿名块或DECLARE块
            if from_dialect == 'oracle' and to_dialect == 'postgres':
                # 转换为大写以便检查关键字
                upper_block_text = block_text.strip().upper()
                if upper_block_text.startswith('CREATE OR REPLACE PROCEDURE') or upper_block_text.startswith('CREATE PROCEDURE') \
                   or upper_block_text.startswith('CREATE OR REPLACE FUNCTION') or upper_block_text.startswith('CREATE FUNCTION'):
                    content_for_llm = f"将此 Oracle PL/SQL 过程或函数转换为 PostgreSQL 过程或函数 (例如 CREATE OR REPLACE PROCEDURE ... LANGUAGE plpgsql AS $$ BEGIN ... END; $$ 或 CREATE OR REPLACE FUNCTION ... RETURNS ... LANGUAGE plpgsql AS $$ BEGIN ... END; $$)。原始SQL是：\n{block_text}"
                elif upper_block_text.startswith('DECLARE') or upper_block_text.startswith('BEGIN'):
                    content_for_llm = f"将此 Oracle PL/SQL 块 (DECLARE ... BEGIN ... END; 或 BEGIN ... END;) 转换为 PostgreSQL 的 PL/pgSQL 块 (DO $$ DECLARE ... BEGIN ... END $$;)。原始SQL是：\n{block_text}"
            processed_sql_parts.append(call_xiyansql(base_url, api_key, block_text, content=content_for_llm))
        elif item_info['type'] == 'ztc':
            inner_sql = match_obj.group(1).strip()
            if inner_sql:
                transpiled_inner_sql = transpile_single_sql(inner_sql, from_dialect, to_dialect, pretty)
                processed_sql_parts.append(f"ZTC_SQLZZ('\n{transpiled_inner_sql}\n');")
            else:
                processed_sql_parts.append(block_text)
        elif item_info['type'] == 'comment':
            comment_inner_content = match_obj.group(1)
            processed_inner_comment = process_comment_block_content(comment_inner_content, from_dialect, to_dialect, pretty)
            processed_sql_parts.append(f"/*{processed_inner_comment}*/")
            
        current_position = match_obj.end()

    plain_sql_after = sql_text[current_position:]
    if plain_sql_after:
        processed_sql_parts.append(process_plain_segment_with_comments_and_empty_lines(plain_sql_after, from_dialect, to_dialect, pretty))

    return "".join(p for p in processed_sql_parts if p)

# 调用析言SQL模型
def call_xiyansql(base_url, api_key, sql, content=None):
    """
    调用析言SQL模型
    """
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    # 优化消息构建逻辑
    user_content = sql
    if content:
        user_content += f'''需求描述：{content}'''

    response = client.chat.completions.create(
        model='Qwen/Qwen2.5-72B-Instruct',
        messages=[
            {
                'role': 'system',
                'content': '你是一个专业的SQL转换助手。请将用户提供的SQL代码从源方言完整地转换为目标方言。确保返回的是完整且可直接执行的SQL代码，不要省略任何部分，包括特殊字符和完整的格式化。仅返回转换后的SQL语句，不包含任何解释性文字或其他内容。'
            },
            {
                'role': 'user',
                'content': user_content
            },
        ],
        temperature=0.1,
        max_tokens=4096,
        stream=False
    )
    return response.choices[0].message.content

# 设置页面标题
st.set_page_config(layout="wide", page_title="SQL方言转换")
st.title('SQL方言转换')

# 初始化 session state 中的输出结果
if 'output_sql_value' not in st.session_state:
    st.session_state.output_sql_value = ""
if 'input_sql_area' not in st.session_state:
    st.session_state.input_sql_area = ""

# 创建两列用于选择方言和转换按钮
col1, col2, col3 = st.columns([12, 1, 12])

with col1:
    # 源方言选择下拉框
    from_dialect = st.selectbox(
        '选择源方言:',
        DIALECTS,
        index=DIALECTS.index('oracle') if 'oracle' in DIALECTS else 0, # 默认选择oracle
        key='from_dialect_select' # 添加key
    )

with col2:
    # 转换按钮
    st.write("<br>", unsafe_allow_html=True) # 添加一些垂直空间
    # 使用 on_click 参数绑定回调函数
    convert_button = st.button('⇄', on_click=handle_conversion)

with col3:
    # 目标方言选择下拉框
    to_dialect = st.selectbox(
        '选择目标方言:',
        DIALECTS,
        index=DIALECTS.index('postgres') if 'postgres' in DIALECTS else 0, # 默认选择postgres
        key='to_dialect_select' # 添加key
    )

# 创建两列用于输入和输出SQL
input_col, output_col = st.columns(2)

with input_col:
    # 输入SQL文本区域
    # input_sql 的值通过 st.session_state.input_sql_area 访问
    st.text_area('输入原始SQL:', height=300, key='input_sql_area')

with output_col:
    # 输出SQL文本区域
    # output_sql 的值通过 st.session_state.output_sql_value 更新
    st.text_area('转换结果:', value=st.session_state.output_sql_value, height=300, disabled=True, key='output_sql_area')