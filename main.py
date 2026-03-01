import asyncio
import aiohttp
from bs4 import BeautifulSoup
import logging
from telegram import Update
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
# It is better to use os.environ.get("TOKEN") for security on hosting
TOKEN = "8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY"
CHAT_ID = "-1003891147099"

DENOMINATIONS = ["1,000", "2,000", "3,000", "4,000", "5,000"]
URLS = [
    "https://amzn.in/d/0atB5gdL",
    # Add your second link here in quotes
]

# Stores the status of every card to detect changes
# Key: (url, denomination) -> Value: "IN_STOCK" or "OUT_STOCK"
stock_states = {}

def iraq_now():
    """Get current time in Iraq (UTC+3)"""
    return datetime.now(timezone.utc) + timedelta(hours=3)

# --- Telegram Command: /status ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a manual report of all tracked items."""
    if not stock_states:
        await update.message.reply_text("🔄 Bot is still scanning. Please wait a moment...")
        return

    report = "📊 **Current Stock Status**\n"
    report += f"⏰ Time: {iraq_now().strftime('%H:%M:%S')} Iraq\n"
    report += "━━━━━━━━━━━━━━━━━━\n"
    
    for url in URLS:
        # Simple label to distinguish links
        label = "Link 1" if "0atB5gdL" in url else "Link 2"
        report += f"📍 **{label}**\n"
        for denom in DENOMINATIONS:
            current = stock_states.get((url, denom), "OUT_STOCK")
            emoji = "✅" if current == "IN_STOCK" else "❌"
            report += f"{emoji} ₹{denom}: {current}\n"
        report += "━━━━━━━━━━━━━━━━━━\n"

    await update.message.reply_text(report, parse_mode="Markdown")

# --- Core Scraper Logic ---
async def run_scanner(application: Application):
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
                    async with session.get(url, headers=headers, timeout=30) as response:
                        if response.status != 200:
                            logger.error(f"Amazon error {response.status} for {url}")
                            continue
                        
                        html = await response.text()
                        soup = BeautifulSoup(html, 'lxml')
                        page_text = soup.get_text()

                        # Check if 'Add to Cart' or 'Buy Now' exists on the page
                        has_buttons = any(soup.find_all("input", {"id": ["add-to-cart-button", "buy-now-button"]}))

                        for denom in DENOMINATIONS:
                            key = (url, denom)
                            
                            # MUST find the denomination text AND the buy button
                            is_available = (denom in page_text) and has_buttons
                            current_status = "IN_STOCK" if is_available else "OUT_STOCK"
                            
                            # Get previous status, default to OUT_STOCK if new
                            previous_status = stock_states.get(key, "OUT_STOCK")

                            # ALERT ONLY ON CHANGE
                            if current_status != previous_status:
                                stock_states[key] = current_status
                                
                                # Prepare Alert
                                emoji = "✅" if current_status == "IN_STOCK" else "❌"
                                alert = (
                                    f"🔔 **Stock Update!**\n\n"
                                    f"📦 Product: PlayStation India\n"
                                    f"💰 Denomination: ₹{denom}\n"
                                    f"📊 Status: {current_status} {emoji}\n"
                                    f"⏰ Time: {iraq_now().strftime('%I:%M %p')} Iraq\n"
                                    f"🔗 [Amazon Link]({url})"
                                )
                                
                                await bot.send_message(chat_id=CHAT_ID, text=alert, parse_mode="Markdown")
                                logger.info(f"Change detected for {denom}: {current_status}")

                except Exception as e:
                    logger.error(f"Scanning error: {e}")

            # Wait 2 minutes between scans
            await asyncio.sleep(120)

# --- Entry Point ---
async def main():
    # Initialize Bot Application
    application = Application.builder().token(TOKEN).build()

    # Register the /status command
    application.add_handler(CommandHandler("status", status_command))

    # Start the background scraper task
    asyncio.create_task(run_scanner(application))

    # Start the command polling
    async with application:
        await application.initialize()
        await application.start()
        logger.info("Bot is LIVE. Monitoring started...")
        await application.updater.start_polling()
        
        # Keep alive
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped manually.")