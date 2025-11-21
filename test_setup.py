# test_setup.py
def test_setup():
    print("Testing environment and configuration...")
    try:
        import openai, pandas
        print(" - Packages: OK")
    except ImportError as e:
        print(f" - Missing package: {e}")
        return False

    try:
        from config import OPENAI_API_KEY, COMPLAINTS_FILE, KPI_FILE
        print(" - config.py loaded")
    except Exception as e:
        print(f" - config.py error: {e}")
        return False

    if OPENAI_API_KEY == "your-api-key-here" or not OPENAI_API_KEY:
        print(" - WARNING: OPENAI_API_KEY not configured in config.py")
        return False

    import os
    if not os.path.exists(COMPLAINTS_FILE):
        print(f" - Complaints file not found: {COMPLAINTS_FILE}")
        return False
    if not os.path.exists(KPI_FILE):
        print(f" - KPI file not found: {KPI_FILE}")
        return False

    print("Setup looks good. You can run run_analysis.py")
    return True

if __name__ == "__main__":
    test_setup()
