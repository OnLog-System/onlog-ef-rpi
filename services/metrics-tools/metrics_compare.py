#!/usr/bin/env python3
import os, argparse, sqlite3, requests, json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Load env
load_dotenv()
API_URL = os.getenv("CHIRPSTACK_API_URL")
API_KEY = os.getenv("CHIRPSTACK_API_KEY")
GATEWAY_ID = os.getenv("GATEWAY_ID")
APPLICATION_ID = os.getenv("APPLICATION_ID")
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH")

headers = {"Grpc-Metadata-Authorization": f"Bearer {API_KEY}"}

