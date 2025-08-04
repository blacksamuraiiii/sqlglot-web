"""
测试运行器 - 统一运行所有测试
"""
import sys
import os
from datetime import datetime

# 添加src路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def run_all_tests():
    """运行所有测试"""
    print("=" * 80)
    print("SQL转换工具 - 完整测试套件")
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 导入测试模块
    try:
        from test_suite import run_test_suite
        from simple_test import main as run_simple_test
        from validate_refactor import main as run_validation_test
    except ImportError as e:
        print(f"❌ 导入测试模块失败: {e}")
        return False
    
    tests = [
        ("测试套件", run_test_suite),
        ("简单测试", run_simple_test),
        ("验证测试", run_validation_test),
    ]
    
    passed_tests = 0
    total_tests = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*60}")
        print(f"运行 {test_name}")
        print(f"{'='*60}")
        
        try:
            if test_func():
                print(f"✅ {test_name} 通过")
                passed_tests += 1
            else:
                print(f"❌ {test_name} 失败")
        except Exception as e:
            print(f"❌ {test_name} 异常: {e}")
    
    print(f"\n{'='*80}")
    print("测试总结")
    print(f"{'='*80}")
    print(f"通过测试: {passed_tests}/{total_tests}")
    print(f"成功率: {(passed_tests/total_tests)*100:.1f}%")
    
    if passed_tests == total_tests:
        print("🎉 所有测试通过！")
        return True
    else:
        print("⚠️  部分测试失败")
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)