"""
日志记录系统
"""
import logging
import json
import time
from typing import Any, Dict, Optional
from datetime import datetime
from pathlib import Path
from ..utils.exceptions import SQLConverterError, ErrorType


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    # ANSI颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m'      # 重置
    }
    
    def format(self, record):
        # 添加颜色
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """JSON格式日志格式化器"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # 添加异常信息
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_entry.update(record.extra_data)
        
        return json.dumps(log_entry, ensure_ascii=False)


class ConversionLogger:
    """SQL转换日志记录器"""
    
    def __init__(self, name: str = "sql_converter", level: int = logging.INFO):
        """初始化日志记录器"""
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        # 避免重复添加处理器
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """设置日志处理器"""
        # 控制台处理器（彩色输出）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        
        # 文件处理器（JSON格式）
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_dir / f"sql_converter_{datetime.now().strftime('%Y%m%d')}.log",
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = JSONFormatter()
        file_handler.setFormatter(file_formatter)
        
        # 添加处理器
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def start_conversion(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        conversion_id: Optional[str] = None,
        method: str = "unknown"
    ):
        """记录转换开始"""
        extra_data = {
            'conversion_id': conversion_id or str(int(time.time())),
            'from_dialect': from_dialect,
            'to_dialect': to_dialect,
            'method': method,
            'sql_length': len(sql),
            'sql_preview': sql[:200] + "..." if len(sql) > 200 else sql
        }
        
        self.logger.info(
            f"开始转换SQL: {from_dialect} → {to_dialect}",
            extra={'extra_data': extra_data}
        )
        return extra_data['conversion_id']
    
    def log_conversion_start(
        self, 
        sql: str, 
        from_dialect: str, 
        to_dialect: str, 
        conversion_id: Optional[str] = None
    ):
        """记录转换开始"""
        return self.start_conversion(sql, from_dialect, to_dialect, conversion_id)
    
    def log_conversion_success(
        self, 
        conversion_id: str, 
        duration: float, 
        result_length: int,
        method: str = "sqlglot"
    ):
        """记录转换成功"""
        extra_data = {
            'conversion_id': conversion_id,
            'duration_ms': round(duration * 1000, 2),
            'result_length': result_length,
            'method': method,
            'status': 'success'
        }
        
        self.logger.info(
            f"转换成功完成: {duration:.3f}s",
            extra={'extra_data': extra_data}
        )
    
    def log_conversion_error(
        self, 
        conversion_id: str, 
        error: SQLConverterError, 
        duration: float,
        method: str = "unknown"
    ):
        """记录转换错误"""
        extra_data = {
            'conversion_id': conversion_id,
            'duration_ms': round(duration * 1000, 2),
            'error_type': error.error_type.value,
            'error_severity': error.severity.value,
            'error_message': error.message,
            'method': method,
            'status': 'error'
        }
        
        if error.context:
            extra_data['error_context'] = error.context
        
        self.logger.error(
            f"转换失败: {error}",
            extra={'extra_data': extra_data},
            exc_info=error.original_error
        )
    
    def log_llm_call(
        self, 
        conversion_id: str, 
        model: str, 
        prompt_length: int, 
        response_length: int,
        duration: float
    ):
        """记录LLM调用"""
        extra_data = {
            'conversion_id': conversion_id,
            'model': model,
            'prompt_length': prompt_length,
            'response_length': response_length,
            'duration_ms': round(duration * 1000, 2),
            'event_type': 'llm_call'
        }
        
        self.logger.debug(
            f"LLM调用: {model} ({duration:.3f}s)",
            extra={'extra_data': extra_data}
        )
    
    def log_validation_result(
        self, 
        conversion_id: str, 
        is_valid: bool, 
        validation_details: Optional[Dict[str, Any]] = None
    ):
        """记录验证结果"""
        extra_data = {
            'conversion_id': conversion_id,
            'validation_passed': is_valid,
            'event_type': 'validation'
        }
        
        if validation_details:
            extra_data['validation_details'] = validation_details
        
        level = logging.INFO if is_valid else logging.WARNING
        message = "SQL验证通过" if is_valid else "SQL验证失败"
        
        self.logger.log(
            level,
            message,
            extra={'extra_data': extra_data}
        )
    
    def log_cache_operation(
        self, 
        operation: str, 
        cache_key: str, 
        hit: bool = False,
        duration: Optional[float] = None
    ):
        """记录缓存操作"""
        extra_data = {
            'cache_operation': operation,
            'cache_key': cache_key,
            'cache_hit': hit,
            'event_type': 'cache'
        }
        
        if duration:
            extra_data['duration_ms'] = round(duration * 1000, 2)
        
        self.logger.debug(
            f"缓存{operation}: {'命中' if hit else '未命中'}",
            extra={'extra_data': extra_data}
        )
    
    def log_performance_metrics(
        self, 
        metrics: Dict[str, Any]
    ):
        """记录性能指标"""
        extra_data = {
            'event_type': 'performance_metrics',
            'metrics': metrics
        }
        
        self.logger.info(
            "性能指标统计",
            extra={'extra_data': extra_data}
        )
    
    def debug(self, message: str, **kwargs):
        """调试日志"""
        self.logger.debug(message, extra={'extra_data': kwargs} if kwargs else None)
    
    def info(self, message: str, **kwargs):
        """信息日志"""
        self.logger.info(message, extra={'extra_data': kwargs} if kwargs else None)
    
    def warning(self, message: str, **kwargs):
        """警告日志"""
        self.logger.warning(message, extra={'extra_data': kwargs} if kwargs else None)
    
    def error(self, message: str, **kwargs):
        """错误日志"""
        self.logger.error(message, extra={'extra_data': kwargs} if kwargs else None)
    
    def critical(self, message: str, **kwargs):
        """严重错误日志"""
        self.logger.critical(message, extra={'extra_data': kwargs} if kwargs else None)


class PerformanceTracker:
    """性能跟踪器"""
    
    def __init__(self, logger: ConversionLogger):
        self.logger = logger
        self.metrics = {
            'total_conversions': 0,
            'successful_conversions': 0,
            'failed_conversions': 0,
            'avg_conversion_time': 0,
            'total_conversion_time': 0,
            'llm_calls': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
    
    def start_conversion(self) -> str:
        """开始转换跟踪"""
        self.metrics['total_conversions'] += 1
        return str(int(time.time()))
    
    def end_conversion_success(self, duration: float):
        """结束成功转换"""
        self.metrics['successful_conversions'] += 1
        self.metrics['total_conversion_time'] += duration
        self.metrics['avg_conversion_time'] = (
            self.metrics['total_conversion_time'] / self.metrics['successful_conversions']
        )
    
    def end_conversion_error(self):
        """结束失败转换"""
        self.metrics['failed_conversions'] += 1
    
    def track_llm_call(self):
        """跟踪LLM调用"""
        self.metrics['llm_calls'] += 1
    
    def track_cache_hit(self):
        """跟踪缓存命中"""
        self.metrics['cache_hits'] += 1
    
    def track_cache_miss(self):
        """跟踪缓存未命中"""
        self.metrics['cache_misses'] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        success_rate = (
            self.metrics['successful_conversions'] / self.metrics['total_conversions']
            if self.metrics['total_conversions'] > 0 else 0
        )
        
        cache_hit_rate = (
            self.metrics['cache_hits'] / (self.metrics['cache_hits'] + self.metrics['cache_misses'])
            if (self.metrics['cache_hits'] + self.metrics['cache_misses']) > 0 else 0
        )
        
        return {
            **self.metrics,
            'success_rate': round(success_rate * 100, 2),
            'cache_hit_rate': round(cache_hit_rate * 100, 2)
        }
    
    def log_metrics(self):
        """记录性能指标"""
        metrics = self.get_metrics()
        self.logger.log_performance_metrics(metrics)


# 全局日志记录器实例
logger = ConversionLogger()
performance_tracker = PerformanceTracker(logger)


def get_logger() -> ConversionLogger:
    """获取日志记录器实例"""
    return logger


def get_performance_tracker() -> PerformanceTracker:
    """获取性能跟踪器实例"""
    return performance_tracker