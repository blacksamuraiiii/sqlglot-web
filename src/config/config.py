"""
配置管理模块
"""
import os
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv


class LLMConfig(BaseModel):
    """LLM配置"""
    base_url: str = Field(default="https://api-inference.modelscope.cn/v1/")
    api_key: str = Field(default="")
    model: str = Field(default="Qwen/Qwen2.5-72B-Instruct")
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=4096, gt=0)
    timeout: int = Field(default=30, gt=0)


class ConversionConfig(BaseModel):
    """转换配置"""
    pretty_print: bool = Field(default=True)
    validate_syntax: bool = Field(default=True)
    llm_fallback_enabled: bool = Field(default=True)
    max_retries: int = Field(default=3, ge=0)
    cache_enabled: bool = Field(default=True)
    cache_ttl: int = Field(default=3600, gt=0)  # 缓存时间（秒）


class DatabaseConfig(BaseModel):
    """数据库方言配置"""
    identifier_quote: str = Field(default='"')
    string_quote: str = Field(default="'")
    max_identifier_length: int = Field(default=63)
    supports_procedures: bool = Field(default=True)
    supports_functions: bool = Field(default=True)
    supports_packages: bool = Field(default=False)


class AppConfig(BaseModel):
    """应用主配置"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    conversion: ConversionConfig = Field(default_factory=ConversionConfig)
    database: Dict[str, DatabaseConfig] = Field(default_factory=dict)
    
    # 支持的SQL方言列表
    supported_dialects: list = Field(default_factory=lambda: [
        "athena", "bigquery", "clickhouse", "databricks", "doris", "drill", 
        "druid", "duckdb", "dune", "hive", "materialize", "mysql", "oracle", 
        "postgres", "presto", "prql", "redshift", "risingwave", "snowflake", 
        "spark", "spark2", "sqlite", "starrocks", "tableau", "teradata", 
        "trino", "tsql"
    ])
    
    class Config:
        env_file = ".env"
        env_prefix = "SQL_CONVERTER_"


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, env_file: str = ".env"):
        """初始化配置管理器"""
        load_dotenv(env_file)
        self._config = self._load_config()
        self._database_configs = self._init_database_configs()
    
    def _load_config(self) -> AppConfig:
        """加载配置"""
        # 从环境变量加载LLM配置
        llm_config = LLMConfig(
            base_url=os.getenv("base_url", "https://api-inference.modelscope.cn/v1/"),
            api_key=os.getenv("api_key", ""),
            model=os.getenv("model", "Qwen/Qwen2.5-72B-Instruct"),
            temperature=float(os.getenv("temperature", "0.1")),
            max_tokens=int(os.getenv("max_tokens", "4096")),
            timeout=int(os.getenv("timeout", "30"))
        )
        
        return AppConfig(llm=llm_config)
    
    def _init_database_configs(self) -> Dict[str, DatabaseConfig]:
        """初始化数据库配置"""
        configs = {}
        
        # Oracle配置
        configs["oracle"] = DatabaseConfig(
            identifier_quote='"',
            string_quote="'",
            max_identifier_length=30,
            supports_procedures=True,
            supports_functions=True,
            supports_packages=True
        )
        
        # PostgreSQL配置
        configs["postgres"] = DatabaseConfig(
            identifier_quote='"',
            string_quote="'",
            max_identifier_length=63,
            supports_procedures=True,
            supports_functions=True,
            supports_packages=False
        )
        
        # MySQL配置
        configs["mysql"] = DatabaseConfig(
            identifier_quote='`',
            string_quote="'",
            max_identifier_length=64,
            supports_procedures=True,
            supports_functions=True,
            supports_packages=False
        )
        
        # SQL Server配置
        configs["tsql"] = DatabaseConfig(
            identifier_quote='"',
            string_quote="'",
            max_identifier_length=128,
            supports_procedures=True,
            supports_functions=True,
            supports_packages=False
        )
        
        # 为其他方言设置默认配置
        for dialect in self._config.supported_dialects:
            if dialect not in configs:
                configs[dialect] = DatabaseConfig()
        
        return configs
    
    @property
    def config(self) -> AppConfig:
        """获取应用配置"""
        return self._config
    
    @property
    def llm_config(self) -> LLMConfig:
        """获取LLM配置"""
        return self._config.llm
    
    @property
    def conversion_config(self) -> ConversionConfig:
        """获取转换配置"""
        return self._config.conversion
    
    def get_database_config(self, dialect: str) -> DatabaseConfig:
        """获取特定数据库配置"""
        return self._database_configs.get(dialect, DatabaseConfig())
    
    def is_dialect_supported(self, dialect: str) -> bool:
        """检查方言是否支持"""
        return dialect in self._config.supported_dialects
    
    def get_supported_dialects(self) -> list:
        """获取支持的方言列表"""
        return self._config.supported_dialects.copy()
    
    def update_llm_config(self, **kwargs):
        """更新LLM配置"""
        for key, value in kwargs.items():
            if hasattr(self._config.llm, key):
                setattr(self._config.llm, key, value)
    
    def update_conversion_config(self, **kwargs):
        """更新转换配置"""
        for key, value in kwargs.items():
            if hasattr(self._config.conversion, key):
                setattr(self._config.conversion, key, value)


# 全局配置实例
config_manager = ConfigManager()

# 便捷访问函数
def get_config() -> AppConfig:
    """获取应用配置"""
    return config_manager.config

def get_llm_config() -> LLMConfig:
    """获取LLM配置"""
    return config_manager.llm_config

def get_conversion_config() -> ConversionConfig:
    """获取转换配置"""
    return config_manager.conversion_config

def get_database_config(dialect: str) -> DatabaseConfig:
    """获取数据库配置"""
    return config_manager.get_database_config(dialect)

def get_supported_dialects() -> list:
    """获取支持的方言列表"""
    return config_manager.get_supported_dialects()