#!/usr/bin/env python3
"""
ETF预测模型 — 每日自动化流水线
运行: python3 daily_pipeline.py

流程:
  1. ETF数据增量更新
  2. 四大报抓取 (机构情绪)
  3. 融资融券数据抓取 (大众情绪)
  4. 规则模型
  5. 计量模型 (含双视角情绪特征)
  6. 生成看板 + 确保 .nojekyll
  7. Git提交并推送至GitHub
"""
import sys
import os
import shutil
import subprocess
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(SCRIPT_DIR, 'dashboard')

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

def ensure_nojekyll():
    """确保 .nojekyll 文件存在于仓库根目录，防止GitHub Pages的Jekyll忽略 _shared 目录"""
    nojekyll_path = os.path.join(SCRIPT_DIR, '.nojekyll')
    if not os.path.exists(nojekyll_path):
        with open(nojekyll_path, 'w') as f:
            pass  # 创建空文件
        log('  创建 .nojekyll (禁用Jekyll处理)')

def git_push():
    """提交并推送所有变更到GitHub"""
    log('=== Git 提交并推送 ===')
    today = datetime.now().strftime('%Y-%m-%d')

    cmds = [
        ['git', 'add', '-A'],
        ['git', 'commit', '-m', f'daily update {today}'],
        ['git', 'push', 'origin', 'main'],
    ]
    for cmd in cmds:
        ret = subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=60)
        if ret.returncode != 0:
            # git commit 可能因无变更而失败，这是正常的
            if cmd[1] == 'commit' and 'nothing to commit' in ret.stdout:
                log('  无变更需要提交')
                return True
            log(f'  [WARN] {" ".join(cmd)}: {ret.stderr.strip()[:200]}')
        else:
            log(f'  ✓ {" ".join(cmd[:2])}')
    log('  推送完成')
    return True

def main():
    start = datetime.now()
    log(f'ETF预测模型每日流水线启动 — {start.strftime("%Y-%m-%d %H:%M")}')

    # Step 0: 检查依赖
    ensure_dependencies()

    # Step 1: 增量更新ETF数据
    log('=== Step 1: ETF数据增量更新 ===')
    run_script('fetch_etf_data.py')

    # Step 2: 抓取四大报 (机构情绪)
    log('=== Step 2: 四大报抓取 (机构情绪) ===')
    run_script('scrape_newspapers.py')

    # Step 3: 抓取融资融券数据 (大众情绪)
    log('=== Step 3: 融资融券数据抓取 (大众情绪) ===')
    run_script('fetch_margin_data.py')

    # Step 4: 规则模型
    log('=== Step 4: 规则模型 ===')
    run_script('etf_model_run.py')

    # Step 5: 计量模型 (含双视角情绪特征)
    log('=== Step 5: 计量模型 (含双视角情绪特征) ===')
    run_script('econometric_model.py')

    # Step 6: 生成看板
    log('=== Step 6: 生成看板 ===')
    # 刷新 _shared 目录 (字体+echarts)
    shared_src = os.path.join(SCRIPT_DIR, '_shared')
    shared_dst = os.path.join(DASHBOARD_DIR, '_shared')
    if os.path.exists(shared_src):
        if os.path.exists(shared_dst):
            shutil.rmtree(shared_dst)
        shutil.copytree(shared_src, shared_dst)
        log(f'  刷新 _shared/ → {shared_dst}')

    # 确保 .nojekyll 存在 (修复GitHub Pages的 _shared 404问题)
    ensure_nojekyll()

    # 生成看板
    run_script('generate_dashboard.py', timeout=120)

    # Step 7: 提交并推送到GitHub
    log('=== Step 7: Git提交推送 ===')
    git_push()

    elapsed = (datetime.now() - start).total_seconds()
    log(f'流水线完成, 耗时 {elapsed:.0f} 秒')

if __name__ == '__main__':
    main()
