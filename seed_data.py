import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "ishtiraf_ai.db"

def seed_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Clear existing data (optional, but good for demo)
    # cursor.execute("DELETE FROM diagnosis")
    # cursor.execute("DELETE FROM patient")

    print("🌱 Seeding Database...")

    names = ["Ali Khan", "Sara Ahmed", "Zainab Bibi", "Usman Gondal", "Fatima Noor", "Bilal HYDER", "Ayesha Siddiqa", "Hamza Shah"]
    
    # 1. Create Patients
    patient_ids = []
    for name in names:
        cursor.execute("SELECT id FROM patient WHERE name = ?", (name,))
        res = cursor.fetchone()
        if not res:
            age = random.randint(20, 80)
            gender = random.choice(["Male", "Female"])
            cursor.execute("INSERT INTO patient (name, age, gender, contact, created_at) VALUES (?, ?, ?, ?, ?)",
                           (name, age, gender, "0300-1234567", datetime.now()))
            patient_ids.append(cursor.lastrowid)
        else:
            patient_ids.append(res[0])

    # 2. Create Diagnoses
    diagnoses = [
        ("NORMAL", "S1 S2 STABLE", 0.05, 1),
        ("NORMAL", "VESICULAR", 0.02, 0),
        ("ABNORMAL", "MITRAL REGURGITATION", 0.89, 9),
        ("ABNORMAL", "AORTIC STENOSIS", 0.92, 9),
        ("ABNORMAL", "WHEEZE (ASTHMA)", 0.75, 7),
        ("NORMAL", "S1 SPLIT", 0.15, 2),
        ("ABNORMAL", "RALES (PNEUMONIA)", 0.81, 8),
        ("ABNORMAL", "GALLOP RHYTHM", 0.88, 8)
    ]

    for pid in patient_ids:
        # Add 1-3 diagnoses per patient
        for _ in range(random.randint(1, 3)):
            status, detail, prob, risk = random.choice(diagnoses)
            
            # Timestamp back in time
            ts = datetime.now() - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))
            
            cursor.execute("""
                INSERT INTO diagnosis (
                    patient_id, diagnosis_id, timestamp, device_id, diagnosis_result, 
                    confidence, risk_score, recommendation, path_used, rms_value,
                    sym_chest_pain, sym_shortness, sym_history, patient_mode, organ_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pid, f"DIAG-{random.randint(1000,9999)}", ts, "RPI-TOUCH-01", 
                f"{status}: {detail}", int(prob*100), risk, 
                "Immediate Consult" if risk > 5 else "Monitor", 
                "Saved_Models/heart_v2.h5", random.uniform(0.1, 0.5),
                1 if risk > 5 else 0, 1 if risk > 5 else 0, 0, "Adult", "Heart"
            ))

    conn.commit()
    conn.close()
    print("✅ Database Seeded Successfully!")

if __name__ == "__main__":
    seed_data()
