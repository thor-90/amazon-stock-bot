#!/usr/bin/env python3
"""
Stock History Checker - Run this anytime to see what the host has recorded
"""

import sqlite3
from datetime import datetime
import json
import os
from collections import defaultdict

DB_PATH = 'stock_history.db'

def format_duration(seconds):
    """Format seconds into readable duration"""
    if not seconds or seconds == 0:
        return "N/A"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def check_host_history():
    """Check what the host has recorded"""
    
    print("\n" + "="*70)
    print("📊 **HOST STOCK HISTORY REPORT** 📊".center(70))
    print("="*70)
    print(f"📅 Checked: {datetime.now().strftime('%d/%m/%Y %I:%M:%S %p')}")
    print("="*70 + "\n")
    
    if not os.path.exists(DB_PATH):
        print("❌ **No history database found on host!**")
        print("\nPossible reasons:")
        print("  • Bot was just deployed (wait for first checks)")
        print("  • Database hasn't been created yet")
        print("  • Bot is running but no stock events occurred")
        print("\n✅ **This is NORMAL if no stock has appeared!**")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        if not tables:
            print("❌ No tables found in database")
            conn.close()
            return
        
        print(f"📂 **Database File:** {DB_PATH}")
        print(f"📊 **Tables Found:** {', '.join(t['name'] for t in tables)}\n")
        
        # ===== STOCK EVENTS =====
        cursor.execute("SELECT COUNT(*) as count FROM stock_events")
        event_count = cursor.fetchone()['count']
        
        print("📈 **STOCK EVENTS**")
        print("-"*50)
        print(f"📊 Total events recorded: {event_count}")
        
        if event_count > 0:
            # Get date range
            cursor.execute("SELECT MIN(start_time) as first, MAX(start_time) as last FROM stock_events")
            row = cursor.fetchone()
            first = datetime.fromisoformat(row['first']).strftime('%d/%m/%Y %H:%M') if row['first'] else "N/A"
            last = datetime.fromisoformat(row['last']).strftime('%d/%m/%Y %H:%M') if row['last'] else "N/A"
            print(f"📅 First event: {first}")
            print(f"📅 Last event: {last}")
            
            # Stats by denomination
            cursor.execute("""
                SELECT denomination, 
                       COUNT(*) as count,
                       SUM(CASE WHEN status='IN_STOCK' THEN 1 ELSE 0 END) as in_count,
                       SUM(CASE WHEN status='OUT_STOCK' THEN 1 ELSE 0 END) as out_count,
                       SUM(duration_seconds) as total_duration
                FROM stock_events 
                GROUP BY denomination
                ORDER BY CAST(denomination AS INTEGER)
            """)
            denom_stats = cursor.fetchall()
            
            print("\n💰 **By Denomination:**")
            for stat in denom_stats:
                print(f"  • **₹{stat['denomination']}:**")
                print(f"    • Events: {stat['count']}")
                print(f"    • IN: {stat['in_count']} | OUT: {stat['out_count']}")
                if stat['total_duration']:
                    print(f"    • Total time: {format_duration(stat['total_duration'])}")
            
            # Recent events
            print("\n📋 **Recent Events (Last 5):**")
            cursor.execute("""
                SELECT * FROM stock_events 
                ORDER BY start_time DESC 
                LIMIT 5
            """)
            recent = cursor.fetchall()
            
            for i, event in enumerate(recent, 1):
                start = datetime.fromisoformat(event['start_time']).strftime('%d/%m %H:%M')
                end = datetime.fromisoformat(event['end_time']).strftime('%d/%m %H:%M') if event['end_time'] else "Still in stock"
                status_emoji = "🟢" if event['status'] == 'IN_STOCK' else "🔴"
                
                print(f"\n  {status_emoji} **Event #{i}:**")
                print(f"    • Denom: ₹{event['denomination']}")
                print(f"    • Status: {event['status']}")
                print(f"    • Started: {start}")
                print(f"    • Ended: {end}")
                if event['duration_seconds']:
                    print(f"    • Duration: {format_duration(event['duration_seconds'])}")
        else:
            print("  ℹ️ **No stock events recorded yet**")
        print()
        
        # ===== DAILY SUMMARIES =====
        cursor.execute("SELECT COUNT(*) as count FROM daily_summaries")
        summary_count = cursor.fetchone()['count']
        
        print("📅 **DAILY SUMMARIES**")
        print("-"*50)
        print(f"📊 Total summaries: {summary_count}")
        
        if summary_count > 0:
            cursor.execute("""
                SELECT summary_date, summary_type, COUNT(*) as count
                FROM daily_summaries 
                GROUP BY summary_date, summary_type
                ORDER BY summary_date DESC
                LIMIT 10
            """)
            summaries = cursor.fetchall()
            
            print("\n📋 **Recent Summaries:**")
            for s in summaries:
                print(f"  • {s['summary_date']} - {s['summary_type']} ({s['count']})")
        print()
        
        # ===== BOT STATS =====
        cursor.execute("SELECT COUNT(*) as count FROM bot_stats")
        stats_count = cursor.fetchone()['count']
        
        print("🤖 **BOT STATISTICS**")
        print("-"*50)
        print(f"📊 Days of stats: {stats_count}")
        
        if stats_count > 0:
            cursor.execute("""
                SELECT SUM(total_checks) as checks,
                       SUM(total_alerts) as alerts,
                       SUM(in_stock_events) as in_stock,
                       SUM(out_stock_events) as out_stock
                FROM bot_stats
            """)
            totals = cursor.fetchone()
            
            print(f"  • Total checks: {totals['checks'] or 0}")
            print(f"  • Total alerts: {totals['alerts'] or 0}")
            print(f"  • IN stock events: {totals['in_stock'] or 0}")
            print(f"  • OUT stock events: {totals['out_stock'] or 0}")
            
            # Today's stats
            today = datetime.now().strftime('%Y-%m-%d')
            cursor.execute("""
                SELECT * FROM bot_stats WHERE stat_date = ?
            """, (today,))
            today_stats = cursor.fetchone()
            
            if today_stats:
                print(f"\n📈 **Today ({today}):**")
                print(f"  • Checks: {today_stats['total_checks']}")
                print(f"  • Alerts: {today_stats['total_alerts']}")
        
        conn.close()
        
        print("\n" + "="*70)
        print("✅ **Report Complete**".center(70))
        print("="*70 + "\n")
        
        # Summary conclusion
        if event_count == 0:
            print("📌 **CONCLUSION:** The host has recorded **NO STOCK EVENTS** since the bot started.")
            print("    This means there has been no stock available - your bot is working correctly!")
        else:
            print(f"📌 **CONCLUSION:** The host has recorded **{event_count} stock events**.")
            print("    Check the details above to see when stock appeared!")
        
    except Exception as e:
        print(f"❌ Error reading history: {e}")

