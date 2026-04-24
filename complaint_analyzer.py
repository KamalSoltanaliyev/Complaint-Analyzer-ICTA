import os
import json
import time
from typing import List, Dict, Optional
from datetime import datetime
import openai
import pandas as pd
import concurrent.futures
from config import OPENAI_API_KEY, MODEL, DELAY_BETWEEN_CALLS, OUTPUT_DIR, BATCH_SIZE, DEFAULT_PROVIDERS


class ComplaintKPIAnalyzer:
    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.model = model or MODEL

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set. Put it into .env or pass api_key")

        try:
            self.client = openai.OpenAI(api_key=self.api_key)
        except Exception:
            openai.api_key = self.api_key
            self.client = openai

        os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ------------------------------ KPI LOOKUP BUILDER --------------------------
    def build_kpi_lookup(self, kpi_list: List[Dict]) -> Dict[str, Dict]:
        """
        Build a lookup dictionary mapping KPI IDs to full KPI objects.
        
        Args:
            kpi_list: List of KPI dictionaries from Excel
            
        Returns:
            Dictionary with {kpi_id: {'kpi_id', 'kpi_name', 'description'}}
        """
        lookup = {}
        for kpi in kpi_list:
            # Handle different possible ID column names
            kpi_id = str(kpi.get("ID") or kpi.get("id") or kpi.get("KPI_ID") or "").strip()
            if kpi_id:
                # Get English name (preferred), fall back to Azerbaijani
                kpi_name = kpi.get("Göstərici (eng)") or kpi.get("Göstərici") or kpi.get("name") or kpi.get("KPI_NAME") or ""
                description = kpi.get("Göstəricinin izahı") or kpi.get("description") or kpi.get("desc") or ""
                
                lookup[kpi_id] = {
                    "kpi_id": kpi_id,
                    "kpi_name": str(kpi_name).strip(),
                    "description": str(description).strip()
                }
        return lookup

    # ------------------------------ TABLE LOADER ------------------------------
    def load_table(self, path: str) -> pd.DataFrame:
        ext = path.lower()

        # CSV
        if ext.endswith(".csv"):
            return pd.read_csv(path, dtype=str)

        # XLS / XLSX
        if ext.endswith(".xlsx") or ext.endswith(".xls"):
            return pd.read_excel(path, dtype=str)

        # ODS (robust handling) - prefer pandas engine first
        if ext.endswith(".ods"):
            try:
                return pd.read_excel(path, dtype=str, engine="odf")
            except Exception:
                print("pandas odf engine failed, trying ezodf fallback")
                try:
                    import ezodf
                    doc = ezodf.opendoc(path)
                    sheet = doc.sheets[0]

                    data = []
                    for row in sheet.rows():
                        values = [cell.value if cell.value is not None else "" for cell in row]
                        data.append(values)

                    df = pd.DataFrame(data)
                    if not df.empty:
                        df.columns = df.iloc[0]
                        df = df[1:]
                        # ensure all columns are strings
                        df.columns = df.columns.astype(str).str.strip()
                        return df.astype(str)
                    return pd.DataFrame()
                except Exception:
                    print("Cannot read ODS file. Convert to XLSX.")
                    return pd.DataFrame()

        print("Unsupported file format:", path)
        return pd.DataFrame()

    # -------------------------------------------------------------------------

    def _build_kpi_str(self, kpi_list: List[Dict]) -> str:
        """Build formatted KPI list for prompt with ID, English name, Azerbaijani name, and description."""
        lines = []
        for k in kpi_list:
            kid = str(k.get("ID") or k.get("id") or k.get("KPI_ID") or "").strip()
            # Get English name (preferred), then Azerbaijani, then fallback
            eng_name = k.get("Göstərici (eng)") or k.get("name") or ""
            az_name = k.get("Göstərici") or ""
            desc = k.get("Göstəricinin izahı") or k.get("description") or k.get("desc") or ""
            
            # Format: ID: English name (Azerbaijani name) — description
            if eng_name and az_name:
                line = f"{kid}: {eng_name} ({az_name}) — {desc}"
            elif eng_name:
                line = f"{kid}: {eng_name} — {desc}"
            elif az_name:
                line = f"{kid}: {az_name} — {desc}"
            else:
                line = f"{kid}: {desc}"
            
            if kid:  # Only add if we have an ID
                lines.append(line)
        return "\n".join(lines)

    def create_prompt(self, complaints_batch: List[Dict], kpi_list: List[Dict], providers: List[str]) -> str:
        kpi_str = self._build_kpi_str(kpi_list)
        complaints_text = "\n".join([f"{c['complaint_id']}: {c['description']}" for c in complaints_batch])

        prompt = f"""
You are a telecom complaint classifier.

---KPI LIST---
{kpi_str}
---END KPI LIST---

---COMPLAINTS---
{complaints_text}
---END COMPLAINTS---

Task:
For each complaint, select the most relevant KPI IDs from the KPI LIST.

Rules:
- Use ONLY KPI IDs from the provided list
- DO NOT generate KPI names or descriptions
- Match based on meaning (e.g., latency, jitter, packet loss, speed, interruptions)
- If no KPI matches, return an empty list

Output JSON format:
[
  {{
    "id": "<complaint_id>",
    "operator": null,
    "kpis": [
      {{"kpi_id": "5", "confidence": 0.85}}
    ]
  }}
]
"""
        return prompt


    def _extract_json_block(self, text: str) -> str:
        t = text.strip()
        if t.startswith("```"):
            t = t.strip("` \n")
            if t.lower().startswith("json"):
                t = t[len("json"):].strip()
        return t

    def analyze_batch(self, complaints_batch: List[Dict], kpi_list: List[Dict], providers: List[str]) -> List[Dict]:
        import random
        start_time = time.time()
        prompt = self.create_prompt(complaints_batch, kpi_list, providers)
        
        # Build KPI lookup for validation and mapping
        kpi_lookup = self.build_kpi_lookup(kpi_list)

        # create a local client per call to be safe for multithreading
        try:
            client = openai.OpenAI(api_key=self.api_key)
        except Exception:
            openai.api_key = self.api_key
            client = openai

        # small jitter to spread concurrent requests
        try:
            time.sleep(random.uniform(0, 0.2))
        except Exception:
            pass

        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an analyst. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=2000
            )
            content = resp.choices[0].message.content.strip()
            elapsed = time.time() - start_time
            print(f"DEBUG: raw ChatGPT response (first 300 chars): {content[:300]}\n  (elapsed {elapsed:.2f}s)")
        except Exception as e:
            print("⚠ API error:", e)
            return [{"complaint_id": c['complaint_id'], "subject_of_the_complaint": c['description'],
                     "operator": None, "kpis": [], "status": "API_ERROR"} for c in complaints_batch]

        parsed = []
        try:
            block = self._extract_json_block(content)
            if block and block != "[]":
                try:
                    parsed = json.loads(block)
                except Exception:
                    start = content.find("[")
                    end = content.rfind("]")
                    if start != -1 and end != -1 and end > start:
                        snippet = content[start:end + 1]
                        parsed = json.loads(snippet)

            if isinstance(parsed, dict):
                parsed = [parsed]

        except Exception:
            parsed = []

        results = []
        for i, c in enumerate(complaints_batch):
            if i < len(parsed):
                raw = parsed[i]
                operator = raw.get('operator') if isinstance(raw, dict) else None

                # Process KPIs: map KPI IDs to actual KPI data from lookup
                kpis_out = []
                raw_kpis = raw.get('kpis') if isinstance(raw, dict) else None
                
                if isinstance(raw_kpis, list):
                    for kp in raw_kpis:
                        if isinstance(kp, dict):
                            # Extract KPI ID from response
                            kpi_id = str(kp.get('kpi_id') or "").strip()
                            confidence = kp.get('confidence', 0.0)
                            
                            # Validate confidence is a number
                            try:
                                confidence = float(confidence)
                                # Clamp confidence to 0.0-1.0 range
                                confidence = max(0.0, min(1.0, confidence))
                            except (TypeError, ValueError):
                                confidence = 0.0
                            
                            # Validate KPI ID exists in lookup (only include valid KPIs)
                            if kpi_id and kpi_id in kpi_lookup:
                                # Use pre-built KPI data from lookup
                                kpi_data = kpi_lookup[kpi_id]
                                kpis_out.append({
                                    'kpi_id': kpi_data['kpi_id'],
                                    'kpi_name': kpi_data['kpi_name'],
                                    'description': kpi_data['description'],
                                    'confidence': confidence
                                })
                            elif kpi_id:
                                # Invalid KPI ID returned by model - log warning and ignore
                                print(f"⚠ WARNING: Invalid/non-existent KPI ID '{kpi_id}' returned by model for complaint {c['complaint_id']} - ignoring")
                
                new_entry = {
                    'complaint_id': c['complaint_id'],
                    'operator': operator if operator is not None else None,
                    'kpis': kpis_out,
                    'subject_of_the_complaint': c['description'],
                    'status': 'OK'
                }
                results.append(new_entry)
            else:
                results.append({
                    'complaint_id': c['complaint_id'],
                    'subject_of_the_complaint': c['description'],
                    'operator': None,
                    'kpis': [],
                    'status': 'EMPTY_RESPONSE'
                })

        return results


    # -------------------------------------------------------------------------

    def process_complaints_file(
        self,
        complaints_file: str,
        kpi_file: str,
        descriptions_file: Optional[str] = None,
        providers_file: Optional[str] = None,
        complaint_id_col: str = "complaint_id",
        complaint_text_col: str = "description",
        delay_seconds: float = DELAY_BETWEEN_CALLS,
        batch_size: int = BATCH_SIZE,
        parallel: bool = False,
        max_workers: int = 4
    ) -> List[Dict]:

        complaints_df = self.load_table(complaints_file)
        kpi_df = self.load_table(kpi_file)

        # Normalize column names to help matching
        if not complaints_df.empty:
            complaints_df.columns = complaints_df.columns.astype(str).str.strip()
        if not kpi_df.empty:
            kpi_df.columns = kpi_df.columns.astype(str).str.strip()

        kpi_list = kpi_df.to_dict(orient="records")

        # Debug: print columns and first rows to help diagnose empty fields
        try:
            print("Debug - complaints_df columns:", list(complaints_df.columns))
            print("Debug - complaints_df first 3 rows:")
            print(complaints_df.head(3).to_dict(orient="records"))
        except Exception:
            pass

        # Auto-detect complaint text / id columns if the provided names are not present
        # (case-insensitive alternatives)
        available_cols = [c.lower() for c in complaints_df.columns]
        def find_col(preferred: str, alternatives: List[str]):
            if preferred and preferred in complaints_df.columns:
                return preferred
            pref_l = (preferred or "").lower()
            if pref_l in available_cols:
                return complaints_df.columns[available_cols.index(pref_l)]
            for alt in alternatives:
                if alt.lower() in available_cols:
                    return complaints_df.columns[available_cols.index(alt.lower())]
            return None

        # common names
        text_alts = ["description", "complaint_text", "text", "subject", "body", "mövzu", "mətn"]
        id_alts = ["complaint_id", "id", "row_id", "index"]

        detected_text_col = find_col(complaint_text_col, text_alts)
        detected_id_col = find_col(complaint_id_col, id_alts)

        if detected_text_col is None:
            print(f"Warning: complaint_text_col '{complaint_text_col}' not found. Candidates: {available_cols}")
        else:
            complaint_text_col = detected_text_col

        if detected_id_col is None:
            # keep using row_{idx}
            pass
        else:
            complaint_id_col = detected_id_col

        if providers_file:
            prov_df = self.load_table(providers_file)
            providers = prov_df.iloc[:, 0].dropna().astype(str).tolist()
        else:
            providers = DEFAULT_PROVIDERS

        complaints = []
        for idx, row in complaints_df.iterrows():
            # robustly extract id and text, handle NaN
            if complaint_id_col in complaints_df.columns:
                raw_id = row.get(complaint_id_col)
            else:
                raw_id = None
            if raw_id is None or (isinstance(raw_id, float) and pd.isna(raw_id)):
                cid = f"row_{idx}"
            else:
                cid = str(raw_id).strip()

            if complaint_text_col in complaints_df.columns:
                raw_text = row.get(complaint_text_col)
            else:
                raw_text = None
            if raw_text is None or (isinstance(raw_text, float) and pd.isna(raw_text)):
                text = ""
            else:
                text = str(raw_text).strip()

            complaints.append({
                "complaint_id": cid,
                "description": text
            })

        print("Debug - first 5 complaints:", complaints[:5])

        results = []
        total = len(complaints)
        print(f"Processing {total} complaints in batches of {batch_size}... (parallel={parallel})")

        # prepare batches
        batches = [complaints[i:i + batch_size] for i in range(0, total, batch_size)]

        if parallel and len(batches) > 1:
            # run batches in parallel (preserves order)
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                mapped = list(ex.map(self.analyze_batch, batches, [kpi_list] * len(batches), [providers] * len(batches)))
                for batch_results in mapped:
                    results.extend(batch_results)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    json_path = os.path.join(OUTPUT_DIR, f"analysis_partial_{timestamp}.json")
                    pd.DataFrame(results).to_csv(os.path.join(OUTPUT_DIR, f"analysis_partial_{timestamp}.csv"), index=False)
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                    print(f"-- Saved partial results: {json_path}")
            # no sleeping when parallel
        else:
            for batch in batches:
                batch_results = self.analyze_batch(batch, kpi_list, providers)
                results.extend(batch_results)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                json_path = os.path.join(OUTPUT_DIR, f"analysis_partial_{timestamp}.json")
                pd.DataFrame(results).to_csv(os.path.join(OUTPUT_DIR, f"analysis_partial_{timestamp}.csv"), index=False)
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)
                print(f"-- Saved partial results: {json_path}")
                time.sleep(delay_seconds)

        return results

