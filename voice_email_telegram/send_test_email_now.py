#!/usr/bin/env python3
"""
Quick test: Send a real email right now via the agency
"""

from agency import agency

print("=" * 80)
print("SENDING REAL EMAIL VIA AGENCY")
print("=" * 80)

# Test message simulating what a user would say
test_request = """
I need to send an email to ashley@mtlcraftcocktails.com about ordering
cocktail supplies for next week. Tell her we need:
- 12 bottles premium vodka
- 6 bottles artisan gin
- Fresh herbs for garnishes
- Organic simple syrup

Delivery by Friday please. Keep it professional but friendly.
Sign from info@mtlcraftcocktails.com.

Please draft and SEND this email (not just a draft - actually send it).
"""

print("\nRequest:")
print(test_request)
print("\n" + "=" * 80)
print("Processing through agency...")
print("=" * 80 + "\n")

response = agency.get_completion(test_request)

print("\n" + "=" * 80)
print("AGENCY RESPONSE:")
print("=" * 80)
print(response)
print("\n" + "=" * 80)
