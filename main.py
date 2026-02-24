import asyncio
import aiohttp
from bs4 import BeautifulSoup
import logging
from telegram import Bot
from telegram.error import TelegramError
import time
from typing import Dict, Tuple
import re
from fake_useragent import UserAgent
import ssl
import certifi

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== CONFIGURATION =====
TELEGRAM_BOT_TOKEN = "8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY"
TELEGRAM_CHAT_ID = "1612876925"

# Products to monitor (URL: product name)
PRODUCTS = {
    "https://amzn.in/d/0atB5gdL": "Rs.1000 PlayStation Gift Card",
    "https://amzn.in/d/081q2grT": "Rs.1000 PlayStation Gift Card",  # Update with actual product name
}

# Stock status indicators (based on Amazon's out of stock message)
OUT_OF_STOCK_INDICATORS = [
    "out of stock",
    "currently unavailable",
    "we don't know when or if this item will be back in stock",
    "temporarily out of stock"
]

# Check interval in seconds (e.g., 300 = 5 minutes)
CHECK_INTERVAL = 300

# ===== STOCK CHECKER =====
class AmazonStockChecker:
    def __init__(self):
        self.ua = UserAgent()
        self.session = None
        self.last_status: Dict[str, Tuple[bool, str]] = {}  # url -> (in_stock, status_text)
        self.connector = None

    async def get_session(self):
        """Create or return aiohttp session with proper headers"""
        if self.session is None or self.session.closed:
            # Create SSL context and connector inside async function
            ssl_context = ssl.create_default_context(cafile=certifi.where())
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

    async def check_product(self, url: str, product_name: str) -> Tuple[bool, str, str]:
        """
        Check if product is in stock
        Returns: (in_stock, status_message, price_info)
        """
        try:
            session = await self.get_session()
            
            # Add random delay to avoid being blocked
            await asyncio.sleep(2)
            
            async with session.get(url, timeout=30, allow_redirects=True) as response:
                if response.status != 200:
                    logger.warning(f"Got status {response.status} for {product_name}")
                    return False, f"HTTP Error: {response.status}", ""
                
                html = await response.text()
                
                # Parse with BeautifulSoup
                soup = BeautifulSoup(html, 'html.parser')
                
                # Check multiple possible stock indicators
                page_text = soup.get_text().lower()
                
                # Look for out of stock messages
                is_out_of_stock = any(
                    indicator in page_text for indicator in OUT_OF_STOCK_INDICATORS
                )
                
                # Check for buy button / add to cart
                buy_box = soup.select_one('#buy-now-button, #add-to-cart-button, .a-button-input')
                has_buy_button = buy_box is not None and buy_box.get('aria-disabled') != 'true'
                
                # Check for price
                price_element = (
                    soup.select_one('.a-price-whole') or 
                    soup.select_one('#priceblock_ourprice') or 
                    soup.select_one('.a-price .a-offscreen')
                )
                price = price_element.get_text().strip() if price_element else "Price not visible"
                
                # Determine stock status
                in_stock = has_buy_button and not is_out_of_stock
                
                # Get specific status message
                status_msg = self._extract_status_message(soup)
                
                logger.info(f"{product_name} - In stock: {in_stock}, Status: {status_msg}")
                
                return in_stock, status_msg, price
                
        except asyncio.TimeoutError:
            logger.error(f"Timeout checking {product_name}")
            return False, "Timeout Error", ""
        except Exception as e:
            logger.error(f"Error checking {product_name}: {str(e)}")
            return False, f"Error: {str(e)[:50]}", ""

    def _extract_status_message(self, soup: BeautifulSoup) -> str:
        """Extract specific stock status message from page"""
        # Check for availability message
        availability = soup.select_one('#availability span, .a-color-success, .a-color-error')
        if availability:
            return availability.get_text().strip()
        
        # Check for out of stock message in various places
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

    async def send_notification(self, product_name: str, url: str, price: str):
        """Send stock notification to Telegram"""
        message = (
            f"🔔 **STOCK ALERT!** 🔔\n\n"
            f"**{product_name}** is now **IN STOCK!**\n\n"
            f"💰 Price: {price}\n"
            f"🛒 Buy now: {url}\n\n"
            f"@amazon @psn #PlayStation #GiftCard"
        )
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode='Markdown',
                disable_web_page_preview=False
            )
            logger.info(f"Notification sent for {product_name}")
        except TelegramError as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def monitor_products(self):
        """Main monitoring loop"""
        logger.info("Starting stock monitor...")
        
        while True:
            try:
                for url, product_name in PRODUCTS.items():
                    logger.info(f"Checking {product_name}...")
                    
                    in_stock, status_msg, price = await self.checker.check_product(url, product_name)
                    
                    # Get previous status
                    prev_in_stock, _ = self.checker.last_status.get(url, (None, ""))
                    
                    # Check if status has changed to IN STOCK
                    if in_stock and not prev_in_stock:
                        logger.info(f"{product_name} is now IN STOCK!")
                        await self.send_notification(product_name, url, price)
                    elif not in_stock and prev_in_stock:
                        logger.info(f"{product_name} went OUT OF STOCK")
                    
                    # Update last status
                    self.checker.last_status[url] = (in_stock, status_msg)
                    
                    # Brief pause between products
                    await asyncio.sleep(5)
                
                logger.info(f"Sleeping for {CHECK_INTERVAL} seconds...")
                await asyncio.sleep(CHECK_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying

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
        product_list = "\n• ".join(PRODUCTS.values())
        await bot.bot.send_message(
            chat_id=bot.chat_id,
            text=f"🚀 **Amazon Stock Monitor Started!**\n\nI'll notify you when these products are back in stock:\n• {product_list}\n\nMonitoring every {CHECK_INTERVAL//60} minutes."
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
    # Run the bot
    asyncio.run(main())