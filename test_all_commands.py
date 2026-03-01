import asyncio
import json
from datetime import datetime, timedelta, timezone
from telegram import Bot
from telegram.error import TelegramError
import os

TELEGRAM_BOT_TOKEN = "8649783060:AAG2EvOnFL1C8nPLjqLfi1k-OQF_NyHTkwY"
GROUP_CHAT_ID = "-1003891147099"

def iraq_now():
    """Get current time in Iraq (UTC+3)"""
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=3)

async def test_bot_connection():
    """Test 1: Basic bot connection"""
    print("\n🔍 TEST 1: Bot Connection")
    print("-" * 40)
    
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        me = await bot.get_me()
        print(f"✅ Bot connected: @{me.username}")
        return bot
    except Exception as e:
        print(f"❌ Bot connection failed: {e}")
        return None

async def test_send_message(bot):
    """Test 2: Send simple text message"""
    print("\n🔍 TEST 2: Send Simple Message")
    print("-" * 40)
    
    try:
        message = "🧪 **Test Message**\n\nIf you see this, the bot can send basic messages to the group!"
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        print("✅ Simple message sent - Check your group!")
    except TelegramError as e:
        print(f"❌ Failed to send message: {e}")

async def test_stock_alert(bot):
    """Test 3: Test IN STOCK alert format"""
    print("\n🔍 TEST 3: IN STOCK Alert Format")
    print("-" * 40)
    
    now = iraq_now()
    date_str = now.strftime('%d/%m/%Y')
    time_str = now.strftime('%H:%M:%S')
    
    message = (
        f"🟢 **STOCK AVAILABLE!** 🟢\n\n"
        f"**PlayStation INDIA Gift Card**\n\n"
        f"**VALUE:** **₹1000**\n\n"
        f"Price: ₹1,000\n"
        f"**BUY NOW:** https://amzn.in/d/0atB5gdL\n"
        f"Date: {date_str}\n"
        f"Time: {time_str} Iraq\n\n"
        f"📌 **TEST ALERT - Not Real Stock**"
    )
    
    try:
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        print("✅ IN STOCK test alert sent - Check the format!")
    except TelegramError as e:
        print(f"❌ Failed to send: {e}")

async def test_out_stock_alert(bot):
    """Test 4: Test OUT OF STOCK alert format"""
    print("\n🔍 TEST 4: OUT OF STOCK Alert Format")
    print("-" * 40)
    
    now = iraq_now()
    date_str = now.strftime('%d/%m/%Y')
    time_str = now.strftime('%H:%M:%S')
    
    message = (
        f"🔴 **OUT OF STOCK** 🔴\n\n"
        f"**PlayStation INDIA Gift Card**\n\n"
        f"**VALUE:** **₹1000**\n\n"
        f"Date: {date_str}\n"
        f"Time: {time_str} Iraq\n\n"
        f"Will alert again when restocked.\n"
        f"📌 **TEST ALERT - Not Real Stock**"
    )
    
    try:
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=message,
            parse_mode='Markdown'
        )
        print("✅ OUT OF STOCK test alert sent - Check the format!")
    except TelegramError as e:
        print(f"❌ Failed to send: {e}")

async def test_12hour_report(bot):
    """Test 5: Test 12-hour report format"""
    print("\n🔍 TEST 5: 12-Hour Report Format")
    print("-" * 40)
    
    now = iraq_now()
    
    message = (
        f"📊 12-HOUR HISTORY REPORT\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ Period: {(now - timedelta(hours=12)).strftime('%H:%M')} → {now.strftime('%H:%M')} Iraq Time\n"
        f"📅 Date: {now.strftime('%d/%m/%Y')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 SUMMARY\n"
        f"  🟢 IN STOCK: 2\n"
        f"  🔴 OUT STOCK: 2\n"
        f"  📊 Total events: 4\n\n"
        f"📋 DETAILS BY DENOMINATION\n\n"
        f"  ₹1000:\n"
        f"    🟢 IN: 1 | 🔴 OUT: 1\n"
        f"    🟢 09:15 - IN_STOCK\n"
        f"    🔴 09:45 - OUT_STOCK\n\n"
        f"  ₹5000:\n"
        f"    🟢 IN: 1 | 🔴 OUT: 1\n"
        f"    🟢 14:30 - IN_STOCK\n"
        f"    🔴 15:20 - OUT_STOCK\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⏱️ Generated: {now.strftime('%H:%M:%S')} Iraq Time\n"
        f"📌 **TEST REPORT - Sample Data**"
    )
    
    try:
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=message
        )
        print("✅ 12-hour test report sent - Check the format!")
    except TelegramError as e:
        print(f"❌ Failed to send: {e}")

