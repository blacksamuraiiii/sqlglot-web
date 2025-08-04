"""
异常处理框架
"""
from typing import Optional, Dict, Any
from enum import Enum


class ErrorType(Enum):
    """错误类型枚举"""
    PARSE_ERROR = "parse_error"
    TRANSPILATION_ERROR = "transpilation_error"
    VALIDATION_ERROR = "validation_error"
    LLM_ERROR = "llm_error"
    CONFIG_ERROR = "config_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    UNKNOWN_ERROR = "unknown_error"


class ErrorSeverity(Enum):
    """错误严重程度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SQLConverterError(Exception):
    """SQL转换器基础异常类"""
    
    def __init__(
        self, 
        message: str,
        error_type: ErrorType = ErrorType.UNKNOWN_ERROR,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        original_error: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.error_type = error_type
        self.severity = severity
        self.original_error = original_error
        self.context = context or {}
        super().__init__(self.message)
    
    def __str__(self) -> str:
        return f"[{self.error_type.value}] {self.message}"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "message": self.message,
            "error_type": self.error_type.value,
            "severity": self.severity.value,
            "original_error": str(self.original_error) if self.original_error else None,
            "context": self.context
        }


class SQLParseError(SQLConverterError):
    """SQL解析错误"""
    
    def __init__(self, message: str, sql: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            error_type=ErrorType.PARSE_ERROR,
            severity=ErrorSeverity.HIGH,
            original_error=original_error,
            context={"sql": sql[:500]}  # 只保留前500个字符
        )


class SQLTranspilationError(SQLConverterError):
    """SQL转换错误"""
    
    def __init__(self, message: str, from_dialect: str, to_dialect: str, sql: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            error_type=ErrorType.TRANSPILATION_ERROR,
            severity=ErrorSeverity.HIGH,
            original_error=original_error,
            context={
                "from_dialect": from_dialect,
                "to_dialect": to_dialect,
                "sql": sql[:500]
            }
        )


class SQLValidationError(SQLConverterError):
    """SQL验证错误"""
    
    def __init__(self, message: str, sql: str, validation_details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            error_type=ErrorType.VALIDATION_ERROR,
            severity=ErrorSeverity.MEDIUM,
            context={
                "sql": sql[:500],
                "validation_details": validation_details or {}
            }
        )


class LLMError(SQLConverterError):
    """LLM调用错误"""
    
    def __init__(self, message: str, model: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            error_type=ErrorType.LLM_ERROR,
            severity=ErrorSeverity.HIGH,
            original_error=original_error,
            context={"model": model}
        )


class LLMTimeoutError(LLMError):
    """LLM调用超时错误"""
    
    def __init__(self, message: str, model: str, timeout: int):
        super().__init__(message, model)
        self.error_type = ErrorType.TIMEOUT_ERROR
        self.severity = ErrorSeverity.MEDIUM
        self.context["timeout"] = timeout


class ConfigError(SQLConverterError):
    """配置错误"""
    
    def __init__(self, message: str, config_key: Optional[str] = None):
        super().__init__(
            message=message,
            error_type=ErrorType.CONFIG_ERROR,
            severity=ErrorSeverity.CRITICAL,
            context={"config_key": config_key}
        )


class NetworkError(SQLConverterError):
    """网络错误"""
    
    def __init__(self, message: str, url: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            error_type=ErrorType.NETWORK_ERROR,
            severity=ErrorSeverity.MEDIUM,
            original_error=original_error,
            context={"url": url}
        )


class UnsupportedFeatureError(SQLConverterError):
    """不支持的特性错误"""
    
    def __init__(self, message: str, feature: str, from_dialect: str, to_dialect: str):
        super().__init__(
            message=message,
            error_type=ErrorType.TRANSPILATION_ERROR,
            severity=ErrorSeverity.MEDIUM,
            context={
                "feature": feature,
                "from_dialect": from_dialect,
                "to_dialect": to_dialect
            }
        )


class RetryableError(SQLConverterError):
    """可重试错误"""
    
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(
            message=message,
            severity=ErrorSeverity.LOW,
            original_error=original_error
        )


class ErrorHandler:
    """错误处理器"""
    
    @staticmethod
    def handle_sqlglot_error(error: Exception, sql: str, from_dialect: str, to_dialect: str) -> SQLConverterError:
        """处理SQLGlot错误"""
        if "ParseError" in str(type(error)):
            return SQLParseError(
                f"SQL解析失败: {str(error)}",
                sql=sql,
                original_error=error
            )
        elif "UnsupportedError" in str(type(error)):
            return UnsupportedFeatureError(
                f"不支持的转换特性: {str(error)}",
                feature="unknown",
                from_dialect=from_dialect,
                to_dialect=to_dialect
            )
        else:
            return SQLTranspilationError(
                f"SQL转换失败: {str(error)}",
                from_dialect=from_dialect,
                to_dialect=to_dialect,
                sql=sql,
                original_error=error
            )
    
    @staticmethod
    def handle_llm_error(error: Exception, model: str) -> SQLConverterError:
        """处理LLM错误"""
        error_msg = str(error).lower()
        
        if "timeout" in error_msg or "time out" in error_msg:
            return LLMTimeoutError(
                f"LLM调用超时: {str(error)}",
                model=model,
                timeout=30
            )
        elif "connection" in error_msg or "network" in error_msg:
            return NetworkError(
                f"网络连接错误: {str(error)}",
                url="llm_api",
                original_error=error
            )
        elif "rate" in error_msg and "limit" in error_msg:
            return LLMError(
                f"LLM API调用频率限制: {str(error)}",
                model=model,
                original_error=error
            )
        elif "authentication" in error_msg or "api key" in error_msg:
            return ConfigError(
                f"LLM API认证失败: {str(error)}",
                config_key="api_key"
            )
        else:
            return LLMError(
                f"LLM调用失败: {str(error)}",
                model=model,
                original_error=error
            )
    
    @staticmethod
    def should_retry(error: SQLConverterError) -> bool:
        """判断是否应该重试"""
        retryable_types = [
            ErrorType.NETWORK_ERROR,
            ErrorType.TIMEOUT_ERROR,
            ErrorType.LLM_ERROR
        ]
        
        retryable_severities = [
            ErrorSeverity.LOW,
            ErrorSeverity.MEDIUM
        ]
        
        return (
            error.error_type in retryable_types and
            error.severity in retryable_severities and
            not isinstance(error, ConfigError)
        )
    
    @staticmethod
    def get_user_friendly_message(error: SQLConverterError) -> str:
        """获取用户友好的错误消息"""
        if isinstance(error, SQLParseError):
            return f"SQL语法解析错误：{error.message}\n请检查SQL语法是否正确。"
        elif isinstance(error, SQLTranspilationError):
            return f"SQL转换错误：{error.message}\n请尝试简化SQL语句或检查方言支持情况。"
        elif isinstance(error, LLMTimeoutError):
            return "AI模型响应超时，请稍后重试或简化SQL语句。"
        elif isinstance(error, NetworkError):
            return "网络连接错误，请检查网络连接后重试。"
        elif isinstance(error, ConfigError):
            return f"配置错误：{error.message}\n请检查系统配置。"
        elif isinstance(error, UnsupportedFeatureError):
            return f"暂不支持的转换特性：{error.message}\n请尝试使用其他语法结构。"
        else:
            return f"转换失败：{error.message}\n请检查输入或联系技术支持。"


def get_user_friendly_message(error: SQLConverterError) -> str:
    """获取用户友好的错误消息（便捷函数）"""
    return ErrorHandler.get_user_friendly_message(error)


def create_error_handler():
    """创建错误处理器实例"""
    return ErrorHandler()