"""
简单测试脚本 - 验证重构后的SQL转换工具
"""
import sys
import os
import time
from datetime import datetime

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_basic_imports():
    """测试基础导入"""
    print("=" * 60)
    print("测试基础导入功能")
    print("=" * 60)
    
    try:
        # 导入模块
        from src.config.config import get_supported_dialects, config_manager
        from src.converters.conversion_coordinator import get_conversion_coordinator
        from src.utils.logger import get_logger
        
        print("OK - 模块导入成功")
        
        # 测试配置
        dialects = get_supported_dialects()
        print(f"OK - 支持的方言数量: {len(dialects)}")
        print(f"    方言列表: {', '.join(dialects[:5])}...")
        
        # 测试日志
        logger = get_logger()
        print("OK - 日志系统初始化成功")
        
        # 测试转换协调器
        coordinator = get_conversion_coordinator()
        print("OK - 转换协调器初始化成功")
        
        return True
        
    except Exception as e:
        print(f"ERROR - 基础功能测试失败: {e}")
        return False

def test_simple_conversion():
    """测试简单SQL转换"""
    print("\n" + "=" * 60)
    print("测试简单SQL转换")
    print("=" * 60)
    
    try:
        from src.converters.conversion_coordinator import get_conversion_coordinator
        
        coordinator = get_conversion_coordinator()
        
        # 简单SELECT测试
        test_sql = "SELECT id, name FROM users WHERE status = 'active'"
        
        result = coordinator.convert_sql(
            sql=test_sql,
            from_dialect="mysql",
            to_dialect="postgres"
        )
        
        if result.success:
            print("OK - 简单SQL转换成功")
            print(f"    策略: {result.metadata.get('strategy', 'unknown')}")
            print(f"    耗时: {result.metadata.get('duration', 0):.3f}秒")
            print(f"    结果长度: {len(result.result_sql)} 字符")
            return True
        else:
            print(f"ERROR - 简单SQL转换失败: {result.error}")
            return False
            
    except Exception as e:
        print(f"ERROR - 简单SQL转换测试失败: {e}")
        return False

def test_oracle_procedure():
    """测试Oracle过程转换"""
    print("\n" + "=" * 60)
    print("测试Oracle过程转换")
    print("=" * 60)
    
    try:
        from src.converters.conversion_coordinator import get_conversion_coordinator
        
        coordinator = get_conversion_coordinator()
        
        # Oracle过程测试
        test_sql = """CREATE OR REPLACE PROCEDURE test_proc IS
BEGIN
    INSERT INTO log_table (message) VALUES ('Test');
    COMMIT;
END test_proc;"""
        
        result = coordinator.convert_sql(
            sql=test_sql,
            from_dialect="oracle",
            to_dialect="postgres"
        )
        
        if result.success:
            print("OK - Oracle过程转换成功")
            print(f"    策略: {result.metadata.get('strategy', 'unknown')}")
            print(f"    耗时: {result.metadata.get('duration', 0):.3f}秒")
            print(f"    复杂度: {result.metadata.get('analysis', {}).get('complexity', 0)}")
            
            if result.warnings:
                print(f"    警告: {len(result.warnings)} 个")
            
            return True
        else:
            print(f"ERROR - Oracle过程转换失败: {result.error}")
            return False
            
    except Exception as e:
        print(f"ERROR - Oracle过程转换测试失败: {e}")
        return False

def test_ztc_sqlzz():
    """测试ZTC_SQLZZ转换"""
    print("\n" + "=" * 60)
    print("测试ZTC_SQLZZ转换")
    print("=" * 60)
    
    try:
        from src.converters.conversion_coordinator import get_conversion_coordinator
        
        coordinator = get_conversion_coordinator()
        
        # ZTC_SQLZZ测试
        test_sql = """CREATE OR REPLACE PROCEDURE ztc_test IS
BEGIN
    ZTC_SQLZZ('INSERT INTO temp_table VALUES (1, ''test'')');
END ztc_test;"""
        
        result = coordinator.convert_sql(
            sql=test_sql,
            from_dialect="oracle",
            to_dialect="postgres"
        )
        
        if result.success:
            print("OK - ZTC_SQLZZ转换成功")
            print(f"    策略: {result.metadata.get('strategy', 'unknown')}")
            print(f"    耗时: {result.metadata.get('duration', 0):.3f}秒")
            print(f"    结果包含ZTC_SQLZZ: {'ZTC_SQLZZ' in result.result_sql}")
            
            return True
        else:
            print(f"ERROR - ZTC_SQLZZ转换失败: {result.error}")
            return False
            
    except Exception as e:
        print(f"ERROR - ZTC_SQLZZ转换测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("SQL转换工具验证测试")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("基础功能", test_basic_imports),
        ("简单SQL转换", test_simple_conversion),
        ("Oracle过程转换", test_oracle_procedure),
        ("ZTC_SQLZZ转换", test_ztc_sqlzz),
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed_tests += 1
        except Exception as e:
            print(f"ERROR - {test_name}测试异常: {e}")
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"通过测试: {passed_tests}/{total_tests}")
    print(f"成功率: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests == total_tests:
        print("SUCCESS - 所有测试通过！重构成功！")
        return True
    else:
        print("WARNING - 部分测试失败，需要进一步调试")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)