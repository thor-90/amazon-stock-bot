import asyncio
import aiohttp
from bs4 import BeautifulSoup
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import os
from datetime import datetime, timedelta, timezone
from fake_useragent import UserAgent

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
TOKEN = "8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY"
CHAT_ID = "-1003891147099"
DENOMINATIONS = ["1,000", "2,000", "3,000", "4,000", "5,000"]
URLS = [
    "https://amzn.in/d/0atB5gdL",
    # Add your second link here
]

# This dictionary stores the current state of every card size
# Example: {("url1", "1,000"): "OUT_STOCK"}
stock_states = {}

def iraq_now():
    return datetime.now(timezone.utc) + timedelta(hours=3)

# --- Telegram Command: /status ---
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Checks the current memory and reports the last known status."""
    if not stock_states:
        await update.message.reply_text("🔄 Still gathering data... Please wait for the first scan.")
        return

    text = "📊 **Current Stock Status**\n"
    text += f"⏰ Last Update: {iraq_now().strftime('%H:%M:%S')} Iraq\n"
    text += "━━━━━━━━━━━━━━━━━━\n"
    
    for url in URLS:
        product_label = "Link 1" if "0atB5gdL" in url else "Link 2"
        text += f"📍 **{product_label}**\n"
        for denom in DENOMINATIONS:
            status = stock_states.get((url, denom), "UNKNOWN")
            emoji = "✅" if status == "IN_STOCK" else "❌"
            text += f"{emoji} ₹{denom}: {status}\n"
        text += "━━━━━━━━━━━━━━━━━━\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# --- Core Logic: The Scraper ---
async def monitor_stock(application: Application):
    ua = UserAgent()
    bot = application.bot

    async with aiohttp.ClientSession() as session:
        while True:
            headers = {
                "User-Agent": ua.random,
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.google.com/"
            }

            for url in URLS:
                try:
                    async with session.get(url, headers=headers, timeout=20) as response:
                        if response.status != 200:
                            logger.warning(f"Amazon returned status {response.status}")
                            continue
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'lxml')
                        page_text = soup.get_text()

                        # Check if ANY buying button exists on the page
                        buy_buttons = soup.find_all("input", {"id": ["add-to-cart-button", "buy-now-button"]})
                        is_buyable = len(buy_buttons) > 0

                        for denom in DENOMINATIONS:
                            key = (url, denom)
                            
                            # LOGIC: It is only IN_STOCK if the specific number (e.g. 1,000) 
                            # is present AND the page has a buy button.
                            is_this_denom_live = denom in page_text and is_buyable
                            current_status = "IN_STOCK" if is_this_denom_live else "OUT_STOCK"

                            # Get previous status (default to OUT if not seen before)
                            previous_status = stock_states.get(key, "OUT_STOCK")

                            if current_status != previous_status:
                                # Update memory
                                stock_states[key] = current_status
                                
                                # Send Alert
                                emoji = "✅" if current_status == "IN_STOCK" else "❌"
                                alert_text = (
                                    f"🔔 **Stock Update!**\n\n"
                                    f"📦 Product: PlayStation India\n"
                                    f"💰 Denomination: ₹{denom}\n"
                                    f"📊 Status: {current_status} {emoji}\n"
                                    f"⏰ Time: {iraq_now().strftime('%I:%M %p')} Iraq\n\n"
                                    f"🔗 [Link to Amazon]({url})"
                                )
                                await bot.send_message(chat_id=CHAT_ID, text=alert_text, parse_mode="Markdown")
                                logger.info(f"Alert sent for {denom}: {current_status}")

                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")

            # Interval: 2 minutes (120 seconds) to avoid being banned
            await asyncio.sleep(120)

# --- Start the Bot ---
async def main():
    # Build the Application
    application = Application.builder().token(TOKEN).build()

    # Add /status command
    application.add_handler(CommandHandler("status", status))

    # Start the background task for monitoring
    asyncio.create_task(monitor_stock(application))

    # Run the bot's command listener
    async with application:
        await application.initialize()
        await application.start()
        logger.info("Bot is running and monitoring...")
        await application.updater.start_polling()
        
        # Keep the main loop alive
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass