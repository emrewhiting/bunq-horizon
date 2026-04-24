import os, time
from dotenv import load_dotenv
from bunq_client import BunqClient

load_dotenv()
api_key = os.getenv("BUNQ_API_KEY", "").strip()
client = BunqClient(api_key=api_key, sandbox=True)
client.authenticate()
account_id = client.get_primary_account_id()

# Request more funds
client.post(
    f"user/{client.user_id}/monetary-account/{account_id}/request-inquiry",
    {
        "amount_inquired": {"value": "500", "currency": "EUR"},
        "counterparty_alias": {"type": "EMAIL", "value": "sugardaddy@bunq.com", "name": "Sugar Daddy"},
        "description": "Top up",
        "allow_bunqme": False,
    },
)
print("Requested €500 from Sugar Daddy, waiting...")
time.sleep(3)

# Retry failed transactions
for amount, description in [("38.00", "NS train monthly"), ("45.00", "Uber rides"), ("29.99", "Netflix + Spotify"), ("42.00", "Cinema + drinks")]:
    client.post(
        f"user/{client.user_id}/monetary-account/{account_id}/payment",
        {"amount": {"value": amount, "currency": "EUR"}, "counterparty_alias": {"type": "EMAIL", "value": "sugardaddy@bunq.com", "name": "Sugar Daddy"}, "description": description},
    )
    print(f"  Sent €{amount} — {description}")
    time.sleep(0.8)

print("Done!")
