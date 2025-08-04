"""
测试用例模块
"""
import pytest
import json
from typing import Dict, Any, List, Tuple
from datetime import datetime

from src.converters.conversion_coordinator import get_conversion_coordinator
from src.config.config import get_supported_dialects
from src.utils.logger import get_logger

logger = get_logger()
coordinator = get_conversion_coordinator()


class TestCase:
    """测试用例类"""
    
    def __init__(
        self, 
        name: str, 
        input_sql: str, 
        from_dialect: str, 
        to_dialect: str,
        expected_result: str = None,
        expected_strategy: str = None,
        complexity_min: int = None,
        complexity_max: int = None,
        tags: List[str] = None
    ):
        self.name = name
        self.input_sql = input_sql
        self.from_dialect = from_dialect
        self.to_dialect = to_dialect
        self.expected_result = expected_result
        self.expected_strategy = expected_strategy
        self.complexity_min = complexity_min
        self.complexity_max = complexity_max
        self.tags = tags or []
        self.result = None
        self.passed = False
        self.error = None
        self.execution_time = None
    
    def run(self) -> bool:
        """运行测试用例"""
        start_time = datetime.now()
        
        try:
            # 执行转换
            result = coordinator.convert_sql(
                self.input_sql, 
                self.from_dialect, 
                self.to_dialect
            )
            
            self.result = result
            self.execution_time = (datetime.now() - start_time).total_seconds()
            
            # 验证结果
            self.passed = self._validate_result(result)
            
            return self.passed
            
        except Exception as e:
            self.error = str(e)
            self.execution_time = (datetime.now() - start_time).total_seconds()
            self.passed = False
            return False
    
    def _validate_result(self, result) -> bool:
        """验证测试结果"""
        if not result.success:
            return False
        
        # 检查策略是否符合预期
        if self.expected_strategy:
            actual_strategy = result.metadata.get('strategy')
            if actual_strategy != self.expected_strategy:
                logger.warning(f"策略不匹配: 预期 {self.expected_strategy}, 实际 {actual_strategy}")
        
        # 检查复杂度范围
        complexity = result.metadata.get('analysis', {}).get('complexity', 0)
        if self.complexity_min and complexity < self.complexity_min:
            logger.warning(f"复杂度低于最小值: {complexity} < {self.complexity_min}")
        
        if self.complexity_max and complexity > self.complexity_max:
            logger.warning(f"复杂度超过最大值: {complexity} > {self.complexity_max}")
        
        # 检查预期结果（如果提供）
        if self.expected_result:
            # 简化的结果比较（忽略空格和大小写差异）
            normalized_result = ' '.join(result.result_sql.lower().split())
            normalized_expected = ' '.join(self.expected_result.lower().split())
            
            if normalized_expected not in normalized_result:
                logger.warning("结果与预期不匹配")
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'name': self.name,
            'input_sql': self.input_sql[:200] + "..." if len(self.input_sql) > 200 else self.input_sql,
            'from_dialect': self.from_dialect,
            'to_dialect': self.to_dialect,
            'expected_strategy': self.expected_strategy,
            'tags': self.tags,
            'passed': self.passed,
            'error': self.error,
            'execution_time': self.execution_time,
            'result': {
                'success': self.result.success if self.result else False,
                'strategy': self.result.metadata.get('strategy') if self.result else None,
                'complexity': self.result.metadata.get('analysis', {}).get('complexity') if self.result else 0,
                'duration': self.result.metadata.get('duration') if self.result else 0
            } if self.result else None
        }


class TestSuite:
    """测试套件类"""
    
    def __init__(self, name: str):
        self.name = name
        self.test_cases = []
        self.results = []
    
    def add_test_case(self, test_case: TestCase):
        """添加测试用例"""
        self.test_cases.append(test_case)
    
    def run_all(self) -> Dict[str, Any]:
        """运行所有测试用例"""
        logger.info(f"开始运行测试套件: {self.name}")
        
        self.results = []
        passed_count = 0
        failed_count = 0
        total_time = 0
        
        for test_case in self.test_cases:
            logger.info(f"运行测试用例: {test_case.name}")
            
            if test_case.run():
                passed_count += 1
            else:
                failed_count += 1
            
            total_time += test_case.execution_time or 0
            self.results.append(test_case)
        
        # 计算统计信息
        success_rate = (passed_count / len(self.test_cases)) * 100 if self.test_cases else 0
        avg_time = total_time / len(self.test_cases) if self.test_cases else 0
        
        stats = {
            'total_tests': len(self.test_cases),
            'passed': passed_count,
            'failed': failed_count,
            'success_rate': success_rate,
            'total_time': total_time,
            'average_time': avg_time
        }
        
        logger.info(f"测试套件完成: {self.name}")
        logger.info(f"通过: {passed_count}/{len(self.test_cases)} ({success_rate:.1f}%)")
        
        return {
            'suite_name': self.name,
            'stats': stats,
            'results': [result.to_dict() for result in self.results]
        }
    
    def get_failed_tests(self) -> List[TestCase]:
        """获取失败的测试用例"""
        return [result for result in self.results if not result.passed]


