"""
LLM转换器
"""
import time
import json
import hashlib
from typing import Dict, Any, Optional, Tuple
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config.config import get_llm_config, get_conversion_config
from ..utils.exceptions import LLMError, LLMTimeoutError, NetworkError, ConfigError, ErrorHandler
from ..utils.logger import get_logger
from ..prompts.prompt_manager import PromptTemplateManager, PromptType, get_prompt_manager


class LLMConverter:
    """LLM转换器"""
    
    def __init__(self):
        """初始化转换器"""
        self.logger = get_logger()
        self.error_handler = ErrorHandler()
        self.config = get_llm_config()
        self.conversion_config = get_conversion_config()
        self.prompt_manager = get_prompt_manager()
        
        # 初始化OpenAI客户端
        self._init_client()
        
        # 初始化缓存
        self.cache = {}
        
        # 性能统计
        self.stats = {
            'total_calls': 0,
            'successful_calls': 0,
            'failed_calls': 0,
            'cache_hits': 0,
            'total_tokens': 0,
            'total_duration': 0
        }
    
    def _init_client(self):
        """初始化OpenAI客户端"""
        if not self.config.api_key:
            raise ConfigError("LLM API密钥未配置", "api_key")
        
        try:
            self.client = OpenAI(
                base_url=self.config.base_url,
                api_key=self.config.api_key,
                timeout=self.config.timeout
            )
        except Exception as e:
            raise ConfigError(f"LLM客户端初始化失败: {str(e)}", "base_url")
    
    def can_handle(self, sql: str, from_dialect: str, to_dialect: str) -> bool:
        """判断是否可以处理该SQL转换"""
        if not sql or not sql.strip():
            return False
        
        # 如果LLM回退被禁用，则不处理
        if not self.conversion_config.llm_fallback_enabled:
            return False
        
        # 检查是否是复杂SQL结构
        complexity = self._assess_complexity(sql)
        
        # 复杂SQL优先使用LLM
        return complexity >= 4
    
    def _assess_complexity(self, sql: str) -> int:
        """评估SQL复杂度 (1-10)"""
        complexity = 0
        
        sql_upper = sql.upper()
        
        # 复杂结构
        if any(keyword in sql_upper for keyword in ['PROCEDURE', 'FUNCTION', 'PACKAGE']):
            complexity += 4
        
        if any(keyword in sql_upper for keyword in ['DECLARE', 'BEGIN', 'EXCEPTION']):
            complexity += 3
        
        if 'ZTC_SQLZZ' in sql_upper:
            complexity += 2
        
        # 动态SQL
        if any(keyword in sql_upper for keyword in ['EXECUTE IMMEDIATE', 'DBMS_SQL']):
            complexity += 3
        
        # 复杂查询
        if sql_upper.count('JOIN') > 2:
            complexity += 2
        
        if sql_upper.count('SELECT') > 2:
            complexity += 1
        
        # 子查询
        if sql_upper.count('(') > 5:
            complexity += 1
        
        # 特殊函数
        complex_functions = [
            'OVER(', 'PARTITION BY', 'CONNECT BY', 'START WITH',
            'MODEL', 'PIVOT', 'UNPIVOT'
        ]
        for func in complex_functions:
            if func in sql_upper:
                complexity += 2
        
        # 语句长度
        if len(sql) > 2000:
            complexity += 1
        elif len(sql) > 1000:
            complexity += 0.5
        
        return min(int(complexity), 10)
    
    def convert(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        使用LLM转换SQL
        
        Returns:
            Tuple[转换结果, 转换元数据]
        """
        conversion_id = self.logger.start_conversion(
            sql, from_dialect, to_dialect, method="llm"
        )
        
        start_time = time.time()
        metadata = {
            'method': 'llm',
            'complexity': self._assess_complexity(sql),
            'template_type': None,
            'tokens_used': 0,
            'cache_hit': False
        }
        
        try:
            # 检查缓存
            if self.conversion_config.cache_enabled:
                cached_result = self._get_from_cache(sql, from_dialect, to_dialect)
                if cached_result:
                    metadata['cache_hit'] = True
                    metadata['duration'] = time.time() - start_time
                    self.logger.log_cache_operation("get", self._get_cache_key(sql, from_dialect, to_dialect), True)
                    return cached_result, metadata
            
            # 选择提示词模板
            template_type = self.prompt_manager.select_template(sql, from_dialect, to_dialect)
            metadata['template_type'] = template_type.value
            
            # 创建提示词
            prompt = self.prompt_manager.create_enhanced_prompt(
                template_type, sql, from_dialect, to_dialect, context
            )
            
            # 调用LLM
            response = self._call_llm(prompt, conversion_id)
            
            # 后处理结果
            result = self._postprocess_response(response, sql, from_dialect, to_dialect)
            
            # 缓存结果
            if self.conversion_config.cache_enabled:
                self._save_to_cache(sql, from_dialect, to_dialect, result)
            
            duration = time.time() - start_time
            self.logger.log_conversion_success(
                conversion_id, duration, len(result), "llm"
            )
            
            # 更新统计
            self.stats['successful_calls'] += 1
            self.stats['total_calls'] += 1
            self.stats['total_tokens'] += metadata['tokens_used']
            self.stats['total_duration'] += duration
            
            metadata['success'] = True
            metadata['duration'] = duration
            
            return result, metadata
            
        except Exception as e:
            duration = time.time() - start_time
            error = self.error_handler.handle_llm_error(e, self.config.model)
            self.logger.log_conversion_error(conversion_id, error, duration, "llm")
            
            # 更新统计
            self.stats['failed_calls'] += 1
            self.stats['total_calls'] += 1
            
            metadata['success'] = False
            metadata['duration'] = duration
            metadata['error'] = error.to_dict()
            
            raise error
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry_error_callback=lambda retry_state: False
    )
    def _call_llm(self, prompt: str, conversion_id: str) -> str:
        """调用LLM API"""
        start_time = time.time()
        
        try:
            self.logger.info(f"开始LLM调用: {self.config.model}", conversion_id=conversion_id)
            
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        'role': 'system',
                        'content': '你是一个专业的SQL转换助手。请确保返回的是完整且可直接执行的SQL代码，不要省略任何部分，包括特殊字符和完整的格式化。'
                    },
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=False,
                extra_body={'enable_thinking': False}
            )
            
            duration = time.time() - start_time
            
            # 提取响应内容
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                tokens_used = response.usage.total_tokens if response.usage else 0
                
                self.logger.log_llm_call(
                    conversion_id, 
                    self.config.model, 
                    len(prompt), 
                    len(content), 
                    duration
                )
                
                return content
            else:
                raise LLMError("LLM返回空响应", self.config.model)
                
        except Exception as e:
            if "timeout" in str(e).lower():
                raise LLMTimeoutError(f"LLM调用超时: {str(e)}", self.config.model, self.config.timeout)
            elif "connection" in str(e).lower():
                raise NetworkError(f"网络连接错误: {str(e)}", self.config.base_url, e)
            else:
                raise LLMError(f"LLM调用失败: {str(e)}", self.config.model, e)
    
    def _postprocess_response(self, response: str, original_sql: str, from_dialect: str, to_dialect: str) -> str:
        """后处理LLM响应"""
        # 清理响应
        cleaned = self._clean_response(response)
        
        # 验证响应质量
        if not self._validate_response(cleaned, original_sql):
            self.logger.warning("LLM响应质量可能不佳，尝试使用基础模板")
            # 尝试使用基础模板重新生成
            return self._fallback_conversion(original_sql, from_dialect, to_dialect)
        
        return cleaned
    
    def _clean_response(self, response: str) -> str:
        """清理LLM响应"""
        # 移除markdown代码块标记
        cleaned = response
        if cleaned.startswith('```sql'):
            cleaned = cleaned[6:]
        if cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        
        # 移除解释性文字
        lines = []
        in_code_block = False
        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('```'):
                in_code_block = not in_code_block
                continue
            if not in_code_block and (
                line.startswith('--') or 
                line.startswith('#') or 
                line.startswith('*') or
                line.startswith('转换结果') or
                line.startswith('以下是') or
                line.startswith('上面的') or
                '转换后的' in line or
                '结果为' in line
            ):
                continue
            if line:
                lines.append(line)
        
        result = '\n'.join(lines)
        
        # 确保以分号结尾
        if result and not result.rstrip().endswith(';'):
            result += ';'
        
        return result.strip()
    
    def _validate_response(self, response: str, original_sql: str) -> bool:
        """验证LLM响应质量"""
        if not response or len(response) < 10:
            return False
        
        # 检查是否包含SQL关键字
        sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP']
        has_keywords = any(keyword in response.upper() for keyword in sql_keywords)
        
        if not has_keywords:
            return False
        
        # 检查长度是否合理
        if len(response) > len(original_sql) * 5:
            return False  # 响应过长，可能包含解释性文字
        
        # 检查是否包含明显的非SQL内容
        non_sql_indicators = ['抱歉', '无法', '错误', '对不起', '请注意', '说明']
        has_indicators = any(indicator in response for indicator in non_sql_indicators)
        
        if has_indicators:
            return False
        
        return True
    
    def _fallback_conversion(self, sql: str, from_dialect: str, to_dialect: str) -> str:
        """回退到基础转换"""
        try:
            prompt = self.prompt_manager.create_enhanced_prompt(
                PromptType.BASIC_CONVERSION, sql, from_dialect, to_dialect
            )
            response = self._call_llm(prompt, "fallback")
            return self._clean_response(response)
        except Exception as e:
            self.logger.error(f"回退转换失败: {e}")
            raise LLMError(f"所有转换尝试均失败: {str(e)}", self.config.model, e)
    
    def _get_cache_key(self, sql: str, from_dialect: str, to_dialect: str) -> str:
        """生成缓存键"""
        content = f"{from_dialect}:{to_dialect}:{sql}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _get_from_cache(self, sql: str, from_dialect: str, to_dialect: str) -> Optional[str]:
        """从缓存获取结果"""
        cache_key = self._get_cache_key(sql, from_dialect, to_dialect)
        
        if cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            # 检查缓存是否过期
            if time.time() - cache_entry['timestamp'] < self.conversion_config.cache_ttl:
                self.stats['cache_hits'] += 1
                return cache_entry['result']
            else:
                # 清理过期缓存
                del self.cache[cache_key]
        
        return None
    
    def _save_to_cache(self, sql: str, from_dialect: str, to_dialect: str, result: str):
        """保存结果到缓存"""
        cache_key = self._get_cache_key(sql, from_dialect, to_dialect)
        
        self.cache[cache_key] = {
            'result': result,
            'timestamp': time.time(),
            'from_dialect': from_dialect,
            'to_dialect': to_dialect
        }
        
        # 限制缓存大小
        if len(self.cache) > 1000:
            # 删除最旧的缓存项
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
    
    def error_recovery(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        error_message: str,
        original_template: PromptType
    ) -> Tuple[str, Dict[str, Any]]:
        """错误恢复"""
        try:
            # 创建错误恢复提示词
            prompt = self.prompt_manager.create_error_recovery_prompt(
                sql, from_dialect, to_dialect, error_message, original_template
            )
            
            response = self._call_llm(prompt, "error_recovery")
            result = self._clean_response(response)
            
            metadata = {
                'method': 'llm_error_recovery',
                'success': True,
                'error_recovered': True
            }
            
            return result, metadata
            
        except Exception as e:
            raise LLMError(f"错误恢复失败: {str(e)}", self.config.model, e)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            'success_rate': (
                self.stats['successful_calls'] / self.stats['total_calls'] * 100
                if self.stats['total_calls'] > 0 else 0
            ),
            'avg_duration': (
                self.stats['total_duration'] / self.stats['successful_calls']
                if self.stats['successful_calls'] > 0 else 0
            ),
            'cache_hit_rate': (
                self.stats['cache_hits'] / self.stats['total_calls'] * 100
                if self.stats['total_calls'] > 0 else 0
            )
        }
    
    def clear_cache(self):
        """清空缓存"""
        self.cache.clear()
        self.logger.info("LLM转换器缓存已清空")
    
    def warm_up(self):
        """预热模型"""
        try:
            test_sql = "SELECT 1 AS test"
            self.convert(test_sql, "mysql", "postgres")
            self.logger.info("LLM转换器预热完成")
        except Exception as e:
            self.logger.warning(f"LLM转换器预热失败: {e}")


# 全局LLM转换器实例
llm_converter = LLMConverter()

def get_llm_converter() -> LLMConverter:
    """获取LLM转换器实例"""
    return llm_converter