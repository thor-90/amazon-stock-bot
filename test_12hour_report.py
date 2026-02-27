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

async def send_12hour_report():
    """Send report of last 12 hours activity"""
    
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    now = iraq_now()
    
    # Check if history file exists
    history_file = 'stock_history.json'
    
    if not os.path.exists(history_file):
        message = (
            f"📊 12-HOUR HISTORY REPORT 📊\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⏱️ Time: {now.strftime('%d/%m/%Y %I:%M %p')} Iraq Time\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"❌ No history file found.\n\n"
            f"This means:\n"
            f"• Bot was recently deployed\n"
            f"• No stock events have occurred yet\n"
            f"• Everything is working normally!\n\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=message
            )
            print("✅ Report sent - No history found")
        except TelegramError as e:
            print(f"❌ Error: {e}")
        return
    
    # Load history
    try:
        with open(history_file, 'r') as f:
            events = json.load(f)
    except Exception as e:
        message = f"❌ Error reading history file: {str(e)}"
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=message)
        return
    
    # Filter last 12 hours using Iraq time
    cutoff = now - timedelta(hours=12)
    
    recent_events = []
    for event in events:
        try:
            # Convert stored time to Iraq time for comparison
            event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            event_time_iraq = event_time.replace(tzinfo=timezone.utc) + timedelta(hours=3)
            if event_time_iraq > cutoff:
                recent_events.append(event)
        except:
            continue
    
    # Count by status
    in_stock_count = sum(1 for e in recent_events if e.get('status') == 'IN_STOCK')
    out_stock_count = sum(1 for e in recent_events if e.get('status') == 'OUT_STOCK')
    
    # Build message
    lines = []
    lines.append("📊 12-HOUR HISTORY REPORT 📊")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"⏱️ Period: {(now - timedelta(hours=12)).strftime('%H:%M')} → {now.strftime('%H:%M')} Iraq Time")
    lines.append(f"📅 Date: {now.strftime('%d/%m/%Y')}")
    lines.append("━━━━━━━━━━━━━━━━━━━━\n")
    
    if not recent_events:
        lines.append("📭 No activity in the last 12 hours")
        lines.append("")
        lines.append("✓ Bot is running")
        lines.append("✓ Checking every 2 minutes")
        lines.append("✓ Waiting for stock")
    else:
        lines.append("📊 SUMMARY")
        lines.append(f"  🟢 IN STOCK: {in_stock_count}")
        lines.append(f"  🔴 OUT STOCK: {out_stock_count}")
        lines.append(f"  📊 Total events: {len(recent_events)}\n")
        
        lines.append("📋 DETAILS BY DENOMINATION")
        
        # Group by denomination
        by_denom = {}
        for e in recent_events:
            denom = e.get('denomination', 'Unknown')
            if denom not in by_denom:
                by_denom[denom] = []
            by_denom[denom].append(e)
        
        for denom in sorted(by_denom.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            events = by_denom[denom]
            in_count = sum(1 for e in events if e.get('status') == 'IN_STOCK')
            out_count = sum(1 for e in events if e.get('status') == 'OUT_STOCK')
            
            lines.append(f"")
            lines.append(f"  ₹{denom}:")
            lines.append(f"    🟢 IN: {in_count} | 🔴 OUT: {out_count}")
            
            # Show last 3 events
            for event in events[-3:]:
                try:
                    event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                    event_time_iraq = event_time.replace(tzinfo=timezone.utc) + timedelta(hours=3)
                    time_str = event_time_iraq.strftime('%H:%M')
                except:
                    time_str = event.get('time', 'Unknown')
                emoji = "🟢" if event.get('status') == 'IN_STOCK' else "🔴"
                lines.append(f"    {emoji} {time_str} - {event.get('status', 'Unknown')}")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"⏱️ Generated: {now.strftime('%H:%M:%S')} Iraq Time")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    
    message = "\n".join(lines)
    
    # Send to group
    try:
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=message
        )
        print("✅ 12-hour report sent successfully!")
        print(f"📊 Events in last 12 hours: {len(recent_events)}")
    except TelegramError as e:
        print(f"❌ Error sending report: {e}")

if __name__ == "__main__":
    asyncio.run(send_12hour_report())