def create_basic_test_suite() -> TestSuite:
    """创建基础测试套件"""
    suite = TestSuite("基础SQL转换测试")
    
    # 简单SELECT测试
    suite.add_test_case(TestCase(
        name="简单SELECT语句",
        input_sql="SELECT id, name FROM users WHERE status = 'active'",
        from_dialect="mysql",
        to_dialect="postgres",
        expected_strategy="sqlglot",
        complexity_min=1,
        complexity_max=3,
        tags=["basic", "select"]
    ))
    
    # 带聚合函数的SELECT
    suite.add_test_case(TestCase(
        name="带聚合函数的SELECT",
        input_sql="SELECT department, COUNT(*) as employee_count FROM employees GROUP BY department",
        from_dialect="oracle",
        to_dialect="postgres",
        expected_strategy="sqlglot",
        complexity_min=2,
        complexity_max=4,
        tags=["aggregate", "group_by"]
    ))
    
    # JOIN操作
    suite.add_test_case(TestCase(
        name="多表JOIN",
        input_sql="SELECT u.name, d.department_name FROM users u JOIN departments d ON u.department_id = d.id",
        from_dialect="mysql",
        to_dialect="postgres",
        expected_strategy="sqlglot",
        complexity_min=2,
        complexity_max=4,
        tags=["join"]
    ))
    
    return suite


def create_oracle_to_postgres_test_suite() -> TestSuite:
    """创建Oracle到PostgreSQL的专用测试套件"""
    suite = TestSuite("Oracle到PostgreSQL转换测试")
    
    # Oracle过程转换
    suite.add_test_case(TestCase(
        name="Oracle简单过程",
        input_sql="""CREATE OR REPLACE PROCEDURE simple_proc IS
BEGIN
    INSERT INTO log_table (message) VALUES ('Procedure executed');
    COMMIT;
END simple_proc;""",
        from_dialect="oracle",
        to_dialect="postgres",
        expected_strategy="llm",
        complexity_min=4,
        complexity_max=6,
        tags=["oracle", "postgres", "procedure"]
    ))
    
    # Oracle函数转换
    suite.add_test_case(TestCase(
        name="Oracle函数",
        input_sql="""CREATE OR REPLACE FUNCTION get_tax(amount NUMBER) RETURN NUMBER IS
    tax_rate NUMBER := 0.1;
BEGIN
    RETURN amount * tax_rate;
END get_tax;""",
        from_dialect="oracle",
        to_dialect="postgres",
        expected_strategy="llm",
        complexity_min=4,
        complexity_max=6,
        tags=["oracle", "postgres", "function"]
    ))
    
    # 带ZTC_SQLZZ的Oracle过程
    suite.add_test_case(TestCase(
        name="带ZTC_SQLZZ的Oracle过程",
        input_sql="""CREATE OR REPLACE PROCEDURE test_ztc IS
BEGIN
    ZTC_SQLZZ('INSERT INTO temp_table VALUES (1, ''test'')');
END test_ztc;""",
        from_dialect="oracle",
        to_dialect="postgres",
        expected_strategy="llm",
        complexity_min=5,
        complexity_max=7,
        tags=["oracle", "postgres", "ztc_sqlzz"]
    ))
    
    return suite


def create_complex_sql_test_suite() -> TestSuite:
    """创建复杂SQL测试套件"""
    suite = TestSuite("复杂SQL转换测试")
    
    # 复杂的嵌套查询
    suite.add_test_case(TestCase(
        name="复杂嵌套查询",
        input_sql="""SELECT d.department_name, 
       (SELECT COUNT(*) FROM employees e WHERE e.department_id = d.department_id) as emp_count
FROM departments d
WHERE d.department_id IN (SELECT department_id FROM projects WHERE status = 'active')""",
        from_dialect="oracle",
        to_dialect="postgres",
        expected_strategy="hybrid",
        complexity_min=5,
        complexity_max=7,
        tags=["complex", "subquery"]
    ))
    
    # 窗口函数
    suite.add_test_case(TestCase(
        name="窗口函数",
        input_sql="""SELECT employee_id, department_id, salary,
       RANK() OVER (PARTITION BY department_id ORDER BY salary DESC) as salary_rank
FROM employees""",
        from_dialect="oracle",
        to_dialect="postgres",
        expected_strategy="sqlglot",
        complexity_min=4,
        complexity_max=6,
        tags=["window_function"]
    ))
    
    return suite


