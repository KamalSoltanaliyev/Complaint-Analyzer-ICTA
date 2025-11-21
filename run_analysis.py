# run_analysis.py
import os
import json
from datetime import datetime
import pandas as pd

from config import OPENAI_API_KEY, COMPLAINTS_FILE, KPI_FILE, DESCRIPTIONS_FILE, PROVIDERS_FILE, OUTPUT_DIR, COMPLAINT_ID_COLUMN, COMPLAINT_TEXT_COLUMN
from complaint_analyzer import ComplaintKPIAnalyzer


# use python_dotenv for hiding and not pushing sensitive info in code
# use concurrent tasks for speeding up if needed
def main():
    if not OPENAI_API_KEY or OPENAI_API_KEY == "your-api-key-here":
        print("ERROR: Please set OPENAI_API_KEY in config.py")
        return

    analyzer = ComplaintKPIAnalyzer(api_key=OPENAI_API_KEY)

    for f in [COMPLAINTS_FILE, KPI_FILE]:
        if not os.path.exists(f):
            print(f"ERROR: File not found: {f}")
            return

    results = analyzer.process_complaints_file(
        complaints_file=COMPLAINTS_FILE,
        kpi_file=KPI_FILE,
        descriptions_file=DESCRIPTIONS_FILE if DESCRIPTIONS_FILE else None,
        providers_file=PROVIDERS_FILE,
        complaint_id_col=COMPLAINT_ID_COLUMN,
        complaint_text_col=COMPLAINT_TEXT_COLUMN
        ,
        parallel=True,
        max_workers=4
    )

    # final save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = os.path.join(OUTPUT_DIR, f"complaint_kpi_analysis_{ts}.csv")
    out_json = os.path.join(OUTPUT_DIR, f"complaint_kpi_analysis_{ts}.json")

    pd.DataFrame(results).to_csv(out_csv, index=False)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Final results saved to {out_csv} and {out_json}")

if __name__ == "__main__":
    main()
