import asyncio
from telegram import Bot
import os
import json
from datetime import datetime, timedelta, timezone

TELEGRAM_BOT_TOKEN = "8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY"
GROUP_CHAT_ID = "-1003891147099"

def iraq_now():
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=3)

async def diagnostic():
    print("🔍 RUNNING DIAGNOSTIC...")
    print("="*50)
    
    # Test 1: Bot connection
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        me = await bot.get_me()
        print(f"✅ Bot is alive: @{me.username}")
    except Exception as e:
        print(f"❌ Bot connection failed: {e}")
        return
    
    # Test 2: Send test message
    try:
        now = iraq_now()
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"🧪 **Diagnostic Test**\n\nBot is running!\nTime: {now.strftime('%d/%m/%Y %I:%M %p')} Iraq"
        )
        print("✅ Test message sent to group")
    except Exception as e:
        print(f"❌ Cannot send to group: {e}")
    
    # Test 3: Check history file
    if os.path.exists('stock_history.json'):
        with open('stock_history.json', 'r') as f:
            history = json.load(f)
        print(f"📊 History file has {len(history)} events")
        
        # Show last event
        if history:
            last = history[-1]
            print(f"📝 Last event: {last.get('date')} {last.get('time')} - {last.get('status')}")
    else:
        print("📁 No history file yet")
    
    # Test 4: Check when last report should have sent
    now = iraq_now()
    print(f"\n⏱️ Current Iraq time: {now.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"   Last 12AM: {(now.replace(hour=0, minute=0) if now.hour >= 0 else now.replace(hour=0, minute=0) - timedelta(days=1)).strftime('%d/%m %H:%M')}")
    print(f"   Last 12PM: {(now.replace(hour=12, minute=0) if now.hour >= 12 else now.replace(hour=12, minute=0) - timedelta(days=1)).strftime('%d/%m %H:%M')}")
    
    print("="*50)
    print("✅ Diagnostic complete. Check Railway logs for more details.")

asyncio.run(diagnostic())