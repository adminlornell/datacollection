"""
Configuration for owner enrichment.
"""
import os
from pathlib import Path

# LLM Configuration
# Supported models via OpenRouter (recommended for free tier):
# - openrouter/meta-llama/llama-3.3-70b-instruct:free
# - openrouter/google/gemini-2.0-flash-exp:free
# - openrouter/mistralai/mistral-7b-instruct:free
# Direct provider models (require API keys):
# - Gemini: gemini/gemini-2.0-flash
# - OpenAI: gpt-4o, gpt-4o-mini
# - Anthropic: claude-3-opus, claude-3-sonnet
# - Local: ollama/llama3 (requires Ollama running)
DEFAULT_LLM = os.getenv("ENRICHMENT_LLM", "openrouter/meta-llama/llama-3.3-70b-instruct:free")

# Research settings
MAX_RESEARCH_DEPTH = int(os.getenv("MAX_RESEARCH_DEPTH", "3"))
MAX_CONCURRENT_RESEARCH = int(os.getenv("MAX_CONCURRENT_RESEARCH", "2"))

# Rate limiting for external APIs
REQUEST_DELAY_SECONDS = float(os.getenv("ENRICHMENT_REQUEST_DELAY", "1.0"))

# Output directory
ENRICHMENT_OUTPUT_DIR = Path(os.getenv(
    "ENRICHMENT_OUTPUT_DIR",
    "data/enrichment"
))

# Logging
VERBOSE = os.getenv("ENRICHMENT_VERBOSE", "true").lower() == "true"

# API Keys (optional - tools work without them but may have rate limits)
# GOOGLE_API_KEY or GEMINI_API_KEY - Required for Gemini models
# OPENAI_API_KEY - Required if using OpenAI models
# ANTHROPIC_API_KEY - Required if using Anthropic models
# SERPER_API_KEY - For enhanced web search (optional)

# Tool-specific settings
MA_SOS_TIMEOUT = int(os.getenv("MA_SOS_TIMEOUT", "30"))
OPENCORPORATES_TIMEOUT = int(os.getenv("OPENCORPORATES_TIMEOUT", "30"))
SEC_EDGAR_TIMEOUT = int(os.getenv("SEC_EDGAR_TIMEOUT", "30"))
WEB_SEARCH_TIMEOUT = int(os.getenv("WEB_SEARCH_TIMEOUT", "30"))
