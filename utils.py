import os
import sqlite3
import datetime
import streamlit as tf
import pandas as pd

DB_PATH = "kyc_history.db"

def init_db():
    """Creates the SQLite table if it doesn't already exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS compliance_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            customer_name TEXT,
            document_id TEXT,
            decision TEXT,
            risk_score REAL
        )
    ''')
    conn.commit()
    conn.close()

def log_case(customer_name, document_id, decision, risk_score):
    """Inserts a new KYC scan result into the database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('INSERT INTO compliance_logs (timestamp, customer_name, document_id, decision, risk_score) VALUES (?, ?, ?, ?, ?)',
              (timestamp, str(customer_name), str(document_id), str(decision), float(risk_score)))
    conn.commit()
    conn.close()

def get_all_cases():
    """Fetches all logged cases as a list of dictionaries for Streamlit."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT id, timestamp, customer_name, document_id, decision, risk_score FROM compliance_logs ORDER BY id DESC')
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def prepare_ingestion_file(uploaded_file, output_directory="temp_storage"):
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)
    
    file_path = os.path.join(output_directory, uploaded_file.name)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
        
    if file_path.lower().endswith(".pdf"):
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(file_path, 200)
            fallback_img_path = file_path.replace(".pdf", "_page1.jpg")
            pages[0].save(fallback_img_path, "JPEG")
            return fallback_img_path
        except Exception as e:
            tf.error("System environment error: 'poppler-utils' is missing. Please upload your identity asset as a PNG or JPEG file instead for this demo version.")
            return None
            
    return file_path

def verify_biometrics(id_image_path, selfie_image_path):
    """Compares a face on an ID to a live selfie and returns a match confidence."""
    import face_recognition
    try:
        id_image = face_recognition.load_image_file(id_image_path)
        selfie_image = face_recognition.load_image_file(selfie_image_path)
        
        id_encodings = face_recognition.face_encodings(id_image)
        selfie_encodings = face_recognition.face_encodings(selfie_image)
        
        if not id_encodings:
            return {"match": False, "score": 0, "error": "No face detected on ID document"}
        if not selfie_encodings:
            return {"match": False, "score": 0, "error": "No face detected in live selfie"}
            
        match_results = face_recognition.compare_faces([id_encodings[0]], selfie_encodings[0], tolerance=0.6)
        face_distances = face_recognition.face_distance([id_encodings[0]], selfie_encodings[0])
        
        confidence = round((1 - face_distances[0]) * 100, 2)
        
        return {"match": bool(match_results[0]), "score": confidence, "error": None}
    except Exception as e:
        return {"match": False, "score": 0, "error": str(e)}

def get_status_counts():
    """Queries the database to count how many cases are Approved, Reviewed, or Escalated."""
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT decision as status, COUNT(*) as count FROM compliance_logs GROUP BY decision"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return pd.DataFrame({"status": ["APPROVE", "REVIEW", "ESCALATE"], "count": [0, 0, 0]})
            
        return df
    except Exception as e:
        print(f"Database error: {e}")
        return pd.DataFrame({"status": ["APPROVE", "REVIEW", "ESCALATE"], "count": [0, 0, 0]})