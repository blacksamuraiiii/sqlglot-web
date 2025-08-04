"""
SQL方言转换工具 - 重构版本
"""
import time
import streamlit as st
import json
from typing import Dict, Any, Optional
from datetime import datetime

# 导入我们的重构模块
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.config.config import config_manager, get_supported_dialects
from src.converters.conversion_coordinator import get_conversion_coordinator, ConversionResult
from src.utils.logger import get_logger, get_performance_tracker
from src.utils.exceptions import ErrorHandler, get_user_friendly_message

# 初始化
logger = get_logger()
performance_tracker = get_performance_tracker()
error_handler = ErrorHandler()
coordinator = get_conversion_coordinator()

# 页面配置
st.set_page_config(
    layout="wide", 
    page_title="SQL方言转换工具 v2.0",
    page_icon="🔄",
    initial_sidebar_state="expanded"
)

# 自定义CSS样式
def load_custom_css():
    """加载自定义CSS样式"""
    st.markdown("""
    <style>
        .main-header {
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            padding: 2rem;
            border-radius: 10px;
            margin-bottom: 2rem;
        }
        
        .metric-card {
            background: #f8f9fa;
            padding: 1rem;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }
        
        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 1rem;
            border-radius: 5px;
            border: 1px solid #c3e6cb;
        }
        
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 1rem;
            border-radius: 5px;
            border: 1px solid #f5c6cb;
        }
        
        .warning-message {
            background: #fff3cd;
            color: #856404;
            padding: 1rem;
            border-radius: 5px;
            border: 1px solid #ffeaa7;
        }
        
        .code-container {
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 5px;
            padding: 1rem;
        }
        
        .loading-spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin: 1rem 0;
        }
        
        .strategy-badge {
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.875rem;
            font-weight: 500;
        }
        
        .strategy-sqlglot {
            background: #d1ecf1;
            color: #0c5460;
        }
        
        .strategy-llm {
            background: #f8d7da;
            color: #721c24;
        }
        
        .strategy-hybrid {
            background: #d4edda;
            color: #155724;
        }
    </style>
    """, unsafe_allow_html=True)

def initialize_session_state():
    """初始化会话状态"""
    if 'conversion_history' not in st.session_state:
        st.session_state.conversion_history = []
    
    if 'current_result' not in st.session_state:
        st.session_state.current_result = None
    
    if 'show_stats' not in st.session_state:
        st.session_state.show_stats = False
    
    if 'theme' not in st.session_state:
        st.session_state.theme = 'light'

def render_header():
    """渲染页面头部"""
    st.markdown("""
    <div class="main-header">
        <h1 style="color: white; margin: 0;">🔄 SQL方言转换工具 v2.0</h1>
        <p style="color: rgba(255,255,255,0.9); margin: 0.5rem 0 0 0;">
            基于SQLGlot和LLM的智能SQL方言转换工具 - 支持复杂PL/SQL结构转换
        </p>
    </div>
    """, unsafe_allow_html=True)

def render_sidebar():
    """渲染侧边栏"""
    st.sidebar.title("⚙️ 设置")
    
    # 方言选择
    st.sidebar.subheader("方言配置")
    
    supported_dialects = get_supported_dialects()
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        from_dialect = st.selectbox(
            "源方言:", 
            supported_dialects,
            index=supported_dialects.index('oracle') if 'oracle' in supported_dialects else 0,
            key='from_dialect'
        )
    
    with col2:
        to_dialect = st.selectbox(
            "目标方言:", 
            supported_dialects,
            index=supported_dialects.index('postgres') if 'postgres' in supported_dialects else 0,
            key='to_dialect'
        )
    
    # 转换选项
    st.sidebar.subheader("转换选项")
    
    pretty_print = st.checkbox("格式化输出", value=True, key='pretty_print')
    validate_syntax = st.checkbox("语法验证", value=True, key='validate_syntax')
    llm_fallback = st.checkbox("LLM智能回退", value=True, key='llm_fallback')
    
    # 更新配置
    config_manager.update_conversion_config(
        pretty_print=pretty_print,
        validate_syntax=validate_syntax,
        llm_fallback_enabled=llm_fallback
    )
    
    # 统计信息
    st.sidebar.subheader("📊 统计信息")
    
    if st.sidebar.button("刷新统计", key='refresh_stats'):
        st.session_state.show_stats = True
    
    if st.session_state.show_stats:
        render_stats_sidebar()
    
    # 历史记录
    st.sidebar.subheader("📝 历史记录")
    
    if st.sidebar.button("清空历史", key='clear_history'):
        st.session_state.conversion_history = []
        st.sidebar.success("历史记录已清空")
    
    # 显示最近的历史记录
    if st.session_state.conversion_history:
        st.sidebar.write("最近转换:")
        for i, record in enumerate(st.session_state.conversion_history[-5:]):
            with st.sidebar.expander(f"{record['timestamp']}"):
                st.write(f"{record['from_dialect']} → {record['to_dialect']}")
                st.write(f"策略: {record['strategy']}")
                st.write(f"状态: {'✅ 成功' if record['success'] else '❌ 失败'}")

