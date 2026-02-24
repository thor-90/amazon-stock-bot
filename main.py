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

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== CONFIGURATION =====
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1612876925")

# Products to monitor with their denominations
PRODUCTS = {
    "https://amzn.in/d/0atB5gdL": {
        "name": "PlayStation Gift Card Link 1",
        "denominations": ["1000", "2000", "3000", "4000", "5000"]
    },
    "https://amzn.in/d/081q2grT": {
        "name": "PlayStation Gift Card Link 2",
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

# Check interval in seconds (e.g., 300 = 5 minutes)
CHECK_INTERVAL = 300

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
            # For Amazon, we need to check if this denomination option is available
            # This might require different approaches based on how the page displays denominations
            
            session = await self.get_session()
            
            # Add random delay to avoid being blocked
            await asyncio.sleep(2)
            
            async with session.get(url, timeout=30, allow_redirects=True) as response:
                if response.status != 200:
                    logger.warning(f"Got status {response.status} for {product_info['name']} - Rs.{denomination}")
                    return False, f"HTTP Error: {response.status}", ""
                
                html = await response.text()
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for denomination-specific elements
                # This is where you'd need to customize based on how the page shows denominations
                
                # Method 1: Check for denomination in dropdown/select
                denomination_selectors = [
                    f'select option[value*="{denomination}"]',
                    f'option:contains("Rs. {denomination}")',
                    f'option:contains("₹{denomination}")',
                    f'a[href*="{denomination}"]',
                    f'[data-value*="{denomination}"]',
                ]
                
                # Check if this denomination option exists and is selectable
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
                # This logic may need adjustment based on how the page actually works
                if denomination_exists or denomination_in_text:
                    # If denomination is mentioned and there's a buy button and not out of stock
                    in_stock = has_buy_button and not is_out_of_stock
                else:
                    in_stock = False
                
                # Try to get price for this denomination
                price = self._extract_price(soup)
                
                # Get status message
                status_msg = self._extract_status_message(soup)
                
                logger.info(f"{product_info['name']} - Rs.{denomination}: {'IN STOCK' if in_stock else 'Out of Stock'} - {status_msg}")
                
                return in_stock, status_msg, price
                
        except Exception as e:
            logger.error(f"Error checking {product_info['name']} - Rs.{denomination}: {str(e)}")
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

# ===== TELEGRAM BOT =====
class StockNotificationBot:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id
        self.checker = AmazonStockChecker()

    async def send_notification(self, product_name: str, url: str, denomination: str, price: str):
        """Send stock notification to Telegram"""
        message = (
            f"🔔 **STOCK ALERT!** 🔔\n\n"
            f"**{product_name}**\n"
            f"**Denomination: Rs.{denomination}**\n\n"
            f"💰 Price: {price}\n"
            f"🛒 Buy now: {url}\n\n"
            f"#PlayStation #GiftCard #Rs{denomination}"
        )
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            logger.info(f"Notification sent: {product_name} - Rs.{denomination}")
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def send_summary(self, in_stock_items: List[Tuple[str, str, str, str]]):
        """Send a summary of all in-stock items"""
        if not in_stock_items:
            return
        
        message = "📊 **Current Stock Summary** 📊\n\n"
        
        for product_name, url, denomination, price in in_stock_items:
            message += f"✅ **{product_name}**\n"
            message += f"   • Rs.{denomination} - {price}\n"
            message += f"   • [Buy Now]({url})\n\n"
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except TelegramError as e:
            logger.error(f"Failed to send summary: {e}")

    async def monitor_products(self):
        """Main monitoring loop"""
        logger.info("Starting stock monitor for all denominations...")
        
        # Initialize tracking for all denominations
        for url, product_info in PRODUCTS.items():
            if url not in self.checker.last_status:
                self.checker.last_status[url] = {}
                for denom in product_info["denominations"]:
                    self.checker.last_status[url][denom] = (False, "")
        
        while True:
            try:
                in_stock_items = []
                
                for url, product_info in PRODUCTS.items():
                    for denomination in product_info["denominations"]:
                        logger.info(f"Checking {product_info['name']} - Rs.{denomination}...")
                        
                        in_stock, status_msg, price = await self.checker.check_denomination_stock(
                            url, denomination, product_info
                        )
                        
                        # Get previous status for this denomination
                        prev_in_stock, _ = self.checker.last_status[url].get(denomination, (False, ""))
                        
                        # Check if status has changed to IN STOCK
                        if in_stock and not prev_in_stock:
                            logger.info(f"{product_info['name']} - Rs.{denomination} is now IN STOCK!")
                            await self.send_notification(product_info['name'], url, denomination, price)
                            in_stock_items.append((product_info['name'], url, denomination, price))
                        
                        # Update last status
                        self.checker.last_status[url][denomination] = (in_stock, status_msg)
                        
                        # Brief pause between checks
                        await asyncio.sleep(3)
                
                # Send summary if any items are in stock
                if in_stock_items:
                    await self.send_summary(in_stock_items)
                
                logger.info(f"Sleeping for {CHECK_INTERVAL} seconds...")
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
        
        # Send startup message
        startup_message = "🚀 **Amazon Stock Monitor Started!** 🚀\n\n"
        startup_message += "Monitoring **5 denominations** across **2 links**:\n\n"
        
        for url, product_info in PRODUCTS.items():
            startup_message += f"📌 **{product_info['name']}**\n"
            startup_message += f"   Denominations: Rs.{', Rs.'.join(product_info['denominations'])}\n"
            startup_message += f"   Link: {url}\n\n"
        
        startup_message += f"Checking every {CHECK_INTERVAL//60} minutes.\n"
        startup_message += "You'll be notified immediately when any denomination comes in stock!"
        
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