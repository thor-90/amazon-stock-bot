#!/usr/bin/env python3
"""
Stock History Checker - Run this anytime to see recorded stock events
"""

import json
import os
from datetime import datetime, timedelta, timezone

HISTORY_FILE = 'stock_history.json'

def iraq_now():
    """Get current time in Iraq (UTC+3)"""
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=3)

def check_history():
    """Check and display stock history"""
    
    print("\n" + "="*60)
    print("📊 STOCK HISTORY REPORT 📊".center(60))
    print("="*60)
    print(f"📅 Generated: {iraq_now().strftime('%d/%m/%Y %I:%M:%S %p')} Iraq Time")
    print("="*60 + "\n")
    
    if not os.path.exists(HISTORY_FILE):
        print("❌ No history file found!")
        print("\nThis means:")
        print("  • Bot was just deployed")
        print("  • No stock events have occurred yet")
        print("  • Everything is working normally!")
        return
    
    try:
        with open(HISTORY_FILE, 'r') as f:
            events = json.load(f)
        
        if not events:
            print("📊 No stock events recorded yet.")
            print("Bot is waiting for first stock appearance!")
            return
        
        print(f"📊 Total events recorded: {len(events)}")
        
        # Get date range
        first_event = datetime.fromisoformat(events[-1]['timestamp'].replace('Z', '+00:00'))
        last_event = datetime.fromisoformat(events[0]['timestamp'].replace('Z', '+00:00'))
        
        # Convert to Iraq time
        first_iraq = first_event.replace(tzinfo=timezone.utc) + timedelta(hours=3)
        last_iraq = last_event.replace(tzinfo=timezone.utc) + timedelta(hours=3)
        
        print(f"📅 First event: {first_iraq.strftime('%d/%m/%Y %H:%M')} Iraq")
        print(f"📅 Last event: {last_iraq.strftime('%d/%m/%Y %H:%M')} Iraq")
        print("")
        
        # Stats by denomination
        print("💰 STATISTICS BY DENOMINATION")
        print("-"*40)
        
        from collections import defaultdict
        by_denom = defaultdict(lambda: {'total': 0, 'in': 0, 'out': 0})
        for e in events:
            denom = e.get('denomination', 'Unknown')
            by_denom[denom]['total'] += 1
            if e.get('status') == 'IN_STOCK':
                by_denom[denom]['in'] += 1
            elif e.get('status') == 'OUT_STOCK':
                by_denom[denom]['out'] += 1
        
        for denom in sorted(by_denom.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            stats = by_denom[denom]
            print(f"  • ₹{denom}:")
            print(f"    • Total: {stats['total']}")
            print(f"    • 🟢 IN: {stats['in']} | 🔴 OUT: {stats['out']}")
        print("")
        
        # Recent events
        print("📋 RECENT EVENTS (Last 10)")
        print("-"*40)
        
        for i, event in enumerate(events[:10], 1):
            event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            event_iraq = event_time.replace(tzinfo=timezone.utc) + timedelta(hours=3)
            time_str = event_iraq.strftime('%d/%m %H:%M')
            emoji = "🟢" if event.get('status') == 'IN_STOCK' else "🔴"
            
            print(f"\n  {emoji} Event #{i}:")
            print(f"    • Denomination: ₹{event.get('denomination', 'Unknown')}")
            print(f"    • Status: {event.get('status', 'Unknown')}")
            print(f"    • Time: {time_str} Iraq")
            print(f"    • Price: {event.get('price', 'Unknown')}")
        
        print("\n" + "="*60)
        print("✅ Report Complete".center(60))
        print("="*60)
        
    except Exception as e:
        print(f"❌ Error reading history: {e}")

def export_history():
    """Export history to formatted text file"""
    if not os.path.exists(HISTORY_FILE):
        print("❌ No history file found")
        return
    
    try:
        with open(HISTORY_FILE, 'r') as f:
            events = json.load(f)
        
        filename = f"history_export_{iraq_now().strftime('%Y%m%d_%H%M')}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("STOCK HISTORY EXPORT\n")
            f.write("="*50 + "\n")
            f.write(f"Generated: {iraq_now().strftime('%d/%m/%Y %H:%M:%S')} Iraq Time\n")
            f.write(f"Total events: {len(events)}\n")
            f.write("="*50 + "\n\n")
            
            for i, event in enumerate(events, 1):
                event_time = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
                event_iraq = event_time.replace(tzinfo=timezone.utc) + timedelta(hours=3)
                
                f.write(f"Event #{i}\n")
                f.write(f"  Time: {event_iraq.strftime('%d/%m/%Y %H:%M:%S')} Iraq\n")
                f.write(f"  Product: {event.get('product', 'Unknown')}\n")
                f.write(f"  Denomination: ₹{event.get('denomination', 'Unknown')}\n")
                f.write(f"  Status: {event.get('status', 'Unknown')}\n")
                f.write(f"  Price: {event.get('price', 'Unknown')}\n")
                f.write("-"*30 + "\n")
        
        print(f"✅ Exported to {filename}")
        
    except Exception as e:
        print(f"❌ Error exporting: {e}")

if __name__ == "__main__":
    print("📊 STOCK HISTORY TOOL")
    print("="*40)
    print("1. View history report")
    print("2. Export history to file")
    print("="*40)
    
    choice = input("Enter your choice (1-2): ").strip()
    
    if choice == "1":
        check_history()
    elif choice == "2":
        export_history()
    else:
        print("❌ Invalid choice")