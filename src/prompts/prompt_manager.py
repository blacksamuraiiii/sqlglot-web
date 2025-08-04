"""
提示词模板系统
"""
from typing import Dict, Any, Optional
from enum import Enum
import json


class PromptType(Enum):
    """提示词类型"""
    BASIC_CONVERSION = "basic_conversion"
    ORACLE_TO_POSTGRES = "oracle_to_postgres"
    PLSQL_PROCEDURE = "plsql_procedure"
    PLSQL_FUNCTION = "plsql_function"
    PLSQL_BLOCK = "plsql_block"
    ZTC_SQLZZ = "ztc_sqlzz"
    COMPLEX_SQL = "complex_sql"
    ERROR_RECOVERY = "error_recovery"


class PromptTemplate:
    """提示词模板基类"""
    
    def __init__(self, template: str, variables: list = None):
        self.template = template
        self.variables = variables or []
    
    def format(self, **kwargs) -> str:
        """格式化提示词"""
        try:
            # 检查必需变量
            for var in self.variables:
                if var not in kwargs:
                    raise ValueError(f"缺少必需变量: {var}")
            
            # 格式化模板
            return self.template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"模板变量未定义: {e}")
    
    def add_validation_rules(self, rules: list) -> 'PromptTemplate':
        """添加验证规则"""
        validation_section = "\n\n验证要求：\n"
        for i, rule in enumerate(rules, 1):
            validation_section += f"{i}. {rule}\n"
        
        new_template = self.template + validation_section
        return PromptTemplate(new_template, self.variables)


