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
from datetime import datetime, timedelta
from collections import defaultdict
import pytz
import sqlite3
import json

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== CONFIGURATION =====
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003891147099")  # Your group ID

# India timezone
IST = pytz.timezone('Asia/Kolkata')

# Products to monitor with their denominations
PRODUCTS = {
    "https://amzn.in/d/0atB5gdL": {
        "name": "PlayStation INDIA Gift Card 🇮🇳",
        "denominations": ["1000", "2000", "3000", "4000", "5000"]
    },
    "https://amzn.in/d/081q2grT": {
        "name": "PlayStation INDIA Gift Card 🇮🇳",
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

# Check interval in seconds (120 = 2 minutes)
CHECK_INTERVAL = 120

# Cooldown period in seconds to prevent duplicate alerts (30 minutes = 1800 seconds)
ALERT_COOLDOWN = 1800

# SSL context for secure connections
ssl_context = ssl.create_default_context(cafile=certifi.where())

# ===== DATABASE MANAGER =====
class DatabaseManager:
    def __init__(self, db_path='stock_history.db'):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize SQLite database with all tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Table for stock events
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT,
                url TEXT,
                denomination TEXT,
                start_time TEXT,
                end_time TEXT,
                duration_seconds INTEGER,
                price TEXT,
                status TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table for daily summaries
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary_date TEXT,
                summary_type TEXT,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table for bot stats
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bot_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_date TEXT,
                total_checks INTEGER DEFAULT 0,
                total_alerts INTEGER DEFAULT 0,
                in_stock_events INTEGER DEFAULT 0,
                out_stock_events INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("📊 Database initialized successfully")
    
    def record_stock_event(self, product_name, url, denomination, start_time, end_time, duration, price, status):
        """Record a complete stock event"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO stock_events 
                (product_name, url, denomination, start_time, end_time, duration_seconds, price, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (product_name, url, denomination, start_time, end_time, duration, price, status))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Recorded stock event: {product_name} - ₹{denomination} ({status})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to record stock event: {e}")
            return False
    
    def record_daily_summary(self, summary_date, summary_type, content):
        """Record daily summary"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO daily_summaries (summary_date, summary_type, content)
                VALUES (?, ?, ?)
            ''', (summary_date, summary_type, content))
            
            conn.commit()
            conn.close()
            logger.info(f"✅ Recorded {summary_type} summary for {summary_date}")
        except Exception as e:
            logger.error(f"❌ Failed to record daily summary: {e}")
    
    def update_bot_stats(self, stat_date, check_count=1, alert_count=0, in_stock=0, out_stock=0):
        """Update bot statistics"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO bot_stats (stat_date, total_checks, total_alerts, in_stock_events, out_stock_events)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(stat_date) DO UPDATE SET
                    total_checks = total_checks + ?,
                    total_alerts = total_alerts + ?,
                    in_stock_events = in_stock_events + ?,
                    out_stock_events = out_stock_events + ?
            ''', (stat_date, check_count, alert_count, in_stock, out_stock,
                  check_count, alert_count, in_stock, out_stock))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Failed to update bot stats: {e}")
    
    def get_complete_history(self):
        """Get all recorded history"""
        history = {
            'stock_events': [],
            'daily_summaries': [],
            'bot_stats': [],
            'summary': {}
        }
        
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all stock events
            cursor.execute('''
                SELECT * FROM stock_events 
                ORDER BY start_time DESC
            ''')
            history['stock_events'] = [dict(row) for row in cursor.fetchall()]
            
            # Get daily summaries
            cursor.execute('''
                SELECT * FROM daily_summaries 
                ORDER BY summary_date DESC
                LIMIT 30
            ''')
            history['daily_summaries'] = [dict(row) for row in cursor.fetchall()]
            
            # Get bot stats
            cursor.execute('''
                SELECT * FROM bot_stats 
                ORDER BY stat_date DESC
                LIMIT 30
            ''')
            history['bot_stats'] = [dict(row) for row in cursor.fetchall()]
            
            # Calculate summary statistics
            history['summary'] = {
                'total_events': len(history['stock_events']),
                'total_in_stock': sum(1 for e in history['stock_events'] if e['status'] == 'IN_STOCK'),
                'total_out_stock': sum(1 for e in history['stock_events'] if e['status'] == 'OUT_STOCK'),
                'first_event': history['stock_events'][-1]['start_time'] if history['stock_events'] else None,
                'last_event': history['stock_events'][0]['start_time'] if history['stock_events'] else None,
            }
            
            conn.close()
            
        except Exception as e:
            logger.error(f"❌ Failed to get history: {e}")
        
        return history
    
    def export_history_to_json(self, filename='stock_history_export.json'):
        """Export all history to JSON file"""
        history = self.get_complete_history()
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"✅ History exported to {filename}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to export history: {e}")
            return False
    
    def get_history_report(self):
        """Generate a readable history report"""
        history = self.get_complete_history()
        
        if not history['stock_events']:
            return "📊 **No stock events recorded yet.**\n\nBot has been running but no stock has appeared."
        
        lines = []
        lines.append("📊 **COMPLETE STOCK HISTORY REPORT** 📊")
        lines.append("="*60)
        lines.append(f"📅 Generated: {datetime.now(IST).strftime('%d/%m/%Y %I:%M:%S %p')} IST")
        lines.append("="*60 + "\n")
        
        # Overall Statistics
        lines.append("📈 **OVERALL STATISTICS**")
        lines.append("-"*40)
        lines.append(f"📊 Total Stock Events: {history['summary']['total_events']}")
        lines.append(f"✅ IN STOCK Events: {history['summary']['total_in_stock']}")
        lines.append(f"❌ OUT STOCK Events: {history['summary']['total_out_stock']}")
        
        if history['summary']['first_event']:
            first_date = datetime.fromisoformat(history['summary']['first_event']).strftime('%d/%m/%Y %H:%M')
            last_date = datetime.fromisoformat(history['summary']['last_event']).strftime('%d/%m/%Y %H:%M')
            lines.append(f"📅 First Event: {first_date}")
            lines.append(f"📅 Last Event: {last_date}")
        lines.append("")
        
        # Statistics by Denomination
        lines.append("💰 **STATISTICS BY DENOMINATION**")
        lines.append("-"*40)
        
        denom_stats = defaultdict(lambda: {'count': 0, 'in_stock': 0, 'out_stock': 0})
        for event in history['stock_events']:
            denom = event['denomination']
            denom_stats[denom]['count'] += 1
            if event['status'] == 'IN_STOCK':
                denom_stats[denom]['in_stock'] += 1
            else:
                denom_stats[denom]['out_stock'] += 1
        
        for denom in sorted(denom_stats.keys(), key=lambda x: int(x)):
            stats = denom_stats[denom]
            lines.append(f"  • **₹{denom}:**")
            lines.append(f"    • Total Events: {stats['count']}")
            lines.append(f"    • IN STOCK: {stats['in_stock']}")
            lines.append(f"    • OUT STOCK: {stats['out_stock']}")
        lines.append("")
        
        # Recent Events
        lines.append("📋 **RECENT STOCK EVENTS (Last 10)**")
        lines.append("-"*40)
        
        for i, event in enumerate(history['stock_events'][:10], 1):
            start = datetime.fromisoformat(event['start_time']).strftime('%d/%m %H:%M')
            end = datetime.fromisoformat(event['end_time']).strftime('%d/%m %H:%M') if event['end_time'] else "Still in stock"
            status_emoji = "🟢" if event['status'] == 'IN_STOCK' else "🔴"
            
            lines.append(f"\n  {status_emoji} **Event #{i}:**")
            lines.append(f"  • Product: {event['product_name']}")
            lines.append(f"  • Denomination: ₹{event['denomination']}")
            lines.append(f"  • Price: {event['price']}")
            lines.append(f"  • Status: {event['status']}")
            lines.append(f"  • Started: {start}")
            lines.append(f"  • Ended: {end}")
            if event['duration_seconds']:
                duration = self._format_duration(event['duration_seconds'])
                lines.append(f"  • Duration: {duration}")
        
        lines.append("\n" + "="*60)
        lines.append("📊 **END OF REPORT** 📊")
        lines.append("="*60)
        
        return "\n".join(lines)
    
    def _format_duration(self, seconds):
        """Format seconds into readable duration"""
        if not seconds:
            return "N/A"
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

