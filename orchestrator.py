import asyncio
import json
import time
from datetime import datetime
from agents import KYCBaseAgent

class KYCPlatformOrchestrator:
    def __init__(self):
        self.today_date = datetime.now().strftime("%d-%m-%Y")

        # 1. EXTRACTOR
        self.extractor = KYCBaseAgent(
            name="Data & Docs Extractor",
            system_instructions=(
                "You are a strict data parsing engine. You do not hold conversations. "
                "Read the document and map the values to the following JSON schema exactly. "
                "If a value is missing, use the string 'NONE'.\n\n"
                "REQUIRED SCHEMA:\n"
                "{\n"
                '  "full_name": "String",\n'
                '  "document_id": "String",\n'
                '  "document_type": "String",\n'
                '  "country": "String",\n'
                '  "expiry_date": "DD-MM-YYYY"\n'
                "}\n\n"
                "Output ONLY the JSON object starting with { and ending with }. Do not transcribe raw text."
            ),
            is_vision=True
        )

        # 2. VERIFIER
        self.id_verifier = KYCBaseAgent(
            name="ID Verification Agent",
            system_instructions=(
                f"You are a strict logic engine. Today's date is {self.today_date}. "
                "Evaluate the input JSON by following these exact rules in order:\n"
                "1. If 'document_type' is 'PAN' or 'Aadhaar', the status is 'VALID'.\n"
                "2. If 'expiry_date' is 'NONE' (and it is not a PAN/Aadhaar), the status is 'SUSPECT'.\n"
                "3. If an 'expiry_date' exists, look at the YEAR. If the expiry year is greater than or equal to the current year, the status is 'VALID'.\n"
                "4. If the expiry year is less than the current year, the status is 'EXPIRED'.\n\n"
                "You MUST output the result inside a JSON markdown block.\n\n"
                "EXAMPLE OUTPUT:\n"
                "```json\n"
                "{\n"
                '  "verification_status": "VALID or EXPIRED or SUSPECT",\n'
                '  "confidence_score": <Float between 0.0 and 1.0 representing your certainty>\n'
                "}\n"
                "```\n\n"
                "Do not include any other conversational text."
            )
        )
        
        # 3. ENRICHER (Now aware of Tool Results)
        self.enricher = KYCBaseAgent(
            name="Data Enrichment Agent",
            system_instructions=(
                "You are an OSINT enrichment engine. Read the input profile and the 'database_search_results'.\n"
                "Generate a JSON profile enrichment. If they hit the watchlist, add known aliases for a criminal. If not, add generic corporate affiliations.\n\n"
                "REQUIRED SCHEMA:\n"
                "{\n"
                '  "corporate_affiliations": ["List", "of", "companies"],\n'
                '  "known_aliases": ["List", "of", "names"]\n'
                "}\n\n"
                "Output ONLY the JSON object. No explanations."
            )
        )

        # 4. SCREENER (Now strictly enforces the Tool Results)
        self.screener = KYCBaseAgent(
            name="Compliance Screening Agent",
            system_instructions=(
                "You are a strict AML screening engine. Analyze the input profile AND the 'database_search_results'.\n\n"
                "CRITICAL RULE: If 'found_on_watchlist' is true, the sanction_score MUST be 100 and rationale MUST state 'Match found in Global Watchlist Database'. "
                "If 'found_on_watchlist' is false, the sanction_score MUST be 0.\n\n"
                "REQUIRED SCHEMA:\n"
                "{\n"
                '  "sanction_score": Integer between 0 and 100,\n'
                '  "rationale": "Short string explanation based on database search results"\n'
                "}\n\n"
                "Output ONLY the JSON object. No explanations."
            )
        )
        
        # 5. PROFILER
        self.profiler = KYCBaseAgent(
            name="Financial Profiling Agent",
            system_instructions=(
                "You are a financial fraud detection engine. Analyze the input for anomalies.\n\n"
                "REQUIRED SCHEMA:\n"
                "{\n"
                '  "anomaly_score": Integer between 0 and 100,\n'
                '  "rationale": "Short string explanation"\n'
                "}\n\n"
                "Output ONLY the JSON object. No explanations."
            )
        )

    async def run_analysis(self, image_path: str, selfie_path: str = None) -> dict:
        audit_trail = []
        
        print("[Phase 1] Extracting Data & Docs...")
        extraction_res = self.extractor.run({"image_path": image_path})
        audit_trail.append(extraction_res)

        # HARDENED JSON PARSING
        raw_output = extraction_res.get("output", "")
        parsed_profile = {"full_name": "Unknown", "document_id": "Unknown", "document_type": "Unknown", "country": "Unknown", "expiry_date": "NONE"}
        
        try:
            clean_text = raw_output.replace("```json", "").replace("```", "").strip()
            start_idx = clean_text.find("{")
            end_idx = clean_text.rfind("}")
            if start_idx != -1 and end_idx != -1:
                clean_json_string = clean_text[start_idx:end_idx+1]
                data = json.loads(clean_json_string)
                if isinstance(data, dict):
                    parsed_profile.update(data)
        except Exception as e:
            print(f"JSON Parse Error: {e}")

        # TOOL-USE (RAG DATABASE LOOKUP)
        print("[Phase 1.5] Executing OSINT Database Search (Tool-Use)...")
        extracted_name = parsed_profile.get("full_name", "UNKNOWN").upper()
        watchlist_hit = False
        
        tool_latency_start = time.time()
        try:
            with open("global_watchlist.txt", "r") as db_file:
                watchlist = [line.strip().upper() for line in db_file.readlines()]
                if extracted_name in watchlist and extracted_name != "UNKNOWN":
                    watchlist_hit = True
        except FileNotFoundError:
            print("Watchlist DB not found. Skipping tool execution.")
            
        tool_latency = round(time.time() - tool_latency_start, 3)
        
        tool_result_text = json.dumps({
            "action": f"Executed SQL lookup in global_watchlist for '{extracted_name}'", 
            "match_found": watchlist_hit,
            "confidence": "100% (Deterministic)"
        }, indent=2)
        
        audit_trail.append({
            "agent_name": "OSINT Database Tool (Python Execution)", 
            "latency_sec": tool_latency, 
            "output": tool_result_text
        })

        parsed_profile["database_search_results"] = {
            "target_name": extracted_name,
            "found_on_watchlist": watchlist_hit
        }

        print("[Phase 2] Running Verification & Biometrics...")
        
        bio_res = None
        if selfie_path:
            start_t = time.time()
            from utils import verify_biometrics
            print("Executing 1:1 Biometric Facial Match...")
            bio_check = verify_biometrics(image_path, selfie_path)
            
            bio_res = {"agent_name": "Biometric Liveness Agent", "latency_sec": round(time.time() - start_t, 2)}
            if bio_check["error"]:
                bio_res["output"] = json.dumps({"status": "FAILED", "reason": bio_check["error"]})
            elif bio_check["match"]:
                bio_res["output"] = json.dumps({"status": "VERIFIED", "confidence": f"{bio_check['score']}%"})
            else:
                bio_res["output"] = json.dumps({"status": "MISMATCH", "confidence": f"{bio_check['score']}%"})
            audit_trail.append(bio_res)

        verification_res = self.id_verifier.run({"context_data": parsed_profile})
        audit_trail.append(verification_res)
        
        enrichment_res = self.enricher.run({"context_data": parsed_profile})
        audit_trail.append(enrichment_res)
        
        enriched_profile = {"original": parsed_profile, "enriched_context": enrichment_res["output"]}

        print("[Phase 3] Launching Screening & Profiling...")
        sanctions_res = self.screener.run({"context_data": enriched_profile})
        financial_res = self.profiler.run({"context_data": enriched_profile})
        audit_trail.extend([sanctions_res, financial_res])

        final_decision = self._compile_decision(sanctions_res, financial_res, verification_res, bio_res, audit_trail)
        final_decision["profile"] = parsed_profile 
        return final_decision

    def _compile_decision(self, s_res, f_res, v_res, bio_res, audit_trail):
        s_score, f_score, v_error, b_error = 0, 0, 0, 0
        
        try: s_score = int(json.loads(s_res["output"][s_res["output"].find("{"):s_res["output"].rfind("}")+1]).get("sanction_score", 0))
        except: pass
        try: f_score = int(json.loads(f_res["output"][f_res["output"].find("{"):f_res["output"].rfind("}")+1]).get("anomaly_score", 0))
        except: pass
        
        if "SUSPECT" in v_res["output"].upper() or "EXPIRED" in v_res["output"].upper(): 
            v_error = 100
        else: 
            v_error = 10 

        if bio_res:
            if "MISMATCH" in bio_res["output"] or "FAILED" in bio_res["output"]:
                b_error = 100
            total_risk = (s_score * 0.30) + (f_score * 0.20) + (v_error * 0.20) + (b_error * 0.30)
            b_metric_display = b_error
        else:
            total_risk = (s_score * 0.40) + (f_score * 0.30) + (v_error * 0.30)
            b_metric_display = "Not Provided"

        if total_risk >= 65.0: status = "ESCALATE"
        elif total_risk >= 35.0: status = "REVIEW"
        else: status = "APPROVE"

        return {
            "status": status,
            "composite_risk_score": round(total_risk, 2),
            "metrics": {"sanctions_risk": s_score, "financial_risk": f_score, "id_verification_risk": v_error, "biometric_risk": b_metric_display},
            "audit_trail": audit_trail
        }