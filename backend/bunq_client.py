# bunq sandbox client. handshake is installation -> device-server -> session-server,
# then signed GET/POST. docs: https://doc.bunq.com/tutorials/your-first-payment

from __future__ import annotations

import base64
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import load_pem_private_key

DEFAULT_USER_AGENT = "bunq-horizon/1.0"
SANDBOX_BASE = "https://public-api.sandbox.bunq.com/v1"
PROD_BASE = "https://api.bunq.com/v1"


def _generate_or_load_keypair(key_dir: Path) -> tuple[str, str]:
    # generates the keypair on first run, reuses it after
    key_dir.mkdir(parents=True, exist_ok=True)
    priv_path = key_dir / "private_key.pem"
    pub_path = key_dir / "public_key.pem"

    if priv_path.exists() and pub_path.exists():
        return priv_path.read_text(), pub_path.read_text()

    private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048, backend=default_backend()
    )
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pub_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    priv_path.write_text(priv_pem)
    pub_path.write_text(pub_pem)
    return priv_pem, pub_pem


def _sign(data: str, private_key_pem: str) -> str:
    private_key = load_pem_private_key(
        private_key_pem.encode(), password=None, backend=default_backend()
    )
    sig = private_key.sign(data.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(sig).decode()


class BunqClient:
    def __init__(
        self,
        api_key: str,
        sandbox: bool = True,
        service_name: str = DEFAULT_USER_AGENT,
        state_dir: str | Path | None = None,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key.strip()
        self.base_url = SANDBOX_BASE if sandbox else PROD_BASE
        self.service_name = service_name
        self.state_dir = Path(state_dir or Path(__file__).parent / ".bunq_state")
        self.private_pem, self.public_pem = _generate_or_load_keypair(self.state_dir)

        self.device_token: str | None = None
        self.session_token: str | None = None
        self.user_id: int | None = None
        self._load_device_token()

    @property
    def _device_token_file(self) -> Path:
        return self.state_dir / "device_token.json"

    def _load_device_token(self) -> None:
        try:
            data = json.loads(self._device_token_file.read_text())
            self.device_token = data.get("device_token")
        except FileNotFoundError:
            pass
        except Exception:
            pass

    def _save_device_token(self) -> None:
        self._device_token_file.write_text(
            json.dumps({"device_token": self.device_token})
        )

    def _base_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": self.service_name,
            "X-Bunq-Language": "en_US",
            "X-Bunq-Region": "nl_NL",
            "X-Bunq-Geolocation": "0 0 0 0 000",
            "X-Bunq-Client-Request-Id": str(uuid.uuid4()),
        }

    def _create_installation(self) -> None:
        if self.device_token:
            return
        payload = json.dumps({"client_public_key": self.public_pem})
        r = requests.post(
            f"{self.base_url}/installation",
            headers=self._base_headers(),
            data=payload,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        self.device_token = next(
            item["Token"]["token"] for item in data["Response"] if "Token" in item
        )
        self._save_device_token()

    def _create_device_server(self) -> None:
        payload = json.dumps(
            {
                "description": self.service_name,
                "secret": self.api_key,
                "permitted_ips": ["*"],
            },
            separators=(",", ":"),
        )
        headers = self._base_headers()
        headers["X-Bunq-Client-Authentication"] = self.device_token
        headers["X-Bunq-Client-Signature"] = _sign(payload, self.private_pem)
        r = requests.post(
            f"{self.base_url}/device-server",
            headers=headers,
            data=payload,
            timeout=20,
        )
        # 400 is fine if the device is already registered for this key
        if r.status_code >= 400 and "already" not in r.text.lower():
            r.raise_for_status()

    def _create_session(self) -> None:
        payload = json.dumps({"secret": self.api_key}, separators=(",", ":"))
        headers = self._base_headers()
        headers["X-Bunq-Client-Authentication"] = self.device_token
        headers["X-Bunq-Client-Signature"] = _sign(payload, self.private_pem)
        r = requests.post(
            f"{self.base_url}/session-server",
            headers=headers,
            data=payload,
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        self.session_token = next(
            item["Token"]["token"] for item in data["Response"] if "Token" in item
        )
        for item in data["Response"]:
            for key in ("UserPerson", "UserCompany", "UserPaymentServiceProvider"):
                if key in item:
                    self.user_id = item[key]["id"]
                    return

    def authenticate(self) -> "BunqClient":
        # full handshake. session is recreated every call, device-server only on first run
        self._create_installation()
        try:
            self._create_device_server()
        except Exception:
            # device-server fails if already registered for this key, that's fine
            pass
        self._create_session()
        return self

    def _ensure_session(self) -> None:
        if not self.session_token or not self.user_id:
            self.authenticate()

    def get(self, path: str) -> dict[str, Any]:
        self._ensure_session()
        headers = self._base_headers()
        headers["X-Bunq-Client-Authentication"] = self.session_token
        # some endpoints want a signature even on empty bodies
        headers["X-Bunq-Client-Signature"] = _sign("", self.private_pem)
        r = requests.get(f"{self.base_url}/{path}", headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self._ensure_session()
        payload = json.dumps(body, separators=(",", ":"))
        headers = self._base_headers()
        headers["X-Bunq-Client-Authentication"] = self.session_token
        headers["X-Bunq-Client-Signature"] = _sign(payload, self.private_pem)
        r = requests.post(
            f"{self.base_url}/{path}", headers=headers, data=payload, timeout=20
        )
        r.raise_for_status()
        return r.json()

    def get_primary_account_id(self) -> int:
        self._ensure_session()
        data = self.get(f"user/{self.user_id}/monetary-account")
        for item in data.get("Response", []):
            for key in ("MonetaryAccountBank", "MonetaryAccountSavings"):
                if key in item and item[key].get("status") == "ACTIVE":
                    return item[key]["id"]
        # nothing active? grab whatever shows up first
        for item in data.get("Response", []):
            for v in item.values():
                if isinstance(v, dict) and "id" in v:
                    return v["id"]
        raise RuntimeError("No monetary account found")

    def get_balance(self, account_id: int) -> float | None:
        try:
            data = self.get(f"user/{self.user_id}/monetary-account/{account_id}")
            for item in data.get("Response", []):
                for v in item.values():
                    if isinstance(v, dict) and "balance" in v:
                        return float(v["balance"]["value"])
        except Exception as e:
            print(f"[bunq] get_balance failed: {e}")
        return None

    def list_payments(self, account_id: int, limit: int = 50) -> list[dict[str, Any]]:
        try:
            data = self.get(
                f"user/{self.user_id}/monetary-account/{account_id}/payment?count={limit}"
            )
            out: list[dict[str, Any]] = []
            for item in data.get("Response", []):
                p = item.get("Payment")
                if not p:
                    continue
                out.append(
                    {
                        "id": p.get("id"),
                        "amount": float(p["amount"]["value"]),
                        "currency": p["amount"]["currency"],
                        "description": p.get("description", ""),
                        "created": p.get("created"),
                        "counterparty": (
                            p.get("counterparty_alias", {}).get("display_name")
                            or ""
                        ),
                    }
                )
            return out
        except Exception as e:
            print(f"[bunq] list_payments failed: {e}")
            return []
