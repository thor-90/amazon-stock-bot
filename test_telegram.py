import asyncio
from telegram import Bot

async def test():
    bot = Bot(token="8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY")
    
    try:
        # Try to send a simple message
        await bot.send_message(
            chat_id="1612876925",
            text="Test message from bot"
        )
        print("✅ Message sent successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")

asyncio.run(test())