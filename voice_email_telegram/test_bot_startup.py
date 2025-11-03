#!/usr/bin/env python3
"""
Test script to verify Telegram bot listener starts without errors
"""
import sys
import subprocess
import time
import signal

def test_bot_startup():
    """Test that the bot starts cleanly and connects to Telegram"""
    print("=" * 80)
    print("TELEGRAM BOT STARTUP TEST")
    print("=" * 80)

    # Start the bot
    print("\n1. Starting telegram_bot_listener.py...")
    process = subprocess.Popen(
        [sys.executable, "telegram_bot_listener.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # Collect output for 10 seconds
    print("2. Collecting output for 10 seconds...")
    output_lines = []
    start_time = time.time()

    try:
        while time.time() - start_time < 10:
            line = process.stdout.readline()
            if line:
                output_lines.append(line.strip())
                print(f"   {line.strip()}")
            time.time() < 10 and time.sleep(0.1)
    except Exception as e:
        print(f"Error reading output: {e}")

    # Terminate the bot
    print("\n3. Terminating bot...")
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

    # Analyze output
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    output_text = "\n".join(output_lines)

    # Check for critical errors
    issues = []
    successes = []

    if "Error importing tool module" in output_text:
        issues.append("❌ Tool import errors detected")
    else:
        successes.append("✅ No tool import errors")

    if "BOT LISTENER STARTED" in output_text:
        successes.append("✅ Bot listener started successfully")
    else:
        issues.append("❌ Bot listener did not start")

    if "409 Client Error: Conflict" in output_text:
        issues.append("❌ Telegram API conflict (webhook or duplicate process)")
    else:
        successes.append("✅ No Telegram API conflicts")

    if "Waiting for messages" in output_text:
        successes.append("✅ Bot entered polling loop")
    else:
        issues.append("❌ Bot did not enter polling loop")

    # Print results
    print("\nSuccesses:")
    for success in successes:
        print(f"  {success}")

    if issues:
        print("\nIssues:")
        for issue in issues:
            print(f"  {issue}")

    # Final verdict
    print("\n" + "=" * 80)
    if not issues:
        print("✅ TEST PASSED: Bot is ready to accept Telegram messages")
    else:
        print(f"❌ TEST FAILED: {len(issues)} issue(s) found")
    print("=" * 80)

    return len(issues) == 0

if __name__ == "__main__":
    success = test_bot_startup()
    sys.exit(0 if success else 1)
