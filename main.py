import asyncio
import aiohttp
from bs4 import BeautifulSoup
import logging
from telegram import Bot
from telegram.error import TelegramError
import time
from typing import Dict, Tuple, List
import re
from fake_useragent import UserAgent
import ssl
import certifi
import os
from datetime import datetime, timedelta, timezone
import json
from collections import defaultdict

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== CONFIGURATION =====
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003891147099")

# Iraq timezone (UTC+3)
def iraq_now():
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=3)

# Products to monitor
PRODUCTS = {
    "https://amzn.in/d/0atB5gdL": {
        "name": "PlayStation INDIA Gift Card",
        "denominations": ["1000", "2000", "3000", "4000", "5000"]
    },
    "https://amzn.in/d/081q2grT": {
        "name": "PlayStation INDIA Gift Card",
        "denominations": ["1000", "2000", "3000", "4000", "5000"]
    }
}

# Stock status indicators
OUT_OF_STOCK_INDICATORS = [
    "out of stock",
    "currently unavailable",
    "we don't know when or if this item will be back in stock",
    "temporarily out of stock"
]

CHECK_INTERVAL = 120
ALERT_COOLDOWN = 1800
ssl_context = ssl.create_default_context(cafile=certifi.where())

# ===== HISTORY TRACKER =====
class StockHistory:
    def __init__(self, history_file='stock_history.json'):
        self.history_file = history_file
        self.events = []
        self.daily_stats = defaultdict(lambda: {'in_stock': 0, 'out_stock': 0, 'events': []})
        self.load_history()
    
    def load_history(self):
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.events = json.load(f)
        except:
            self.events = []
    
    def save_history(self):
        try:
            events_to_save = self.events[-1000:]
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(events_to_save, f, indent=2)
        except:
            pass
    
    def record_event(self, product_name, denomination, status, price):
        now = iraq_now()
        event = {
            'timestamp': now.isoformat(),
            'date': now.strftime('%Y-%m-%d'),
            'time': now.strftime('%H:%M:%S'),
            'product': product_name,
            'denomination': denomination,
            'status': status,
            'price': price
        }
        self.events.append(event)
        date_key = now.strftime('%Y-%m-%d')
        if status == 'IN_STOCK':
            self.daily_stats[date_key]['in_stock'] += 1
        else:
            self.daily_stats[date_key]['out_stock'] += 1
        self.daily_stats[date_key]['events'].append(event)
        self.save_history()
    
    def get_daily_summary(self, date=None):
        if date is None:
            date = iraq_now().strftime('%Y-%m-%d')
        if date not in self.daily_stats:
            return f"No events recorded for {date}"
        stats = self.daily_stats[date]
        events = stats['events']
        lines = []
        lines.append(f"📊 DAILY SUMMARY - {date}")
        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"🟢 IN STOCK: {stats['in_stock']}")
        lines.append(f"🔴 OUT STOCK: {stats['out_stock']}")
        lines.append(f"📊 Total: {len(events)}")
        if events:
            lines.append("")
            lines.append("📋 Events:")
            by_denom = defaultdict(list)
            for e in events:
                by_denom[e['denomination']].append(e)
            for denom in sorted(by_denom.keys(), key=lambda x: int(x)):
                denom_events = by_denom[denom]
                lines.append(f"  ₹{denom}:")
                for e in denom_events:
                    emoji = "🟢" if e['status'] == 'IN_STOCK' else "🔴"
                    lines.append(f"    {emoji} {e['time']} - {e['status']}")
        return "\n".join(lines)

# ===== STOCK CHECKER =====
class AmazonStockChecker:
    def __init__(self):
        self.ua = UserAgent()
        self.session = None
        self.connector = None
        self.last_status: Dict[str, Dict[str, Tuple[bool, str]]] = {}

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.connector = aiohttp.TCPConnector(ssl=ssl_context)
            headers = {
                'User-Agent': self.ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            }
            self.session = aiohttp.ClientSession(headers=headers, connector=self.connector)
        return self.session

    async def check_denomination_stock(self, url: str, denomination: str, product_info: dict) -> Tuple[bool, str, str]:
        try:
            session = await self.get_session()
            await asyncio.sleep(2)
            async with session.get(url, timeout=30, allow_redirects=True) as response:
                if response.status != 200:
                    return False, f"HTTP Error: {response.status}", ""
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Check denomination
                denomination_selectors = [
                    f'select option[value*="{denomination}"]',
                    f'option:contains("Rs. {denomination}")',
                    f'option:contains("₹{denomination}")',
                ]
                denomination_exists = False
                for selector in denomination_selectors:
                    if soup.select_one(selector):
                        denomination_exists = True
                        break
                
                page_text = soup.get_text()
                denomination_in_text = f"Rs.{denomination}" in page_text or f"₹{denomination}" in page_text
                page_text_lower = page_text.lower()
                is_out_of_stock = any(indicator in page_text_lower for indicator in OUT_OF_STOCK_INDICATORS)
                buy_box = soup.select_one('#buy-now-button, #add-to-cart-button, .a-button-input')
                has_buy_button = buy_box is not None and buy_box.get('aria-disabled') != 'true'
                
                if denomination_exists or denomination_in_text:
                    in_stock = has_buy_button and not is_out_of_stock
                else:
                    in_stock = False
                
                price_element = (soup.select_one('.a-price-whole') or 
                               soup.select_one('#priceblock_ourprice') or 
                               soup.select_one('.a-price .a-offscreen'))
                price = price_element.get_text().strip() if price_element else "Price not visible"
                
                availability = soup.select_one('#availability span, .a-color-success, .a-color-error')
                status_msg = availability.get_text().strip() if availability else "Unknown status"
                
                logger.info(f"{product_info['name']} - ₹{denomination}: {'IN STOCK' if in_stock else 'OUT OF STOCK'}")
                return in_stock, status_msg, price
        except Exception as e:
            logger.error(f"Error checking ₹{denomination}: {str(e)}")
            return False, f"Error", ""

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()
        if self.connector and not self.connector.closed:
            await self.connector.close()