class PromptTemplateManager:
    """提示词模板管理器"""
    
    def __init__(self):
        """初始化模板管理器"""
        self.templates = self._init_templates()
        self.dialect_rules = self._init_dialect_rules()
    
    def _init_templates(self) -> Dict[PromptType, PromptTemplate]:
        """初始化提示词模板"""
        templates = {}
        
        # 基础转换模板
        templates[PromptType.BASIC_CONVERSION] = PromptTemplate(
            """你是一个专业的SQL转换助手。请将用户提供的SQL代码从{from_dialect}方言完整地转换为{to_dialect}方言。

转换要求：
1. 确保转换后的SQL在{to_dialect}中可以正确执行
2. 保持原始SQL的业务逻辑不变
3. 优化语法以符合{to_dialect}的最佳实践
4. 保留注释和格式（如果可能）

原始SQL：
{sql}

请只返回转换后的SQL语句，不要包含任何解释性文字。""",
            variables=['from_dialect', 'to_dialect', 'sql']
        )
        
        # Oracle到PostgreSQL专用模板
        templates[PromptType.ORACLE_TO_POSTGRES] = PromptTemplate(
            """你是一个专业的Oracle到PostgreSQL转换专家。请将以下Oracle SQL转换为PostgreSQL语法。

特殊转换要求：
1. SYSDATE → CURRENT_DATE 或 NOW()
2. TO_CHAR(date, 'YYYYMMDD') → TO_CHAR(date, 'YYYYMMDD')
3. TO_DATE(string, 'yyyy-mm-dd hh24:mi:ss') → TO_TIMESTAMP(string, 'YYYY-MM-DD HH24:MI:SS')
4. DECODE → CASE WHEN
5. CONNECT BY → WITH RECURSIVE
6. (+) 外连接语法 → 标准OUTER JOIN
7. ROWNUM → ROW_NUMBER() 或 LIMIT
8. 包声明和包体 → PostgreSQL函数或模式

Oracle SQL：
{sql}

请返回完整的PostgreSQL SQL语句，确保语法正确性。""",
            variables=['sql']
        )
        
        # PL/SQL过程转换模板
        templates[PromptType.PLSQL_PROCEDURE] = PromptTemplate(
            """请将以下Oracle PL/SQL过程转换为PostgreSQL过程。

转换规则：
1. CREATE OR REPLACE PROCEDURE name IS → CREATE OR REPLACE PROCEDURE name() LANGUAGE plpgsql AS $$
2. 变量声明：直接在BEGIN前声明
3. 参数处理：PostgreSQL过程参数需要指定类型
4. 异常处理：使用PostgreSQL的EXCEPTION语法
5. 游标：使用PostgreSQL游标语法
6. 动态SQL：使用EXECUTE format()

Oracle过程：
{sql}

返回PostgreSQL过程代码。""",
            variables=['sql']
        )
        
        # PL/SQL函数转换模板
        templates[PromptType.PLSQL_FUNCTION] = PromptTemplate(
            """请将以下Oracle PL/SQL函数转换为PostgreSQL函数。

转换规则：
1. 指定返回类型：RETURNS return_type
2. 使用LANGUAGE plpgsql
3. 函数体用$$包围
4. 处理Oracle特有的数据类型转换
5. 调整异常处理语法

Oracle函数：
{sql}

返回PostgreSQL函数代码。""",
            variables=['sql']
        )
        
        # PL/SQL匿名块转换模板
        templates[PromptType.PLSQL_BLOCK] = PromptTemplate(
            """请将以下Oracle PL/SQL匿名块转换为PostgreSQL的DO语句。

转换规则：
1. DECLARE ... BEGIN ... END; → DO $$ DECLARE ... BEGIN ... END $$;
2. 变量声明保持不变
3. 异常处理使用PostgreSQL语法
4. 确保所有变量都有正确的数据类型

Oracle块：
{sql}

返回PostgreSQL DO语句。""",
            variables=['sql']
        )
        
        # ZTC_SQLZZ转换模板
        templates[PromptType.ZTC_SQLZZ] = PromptTemplate(
            """请转换以下ZTC_SQLZZ动态SQL中的内容。

ZTC_SQLZZ是一个动态SQL执行函数，请转换其中的SQL语句：
{sql}

要求：
1. 只转换ZTC_SQLZZ括号内的SQL内容
2. 保持ZTC_SQLZZ函数结构不变
3. 确保内部SQL语法正确

返回转换后的完整ZTC_SQLZZ语句。""",
            variables=['sql']
        )
        
        # 复杂SQL转换模板
        templates[PromptType.COMPLEX_SQL] = PromptTemplate(
            """请转换以下复杂的SQL语句，它包含多个子查询、连接或高级特性。

SQL复杂度分析：
- 包含多个表连接
- 使用子查询或嵌套查询
- 使用聚合函数或窗口函数
- 包含条件逻辑或CASE语句

原始SQL ({from_dialect} → {to_dialect})：
{sql}

请仔细分析并确保转换后的SQL保持相同的业务逻辑和性能特征。""",
            variables=['from_dialect', 'to_dialect', 'sql']
        )
        
        # 错误恢复模板
        templates[PromptType.ERROR_RECOVERY] = PromptTemplate(
            """之前的SQL转换失败，请尝试修复并重新转换。

原始SQL ({from_dialect} → {to_dialect})：
{sql}

错误信息：
{error_message}

请分析错误原因并提供修复后的转换结果。""",
            variables=['from_dialect', 'to_dialect', 'sql', 'error_message']
        )
        
        return templates
    
    def _init_dialect_rules(self) -> Dict[str, Dict[str, Any]]:
        """初始化方言规则"""
        return {
            'oracle': {
                'date_functions': {
                    'SYSDATE': 'CURRENT_DATE',
                    'TO_DATE': 'TO_TIMESTAMP',
                    'TO_CHAR': 'TO_CHAR',
                    'ADD_MONTHS': 'date + interval',
                    'MONTHS_BETWEEN': 'EXTRACT(MONTH FROM age)'
                },
                'string_functions': {
                    'SUBSTR': 'SUBSTRING',
                    'INSTR': 'POSITION',
                    'LENGTH': 'LENGTH',
                    'REPLACE': 'REPLACE',
                    'TRIM': 'TRIM'
                },
                'control_flow': {
                    'DECODE': 'CASE WHEN',
                    'NVL': 'COALESCE',
                    'NVL2': 'CASE WHEN'
                },
                'syntax_patterns': {
                    'outer_join': '(+) → LEFT/RIGHT JOIN',
                    'rownum': 'ROWNUM → ROW_NUMBER()',
                    'connect_by': 'CONNECT BY → WITH RECURSIVE',
                    'hierarchical': 'START WITH → WITH RECURSIVE'
                }
            },
            'postgres': {
                'date_functions': {
                    'CURRENT_DATE': 'SYSDATE',
                    'TO_TIMESTAMP': 'TO_DATE',
                    'TO_CHAR': 'TO_CHAR',
                    'date + interval': 'ADD_MONTHS',
                    'EXTRACT(MONTH FROM age)': 'MONTHS_BETWEEN'
                },
                'string_functions': {
                    'SUBSTRING': 'SUBSTR',
                    'POSITION': 'INSTR',
                    'LENGTH': 'LENGTH',
                    'REPLACE': 'REPLACE',
                    'TRIM': 'TRIM'
                },
                'control_flow': {
                    'CASE WHEN': 'DECODE',
                    'COALESCE': 'NVL',
                    'NULLIF': 'NVL2'
                },
                'syntax_patterns': {
                    'LEFT/RIGHT JOIN': '(+)',
                    'ROW_NUMBER()': 'ROWNUM',
                    'WITH RECURSIVE': 'CONNECT BY',
                    'WITH RECURSIVE': 'START WITH'
                }
            }
        }
    
    def get_template(self, template_type: PromptType) -> PromptTemplate:
        """获取提示词模板"""
        if template_type not in self.templates:
            raise ValueError(f"未知的模板类型: {template_type}")
        return self.templates[template_type]
    
    def get_dialect_rules(self, from_dialect: str, to_dialect: str) -> Dict[str, Any]:
        """获取方言转换规则"""
        return self.dialect_rules.get(from_dialect, {})
    
    def select_template(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str,
        complexity: int = 5
    ) -> PromptType:
        """根据SQL特征选择合适的模板"""
        sql_upper = sql.upper()
        
        # 特殊转换场景
        if from_dialect == 'oracle' and to_dialect == 'postgres':
            if 'CREATE OR REPLACE PROCEDURE' in sql_upper:
                return PromptType.PLSQL_PROCEDURE
            elif 'CREATE OR REPLACE FUNCTION' in sql_upper:
                return PromptType.PLSQL_FUNCTION
            elif 'DECLARE' in sql_upper or 'BEGIN' in sql_upper:
                return PromptType.PLSQL_BLOCK
            else:
                return PromptType.ORACLE_TO_POSTGRES
        
        # ZTC_SQLZZ处理
        if 'ZTC_SQLZZ' in sql_upper:
            return PromptType.ZTC_SQLZZ
        
        # 复杂SQL处理
        if complexity >= 7:
            return PromptType.COMPLEX_SQL
        
        # 默认使用基础转换模板
        return PromptType.BASIC_CONVERSION
    
    def create_enhanced_prompt(
        self, 
        template_type: PromptType,
        sql: str,
        from_dialect: str,
        to_dialect: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """创建增强的提示词"""
        template = self.get_template(template_type)
        
        # 基础变量
        variables = {
            'sql': sql,
            'from_dialect': from_dialect,
            'to_dialect': to_dialect
        }
        
        # 添加上下文信息
        if context:
            variables.update(context)
        
        # 格式化基础提示词
        prompt = template.format(**variables)
        
        # 添加方言规则
        if from_dialect in self.dialect_rules:
            rules = self.dialect_rules[from_dialect]
            prompt += "\n\n方言转换规则：\n"
            
            for category, mappings in rules.items():
                prompt += f"{category}:\n"
                for source, target in mappings.items():
                    prompt += f"  {source} → {target}\n"
        
        # 添加验证要求
        validation_rules = [
            "确保语法符合目标方言规范",
            "保持原始业务逻辑不变",
            "优化性能和可读性",
            "处理数据类型兼容性",
            "确保错误处理适当"
        ]
        
        prompt += "\n\n验证要求：\n"
        for i, rule in enumerate(validation_rules, 1):
            prompt += f"{i}. {rule}\n"
        
        return prompt
    
    def create_error_recovery_prompt(
        self,
        sql: str,
        from_dialect: str,
        to_dialect: str,
        error_message: str,
        original_template: PromptType
    ) -> str:
        """创建错误恢复提示词"""
        template = self.get_template(PromptType.ERROR_RECOVERY)
        
        return template.format(
            sql=sql,
            from_dialect=from_dialect,
            to_dialect=to_dialect,
            error_message=error_message
        )
    
    def analyze_sql_features(self, sql: str) -> Dict[str, Any]:
        """分析SQL特征"""
        features = {
            'has_procedures': False,
            'has_functions': False,
            'has_dynamic_sql': False,
            'has_complex_joins': False,
            'has_subqueries': False,
            'has_aggregates': False,
            'has_window_functions': False,
            'has_plsql_blocks': False
        }
        
        sql_upper = sql.upper()
        
        # 分析特征
        if 'PROCEDURE' in sql_upper:
            features['has_procedures'] = True
        if 'FUNCTION' in sql_upper:
            features['has_functions'] = True
        if 'EXECUTE IMMEDIATE' in sql_upper or 'ZTC_SQLZZ' in sql_upper:
            features['has_dynamic_sql'] = True
        if 'JOIN' in sql_upper and sql_upper.count('JOIN') > 2:
            features['has_complex_joins'] = True
        if 'SELECT' in sql_upper and sql_upper.count('SELECT') > 1:
            features['has_subqueries'] = True
        if any(func in sql_upper for func in ['SUM(', 'COUNT(', 'AVG(', 'MAX(', 'MIN(']):
            features['has_aggregates'] = True
        if any(func in sql_upper for func in ['OVER(', 'ROW_NUMBER(', 'RANK(', 'DENSE_RANK(']):
            features['has_window_functions'] = True
        if 'DECLARE' in sql_upper or 'BEGIN' in sql_upper:
            features['has_plsql_blocks'] = True
        
        return features


# 全局模板管理器实例
prompt_manager = PromptTemplateManager()

def get_prompt_manager() -> PromptTemplateManager:
    """获取提示词模板管理器"""
    return prompt_manager