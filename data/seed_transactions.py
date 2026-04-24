import os
import time
from dotenv import load_dotenv
from bunq_client import BunqClient

load_dotenv()

api_key = os.getenv("BUNQ_API_KEY", "").strip()
client = BunqClient(api_key=api_key, sandbox=True)
client.authenticate()
account_id = client.get_primary_account_id()

print(f"Authenticated — user {client.user_id}, account {account_id}\n")

# Simulated spending history (category: [amounts])
transactions = [
    # Clothing - avg should be ~120
    ("85.00",  "Sugar Daddy", "Zara jacket"),
    ("140.00", "Sugar Daddy", "Nike sneakers"),
    ("135.00", "Sugar Daddy", "H&M coat"),

    # Food - avg should be ~25
    ("22.50", "Sugar Daddy", "Albert Heijn groceries"),
    ("28.00", "Sugar Daddy", "Jumbo groceries"),
    ("19.50", "Sugar Daddy", "Lunch cafe"),
    ("31.00", "Sugar Daddy", "Takeaway dinner"),

    # Transport - avg ~40
    ("38.00", "Sugar Daddy", "NS train monthly"),
    ("45.00", "Sugar Daddy", "Uber rides"),

    # Entertainment - avg ~35
    ("29.99", "Sugar Daddy", "Netflix + Spotify"),
    ("42.00", "Sugar Daddy", "Cinema + drinks"),
]

for amount, counterparty, description in transactions:
    try:
        client.post(
            f"user/{client.user_id}/monetary-account/{account_id}/payment",
            {
                "amount": {"value": amount, "currency": "EUR"},
                "counterparty_alias": {
                    "type": "EMAIL",
                    "value": "sugardaddy@bunq.com",
                    "name": counterparty,
                },
                "description": description,
            },
        )
        print(f"  Sent €{amount} — {description}")
        time.sleep(0.8)  # stay under rate limit
    except Exception as e:
        print(f"  Failed: {description} — {e}")

print("\nDone! Run 06_list_transactions.py to verify.")
