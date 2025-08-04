"""
SQLGlot转换器
"""
import re
import sqlglot
import sqlparse
from typing import Optional, Tuple, Dict, Any
from sqlglot import transpile, errors
from sqlglot.dialects import Dialect

from ..config.config import get_database_config, get_conversion_config
from ..utils.exceptions import (
    SQLConverterError, SQLParseError, SQLTranspilationError, 
    SQLValidationError, UnsupportedFeatureError, ErrorHandler
)
from ..utils.logger import get_logger


class SQLGlotConverter:
    """SQLGlot转换器"""
    
    def __init__(self):
        """初始化转换器"""
        self.logger = get_logger()
        self.error_handler = ErrorHandler()
        self.config = get_conversion_config()
        
        # 预编译正则表达式
        self._compile_patterns()
        
        # 初始化SQL解析器
        self._init_parsers()
    
    def _compile_patterns(self):
        """预编译正则表达式"""
        self.patterns = {
            'plsql_block': re.compile(
                r"""((CREATE\s+(OR\s+REPLACE\s+)?(PROCEDURE|FUNCTION)\s+[\s\S]*?END\s*([A-Za-z0-9_]+)?\s*;)|"""
                r"""(\bDECLARE\b[\s\S]*?END\s*;)|"""
                r"""(\bBEGIN\b[\s\S]*?END\s*;))""",
                re.IGNORECASE | re.VERBOSE
            ),
            'ztc_sqlzz': re.compile(
                r"ZTC_SQLZZ\s*\(\s*'([\s\S]*?)'\s*\)\s*;",
                re.IGNORECASE
            ),
            'comment_block': re.compile(
                r"/\*([\s\S]*?)\*/",
                re.IGNORECASE
            ),
            'line_comment': re.compile(
                r"--.*$",
                re.MULTILINE
            ),
            'oracle_procedure': re.compile(
                r"""^\s*(CREATE\s+(OR\s+REPLACE\s+)?PROCEDURE\s+([a-zA-Z0-9_."]+))"""
                r"""\s+IS\s+([\s\S]*?)BEGIN\s+([\s\S]+?)"""
                r"""\s*END\s+\2\s*;\s*$""",
                re.IGNORECASE | re.VERBOSE | re.DOTALL
            )
        }
    
    def _init_parsers(self):
        """初始化SQL解析器"""
        self.parsers = {}
        for dialect in ['oracle', 'postgres', 'mysql', 'tsql']:
            try:
                self.parsers[dialect] = Dialect.get_or_raise(dialect)
            except Exception:
                self.logger.warning(f"无法初始化 {dialect} 解析器")
    
    def can_handle(self, sql: str, from_dialect: str, to_dialect: str) -> bool:
        """判断是否可以处理该SQL转换"""
        if not sql or not sql.strip():
            return False
        
        # 检查方言支持
        if not self._is_dialect_supported(from_dialect) or not self._is_dialect_supported(to_dialect):
            return False
        
        # 评估SQL复杂度
        complexity = self._assess_complexity(sql)
        
        # 简单SQL优先使用SQLGlot
        return complexity <= 3
    
    def _is_dialect_supported(self, dialect: str) -> bool:
        """检查方言是否支持"""
        try:
            Dialect.get_or_raise(dialect)
            return True
        except Exception:
            return False
    
    def _assess_complexity(self, sql: str) -> int:
        """评估SQL复杂度 (1-10)"""
        complexity = 0
        
        # 基础复杂度指标
        sql_upper = sql.upper()
        
        # 包含PL/SQL块
        if self.patterns['plsql_block'].search(sql):
            complexity += 5
        
        # 包含ZTC_SQLZZ
        if self.patterns['ztc_sqlzz'].search(sql):
            complexity += 3
        
        # 包含复杂关键字
        complex_keywords = [
            'CURSOR', 'EXCEPTION', 'PACKAGE', 'TRIGGER', 
            'TYPE', 'RECORD', 'TABLE', 'ROWTYPE'
        ]
        for keyword in complex_keywords:
            if keyword in sql_upper:
                complexity += 1
        
        # 语句长度
        if len(sql) > 1000:
            complexity += 1
        elif len(sql) > 500:
            complexity += 0.5
        
        # 嵌套层级（简单计算）
        nest_level = sql_upper.count('BEGIN') + sql_upper.count('IF')
        complexity += min(nest_level * 0.5, 2)
        
        return min(int(complexity), 10)
    
    def convert(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        pretty: bool = True
    ) -> Tuple[str, Dict[str, Any]]:
        """
        转换SQL
        
        Returns:
            Tuple[转换结果, 转换元数据]
        """
        conversion_id = self.logger.start_conversion(
            sql, from_dialect, to_dialect, method="sqlglot"
        )
        
        start_time = time.time()
        metadata = {
            'method': 'sqlglot',
            'complexity': self._assess_complexity(sql),
            'warnings': [],
            'optimizations': []
        }
        
        try:
            # 预处理SQL
            processed_sql = self._preprocess_sql(sql, from_dialect, to_dialect)
            
            # 执行转换
            result = self._transpile_sql(processed_sql, from_dialect, to_dialect, pretty)
            
            # 后处理结果
            final_result = self._postprocess_result(result, to_dialect)
            
            # 验证结果
            if self.config.validate_syntax:
                validation_result = self._validate_sql(final_result, to_dialect)
                metadata['validation'] = validation_result
                if not validation_result['is_valid']:
                    metadata['warnings'].extend(validation_result['warnings'])
            
            duration = time.time() - start_time
            self.logger.log_conversion_success(
                conversion_id, duration, len(final_result), "sqlglot"
            )
            
            metadata['success'] = True
            metadata['duration'] = duration
            
            return final_result, metadata
            
        except Exception as e:
            duration = time.time() - start_time
            error = self.error_handler.handle_sqlglot_error(e, sql, from_dialect, to_dialect)
            self.logger.log_conversion_error(conversion_id, error, duration, "sqlglot")
            
            metadata['success'] = False
            metadata['duration'] = duration
            metadata['error'] = error.to_dict()
            
            raise error
    
    def _preprocess_sql(self, sql: str, from_dialect: str, to_dialect: str) -> str:
        """预处理SQL"""
        # 标准化空白字符
        processed = ' '.join(sql.split())
        
        # 确保语句以分号结尾
        if not processed.rstrip().endswith(';'):
            processed += ';'
        
        return processed
    
    def _transpile_sql(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        pretty: bool
    ) -> str:
        """执行SQL转换"""
        try:
            # 获取方言配置
            from_config = get_database_config(from_dialect)
            to_config = get_database_config(to_dialect)
            
            # 执行转换
            transpiled = transpile(
                sql,
                read=from_dialect,
                write=to_dialect,
                pretty=pretty,
                identity=False
            )
            
            if transpiled:
                result = transpiled[0] if isinstance(transpiled, list) else transpiled
                return result if result else sql
            else:
                return sql
                
        except errors.ParseError as e:
            raise SQLParseError(f"SQL解析失败: {str(e)}", sql, e)
        except errors.UnsupportedError as e:
            raise UnsupportedFeatureError(
                f"不支持的转换特性: {str(e)}", 
                "unknown", from_dialect, to_dialect
            )
        except Exception as e:
            raise SQLTranspilationError(
                f"SQL转换失败: {str(e)}", 
                from_dialect, to_dialect, sql, e
            )
    
    def _postprocess_result(self, result: str, to_dialect: str) -> str:
        """后处理转换结果"""
        # 获取目标方言配置
        to_config = get_database_config(to_dialect)
        
        # 标准化标识符引用
        result = self._normalize_identifiers(result, to_config)
        
        # 格式化输出
        if self.config.pretty_print:
            result = self._format_sql(result)
        
        return result
    
    def _normalize_identifiers(self, sql: str, config) -> str:
        """标准化标识符引用"""
        # 这里可以根据不同方言的规则进行标识符标准化
        # 例如，PostgreSQL对大小写敏感，需要适当处理
        
        # 简单的实现：确保关键字使用正确的引用
        keywords = {
            'user', 'group', 'order', 'limit', 'table', 'column', 
            'index', 'view', 'sequence', 'function', 'procedure'
        }
        
        for keyword in keywords:
            # 替换未引用的关键字
            pattern = r'\b' + keyword + r'\b(?=(?:[^"]*"[^"]*")*[^"]*$)'
            sql = re.sub(pattern, f'{config.identifier_quote}{keyword}{config.identifier_quote}', sql)
        
        return sql
    
    def _format_sql(self, sql: str) -> str:
        """格式化SQL"""
        try:
            # 使用sqlparse进行格式化
            formatted = sqlparse.format(
                sql,
                reindent=True,
                keyword_case='upper',
                identifier_case='lower'
            )
            return formatted
        except Exception:
            return sql
    
    def _validate_sql(self, sql: str, dialect: str) -> Dict[str, Any]:
        """验证SQL语法"""
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'errors': []
        }
        
        try:
            # 基础语法检查
            parsed = sqlparse.parse(sql)
            if not parsed:
                validation_result['is_valid'] = False
                validation_result['errors'].append("无法解析SQL语句")
                return validation_result
            
            # 检查语法结构
            for statement in parsed:
                if statement.get_type() == 'UNKNOWN':
                    validation_result['warnings'].append("检测到未知语法结构")
                
                # 检查括号匹配
                if sql.count('(') != sql.count(')'):
                    validation_result['errors'].append("括号不匹配")
                    validation_result['is_valid'] = False
                
                # 检查引号匹配
                if sql.count("'") % 2 != 0:
                    validation_result['errors'].append("单引号不匹配")
                    validation_result['is_valid'] = False
                
                # 检查双引号匹配
                if sql.count('"') % 2 != 0:
                    validation_result['errors'].append("双引号不匹配")
                    validation_result['is_valid'] = False
            
            # 方言特定检查
            self._dialect_specific_validation(sql, dialect, validation_result)
            
        except Exception as e:
            validation_result['is_valid'] = False
            validation_result['errors'].append(f"验证失败: {str(e)}")
        
        return validation_result
    
    def _dialect_specific_validation(
        self, 
        sql: str, 
        dialect: str, 
        validation_result: Dict[str, Any]
    ):
        """方言特定验证"""
        sql_upper = sql.upper()
        
        if dialect == 'postgres':
            # PostgreSQL特定检查
            if 'TO_DATE(' in sql_upper and 'YYYYMMDD' in sql_upper:
                validation_result['warnings'].append(
                    "PostgreSQL中TO_DATE格式可能需要调整"
                )
            
            if 'SYSDATE' in sql_upper:
                validation_result['warnings'].append(
                    "PostgreSQL中应使用CURRENT_DATE替代SYSDATE"
                )
        
        elif dialect == 'oracle':
            # Oracle特定检查
            if 'CURRENT_DATE' in sql_upper:
                validation_result['warnings'].append(
                    "Oracle中应使用SYSDATE替代CURRENT_DATE"
                )
    
    def get_optimization_suggestions(self, sql: str, dialect: str) -> list:
        """获取优化建议"""
        suggestions = []
        sql_upper = sql.upper()
        
        # 通用优化建议
        if 'SELECT *' in sql_upper:
            suggestions.append("避免使用SELECT *，明确指定所需列")
        
        if sql_upper.count('DISTINCT') > 2:
            suggestions.append("过多DISTINCT操作可能影响性能")
        
        # 方言特定建议
        if dialect == 'postgres':
            if 'LIKE ' in sql_upper and '%' in sql_upper:
                suggestions.append("考虑使用全文索引优化LIKE查询")
        
        elif dialect == 'oracle':
            if 'ROWNUM' in sql_upper:
                suggestions.append("考虑使用ROW_NUMBER()替代ROWNUM")
        
        return suggestions


# 需要导入time模块
import time