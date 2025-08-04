"""
转换协调器 - 统一管理SQL转换流程
"""
import time
import re
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass

from ..config.config import get_conversion_config, get_database_config, config_manager
from ..utils.exceptions import SQLConverterError, ErrorHandler
from ..utils.logger import get_logger, get_performance_tracker
from .sqlglot_converter import SQLGlotConverter
from .llm_converter import LLMConverter, get_llm_converter
from ..prompts.prompt_manager import PromptType


@dataclass
class ConversionResult:
    """转换结果"""
    success: bool
    result_sql: str
    metadata: Dict[str, Any]
    error: Optional[SQLConverterError] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class ConversionCoordinator:
    """转换协调器"""
    
    def __init__(self):
        """初始化协调器"""
        self.logger = get_logger()
        self.performance_tracker = get_performance_tracker()
        self.error_handler = ErrorHandler()
        self.config = get_conversion_config()
        
        # 初始化转换器
        self.sqlglot_converter = SQLGlotConverter()
        self.llm_converter = get_llm_converter()
        
        # 预编译正则表达式
        self._compile_patterns()
        
        # 统计信息
        self.stats = {
            'total_conversions': 0,
            'successful_conversions': 0,
            'failed_conversions': 0,
            'sqlglot_conversions': 0,
            'llm_conversions': 0,
            'error_recoveries': 0,
            'avg_conversion_time': 0
        }
    
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
    
    def convert_sql(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        pretty: bool = True
    ) -> ConversionResult:
        """
        转换SQL的主要入口点
        
        Args:
            sql: 要转换的SQL语句
            from_dialect: 源方言
            to_dialect: 目标方言
            pretty: 是否格式化输出
        
        Returns:
            ConversionResult: 转换结果
        """
        # 验证输入
        validation_result = self._validate_input(sql, from_dialect, to_dialect)
        if not validation_result['is_valid']:
            return ConversionResult(
                success=False,
                result_sql="",
                metadata={},
                error=SQLConverterError(
                    f"输入验证失败: {validation_result['errors'][0]}",
                    context={"validation_errors": validation_result['errors']}
                ),
                warnings=validation_result['warnings']
            )
        
        # 开始转换
        conversion_id = self.performance_tracker.start_conversion()
        start_time = time.time()
        
        try:
            # 预处理SQL
            processed_sql = self._preprocess_sql(sql)
            
            # 分析SQL特征
            analysis = self._analyze_sql(processed_sql)
            
            # 选择转换策略
            strategy = self._select_conversion_strategy(processed_sql, from_dialect, to_dialect, analysis)
            
            # 执行转换
            result_sql, metadata = self._execute_conversion(
                processed_sql, from_dialect, to_dialect, strategy, analysis
            )
            
            # 后处理结果
            final_result = self._postprocess_result(result_sql, to_dialect)
            
            # 验证转换结果
            validation = self._validate_conversion_result(final_result, to_dialect)
            
            duration = time.time() - start_time
            
            # 更新统计
            self._update_stats(True, duration, strategy)
            
            # 记录成功
            self.performance_tracker.end_conversion_success(duration)
            self.logger.log_conversion_success(
                conversion_id, duration, len(final_result), strategy
            )
            
            # 组合最终结果
            warnings = validation.get('warnings', [])
            warnings.extend(metadata.get('warnings', []))
            
            return ConversionResult(
                success=True,
                result_sql=final_result,
                metadata={
                    **metadata,
                    'strategy': strategy,
                    'duration': duration,
                    'analysis': analysis,
                    'validation': validation
                },
                warnings=warnings
            )
            
        except SQLConverterError as e:
            duration = time.time() - start_time
            
            # 尝试错误恢复
            if self.config.llm_fallback_enabled:
                try:
                    recovery_result = self._attempt_error_recovery(
                        sql, from_dialect, to_dialect, e
                    )
                    if recovery_result:
                        self.stats['error_recoveries'] += 1
                        return recovery_result
                except Exception as recovery_error:
                    self.logger.warning(f"错误恢复失败: {recovery_error}")
            
            # 更新统计
            self._update_stats(False, duration, 'failed')
            self.performance_tracker.end_conversion_error()
            
            # 记录失败
            self.logger.log_conversion_error(
                conversion_id, e, duration, 'coordinator'
            )
            
            return ConversionResult(
                success=False,
                result_sql="",
                metadata={'duration': duration},
                error=e,
                warnings=[]
            )
        
        except Exception as e:
            duration = time.time() - start_time
            error = self.error_handler.handle_sqlglot_error(e, sql, from_dialect, to_dialect)
            
            # 更新统计
            self._update_stats(False, duration, 'failed')
            self.performance_tracker.end_conversion_error()
            
            # 记录失败
            self.logger.log_conversion_error(
                conversion_id, error, duration, 'coordinator'
            )
            
            return ConversionResult(
                success=False,
                result_sql="",
                metadata={'duration': duration},
                error=error,
                warnings=[]
            )
    
    def _validate_input(self, sql: str, from_dialect: str, to_dialect: str) -> Dict[str, Any]:
        """验证输入参数"""
        errors = []
        warnings = []
        
        # 检查SQL是否为空
        if not sql or not sql.strip():
            errors.append("SQL语句不能为空")
            return {'is_valid': False, 'errors': errors, 'warnings': warnings}
        
        # 检查方言支持
        if not config_manager.is_dialect_supported(from_dialect):
            errors.append(f"不支持的源方言: {from_dialect}")
        
        if not config_manager.is_dialect_supported(to_dialect):
            errors.append(f"不支持的目标方言: {to_dialect}")
        
        # 检查方言是否相同
        if from_dialect == to_dialect:
            warnings.append("源方言和目标方言相同")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings
        }
    
    def _preprocess_sql(self, sql: str) -> str:
        """预处理SQL"""
        # 移除多余的空白行
        lines = [line.strip() for line in sql.split('\n') if line.strip()]
        processed = '\n'.join(lines)
        
        # 确保以分号结尾
        if not processed.rstrip().endswith(';'):
            processed += ';'
        
        return processed
    
    def _analyze_sql(self, sql: str) -> Dict[str, Any]:
        """分析SQL特征"""
        analysis = {
            'complexity': 0,
            'has_plsql': False,
            'has_ztc_sqlzz': False,
            'has_comments': False,
            'has_complex_joins': False,
            'has_subqueries': False,
            'estimated_lines': len(sql.split('\n')),
            'estimated_tokens': len(sql.split())
        }
        
        sql_upper = sql.upper()
        
        # 分析复杂度
        if self.patterns['plsql_block'].search(sql):
            analysis['has_plsql'] = True
            analysis['complexity'] += 5
        
        if self.patterns['ztc_sqlzz'].search(sql):
            analysis['has_ztc_sqlzz'] = True
            analysis['complexity'] += 3
        
        if self.patterns['comment_block'].search(sql) or self.patterns['line_comment'].search(sql):
            analysis['has_comments'] = True
        
        if sql_upper.count('JOIN') > 2:
            analysis['has_complex_joins'] = True
            analysis['complexity'] += 2
        
        if sql_upper.count('SELECT') > 1:
            analysis['has_subqueries'] = True
            analysis['complexity'] += 1
        
        # 根据长度调整复杂度
        if analysis['estimated_lines'] > 50:
            analysis['complexity'] += 2
        elif analysis['estimated_lines'] > 20:
            analysis['complexity'] += 1
        
        return analysis
    
    def _select_conversion_strategy(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        analysis: Dict[str, Any]
    ) -> str:
        """选择转换策略"""
        complexity = analysis['complexity']
        
        # Oracle到PostgreSQL的特殊处理
        if from_dialect == 'oracle' and to_dialect == 'postgres':
            if analysis['has_plsql']:
                return 'llm'  # PL/SQL优先使用LLM
            elif complexity <= 3:
                return 'sqlglot'
            else:
                return 'hybrid'
        
        # 基于复杂度的策略选择
        if complexity <= 3:
            return 'sqlglot'
        elif complexity <= 6:
            return 'hybrid'
        else:
            return 'llm'
    
    def _execute_conversion(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        strategy: str,
        analysis: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """执行转换"""
        if strategy == 'sqlglot':
            return self._sqlglot_conversion(sql, from_dialect, to_dialect)
        elif strategy == 'llm':
            return self._llm_conversion(sql, from_dialect, to_dialect, analysis)
        elif strategy == 'hybrid':
            return self._hybrid_conversion(sql, from_dialect, to_dialect, analysis)
        else:
            raise ValueError(f"未知的转换策略: {strategy}")
    
    def _sqlglot_conversion(self, sql: str, from_dialect: str, to_dialect: str) -> Tuple[str, Dict[str, Any]]:
        """SQLGlot转换"""
        result, metadata = self.sqlglot_converter.convert(sql, from_dialect, to_dialect)
        self.stats['sqlglot_conversions'] += 1
        return result, metadata
    
    def _llm_conversion(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        analysis: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """LLM转换"""
        context = {
            'complexity': analysis['complexity'],
            'has_plsql': analysis['has_plsql'],
            'has_ztc_sqlzz': analysis['has_ztc_sqlzz']
        }
        
        result, metadata = self.llm_converter.convert(sql, from_dialect, to_dialect, context)
        self.stats['llm_conversions'] += 1
        return result, metadata
    
    def _hybrid_conversion(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        analysis: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """混合转换策略"""
        # 首先尝试SQLGlot
        try:
            result, metadata = self.sqlglot_converter.convert(sql, from_dialect, to_dialect)
            
            # 如果SQLGlot转换成功且结果质量良好，直接返回
            if metadata.get('success', False) and len(result) > 0:
                metadata['strategy'] = 'hybrid_sqlglot_success'
                return result, metadata
            
        except Exception:
            pass
        
        # SQLGlot失败，使用LLM
        try:
            result, metadata = self.llm_converter.convert(sql, from_dialect, to_dialect, analysis)
            metadata['strategy'] = 'hybrid_llm_fallback'
            self.stats['llm_conversions'] += 1
            return result, metadata
            
        except Exception as e:
            raise SQLConverterError(
                f"混合转换策略失败: {str(e)}",
                context={'strategy': 'hybrid', 'sql_preview': sql[:200]}
            )
    
    def _postprocess_result(self, result: str, to_dialect: str) -> str:
        """后处理转换结果"""
        # 获取目标方言配置
        db_config = get_database_config(to_dialect)
        
        # 标准化格式
        result = self._normalize_sql_format(result, db_config)
        
        return result
    
    def _normalize_sql_format(self, sql: str, db_config) -> str:
        """标准化SQL格式"""
        # 移除多余的空行
        lines = []
        for line in sql.split('\n'):
            if line.strip():
                lines.append(line)
        
        # 确保关键字大写（可选）
        # 这里可以根据配置进行格式化
        
        return '\n'.join(lines)
    
    def _validate_conversion_result(self, result: str, to_dialect: str) -> Dict[str, Any]:
        """验证转换结果"""
        validation = {
            'is_valid': True,
            'warnings': [],
            'errors': []
        }
        
        # 基础检查
        if not result or len(result.strip()) < 5:
            validation['is_valid'] = False
            validation['errors'].append("转换结果为空")
            return validation
        
        # 检查语法结构
        if result.count('(') != result.count(')'):
            validation['warnings'].append("括号数量不匹配")
        
        if result.count("'") % 2 != 0:
            validation['warnings'].append("单引号数量不匹配")
        
        # 方言特定检查
        if to_dialect == 'postgres':
            if 'SYSDATE' in result.upper():
                validation['warnings'].append("建议使用CURRENT_DATE替代SYSDATE")
        
        return validation
    
    def _attempt_error_recovery(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        original_error: SQLConverterError
    ) -> Optional[ConversionResult]:
        """尝试错误恢复"""
        try:
            # 使用LLM进行错误恢复
            result, metadata = self.llm_converter.error_recovery(
                sql, from_dialect, to_dialect, 
                str(original_error), 
                PromptType.BASIC_CONVERSION
            )
            
            return ConversionResult(
                success=True,
                result_sql=result,
                metadata={
                    **metadata,
                    'error_recovered': True,
                    'original_error': str(original_error)
                },
                warnings=["通过错误恢复机制修复"]
            )
            
        except Exception:
            return None
    
    def _update_stats(self, success: bool, duration: float, strategy: str):
        """更新统计信息"""
        self.stats['total_conversions'] += 1
        
        if success:
            self.stats['successful_conversions'] += 1
        else:
            self.stats['failed_conversions'] += 1
        
        self.stats['avg_conversion_time'] = (
            (self.stats['avg_conversion_time'] * (self.stats['total_conversions'] - 1) + duration) /
            self.stats['total_conversions']
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'success_rate': (
                self.stats['successful_conversions'] / self.stats['total_conversions'] * 100
                if self.stats['total_conversions'] > 0 else 0
            ),
            'sqlglot_usage_rate': (
                self.stats['sqlglot_conversions'] / self.stats['total_conversions'] * 100
                if self.stats['total_conversions'] > 0 else 0
            ),
            'llm_usage_rate': (
                self.stats['llm_conversions'] / self.stats['total_conversions'] * 100
                if self.stats['total_conversions'] > 0 else 0
            )
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.stats = {
            'total_conversions': 0,
            'successful_conversions': 0,
            'failed_conversions': 0,
            'sqlglot_conversions': 0,
            'llm_conversions': 0,
            'error_recoveries': 0,
            'avg_conversion_time': 0
        }
    
    def warm_up(self):
        """预热转换器"""
        try:
            test_sql = "SELECT 1 AS test_column"
            self.convert_sql(test_sql, "mysql", "postgres")
            self.logger.info("转换协调器预热完成")
        except Exception as e:
            self.logger.warning(f"转换协调器预热失败: {e}")


# 全局转换协调器实例
conversion_coordinator = ConversionCoordinator()

def get_conversion_coordinator() -> ConversionCoordinator:
    """获取转换协调器实例"""
    return conversion_coordinator