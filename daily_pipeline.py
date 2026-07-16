#!/usr/bin/env python3
"""
ETF预测模型 — 每日自动化流水线
运行: python3 daily_pipeline.py
"""
import sys
import os
import shutil
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'etf-dashboard')

def log(msg):
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}', flush=True)

def run_script(script_name, timeout=300):
    log(f'--- {script_name} ---')
    ret = subprocess.run(
        [sys.executable, script_name],
        cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=timeout
    )
    for line in ret.stdout.strip().split('\n'):
        if line:
            print(f'  {line}', flush=True)
    if ret.returncode != 0:
        log(f'  [ERROR] {script_name}:')
        for line in ret.stderr.strip().split('\n')[-5:]:
            print(f'  {line}', flush=True)
        return False
    return True

def ensure_dependencies():
    """检查并安装必要的Python依赖"""
    missing = []
    for mod in ['requests', 'pandas', 'numpy', 'statsmodels', 'sklearn']:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        log(f'安装缺失依赖: {", ".join(missing)}')
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install'] + missing + ['--break-system-packages', '-q'],
            capture_output=True, text=True, timeout=120
        )
        log('依赖安装完成')

def main():
    start = datetime.now()
    log(f'ETF预测模型每日流水线启动 — {start.strftime("%Y-%m-%d %H:%M")}')

    # Step 0: 检查依赖
    ensure_dependencies()

    # Step 1: 增量更新ETF数据
    log('=== Step 1: ETF数据增量更新 ===')
    run_script('fetch_etf_data.py')

    # Step 2: 抓取四大报
    log('=== Step 2: 四大报抓取 ===')
    run_script('scrape_newspapers.py')

    # Step 3: 规则模型
    log('=== Step 3: 规则模型 ===')
    run_script('etf_model_run.py')

    # Step 4: 计量模型
    log('=== Step 4: 计量模型 ===')
    run_script('econometric_model.py')

    # Step 5: 准备看板目录（复制_shared）
    log('=== Step 5: 生成看板 ===')
    shared_src = os.path.join(SCRIPT_DIR, '_shared')
    shared_dst = os.path.join(DASHBOARD_DIR, '_shared')
    if os.path.exists(shared_src):
        if os.path.exists(shared_dst):
            shutil.rmtree(shared_dst)
        shutil.copytree(shared_src, shared_dst)
        log(f'  复制 _shared/ → {shared_dst}')

    # 生成看板
    run_script('generate_dashboard.py', timeout=120)

    elapsed = (datetime.now() - start).total_seconds()
    log(f'流水线完成, 耗时 {elapsed:.0f} 秒')

if __name__ == '__main__':
    main()
