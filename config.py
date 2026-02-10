"""Configuration for the Azure AI Foundry Product Hierarchy Agent."""

import os
from dotenv import load_dotenv

load_dotenv()

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.2")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

# Data API base URL (your backend that serves hierarchy/measure data)
DATA_API_BASE_URL = os.getenv("DATA_API_BASE_URL", "http://localhost:8000/api/v1")
