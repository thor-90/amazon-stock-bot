#!/usr/bin/env python3
"""
Run this in Railway console to check host history
"""

import sqlite3
from datetime import datetime
import os

DB_PATH = 'stock_history.db'

print("\n" + "="*60)
print("RAILWAY HOST - STOCK HISTORY CHECK")
print("="*60)

if not os.path.exists(DB_PATH):
    print("❌ No database found!")
    print("This means either:")
    print("  • Bot was just deployed")
    print("  • No stock events occurred yet")
    print("  • Database not initialized")
else:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check stock events
    cursor.execute("SELECT COUNT(*) FROM stock_events")
    count = cursor.fetchone()[0]
    print(f"\n📊 Stock events recorded: {count}")
    
    if count > 0:
        cursor.execute("SELECT MIN(start_time), MAX(start_time) FROM stock_events")
        first, last = cursor.fetchone()
        print(f"📅 First event: {first}")
        print(f"📅 Last event: {last}")
    
    # Check bot stats
    cursor.execute("SELECT SUM(total_checks) FROM bot_stats")
    checks = cursor.fetchone()[0] or 0
    print(f"🤖 Total checks performed: {checks}")
    
    conn.close()

print("\n" + "="*60)