def create_performance_test_suite() -> TestSuite:
    """创建性能测试套件"""
    suite = TestSuite("性能测试")
    
    # 大量数据的SQL
    large_sql = """SELECT /*+ INDEX(u idx_user_name) */ u.user_id, u.username, u.email,
       o.order_id, o.order_date, o.total_amount,
       (SELECT COUNT(*) FROM order_items oi WHERE oi.order_id = o.order_id) as item_count
FROM users u
JOIN orders o ON u.user_id = o.user_id
WHERE u.created_date >= TO_DATE('2023-01-01', 'YYYY-MM-DD')
  AND o.status = 'completed'
ORDER BY u.username, o.order_date"""
    
    suite.add_test_case(TestCase(
        name="大数据量查询",
        input_sql=large_sql,
        from_dialect="oracle",
        to_dialect="postgres",
        expected_strategy="hybrid",
        complexity_min=6,
        complexity_max=8,
        tags=["performance", "large_query"]
    ))
    
    return suite


def run_all_tests() -> Dict[str, Any]:
    """运行所有测试套件"""
    logger.info("开始运行所有测试套件")
    
    # 创建所有测试套件
    test_suites = [
        create_basic_test_suite(),
        create_oracle_to_postgres_test_suite(),
        create_complex_sql_test_suite(),
        create_performance_test_suite()
    ]
    
    all_results = []
    total_stats = {
        'total_tests': 0,
        'passed': 0,
        'failed': 0,
        'success_rate': 0,
        'total_time': 0
    }
    
    # 运行每个测试套件
    for suite in test_suites:
        suite_result = suite.run_all()
        all_results.append(suite_result)
        
        # 累加统计信息
        stats = suite_result['stats']
        total_stats['total_tests'] += stats['total_tests']
        total_stats['passed'] += stats['passed']
        total_stats['failed'] += stats['failed']
        total_stats['total_time'] += stats['total_time']
    
    # 计算总体成功率
    if total_stats['total_tests'] > 0:
        total_stats['success_rate'] = (total_stats['passed'] / total_stats['total_tests']) * 100
    
    final_result = {
        'test_run_summary': {
            'timestamp': datetime.now().isoformat(),
            'total_suites': len(test_suites),
            'stats': total_stats
        },
        'suite_results': all_results
    }
    
    logger.info(f"所有测试完成: 总体成功率 {total_stats['success_rate']:.1f}%")
    
    return final_result


def generate_test_report(test_results: Dict[str, Any]) -> str:
    """生成测试报告"""
    report = []
    
    # 报告头部
    report.append("# SQL转换工具测试报告")
    report.append(f"**生成时间**: {test_results['test_run_summary']['timestamp']}")
    report.append(f"**测试套件数量**: {test_results['test_run_summary']['total_suites']}")
    report.append("")
    
    # 总体统计
    stats = test_results['test_run_summary']['stats']
    report.append("## 总体统计")
    report.append(f"- **总测试用例数**: {stats['total_tests']}")
    report.append(f"- **通过数量**: {stats['passed']}")
    report.append(f"- **失败数量**: {stats['failed']}")
    report.append(f"- **成功率**: {stats['success_rate']:.1f}%")
    report.append(f"- **总执行时间**: {stats['total_time']:.2f}秒")
    report.append("")
    
    # 各测试套件详情
    report.append("## 测试套件详情")
    for suite_result in test_results['suite_results']:
        suite_name = suite_result['suite_name']
        suite_stats = suite_result['stats']
        
        report.append(f"### {suite_name}")
        report.append(f"- **测试用例数**: {suite_stats['total_tests']}")
        report.append(f"- **通过数**: {suite_stats['passed']}")
        report.append(f"- **失败数**: {suite_stats['failed']}")
        report.append(f"- **成功率**: {suite_stats['success_rate']:.1f}%")
        report.append(f"- **平均耗时**: {suite_stats['average_time']:.2f}秒")
        report.append("")
        
        # 失败的测试用例
        failed_tests = [r for r in suite_result['results'] if not r['passed']]
        if failed_tests:
            report.append("#### 失败的测试用例:")
            for test in failed_tests:
                report.append(f"- **{test['name']}**")
                if test['error']:
                    report.append(f"  - 错误: {test['error']}")
                report.append("")
    
    return "\n".join(report)


if __name__ == "__main__":
    # 运行测试
    results = run_all_tests()
    
    # 生成报告
    report = generate_test_report(results)
    
    # 保存报告
    with open("test_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    
    print("测试完成！报告已保存到 test_report.md")
    print(f"总体成功率: {results['test_run_summary']['stats']['success_rate']:.1f}%")