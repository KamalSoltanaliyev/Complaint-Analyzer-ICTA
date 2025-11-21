# config.py
# Configuration file for Complaint Analysis
# config.py
# Configuration file for Complaint Analysis

import os
from dotenv import load_dotenv

# Load environment variables from .env (if present)
load_dotenv()

# OpenAI API Configuration (set in .env or system env)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("MODEL", "gpt-4o-mini")

# File paths (update to match your filenames)
COMPLAINTS_FILE = os.getenv("COMPLAINTS_FILE", "Şikayətlər_v1 (1).ods")
KPI_FILE = os.getenv("KPI_FILE", "data (2).xlsx")
DESCRIPTIONS_FILE = os.getenv("DESCRIPTIONS_FILE", "Keyfiyyət göstəricilərinin izahı və ölçmə metodologiyası.xlsx")
PROVIDERS_FILE = os.getenv("PROVIDERS_FILE", None)  # optional providers CSV/XLSX (first column = provider names)

# Column names in your complaints file (override via .env if necessary)
COMPLAINT_ID_COLUMN = os.getenv("COMPLAINT_ID_COLUMN", "complaint_id")
COMPLAINT_TEXT_COLUMN = os.getenv("COMPLAINT_TEXT_COLUMN", "description")

# API & runtime settings
DELAY_BETWEEN_CALLS = float(os.getenv("DELAY_BETWEEN_CALLS", "1.0"))   # seconds (pause between batch requests)
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "20"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "outputs")

# Default Azerbaijan ISP Providers (update as needed)
DEFAULT_PROVIDERS = [
    "Azercell",
    "Bakcell",
    "Nar",
    "Delta Telecom",
    "AzTelecom",
    "Ultel",
    "Naxtel",
    "AzerOnline",
    "Azintelecom"
]

# Helpful defaults (do not modify unless needed)
os.makedirs(OUTPUT_DIR, exist_ok=True)

TELECOM_KPIS = [
    "Connection Speed/Bandwidth",
    "Network Availability/Uptime",
    "Connection Reliability",
    "Customer Service Response Time",
    "Installation Time",
    "Signal Quality",
    "Data Usage Accuracy",
    "Billing Accuracy",
    "Service Coverage",
    "Technical Support Quality",
    "Equipment Functionality",
    "Service Interruptions",
    "Coverage Quality",
    "Internet Speed Consistency"
]
