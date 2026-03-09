from dotenv import load_dotenv
import os

load_dotenv()

# Challenge requirement: config file with staging base URL – NO hardcoded URLs anywhere else
BASE_URL = os.getenv("BASE_URL", "https://app.staging.shipsticks.com")
# Note: We use the exact URL from the PDF (no www.). Change in .env if needed.