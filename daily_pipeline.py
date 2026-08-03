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
import argparse
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
    parser = argparse.ArgumentParser(description='ETF预测模型每日流水线')
    parser.add_argument('--dry-run', action='store_true', help='完整执行数据、模型和看板，但不提交或推送')
    args = parser.parse_args()
    start = datetime.now()
    log(f'ETF预测模型每日流水线启动 — {start.strftime("%Y-%m-%d %H:%M")}（{"模拟运行" if args.dry_run else "生产运行"}）')

    # Step 0: 检查依赖
    ensure_dependencies()

    # Step 1: 增量更新ETF数据
    log('=== Step 1: ETF数据增量更新 ===')
    ok = run_script('fetch_etf_data.py')
    if not ok:
        raise SystemExit('ETF行情更新失败，停止后续模型计算')

    # Step 2: 抓取四大报 (机构情绪)
    log('=== Step 2: 四大报抓取 (机构情绪) ===')
    run_script('scrape_newspapers.py')

    # Step 3: 抓取融资融券数据 (大众情绪)
    log('=== Step 3: 融资融券数据抓取 (大众情绪) ===')
    run_script('fetch_margin_data.py')

    # Step 3.5: 抓取公开政策、行业和宏观新闻（无 API Key）
    log('=== Step 3.5: 外部政策/行业/宏观新闻 ===')
    run_script('fetch_external_news.py')

    # Step 3.6: 交易所 ETF 份额（真实申赎方向，缺失时仅作诊断）
    log('=== Step 3.6: 交易所 ETF 份额 ===')
    run_script('fetch_etf_shares.py', timeout=300)

    # Step 4: 规则模型
    log('=== Step 4: 规则模型 ===')
    ok = run_script('etf_model_run.py', timeout=300)
    if not ok:
        raise SystemExit('规则模型失败，停止后续输出')

    # Step 5: 计量模型 (含双视角情绪特征)
    log('=== Step 5: 计量模型 (含双视角情绪特征) ===')
    ok = run_script('econometric_model.py', timeout=600)
    if not ok:
        raise SystemExit('计量诊断失败，停止生成看板')

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
    ok = run_script('generate_dashboard.py', timeout=120)
    if not ok:
        raise SystemExit('看板生成失败')

    # Step 7: 提交并推送到GitHub
    if args.dry_run:
        log('=== Step 7: 模拟运行，跳过 Git 提交与推送 ===')
    else:
        log('=== Step 7: Git提交推送 ===')
        git_push()

    elapsed = (datetime.now() - start).total_seconds()
    log(f'流水线完成, 耗时 {elapsed:.0f} 秒')

if __name__ == '__main__':
    main()
