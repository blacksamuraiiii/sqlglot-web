# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a SQL dialect conversion tool that combines SQLGlot (for standard SQL conversions) with LLM assistance (for complex PL/SQL structures like stored procedures, functions, and dynamic SQL). The application provides a Streamlit web interface for converting SQL between different database dialects.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Run the Streamlit web application
streamlit run app.py
```

## Architecture

### Core Components

1. **SQLGlot Integration** (`app.py:47-67`): Handles standard SQL dialect conversions using the `transpile_single_sql` function
2. **LLM Enhancement** (`app.py:287-318`): Uses Qwen model for complex PL/SQL structures via `call_xiyansql` function
3. **Pattern Matching** (`app.py:94-117`): Regex patterns for identifying PL/SQL blocks, ZTC_SQLZZ dynamic SQL, and comment blocks
4. **Streamlit UI** (`app.py:320-368`): Web interface with dialect selectors and SQL input/output areas

### Supported SQL Dialects
Supports 26 dialects including: oracle, postgres, mysql, snowflake, bigquery, spark, hive, and others. Full list in `DIALECTS` constant (`app.py:16-44`).

### Conversion Logic Flow

1. **Pattern Detection**: Identifies PL/SQL blocks, ZTC_SQLZZ calls, and comment blocks using regex
2. **Oracle→PostgreSQL Special Handling**: For CREATE PROCEDURE statements, performs code transformation to PostgreSQL syntax
3. **LLM Fallback**: Uses LLM for complex structures that SQLGlot cannot handle
4. **Comment Preservation**: Maintains line comments, block comments, and empty lines during conversion

### Special Features

- **ZTC_SQLZZ Processing**: Handles dynamic SQL wrapped in `ZTC_SQLZZ('...')` calls
- **PL/SQL Block Conversion**: Special handling for Oracle procedures, functions, and anonymous blocks
- **Comment-aware Processing**: Preserves comments and formatting while converting embedded SQL

## Configuration

Requires `.env` file with:
- `base_url`: LLM API endpoint (ModelScope)
- `api_key`: LLM API key

Example `.env.example`:
```
base_url='https://api-inference.modelscope.cn/v1/'
api_key='xxxx'
```

## Testing

Test SQL files are located in the repository root (e.g., `test.sql`, `ZTC_JURUI_KHZF_PRC.txt`). These contain complex Oracle PL/SQL procedures with dynamic SQL that demonstrate the tool's capabilities.