import os
from dotenv import load_dotenv
load_dotenv()

import requests
import websockets
import asyncio
from .file_manager import append_rule_to_file, remove_rule_from_file


SERVER_URL = os.getenv("SERVER_URL")
WS_URL = os.getenv("WS_URL")

# CLI command - remember
def send_memory(text: str):
    print("Evaluating rule...")
    try:
        response = requests.post(f"{SERVER_URL}/remember", json={"text": text})
        response.raise_for_status()
        data = response.json()
        
        if data.get("type") == "conflict":
            print(f"\nCONFLICT DETECTED: {data.get('explanation')}")
            print("\nConflicting Existing Rules:")
            for rule in data.get("conflicting_rules", []):
                print(f"  - {rule}")
            print("\nPlease use forget command to remove the old rule before inserting this one.\n")
            
        elif data.get("type") == "error":
            print(f"\nError: {data.get('status')}\n")
            
        else:
            print(f"\nSuccess: {data.get('status')}\n")
            
    except Exception as e:
        print(f"\nError connecting to server: {e}\n")

# CLI command - sync
async def listen_for_updates():
    print(f"Connecting to live memory stream at {WS_URL}...")
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("Connected. Listening for peer updates... (Press CTRL+C to quit)")
            while True:
                message = await websocket.recv()
                if message.startswith("NEW_RULE:"):
                    rule = message.split("NEW_RULE:", 1)[1]
                    append_rule_to_file(rule)
                    print(f"\nSynced new rule: {rule}")
                    
                elif message.startswith("DELETE_RULE:"):
                    rule = message.split("DELETE_RULE:", 1)[1]
                    remove_rule_from_file(rule)
                    print(f"\nRemoved revoked rule: {rule}")
                    
    except websockets.exceptions.ConnectionClosed:
        print("Connection to server lost.")
    except Exception as e:
        print(f"WebSocket error: {e}")

# CLI command - ask
def ask_question(question: str) -> str:
    print("Searching project memory...")
    try:
        response = requests.post(f"{SERVER_URL}/ask", json={"question": question})
        response.raise_for_status()
        return response.json()["answer"]
    except Exception as e:
        return f"Error connecting to server: {e}"

# CLI command - forget
def forget_rule(content: str):
    print("Executing deletion...")
    try:
        response = requests.post(f"{SERVER_URL}/forget", json={"content": content})
        response.raise_for_status()
        print(f"\n{response.json()['status']}\n")
    except Exception as e:
        print(f"\nError connecting to server: {e}\n")