def render_stats_sidebar():
    """渲染侧边栏统计信息"""
    stats = coordinator.get_stats()
    perf_stats = performance_tracker.get_metrics()
    
    st.sidebar.markdown("""
    <div class="stats-grid">
        <div class="metric-card">
            <h4>总转换次数</h4>
            <h3>{}</h3>
        </div>
        <div class="metric-card">
            <h4>成功率</h4>
            <h3>{:.1f}%</h3>
        </div>
        <div class="metric-card">
            <h4>平均耗时</h4>
            <h3>{:.2f}s</h3>
        </div>
        <div class="metric-card">
            <h4>SQLGlot使用率</h4>
            <h3>{:.1f}%</h3>
        </div>
    </div>
    """.format(
        stats['total_conversions'],
        stats['success_rate'],
        stats['avg_conversion_time'],
        stats['sqlglot_usage_rate']
    ), unsafe_allow_html=True)

def render_main_content():
    """渲染主要内容"""
    # 创建两列布局
    input_col, output_col = st.columns([1, 1])
    
    with input_col:
        st.subheader("📝 输入SQL")
        
        # SQL输入区域
        input_sql = st.text_area(
            "请输入要转换的SQL语句:",
            height=400,
            key="input_sql_area",
            help="支持复杂的PL/SQL过程、函数、动态SQL等结构"
        )
        
        # 示例SQL按钮
        if st.button("📋 加载示例SQL", key="load_example"):
            example_sql = """create or replace procedure ZTC_JURUI_KHZF_PRC is
begin
  ZTC_SQLZZ('
  INSERT INTO ztc_jurui_khjl_tmp2
  SELECT to_char(sysdate-1,''yyyymmdd'') as 账期,''累计已走访客户经理数'' as tp,2 as xh,
  count(case when a.行政架构下的政企承包支局名称 = ''市数字政府行客支局'' 
         then 1 else null end) 创新中心
  FROM ztc_jurui_khjl_tmp1 a
  WHERE TO_CHAR(to_date(a.创建时间,''yyyy-mm-dd hh24:mi:ss''),''YYYYMMdd'') >= 202008
  ');
end ZTC_JURUI_KHZF_PRC;"""
            
            st.session_state.input_sql_area = example_sql
            st.success("示例SQL已加载")
    
    with output_col:
        st.subheader("🎯 转换结果")
        
        # 转换按钮
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            convert_button = st.button(
                "🚀 开始转换", 
                key="convert_button",
                type="primary",
                use_container_width=True
            )
        
        with col2:
            clear_button = st.button(
                "🗑️ 清空", 
                key="clear_button",
                use_container_width=True
            )
        
        with col3:
            copy_button = st.button(
                "📋 复制", 
                key="copy_button",
                use_container_width=True
            )
        
        # 处理按钮点击
        if convert_button:
            handle_conversion()
        
        if clear_button:
            st.session_state.current_result = None
            st.rerun()
        
        if copy_button and st.session_state.current_result:
            st.success("结果已复制到剪贴板")
        
        # 显示转换结果
        display_conversion_result()

def handle_conversion():
    """处理转换请求"""
    input_sql = st.session_state.get("input_sql_area", "")
    from_dialect = st.session_state.get("from_dialect", "oracle")
    to_dialect = st.session_state.get("to_dialect", "postgres")
    
    if not input_sql.strip():
        st.error("请输入要转换的SQL语句")
        return
    
    # 显示加载状态
    with st.spinner("正在转换SQL，请稍候..."):
        try:
            start_time = time.time()
            
            # 执行转换
            result = coordinator.convert_sql(
                sql=input_sql,
                from_dialect=from_dialect,
                to_dialect=to_dialect,
                pretty=st.session_state.get("pretty_print", True)
            )
            
            duration = time.time() - start_time
            
            # 保存结果
            st.session_state.current_result = {
                'result': result,
                'duration': duration
            }
            
            # 添加到历史记录
            history_record = {
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'from_dialect': from_dialect,
                'to_dialect': to_dialect,
                'strategy': result.metadata.get('strategy', 'unknown'),
                'success': result.success,
                'duration': duration
            }
            
            st.session_state.conversion_history.append(history_record)
            
            # 限制历史记录数量
            if len(st.session_state.conversion_history) > 50:
                st.session_state.conversion_history = st.session_state.conversion_history[-50:]
            
        except Exception as e:
            error_result = ConversionResult(
                success=False,
                result_sql="",
                metadata={'duration': time.time() - start_time},
                error=error_handler.handle_sqlglot_error(e, input_sql, from_dialect, to_dialect)
            )
            
            st.session_state.current_result = {
                'result': error_result,
                'duration': time.time() - start_time
            }

