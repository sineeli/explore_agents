"""Configuration for the Azure AI Foundry Product Hierarchy Agent."""

import os
from dotenv import load_dotenv

load_dotenv()

# Azure OpenAI
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-5.2")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

# Realm metadata API — the environment-specific backend
# All hierarchy/member/measure definitions are fetched from here at startup
REALM_API_BASE_URL = os.getenv("REALM_API_BASE_URL", "http://localhost:8000/api/v1")

# Data API — where actual measure data is queried from
DATA_API_BASE_URL = os.getenv("DATA_API_BASE_URL", "http://localhost:8000/api/v1")
