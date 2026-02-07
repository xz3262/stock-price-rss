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


def fetch_latest_item(cfg: StockConfig, now_utc: datetime, manual: bool, base_url: str) -> FeedItem | None:
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

    if len(hist) >= 2:
        prev_close = float(hist.iloc[-2]["Close"])
        change_pct = ((close_price - prev_close) / prev_close) * 100 if prev_close else 0.0
    else:
        change_pct = 0.0

    direction = "涨" if change_pct >= 0 else "跌"
    title = f"{cfg.name} ({cfg.symbol}) | {trade_date} | {direction} {change_pct:+.2f}%"

    description = (
        f"交易日: {trade_date}\n"
        f"Open: {format_price(open_price)}\n"
        f"Close: {format_price(close_price)}\n"
        f"High: {format_price(high_price)}\n"
        f"Low: {format_price(low_price)}\n"
        f"Volume: {volume:,}\n"
        f"Change: {change_pct:+.2f}%"
    )

    if manual:
        guid = f"{cfg.symbol}-{trade_date}-manual-{now_utc.strftime('%Y%m%d%H%M%S')}"
    else:
        guid = f"{cfg.symbol}-{trade_date}"

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

    ET.SubElement(channel, "title").text = "US Stock Daily OHLC Feed"
    ET.SubElement(channel, "link").text = f"{base_url.rstrip('/')}/"
    ET.SubElement(channel, "description").text = "Daily OHLCV updates for selected US stocks"
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

    existing = parse_existing_items(output_path)
    merged: Dict[str, FeedItem] = dict(existing)

    for cfg in configs:
        item = fetch_latest_item(cfg, now_utc, args.manual, args.base_url)
        if item is None:
            print(f"WARN: no data for {cfg.symbol}")
            continue
        merged[item.guid] = item
        print(f"OK: {cfg.symbol} -> {item.guid}")

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
