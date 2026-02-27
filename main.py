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
    def __init__(self):
        # Track stock events: {product_key: {denomination: [(start_time, end_time, status)]}}
        self.stock_history = defaultdict(lambda: defaultdict(list))
        # Track current stock start times
        self.current_stock_start = defaultdict(dict)
        # Track last report time
        self.last_report_time = None
        
    def record_status_change(self, product_name: str, url: str, denomination: str, in_stock: bool):
        """Record when stock status changes"""
        product_key = f"{product_name}|{url}"
        current_time = datetime.now(IST)
        
        if in_stock:
            # Stock became available - record start time
            self.current_stock_start[product_key][denomination] = current_time
            logger.info(f"📝 TRACKING: {product_name} - ₹{denomination} went IN STOCK at {current_time.strftime('%H:%M:%S')}")
        else:
            # Stock sold out - if we had a start time, record the event
            if denomination in self.current_stock_start.get(product_key, {}):
                start_time = self.current_stock_start[product_key][denomination]
                duration = current_time - start_time
                
                # Record this stock event
                self.stock_history[product_key][denomination].append({
                    'start': start_time,
                    'end': current_time,
                    'duration': duration
                })
                
                # Clear current stock start
                del self.current_stock_start[product_key][denomination]
                
                logger.info(f"📝 TRACKING: {product_name} - ₹{denomination} was in stock for {self._format_duration(duration)}")
    
    def _format_duration(self, duration):
        """Format timedelta into readable string"""
        total_seconds = int(duration.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def get_daily_summary(self, period="12h"):
        """Generate summary for the last 12 hours"""
        now = datetime.now(IST)
        
        if period == "12h":
            cutoff_time = now - timedelta(hours=12)
            period_name = "Last 12 Hours"
        else:
            cutoff_time = now - timedelta(hours=24)
            period_name = "Last 24 Hours"
        
        summary_lines = []
        summary_lines.append(f"📊 **STOCK SUMMARY REPORT** 📊")
        summary_lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        summary_lines.append(f"📅 **Period:** {period_name}")
        summary_lines.append(f"⏱️ **Generated:** {now.strftime('%d/%m/%Y %I:%M %p')}")
        summary_lines.append(f"━━━━━━━━━━━━━━━━━━━━\n")
        
        total_events = 0
        any_stock = False
        
        # Check each product and denomination
        for product_key, denominations in self.stock_history.items():
            product_name = product_key.split('|')[0]
            summary_lines.append(f"**{product_name}**")
            
            for denomination, events in denominations.items():
                # Filter events within last 12 hours
                recent_events = [e for e in events if e['start'] >= cutoff_time]
                
                if recent_events:
                    any_stock = True
                    total_events += len(recent_events)
                    
                    # Calculate total time in stock
                    total_duration = sum((e['duration'] for e in recent_events), timedelta())
                    
                    summary_lines.append(f"  • **₹{denomination}:**")
                    summary_lines.append(f"    • Times in stock: {len(recent_events)}")
                    summary_lines.append(f"    • Total duration: {self._format_duration(total_duration)}")
                    
                    # Show each event
                    for i, event in enumerate(recent_events, 1):
                        start_str = event['start'].strftime('%H:%M')
                        end_str = event['end'].strftime('%H:%M')
                        duration_str = self._format_duration(event['duration'])
                        summary_lines.append(f"    • Event {i}: {start_str} → {end_str} ({duration_str})")
            
            summary_lines.append("")
        
        # Add currently in stock items
        current_stock_lines = []
        for product_key, denominations in self.current_stock_start.items():
            if denominations:  # If there are items currently in stock
                product_name = product_key.split('|')[0]
                for denomination, start_time in denominations.items():
                    if start_time >= cutoff_time:  # Only if started in last 12h
                        current_duration = now - start_time
                        current_stock_lines.append(f"  • **₹{denomination}** - In stock for {self._format_duration(current_duration)} (since {start_time.strftime('%H:%M')})")
        
        if current_stock_lines:
            summary_lines.append(f"🟢 **CURRENTLY IN STOCK:**")
            summary_lines.extend(current_stock_lines)
            summary_lines.append("")
        
        if not any_stock and not current_stock_lines:
            summary_lines.append("❌ **No stock activity in the last 12 hours.**")
        else:
            summary_lines.append(f"━━━━━━━━━━━━━━━━━━━━")
            summary_lines.append(f"📊 **Total stock events: {total_events}**")
        
        summary_lines.append(f"━━━━━━━━━━━━━━━━━━━━")
        
        return "\n".join(summary_lines)
    
    def reset_history(self, hours=12):
        """Clear history older than specified hours"""
        cutoff_time = datetime.now(IST) - timedelta(hours=hours)
        
        for product_key in list(self.stock_history.keys()):
            for denomination in list(self.stock_history[product_key].keys()):
                # Keep only recent events
                self.stock_history[product_key][denomination] = [
                    e for e in self.stock_history[product_key][denomination]
                    if e['start'] >= cutoff_time
                ]
                
                # Remove empty denomination entries
                if not self.stock_history[product_key][denomination]:
                    del self.stock_history[product_key][denomination]
            
            # Remove empty product entries
            if not self.stock_history[product_key]:
                del self.stock_history[product_key]

# ===== TELEGRAM BOT =====
class StockNotificationBot:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id
        self.checker = AmazonStockChecker()
        self.tracker = StockTracker()
        self.last_alert_time: Dict[str, float] = {}  # Track when last alert was sent
        self.last_status_change: Dict[str, bool] = {}  # Track last known status
        self.last_summary_time = None

    async def send_stock_alert(self, product_name: str, url: str, denomination: str, price: str, in_stock: bool):
        """
        Send stock notification to Telegram (both in-stock and out-of-stock alerts)
        With cooldown to prevent duplicates
        """
        # Create a unique key for this specific product and denomination
        alert_key = f"{url}_{denomination}"
        current_time = time.time()
        
        # Check if we've sent an alert for this item recently
        if alert_key in self.last_alert_time:
            time_since_last = current_time - self.last_alert_time[alert_key]
            if time_since_last < ALERT_COOLDOWN:
                logger.info(f"Cooldown active for {product_name} - ₹{denomination} ({time_since_last:.0f}s since last alert). Skipping.")
                return  # Don't send the message
        
        # Get current date and time in IST
        now_ist = datetime.now(IST)
        date_str = now_ist.strftime('%d/%m/%Y')
        time_str = now_ist.strftime('%H:%M:%S')
        
        # Record this status change in tracker
        self.tracker.record_status_change(product_name, url, denomination, in_stock)
        
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
            self.last_alert_time[alert_key] = current_time
            logger.info(f"Alert sent: {product_name} - ₹{denomination} - {'In Stock' if in_stock else 'Out of Stock'}")
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def send_daily_summary(self, period="12h"):
        """Send daily summary report"""
        summary = self.tracker.get_daily_summary(period)
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=summary,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
            logger.info(f"📊 Daily summary sent for period: {period}")
            
            # Clean up old history
            self.tracker.reset_history(12)
            
        except TelegramError as e:
            logger.error(f"Failed to send daily summary: {e}")

    async def check_summary_time(self):
        """Check if it's time to send summary (12 AM and 12 PM IST)"""
        now_ist = datetime.now(IST)
        
        # Send at 12:00 AM and 12:00 PM (with 1-minute window)
        if (now_ist.hour == 0 and now_ist.minute == 0) or (now_ist.hour == 12 and now_ist.minute == 0):
            # Check if we already sent summary in this minute
            if self.last_summary_time != now_ist.strftime('%Y%m%d%H%M'):
                await self.send_daily_summary("12h")
                self.last_summary_time = now_ist.strftime('%Y%m%d%H%M')
                await asyncio.sleep(60)  # Wait a minute to avoid duplicate

    async def monitor_products(self):
        """Main monitoring loop"""
        logger.info("Starting stock monitor for all denominations...")
        logger.info(f"Check interval: {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.1f} minutes)")
        logger.info(f"Alert cooldown: {ALERT_COOLDOWN} seconds ({ALERT_COOLDOWN/60:.1f} minutes)")
        logger.info("📊 Daily summaries at 12:00 AM and 12:00 PM IST")
        
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
                
                # Check if it's time for daily summary
                await self.check_summary_time()
                
                # Log summary of any status changes
                if status_changes:
                    logger.info(f"✅ Status changes detected: {len(status_changes)} items changed state")
                else:
                    logger.info("ℹ️ No status changes detected in this cycle")
                
                logger.info(f"💤 Sleeping for {CHECK_INTERVAL} seconds ({CHECK_INTERVAL/60:.1f} minutes)...")
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