# ===== TELEGRAM BOT =====
class StockNotificationBot:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id
        self.checker = AmazonStockChecker()
        self.history = StockHistory()
        self.last_alert_time: Dict[str, float] = {}
        self.last_status_change: Dict[str, bool] = {}
        self.last_daily_report = None

    async def send_stock_alert(self, product_name: str, url: str, denomination: str, price: str, in_stock: bool):
        alert_key = f"{url}_{denomination}"
        current_time = time.time()
        
        if alert_key in self.last_alert_time:
            time_since_last = current_time - self.last_alert_time[alert_key]
            if time_since_last < ALERT_COOLDOWN:
                logger.info(f"Cooldown active for ₹{denomination}")
                return
        
        now = iraq_now()
        date_str = now.strftime('%d/%m/%Y')
        time_str = now.strftime('%H:%M:%S')
        
        status = 'IN_STOCK' if in_stock else 'OUT_STOCK'
        self.history.record_event(product_name, denomination, status, price)
        
        if in_stock:
            # IN STOCK alert
            message = (
                f"🟢 **STOCK AVAILABLE!** 🟢\n\n"
                f"**{product_name}**\n\n"
                f"**VALUE:** **₹{denomination}**\n\n"
                f"Price: {price}\n"
                f"**BUY NOW:** {url}\n"
                f"Date: {date_str}\n"
                f"Time: {time_str} Iraq"
            )
            logger.info(f"📦 IN STOCK: ₹{denomination}")
        else:
            # OUT OF STOCK alert - FIXED VERSION
            message = (
                f"🔴 **OUT OF STOCK** 🔴\n\n"
                f"**{product_name}**\n\n"
                f"**VALUE:** **₹{denomination}**\n\n"
                f"Date: {date_str}\n"
                f"Time: {time_str} Iraq\n\n"
                f"Will alert again when restocked."
            )
            logger.info(f"❌ OUT OF STOCK: ₹{denomination}")
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            self.last_alert_time[alert_key] = current_time
        except TelegramError as e:
            logger.error(f"Failed to send: {e}")

    async def send_daily_report(self, report_type):
        now = iraq_now()
        today = now.strftime('%Y-%m-%d')
        summary = self.history.get_daily_summary(today)
        header = "🌙 MIDNIGHT SUMMARY" if report_type == "midnight" else "☀️ NOON SUMMARY"
        message = f"{header}\n\n{summary}"
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message)
        except TelegramError as e:
            logger.error(f"Failed to send report: {e}")

    async def check_daily_report_time(self):
        now = iraq_now()
        current_time = now.strftime('%H:%M')
        today = now.strftime('%Y-%m-%d')
        
        if current_time in ['00:00', '00:01', '00:02', '00:03', '00:04', '00:05']:
            report_key = f"{today}_midnight"
            if self.last_daily_report != report_key:
                await self.send_daily_report("midnight")
                self.last_daily_report = report_key
                await asyncio.sleep(60)
        elif current_time in ['12:00', '12:01', '12:02', '12:03', '12:04', '12:05']:
            report_key = f"{today}_noon"
            if self.last_daily_report != report_key:
                await self.send_daily_report("noon")
                self.last_daily_report = report_key
                await asyncio.sleep(60)

    async def monitor_products(self):
        logger.info("Starting stock monitor...")
        logger.info(f"Check interval: {CHECK_INTERVAL//60} minutes")
        
        for url, product_info in PRODUCTS.items():
            if url not in self.checker.last_status:
                self.checker.last_status[url] = {}
                for denom in product_info["denominations"]:
                    self.checker.last_status[url][denom] = (False, "")
        
        while True:
            try:
                for url, product_info in PRODUCTS.items():
                    for denomination in product_info["denominations"]:
                        logger.info(f"Checking ₹{denomination}...")
                        in_stock, status_msg, price = await self.checker.check_denomination_stock(url, denomination, product_info)
                        prev_in_stock, _ = self.checker.last_status[url].get(denomination, (False, ""))
                        
                        if in_stock != prev_in_stock:
                            logger.info(f"Status change: ₹{denomination}: {prev_in_stock} -> {in_stock}")
                            await self.send_stock_alert(product_info['name'], url, denomination, price, in_stock)
                        
                        self.checker.last_status[url][denomination] = (in_stock, status_msg)
                        await asyncio.sleep(3)
                
                await self.check_daily_report_time()
                await asyncio.sleep(CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"Error: {e}")
                await asyncio.sleep(60)

    async def cleanup(self):
        await self.checker.close()

async def main():
    bot = StockNotificationBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    try:
        me = await bot.bot.get_me()
        logger.info(f"Bot connected: @{me.username}")
        now = iraq_now()
        startup_message = (
            f"🚀 Bot Started!\n\n"
            f"Monitoring all denominations\n"
            f"Time: {now.strftime('%d/%m/%Y %I:%M %p')} Iraq"
        )
        await bot.bot.send_message(chat_id=bot.chat_id, text=startup_message)
        await bot.monitor_products()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await bot.cleanup()

if __name__ == "__main__":
    asyncio.run(main())