def export_host_history():
    """Export all host history to JSON"""
    
    if not os.path.exists(DB_PATH):
        print("❌ No history database found on host")
        return
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        history = {}
        
        # Export stock events
        cursor.execute("SELECT * FROM stock_events ORDER BY start_time DESC")
        history['stock_events'] = [dict(row) for row in cursor.fetchall()]
        
        # Export daily summaries
        cursor.execute("SELECT * FROM daily_summaries ORDER BY summary_date DESC")
        history['daily_summaries'] = [dict(row) for row in cursor.fetchall()]
        
        # Export bot stats
        cursor.execute("SELECT * FROM bot_stats ORDER BY stat_date DESC")
        history['bot_stats'] = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        # Save to file
        filename = f"host_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"✅ History exported to {filename}")
        print(f"📊 Stock events: {len(history['stock_events'])}")
        print(f"📅 Daily summaries: {len(history['daily_summaries'])}")
        print(f"🤖 Bot stats: {len(history['bot_stats'])} days")
        
    except Exception as e:
        print(f"❌ Error exporting history: {e}")

if __name__ == "__main__":
    print("📊 **HOST HISTORY CHECKER**")
    print("="*40)
    print("1. Check what host has recorded")
    print("2. Export host history to JSON")
    print("3. Delete old history (older than 30 days)")
    print("="*40)
    
    choice = input("Enter your choice (1-3): ").strip()
    
    if choice == "1":
        check_host_history()
    elif choice == "2":
        export_host_history()
    elif choice == "3":
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stock_events WHERE date(start_time) < date('now', '-30 days')")
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            print(f"✅ Deleted {deleted} events older than 30 days")
        except Exception as e:
            print(f"❌ Error: {e}")
    else:
        print("❌ Invalid choice")