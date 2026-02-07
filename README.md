# Stock RSS Feed

每天在美股收盘后自动更新 `feed.xml`，内容包含你关心股票的：
- Open
- Close
- High
- Low
- Volume
- Change%

## Stocks
配置文件：`stock_list.json`

当前默认：
- RBLX
- NVDA
- GOOGL
- META
- TSLA
- CRWV

## Local usage

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# 正常模式（按交易日去重）
python generate_rss.py --base-url "https://<YOUR_NAME>.github.io/<REPO_NAME>"

# 手动强制推送模式（生成新的 guid，便于 RSS 阅读器识别新条目）
python generate_rss.py --manual --base-url "https://<YOUR_NAME>.github.io/<REPO_NAME>"
```

## GitHub setup
1. 创建 GitHub 仓库并 push 本项目。
2. 到仓库 `Settings -> Pages`，`Source` 选 `Deploy from a branch`。
3. 选择分支（通常 `main`）和目录 `/ (root)`。
4. Pages 生效后，订阅：
   - `https://<YOUR_NAME>.github.io/<REPO_NAME>/feed.xml`

## Automation
GitHub Actions 文件：`.github/workflows/update-rss.yml`
- 工作日收盘后自动跑（UTC 20:15 + 21:15，兼容美东夏/冬令时）。
- 支持手动触发：`Actions -> Update RSS -> Run workflow`，并可把 `manual_push` 设为 `true`。
