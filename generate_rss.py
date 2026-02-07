#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import Dict, List
import xml.etree.ElementTree as ET

import yfinance as yf


@dataclass
class StockConfig:
    name: str
    symbol: str


@dataclass
class FeedItem:
    guid: str
    title: str
    description: str
    pub_date: str
    link: str


@dataclass
class StockSnapshot:
    name: str
    symbol: str
    trade_date: str
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    volume: int
    change_pct: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate stock RSS feed")
    parser.add_argument("--config", default="stock_list.json", help="Stock config JSON file")
    parser.add_argument("--output", default="feed.xml", help="Output RSS file")
    parser.add_argument("--base-url", default="https://example.github.io/stock-rss", help="Public base URL")
    parser.add_argument("--max-items", type=int, default=200, help="Max items kept in RSS")
    parser.add_argument("--manual", action="store_true", help="Force unique entries for manual run")
    return parser.parse_args()


def load_stock_configs(path: Path) -> List[StockConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    out: List[StockConfig] = []
    for row in raw:
        out.append(StockConfig(name=row["name"], symbol=row["symbol"]))
    return out


def format_price(v: float) -> str:
    return f"{v:.2f}"


def fetch_latest_snapshot(cfg: StockConfig) -> StockSnapshot | None:
    hist = yf.Ticker(cfg.symbol).history(period="10d", interval="1d", auto_adjust=False)
    if hist.empty:
        return None

    last_idx = hist.index[-1]
    last = hist.iloc[-1]
    trade_date = last_idx.strftime("%Y-%m-%d")

    close_price = float(last["Close"])
    open_price = float(last["Open"])
    high_price = float(last["High"])
    low_price = float(last["Low"])
    volume = int(last["Volume"])

    # Change% is intraday move from open to close.
    change_pct = ((close_price - open_price) / open_price) * 100 if open_price else 0.0

    return StockSnapshot(
        name=cfg.name,
        symbol=cfg.symbol,
        trade_date=trade_date,
        open_price=open_price,
        close_price=close_price,
        high_price=high_price,
        low_price=low_price,
        volume=volume,
        change_pct=change_pct,
    )


def build_summary_item(
    snapshots: List[StockSnapshot], now_utc: datetime, manual: bool, base_url: str
) -> FeedItem:
    # Most symbols should share the same trading day; use the latest available day.
    trade_date = max(s.trade_date for s in snapshots)
    up_count = sum(1 for s in snapshots if s.change_pct >= 0)
    down_count = len(snapshots) - up_count

    title = f"市场收盘汇总 | {trade_date} | 上涨 {up_count} / 下跌 {down_count}"
    rows: List[str] = []
    rows.append("<p><strong>字段:</strong> Open / Close / High / Low / Volume / Change%</p>")
    rows.append("<table border='1' cellpadding='6' cellspacing='0'>")
    rows.append("<tr><th>股票</th><th>Change%</th><th>Open</th><th>Close</th><th>High</th><th>Low</th><th>Volume</th></tr>")

    for s in sorted(snapshots, key=lambda x: x.symbol):
        rows.append(
            "<tr>"
            f"<td>{s.name} ({s.symbol})</td>"
            f"<td>{s.change_pct:+.2f}%</td>"
            f"<td>{format_price(s.open_price)}</td>"
            f"<td>{format_price(s.close_price)}</td>"
            f"<td>{format_price(s.high_price)}</td>"
            f"<td>{format_price(s.low_price)}</td>"
            f"<td>{s.volume:,}</td>"
            "</tr>"
        )
    rows.append("</table>")
    rows.append(f"<p>生成时间(UTC): {now_utc.strftime('%Y-%m-%d %H:%M:%S')}</p>")
    description = "".join(rows)

    if manual:
        guid = f"daily-{trade_date}-manual-{now_utc.strftime('%Y%m%d%H%M%S')}"
    else:
        guid = f"daily-{trade_date}"

    return FeedItem(
        guid=guid,
        title=title,
        description=description,
        pub_date=format_datetime(now_utc),
        link=f"{base_url.rstrip('/')}/feed.xml",
    )


def parse_existing_items(path: Path) -> Dict[str, FeedItem]:
    if not path.exists():
        return {}

    tree = ET.parse(path)
    channel = tree.getroot().find("channel")
    if channel is None:
        return {}

    out: Dict[str, FeedItem] = {}
    for item in channel.findall("item"):
        guid = (item.findtext("guid") or "").strip()
        if not guid:
            continue
        out[guid] = FeedItem(
            guid=guid,
            title=item.findtext("title") or "",
            description=item.findtext("description") or "",
            pub_date=item.findtext("pubDate") or "",
            link=item.findtext("link") or "",
        )
    return out


def write_feed(path: Path, base_url: str, items: List[FeedItem], now_utc: datetime) -> None:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "Market Daily OHLC Feed"
    ET.SubElement(channel, "link").text = f"{base_url.rstrip('/')}/"
    ET.SubElement(channel, "description").text = "Daily OHLCV updates for selected indexes and stocks"
    ET.SubElement(channel, "language").text = "zh-CN"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(now_utc)

    for it in items:
        node = ET.SubElement(channel, "item")
        ET.SubElement(node, "title").text = it.title
        ET.SubElement(node, "link").text = it.link
        ET.SubElement(node, "guid", isPermaLink="false").text = it.guid
        ET.SubElement(node, "pubDate").text = it.pub_date
        ET.SubElement(node, "description").text = it.description

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    args = parse_args()
    now_utc = datetime.now(timezone.utc)

    config_path = Path(args.config)
    output_path = Path(args.output)
    configs = load_stock_configs(config_path)

    existing = {k: v for k, v in parse_existing_items(output_path).items() if k.startswith("daily-")}
    merged: Dict[str, FeedItem] = dict(existing)
    snapshots: List[StockSnapshot] = []

    for cfg in configs:
        snap = fetch_latest_snapshot(cfg)
        if snap is None:
            print(f"WARN: no data for {cfg.symbol}")
            continue
        snapshots.append(snap)
        print(f"OK: {cfg.symbol} -> {snap.trade_date}")

    if not snapshots:
        print("ERROR: no stock data fetched")
        return 1

    summary_item = build_summary_item(snapshots, now_utc, args.manual, args.base_url)
    merged[summary_item.guid] = summary_item
    print(f"OK: summary -> {summary_item.guid}")

    sorted_items = sorted(
        merged.values(),
        key=lambda x: parsedate_to_datetime(x.pub_date) if x.pub_date else datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[: args.max_items]

    write_feed(output_path, args.base_url, sorted_items, now_utc)
    print(f"DONE: wrote {output_path} with {len(sorted_items)} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