async def test_history_recording():
    """Test 6: Test history file creation and recording"""
    print("\n🔍 TEST 6: History Recording")
    print("-" * 40)
    
    history_file = 'stock_history.json'
    test_event = {
        'timestamp': iraq_now().isoformat(),
        'date': iraq_now().strftime('%Y-%m-%d'),
        'time': iraq_now().strftime('%H:%M:%S'),
        'product': 'PlayStation INDIA Gift Card',
        'denomination': '1000',
        'status': 'TEST_EVENT',
        'price': '₹1,000'
    }
    
    try:
        # Load existing or create new
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                history = json.load(f)
        else:
            history = []
        
        # Add test event
        history.append(test_event)
        
        # Save
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)
        
        print(f"✅ Test event recorded to {history_file}")
        print(f"📊 Total events in history: {len(history)}")
        
        # Show the recorded event
        print(f"\n📝 Last recorded event:")
        print(f"   • Time: {test_event['time']}")
        print(f"   • Denomination: ₹{test_event['denomination']}")
        print(f"   • Status: {test_event['status']}")
        
    except Exception as e:
        print(f"❌ Failed to record history: {e}")

async def test_cleanup():
    """Test 7: Clean up test events from history"""
    print("\n🔍 TEST 7: Clean Up Test Events")
    print("-" * 40)
    
    history_file = 'stock_history.json'
    
    if not os.path.exists(history_file):
        print("✅ No history file to clean")
        return
    
    try:
        with open(history_file, 'r') as f:
            history = json.load(f)
        
        # Remove test events
        original_count = len(history)
        real_events = [e for e in history if e.get('status') != 'TEST_EVENT']
        
        with open(history_file, 'w') as f:
            json.dump(real_events, f, indent=2)
        
        removed = original_count - len(real_events)
        print(f"✅ Removed {removed} test events from history")
        print(f"📊 Kept {len(real_events)} real events")
        
    except Exception as e:
        print(f"❌ Failed to clean history: {e}")

async def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "="*60)
    print("🚀 RUNNING COMPLETE BOT TEST SUITE 🚀".center(60))
    print("="*60)
    print(f"📅 Time: {iraq_now().strftime('%d/%m/%Y %I:%M:%S %p')} Iraq Time")
    print(f"📱 Group: {GROUP_CHAT_ID}")
    print("="*60)
    
    # Test 1: Bot Connection
    bot = await test_bot_connection()
    if not bot:
        print("\n❌ Cannot proceed without bot connection!")
        return
    
    await asyncio.sleep(2)
    
    # Test 2: Simple Message
    await test_send_message(bot)
    await asyncio.sleep(3)
    
    # Test 3: IN STOCK Alert
    await test_stock_alert(bot)
    await asyncio.sleep(3)
    
    # Test 4: OUT OF STOCK Alert
    await test_out_stock_alert(bot)
    await asyncio.sleep(3)
    
    # Test 5: 12-Hour Report
    await test_12hour_report(bot)
    await asyncio.sleep(3)
    
    # Test 6: History Recording
    await test_history_recording()
    await asyncio.sleep(2)
    
    # Test 7: Clean Up
    await test_cleanup()
    
    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETED! ✅".center(60))
    print("="*60)
    print("\n📱 **Check your Telegram group now!**")
    print("   You should see 5 test messages:")
    print("   1. Simple test message")
    print("   2. 🟢 IN STOCK test alert")
    print("   3. 🔴 OUT OF STOCK test alert")
    print("   4. 📊 12-hour test report")
    print("   5. History recording confirmation")
    print("\n📁 **Local files checked:**")
    print("   • stock_history.json - created/updated")
    print("   • Test events added then removed")
    print("\n" + "="*60)

if __name__ == "__main__":
    asyncio.run(run_all_tests())