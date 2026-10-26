"""One-Command Launcher for Intake AI Document IDP & Clinician Terminal."""

import sys
import threading
import time
import webbrowser
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn


def open_browser(port: int = 8001):
    time.sleep(1.2)
    url = f"http://127.0.0.1:{port}"
    print(f"\n[INTAKE AI] Launching Clinician Review Terminal at: {url}\n")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Notice: Open {url} manually in your browser ({e})")


def main():
    port = 8001
    print("=" * 72)
    print("  INTAKE AI // Production Document IDP & Conformal Triage Terminal")
    print("  CMS 10-Digit NPI Luhn + ICD-10 Taxonomy + HL7 FHIR R4 Bundle Export")
    print("=" * 72)

    # Launch browser on separate thread
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    # Run uvicorn server bound to localhost
    uvicorn.run("web.server:app", host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
