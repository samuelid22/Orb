"""Paxos test USDG ABI helpers. No signing keys, floats, or network calls."""

import re

from eth_utils import is_address, keccak, to_checksum_address

USDG_CONTRACT = "0xFFC95faa3d63Cde504a05B567C600B78C0b41892"
USDG_DECIMALS = 6
USDG_PRICE = 100_000
TRANSFER_TOPIC = "0x" + keccak(text="Transfer(address,address,uint256)").hex()
TRANSFER_SELECTOR = "a9059cbb"
WORD = re.compile(r"^0x[0-9a-fA-F]{64}$")


def transfer_data(receiver: str, amount: int) -> str:
    if not is_address(receiver) or not 0 < amount < 2**256:
        raise ValueError("Invalid USDG transfer.")
    return "0x" + TRANSFER_SELECTOR + receiver[2:].lower().rjust(64, "0") + f"{amount:064x}"


def matching_transfer(receipt: dict, wallet: str, receiver: str, amount: int) -> bool:
    """Require one exact, well-formed Transfer from the configured token."""
    logs = receipt.get("logs")
    if not isinstance(logs, list):
        return False
    matches = 0
    for log in logs:
        if not isinstance(log, dict):
            return False
        if not isinstance(log.get("address"), str):
            return False
        if log["address"].lower() != USDG_CONTRACT.lower():
            continue
        topics = log.get("topics")
        if not isinstance(topics, list) or not topics or not isinstance(topics[0], str):
            return False
        if topics[0].lower() != TRANSFER_TOPIC:
            continue
        if (len(topics) != 3 or not all(isinstance(t, str) and WORD.fullmatch(t) for t in topics)
                or not isinstance(log.get("data"), str) or not WORD.fullmatch(log["data"])
                or topics[1][2:26] != "0" * 24 or topics[2][2:26] != "0" * 24
                or log.get("removed", False) is not False
                or log.get("transactionHash", "").lower() != receipt["transactionHash"].lower()
                or log.get("blockHash") != receipt["blockHash"]):
            return False
        if (topics[1][-40:].lower() == wallet[2:].lower()
                and topics[2][-40:].lower() == receiver[2:].lower()
                and int(log["data"], 16) == amount):
            matches += 1
    return matches == 1


def usdg_payment_config(config) -> dict:
    return {"payment_method": "usdg", "token_symbol": "USDG",
            "token_contract": to_checksum_address(config.usdg_contract),
            "token_decimals": USDG_DECIMALS, "price_base_units": str(config.usdg_price),
            "deployment_target": config.deployment_target}
