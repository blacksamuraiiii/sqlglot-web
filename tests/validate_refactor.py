"""
验证重构后的SQL转换工具
"""
import sys
import os
import time
from datetime import datetime

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_basic_functionality():
    """测试基础功能"""
    print("=" * 60)
    print("测试基础功能")
    print("=" * 60)
    
    try:
        # 导入模块
        from src.config.config import get_supported_dialects, config_manager
        from src.converters.conversion_coordinator import get_conversion_coordinator
        from src.utils.logger import get_logger
        
        print("✅ 模块导入成功")
        
        # 测试配置
        dialects = get_supported_dialects()
        print(f"✅ 支持的方言数量: {len(dialects)}")
        print(f"   方言列表: {', '.join(dialects[:5])}...")
        
        # 测试日志
        logger = get_logger()
        print("✅ 日志系统初始化成功")
        
        # 测试转换协调器
        coordinator = get_conversion_coordinator()
        print("✅ 转换协调器初始化成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 基础功能测试失败: {e}")
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
            print("✅ 简单SQL转换成功")
            print(f"   策略: {result.metadata.get('strategy', 'unknown')}")
            print(f"   耗时: {result.metadata.get('duration', 0):.3f}秒")
            print(f"   结果长度: {len(result.result_sql)} 字符")
            return True
        else:
            print(f"❌ 简单SQL转换失败: {result.error}")
            return False
            
    except Exception as e:
        print(f"❌ 简单SQL转换测试失败: {e}")
        return False

def test_oracle_procedure_conversion():
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
            print("✅ Oracle过程转换成功")
            print(f"   策略: {result.metadata.get('strategy', 'unknown')}")
            print(f"   耗时: {result.metadata.get('duration', 0):.3f}秒")
            print(f"   复杂度: {result.metadata.get('analysis', {}).get('complexity', 0)}")
            
            if result.warnings:
                print(f"   警告: {len(result.warnings)} 个")
            
            return True
        else:
            print(f"❌ Oracle过程转换失败: {result.error}")
            return False
            
    except Exception as e:
        print(f"❌ Oracle过程转换测试失败: {e}")
        return False

def test_ztc_sqlzz_conversion():
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
            print("✅ ZTC_SQLZZ转换成功")
            print(f"   策略: {result.metadata.get('strategy', 'unknown')}")
            print(f"   耗时: {result.metadata.get('duration', 0):.3f}秒")
            print(f"   结果包含ZTC_SQLZZ: {'ZTC_SQLZZ' in result.result_sql}")
            
            return True
        else:
            print(f"❌ ZTC_SQLZZ转换失败: {result.error}")
            return False
            
    except Exception as e:
        print(f"❌ ZTC_SQLZZ转换测试失败: {e}")
        return False

def test_performance():
    """测试性能"""
    print("\n" + "=" * 60)
    print("性能测试")
    print("=" * 60)
    
    try:
        from src.converters.conversion_coordinator import get_conversion_coordinator
        
        coordinator = get_conversion_coordinator()
        
        # 测试SQL
        test_sqls = [
            "SELECT * FROM users",
            "SELECT id, name FROM users WHERE status = 'active'",
            """CREATE OR REPLACE PROCEDURE simple_proc IS
            BEGIN
                NULL;
            END simple_proc;""",
            """CREATE OR REPLACE PROCEDURE complex_proc IS
            BEGIN
                ZTC_SQLZZ('SELECT * FROM table1');
                ZTC_SQLZZ('INSERT INTO table2 VALUES (1)');
            END complex_proc;"""
        ]
        
        total_time = 0
        success_count = 0
        
        for i, sql in enumerate(test_sqls):
            start_time = time.time()
            
            try:
                result = coordinator.convert_sql(
                    sql=sql,
                    from_dialect="oracle",
                    to_dialect="postgres"
                )
                
                duration = time.time() - start_time
                total_time += duration
                
                if result.success:
                    success_count += 1
                    print(f"✅ 测试 {i+1}: 成功 ({duration:.3f}s)")
                else:
                    print(f"❌ 测试 {i+1}: 失败 ({duration:.3f}s)")
                    
            except Exception as e:
                duration = time.time() - start_time
                total_time += duration
                print(f"❌ 测试 {i+1}: 异常 ({duration:.3f}s) - {e}")
        
        avg_time = total_time / len(test_sqls)
        success_rate = (success_count / len(test_sqls)) * 100
        
        print(f"\n📊 性能统计:")
        print(f"   总耗时: {total_time:.3f}秒")
        print(f"   平均耗时: {avg_time:.3f}秒")
        print(f"   成功率: {success_rate:.1f}%")
        
        return success_rate >= 75  # 至少75%成功率
        
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("SQL转换工具验证测试")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("基础功能", test_basic_functionality),
        ("简单SQL转换", test_simple_conversion),
        ("Oracle过程转换", test_oracle_procedure_conversion),
        ("ZTC_SQLZZ转换", test_ztc_sqlzz_conversion),
        ("性能测试", test_performance)
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed_tests += 1
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"通过测试: {passed_tests}/{total_tests}")
    print(f"成功率: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests == total_tests:
        print("🎉 所有测试通过！重构成功！")
        return True
    else:
        print("⚠️  部分测试失败，需要进一步调试")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)