def display_conversion_result():
    """显示转换结果"""
    if 'current_result' not in st.session_state or not st.session_state.current_result:
        st.info("请在左侧输入SQL并点击转换按钮")
        return
    
    current_data = st.session_state.current_result
    result = current_data['result']
    duration = current_data['duration']
    
    # 结果状态显示
    if result.success:
        status_col1, status_col2, status_col3 = st.columns([3, 1, 1])
        
        with status_col1:
            st.markdown("""
            <div class="success-message">
                <strong>✅ 转换成功!</strong> 耗时: {:.2f}秒 | 策略: <span class="strategy-badge strategy-{}">{}</span>
            </div>
            """.format(
                duration,
                result.metadata.get('strategy', 'unknown'),
                result.metadata.get('strategy', 'unknown').upper()
            ), unsafe_allow_html=True)
        
        with status_col2:
            if st.button("📊 详情", key="show_details"):
                st.session_state.show_details = not st.session_state.get('show_details', False)
        
        with status_col3:
            if st.button("💾 保存", key="save_result"):
                save_conversion_result(result)
                st.success("结果已保存")
        
        # 显示转换结果
        st.markdown('<div class="code-container">', unsafe_allow_html=True)
        st.code(result.result_sql, language='sql', line_numbers=True)
        st.markdown('</div>', unsafe_allow_html=True)
        
        # 显示详细信息
        if st.session_state.get('show_details', False):
            with st.expander("📋 转换详情"):
                render_conversion_details(result)
        
        # 显示警告信息
        if result.warnings:
            with st.expander("⚠️ 警告信息"):
                for warning in result.warnings:
                    st.markdown(f"""
                    <div class="warning-message">
                        {warning}
                    </div>
                    """, unsafe_allow_html=True)
    
    else:
        # 显示错误信息
        st.markdown("""
        <div class="error-message">
            <strong>❌ 转换失败!</strong> 耗时: {:.2f}秒
        </div>
        """.format(duration), unsafe_allow_html=True)
        
        if result.error:
            user_message = get_user_friendly_message(result.error)
            st.error(user_message)
            
            with st.expander("🔍 错误详情"):
                st.json(result.error.to_dict())

def render_conversion_details(result: ConversionResult):
    """渲染转换详情"""
    details = result.metadata
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**基本信息:**")
        st.write(f"- 转换策略: {details.get('strategy', 'unknown')}")
        st.write(f"- 复杂度: {details.get('analysis', {}).get('complexity', 'unknown')}")
        st.write(f"- 验证状态: {'✅ 通过' if details.get('validation', {}).get('is_valid', False) else '❌ 失败'}")
    
    with col2:
        st.write("**性能指标:**")
        st.write(f"- 转换耗时: {details.get('duration', 0):.2f}秒")
        if 'tokens_used' in details:
            st.write(f"- 使用Token: {details['tokens_used']}")
        if 'cache_hit' in details:
            st.write(f"- 缓存命中: {'✅' if details['cache_hit'] else '❌'}")
    
    # 显示分析信息
    if 'analysis' in details:
        analysis = details['analysis']
        st.write("**SQL分析:**")
        
        analysis_col1, analysis_col2 = st.columns(2)
        
        with analysis_col1:
            st.write(f"- 估计行数: {analysis.get('estimated_lines', 0)}")
            st.write(f"- 估计词数: {analysis.get('estimated_tokens', 0)}")
            st.write(f"- 包含PL/SQL: {'✅' if analysis.get('has_plsql', False) else '❌'}")
        
        with analysis_col2:
            st.write(f"- 包含ZTC_SQLZZ: {'✅' if analysis.get('has_ztc_sqlzz', False) else '❌'}")
            st.write(f"- 包含注释: {'✅' if analysis.get('has_comments', False) else '❌'}")
            st.write(f"- 复杂连接: {'✅' if analysis.get('has_complex_joins', False) else '❌'}")

def save_conversion_result(result: ConversionResult):
    """保存转换结果"""
    if not result.success:
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"conversion_result_{timestamp}.sql"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"-- SQL转换结果\n")
            f.write(f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"-- 转换策略: {result.metadata.get('strategy', 'unknown')}\n")
            f.write(f"-- 耗时: {result.metadata.get('duration', 0):.2f}秒\n")
            f.write("\n")
            f.write(result.result_sql)
        
        st.success(f"结果已保存到: {filename}")
        
    except Exception as e:
        st.error(f"保存失败: {str(e)}")

def main():
    """主函数"""
    # 加载自定义样式
    load_custom_css()
    
    # 初始化会话状态
    initialize_session_state()
    
    # 渲染页面
    render_header()
    render_sidebar()
    render_main_content()
    
    # 页脚
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align: center; color: #666;">
            <p>SQL方言转换工具 v2.0 | 基于SQLGlot和LLM技术 | 支持复杂PL/SQL转换</p>
        </div>
        """, 
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    main()