if __name__ == "__main__":
    # Allow running this module directly for quick checks (mirrors run_analysis.py)
    from config import COMPLAINTS_FILE, KPI_FILE, DESCRIPTIONS_FILE, PROVIDERS_FILE, COMPLAINT_ID_COLUMN, COMPLAINT_TEXT_COLUMN
    print("Running complaint_analyzer.py as script — will process files from config.py")
    analyzer = ComplaintKPIAnalyzer()
    # basic existence checks
    for f in [COMPLAINTS_FILE, KPI_FILE]:
        if not os.path.exists(f):
            print(f"ERROR: File not found: {f}")
            raise SystemExit(1)

    results = analyzer.process_complaints_file(
        complaints_file=COMPLAINTS_FILE,
        kpi_file=KPI_FILE,
        descriptions_file=DESCRIPTIONS_FILE if DESCRIPTIONS_FILE else None,
        providers_file=PROVIDERS_FILE,
        complaint_id_col=COMPLAINT_ID_COLUMN,
        complaint_text_col=COMPLAINT_TEXT_COLUMN,
    )

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = os.path.join(OUTPUT_DIR, f"complaint_kpi_analysis_{ts}.csv")
    out_json = os.path.join(OUTPUT_DIR, f"complaint_kpi_analysis_{ts}.json")

    pd.DataFrame(results).to_csv(out_csv, index=False)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Done. Final results saved to {out_csv} and {out_json}")
    
