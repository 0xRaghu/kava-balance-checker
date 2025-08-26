#!/usr/bin/env python3
"""
Kava Balance Checker
Fetches the balance of a given 0x address on any specific day from the Kava blockchain.
"""

import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
from datetime import datetime, timezone
from typing import Optional, Tuple


class KavaRPCClient:
    """RPC client for interacting with Kava blockchain archival node."""
    
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
    
    def _make_rpc_call(self, method: str, params: list) -> dict:
        """Make a JSON-RPC call to the archival node."""
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": 1
        }
        
        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self.rpc_url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            
            # Use secure SSL context with certificate verification
            ssl_context = ssl.create_default_context()
            
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as response:
                result = json.loads(response.read().decode('utf-8'))
            
            if "error" in result:
                raise Exception(f"RPC error: {result['error']}")
            
            return result["result"]
        except urllib.error.URLError as e:
            raise Exception(f"Network error: {e}")
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON response: {e}")
    
    def get_block_number(self) -> int:
        """Get the latest block number."""
        result = self._make_rpc_call("eth_blockNumber", [])
        return int(result, 16)
    
    def get_block_by_number(self, block_number: int, include_transactions: bool = False) -> dict:
        """Get block details by block number."""
        block_hex = hex(block_number)
        return self._make_rpc_call("eth_getBlockByNumber", [block_hex, include_transactions])
    
    def get_balance(self, address: str, block_number: int) -> int:
        """Get balance in wei at a specific block."""
        block_hex = hex(block_number)
        result = self._make_rpc_call("eth_getBalance", [address, block_hex])
        return int(result, 16)


class KavaBalanceChecker:
    """Main class for checking balances on specific dates."""
    
    def __init__(self, rpc_url: str, address: str):
        self.rpc_client = KavaRPCClient(rpc_url)
        self.address = address
    
    def validate_date(self, date_str: str) -> datetime:
        """Validate and parse the date string."""
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_obj = date_obj.replace(tzinfo=timezone.utc)
            
            # Check if date is not in the future
            if date_obj.date() > datetime.now(timezone.utc).date():
                raise ValueError("Date cannot be in the future")
            
            return date_obj
        except ValueError as e:
            if "time data" in str(e):
                raise ValueError("Invalid date format. Use YYYY-MM-DD format")
            raise e
    
    def date_to_timestamps(self, date_obj: datetime) -> Tuple[int, int]:
        """Convert date to start and end timestamps of the day."""
        start_of_day = int(date_obj.timestamp())
        end_of_day = start_of_day + 86399  # 23:59:59 of the same day
        return start_of_day, end_of_day
    
    def find_last_block_of_day(self, target_timestamp: int) -> Optional[int]:
        """Find the last block with timestamp <= target_timestamp using binary search."""
        latest_block = self.rpc_client.get_block_number()
        
        # Binary search for the last block with timestamp <= target_timestamp
        left, right = 0, latest_block
        result_block = None
        
        while left <= right:
            mid = (left + right) // 2
            
            try:
                block = self.rpc_client.get_block_by_number(mid)
                if block is None:
                    right = mid - 1
                    continue
                
                block_timestamp = int(block["timestamp"], 16)
                
                if block_timestamp <= target_timestamp:
                    result_block = mid
                    left = mid + 1
                else:
                    right = mid - 1
                    
            except Exception as e:
                print(f"Warning: Error accessing block {mid}: {e}")
                right = mid - 1
                continue
        
        return result_block
    
    def wei_to_kava(self, wei_amount: int) -> float:
        """Convert wei to KAVA (18 decimal places)."""
        return wei_amount / (10 ** 18)
    
    def get_balance_on_date(self, date_str: str) -> dict:
        """Get the balance of the address on the specified date."""
        # Validate date
        date_obj = self.validate_date(date_str)
        start_timestamp, end_timestamp = self.date_to_timestamps(date_obj)
        
        print(f"Finding balance for {self.address} on {date_str}")
        print(f"Looking for last block before {end_timestamp} ({datetime.fromtimestamp(end_timestamp, tz=timezone.utc)})")
        
        # Find the last block of the day
        last_block = self.find_last_block_of_day(end_timestamp)
        
        if last_block is None:
            raise Exception(f"No blocks found for date {date_str}")
        
        # Get block details for verification
        block_details = self.rpc_client.get_block_by_number(last_block)
        block_timestamp = int(block_details["timestamp"], 16)
        block_datetime = datetime.fromtimestamp(block_timestamp, tz=timezone.utc)
        
        # Get balance at that block
        balance_wei = self.rpc_client.get_balance(self.address, last_block)
        balance_kava = self.wei_to_kava(balance_wei)
        
        return {
            "date": date_str,
            "address": self.address,
            "block_number": last_block,
            "block_timestamp": block_timestamp,
            "block_datetime": block_datetime.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "balance_wei": balance_wei,
            "balance_kava": balance_kava
        }


def main():
    """Main function to run the balance checker."""
    if len(sys.argv) != 2:
        print("Usage: python kava_balance_checker.py <date>")
        print("Date format: YYYY-MM-DD (e.g., 2024-12-31)")
        sys.exit(1)
    
    # Configuration
    RPC_URL = "https://evm.data.kava.io"
    ADDRESS = "0x7D5CEA2e5fBDFecca8CcfbFe85AC021C817a7f38"
    
    date_input = sys.argv[1]
    
    try:
        checker = KavaBalanceChecker(RPC_URL, ADDRESS)
        result = checker.get_balance_on_date(date_input)
        
        print("\n" + "="*60)
        print(f"KAVA Balance Report for {result['address']}")
        print("="*60)
        print(f"Date: {result['date']}")
        print(f"Block Number: {result['block_number']:,}")
        print(f"Block Timestamp: {result['block_datetime']}")
        print(f"Balance: {result['balance_kava']:.6f} KAVA")
        print(f"Balance (wei): {result['balance_wei']:,}")
        print("="*60)
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()