# ===== STOCK CHECKER =====
class AmazonStockChecker:
    def __init__(self):
        self.ua = UserAgent()
        self.session = None
        self.connector = None
        # Track stock status for each product and denomination
        # Format: {url: {denomination: (in_stock, status_text)}}
        self.last_status: Dict[str, Dict[str, Tuple[bool, str]]] = {}

    async def get_session(self):
        """Create or return aiohttp session with proper headers"""
        if self.session is None or self.session.closed:
            self.connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            headers = {
                'User-Agent': self.ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            self.session = aiohttp.ClientSession(headers=headers, connector=self.connector)
        return self.session

    async def check_denomination_stock(self, url: str, denomination: str, product_info: dict) -> Tuple[bool, str, str]:
        """
        Check if a specific denomination is in stock
        Returns: (in_stock, status_message, price)
        """
        try:
            session = await self.get_session()
            
            # Add random delay to avoid being blocked
            await asyncio.sleep(2)
            
            async with session.get(url, timeout=30, allow_redirects=True) as response:
                if response.status != 200:
                    logger.warning(f"Got status {response.status} for {product_info['name']} - ₹{denomination}")
                    return False, f"HTTP Error: {response.status}", ""
                
                html = await response.text()
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for denomination-specific elements
                # Check if this denomination option exists and is selectable
                denomination_selectors = [
                    f'select option[value*="{denomination}"]',
                    f'option:contains("Rs. {denomination}")',
                    f'option:contains("₹{denomination}")',
                    f'a[href*="{denomination}"]',
                    f'[data-value*="{denomination}"]',
                ]
                
                # Check if this denomination option exists
                denomination_exists = False
                for selector in denomination_selectors:
                    element = soup.select_one(selector)
                    if element:
                        denomination_exists = True
                        break
                
                # Also check page text for denomination
                page_text = soup.get_text()
                denomination_in_text = f"Rs.{denomination}" in page_text or f"₹{denomination}" in page_text
                
                # Check if product is out of stock overall
                page_text_lower = page_text.lower()
                is_out_of_stock = any(
                    indicator in page_text_lower for indicator in OUT_OF_STOCK_INDICATORS
                )
                
                # Check for buy button / add to cart
                buy_box = soup.select_one('#buy-now-button, #add-to-cart-button, .a-button-input')
                has_buy_button = buy_box is not None and buy_box.get('aria-disabled') != 'true'
                
                # Determine if this specific denomination is in stock
                if denomination_exists or denomination_in_text:
                    in_stock = has_buy_button and not is_out_of_stock
                else:
                    in_stock = False
                
                # Try to get price for this denomination
                price = self._extract_price(soup)
                
                # Get status message
                status_msg = self._extract_status_message(soup)
                
                logger.info(f"{product_info['name']} - ₹{denomination}: {'IN STOCK' if in_stock else 'OUT OF STOCK'} - {status_msg}")
                
                return in_stock, status_msg, price
                
        except Exception as e:
            logger.error(f"Error checking {product_info['name']} - ₹{denomination}: {str(e)}")
            return False, f"Error: {str(e)[:50]}", ""

    def _extract_price(self, soup: BeautifulSoup) -> str:
        """Extract price from page"""
        price_element = (
            soup.select_one('.a-price-whole') or 
            soup.select_one('#priceblock_ourprice') or 
            soup.select_one('.a-price .a-offscreen')
        )
        return price_element.get_text().strip() if price_element else "Price not visible"

    def _extract_status_message(self, soup: BeautifulSoup) -> str:
        """Extract specific stock status message from page"""
        availability = soup.select_one('#availability span, .a-color-success, .a-color-error')
        if availability:
            return availability.get_text().strip()
        
        out_of_stock_msg = soup.find(string=re.compile(r'out of stock|currently unavailable', re.I))
        if out_of_stock_msg:
            return out_of_stock_msg.strip()
        
        return "Unknown status"

    async def close(self):
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()
        if self.connector and not self.connector.closed:
            await self.connector.close()

# ===== STOCK TRACKER FOR DAILY REPORTS =====
class StockTracker:
    def __init__(self, db_manager):
        self.db = db_manager
        # Track stock events: {product_key: {denomination: [(start_time, end_time, status)]}}
        self.stock_history = defaultdict(lambda: defaultdict(list))
        # Track current stock start times
        self.current_stock_start = defaultdict(dict)
        # Track last report time
        self.last_report_time = None
        
    def record_status_change(self, product_name: str, url: str, denomination: str, in_stock: bool, price: str):
        """Record when stock status changes"""
        product_key = f"{product_name}|{url}"
        current_time = datetime.now(IST)
        
        if in_stock:
            # Stock became available - record start time
            self.current_stock_start[product_key][denomination] = {
                'time': current_time,
                'price': price
            }
            logger.info(f"📝 TRACKING: {product_name} - ₹{denomination} went IN STOCK at {current_time.strftime('%H:%M:%S')}")
            
            # Record in database
            self.db.record_stock_event(
                product_name, url, denomination,
                current_time.isoformat(), None, 0, price, 'IN_STOCK'
            )
        else:
            # Stock sold out - if we had a start time, record the event
            if denomination in self.current_stock_start.get(product_key, {}):
                start_info = self.current_stock_start[product_key][denomination]
                start_time = start_info['time']
                duration = (current_time - start_time).total_seconds()
                
                # Record the complete stock event in database
                self.db.record_stock_event(
                    product_name, url, denomination,
                    start_time.isoformat(), current_time.isoformat(),
                    int(duration), start_info['price'], 'OUT_STOCK'
                )
                
                # Clear current stock start
                del self.current_stock_start[product_key][denomination]
                
                logger.info(f"📝 TRACKING: {product_name} - ₹{denomination} was in stock for {self._format_duration(duration)}")
    
    def _format_duration(self, seconds):
        """Format seconds into readable string"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

# ===== TELEGRAM BOT =====
class StockNotificationBot:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id
        self.checker = AmazonStockChecker()
        self.db = DatabaseManager()
        self.tracker = StockTracker(self.db)
        self.last_alert_time: Dict[str, float] = {}  # Track when last alert was sent
        self.last_status_change: Dict[str, bool] = {}  # Track last known status
        self.last_summary_time = None
        self.check_count = 0

    async def send_stock_alert(self, product_name: str, url: str, denomination: str, price: str, in_stock: bool):
        """
        Send stock notification to Telegram (both in-stock and out-of-stock alerts)
        With cooldown to prevent duplicates
        """
        # Create a unique key for this specific product and denomination
        alert_key = f"{url}_{denomination}"
        current_time_seconds = time.time()
        
        # Check if we've sent an alert for this item recently
        if alert_key in self.last_alert_time:
            time_since_last = current_time_seconds - self.last_alert_time[alert_key]
            if time_since_last < ALERT_COOLDOWN:
                logger.info(f"Cooldown active for {product_name} - ₹{denomination} ({time_since_last:.0f}s since last alert). Skipping.")
                return  # Don't send the message
        
        # Get current date and time in IST
        now_ist = datetime.now(IST)
        date_str = now_ist.strftime('%d/%m/%Y')
        time_str = now_ist.strftime('%H:%M:%S')
        
        # Record this status change in tracker
        self.tracker.record_status_change(product_name, url, denomination, in_stock, price)
        
        # Update database stats
        today = now_ist.strftime('%Y-%m-%d')
        if in_stock:
            self.db.update_bot_stats(today, alert_count=1, in_stock=1)
        else:
            self.db.update_bot_stats(today, alert_count=1, out_stock=1)
        
        # Create appropriate message based on stock status
        if in_stock:
            # IN STOCK alert with bold and emphasis on key elements
            message = (
                f"🟢 **STOCK AVAILABLE!** 🟢\n\n"
                f"**{product_name}**\n"
                f"━━━━━━━━━━━━━━\n"
                f"**💎 VALUE: ** **₹{denomination}**\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"💰 Price: {price}\n"
                f"🛒 [**⚡ BUY NOW ⚡**]({url})\n"
                f"📅 Date: {date_str}\n"
                f"⏱️ Time: {time_str}\n"
                f"━━━━━━━━━━━━━━\n"
            )
            logger.info(f"📦 IN STOCK: {product_name} - ₹{denomination}")
        else:
            # OUT OF STOCK alert with bold denomination
            message = (
                f"🔴 **SOLD OUT / OUT OF STOCK** 🔴\n\n"
                f"**{product_name}**\n"
                f"━━━━━━━━━━━━━━\n"
                f"**💎 VALUE: ** **₹{denomination}**\n"
                f"━━━━━━━━━━━━━━\n\n"
                f"📅 Date: {date_str}\n"
                f"⏱️ Time: {time_str}\n\n"
                f"Will alert again when restocked.\n"
                f"━━━━━━━━━━━━━━\n"
            )
            logger.info(f"❌ OUT OF STOCK: {product_name} - ₹{denomination}")
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            # Update the last alert time AFTER successfully sending
            self.last_alert_time[alert_key] = current_time_seconds
            logger.info(f"Alert sent: {product_name} - ₹{denomination} - {'In Stock' if in_stock else 'Out of Stock'}")
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def send_history_report(self):
        """Send complete history report to Telegram"""
        report = self.db.get_history_report()
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=report,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            logger.info("📊 History report sent to group")
        except TelegramError as e:
            logger.error(f"Failed to send history report: {e}")

    async def monitor_products(self):
        """Main monitoring loop"""
        logger.info("Starting stock monitor for all denominations...")
        logger.info(f"Check interval: {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.1f} minutes)")
        logger.info(f"Alert cooldown: {ALERT_COOLDOWN} seconds ({ALERT_COOLDOWN/60:.1f} minutes)")
        logger.info("📊 Daily summaries at 12:00 AM and 12:00 PM IST")
        logger.info("📊 Complete history tracking enabled")
        
        # Initialize tracking for all denominations
        for url, product_info in PRODUCTS.items():
            if url not in self.checker.last_status:
                self.checker.last_status[url] = {}
                for denom in product_info["denominations"]:
                    self.checker.last_status[url][denom] = (False, "")
                    # Initialize last_status_change
                    status_key = f"{url}_{denom}"
                    self.last_status_change[status_key] = False
        
        while True:
            try:
                status_changes = []
                
                for url, product_info in PRODUCTS.items():
                    for denomination in product_info["denominations"]:
                        logger.info(f"Checking {product_info['name']} - ₹{denomination}...")
                        
                        in_stock, status_msg, price = await self.checker.check_denomination_stock(
                            url, denomination, product_info
                        )
                        
                        # Update check count
                        self.check_count += 1
                        
                        # Create unique key for this product+denomination
                        status_key = f"{url}_{denomination}"
                        
                        # Get previous status for this denomination
                        prev_in_stock, _ = self.checker.last_status[url].get(denomination, (False, ""))
                        
                        # Check if status has CHANGED (either in-stock or out-of-stock)
                        if in_stock != prev_in_stock:
                            # Status changed! Send alert
                            logger.info(f"🔥 STATUS CHANGE: {product_info['name']} - ₹{denomination}: {prev_in_stock} -> {in_stock}")
                            await self.send_stock_alert(product_info['name'], url, denomination, price, in_stock)
                            status_changes.append((product_info['name'], url, denomination, price, in_stock))
                            
                            # Update last_status_change
                            self.last_status_change[status_key] = in_stock
                        
                        # Update last status regardless
                        self.checker.last_status[url][denomination] = (in_stock, status_msg)
                        
                        # Brief pause between checks
                        await asyncio.sleep(3)
                
                # Update daily stats with check count
                today = datetime.now(IST).strftime('%Y-%m-%d')
                self.db.update_bot_stats(today, check_count=len(PRODUCTS) * 5)  # 5 denominations per product
                
                # Log summary of any status changes
                if status_changes:
                    logger.info(f"✅ Status changes detected: {len(status_changes)} items changed state")
                else:
                    logger.info("ℹ️ No status changes detected in this cycle")
                
                logger.info(f"💤 Sleeping for {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.1f} minutes)...")
                logger.info(f"📊 Total checks so far: {self.check_count}")
                
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)

    async def cleanup(self):
        """Cleanup resources"""
        await self.checker.close()

# ===== MAIN FUNCTION =====
async def main():
    """Main entry point"""
    bot = StockNotificationBot(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    
    try:
        # Test connection
        me = await bot.bot.get_me()
        logger.info(f"Bot connected successfully! @{me.username}")
        
        # Get current date for startup message
        now = datetime.now(IST)
        date_str = now.strftime('%d/%m/%Y')
        time_str = now.strftime('%I:%M %p')
        
        # Send startup message
        startup_message = "🚀 **Amazon Stock Monitor Started!** 🚀\n\n"
        startup_message += "**Monitoring PlayStation INDIA Gift Card 🇮🇳**\n\n"
        startup_message += "**Denominations:**\n"
        startup_message += "• ₹1000\n• ₹2000\n• ₹3000\n• ₹4000\n• ₹5000\n\n"
        startup_message += f"📌 **2 Links being monitored**\n\n"
        startup_message += f"⏱️ **Check interval:** Every {CHECK_INTERVAL//60} minutes\n"
        startup_message += f"🔄 **Alert cooldown:** {ALERT_COOLDOWN//60} minutes (prevents spam)\n"
        startup_message += f"📊 **Daily Reports:** 12:00 AM & 12:00 PM IST\n"
        startup_message += f"📊 **Complete History Tracking:** Enabled\n"
        startup_message += f"   ✅ When items come IN STOCK\n"
        startup_message += f"   ❌ When items go OUT OF STOCK\n"
        startup_message += f"   📈 Summary of all stock activity\n\n"
        startup_message += f"━━━━━━━━━━━━━━━━━━━━\n"
        startup_message += f"📅 Date: {date_str}\n"
        startup_message += f"⏱️ Time: {time_str} IST\n"
        startup_message += f"━━━━━━━━━━━━━━━━━━━━\n\n"
        startup_message += f"Bot is live and monitoring 24/7! 🇮🇳"
        
        await bot.bot.send_message(
            chat_id=bot.chat_id,
            text=startup_message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        # Send initial history report (empty)
        await bot.send_history_report()
        
        # Start monitoring
        await bot.monitor_products()
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await bot.cleanup()

if __name__ == "__main__":
    asyncio.run(main())