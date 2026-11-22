"""
IshtirafAI - HL7 FHIR Export Utility
====================================
Export diagnoses in HL7 FHIR R4 format for healthcare interoperability.
"""

import json
from datetime import datetime
from typing import Dict, Any


def generate_fhir_patient(patient) -> Dict[str, Any]:
    """Generate FHIR R4 Patient resource."""
    return {
        "resourceType": "Patient",
        "id": f"patient-{patient.id}",
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Patient"]
        },
        "identifier": [{
            "system": "http://ishtirafai.local/patients",
            "value": f"PAT-{patient.id:04d}"
        }],
        "name": [{
            "use": "official",
            "text": patient.name,
            "family": patient.name.split()[-1] if ' ' in patient.name else patient.name,
            "given": patient.name.split()[:-1] if ' ' in patient.name else []
        }],
        "gender": patient.gender.lower() if patient.gender else "unknown",
        "birthDate": None,  # Would calculate from age
        "telecom": [{
            "system": "phone",
            "value": patient.contact,
            "use": "mobile"
        }] if patient.contact else []
    }


SCREEN_CS = "https://ishtiraf.ai/fhir/CodeSystem/screening"          # placeholder URL (spec section 4)
RESULT_CS = "https://ishtiraf.ai/fhir/CodeSystem/screening-result"
RESULT_CODES = {  # device status -> spec valueCodeableConcept
    "ABNORMAL": ("refer", "Refer for echo"),
    "UNSURE": ("unsure", "Unsure: re-record or refer"),
    "NORMAL": ("no-referral", "No referral by sound"),
}
SCREEN_NOTE = "Screening aid only - not a diagnosis. Refer anyway if symptoms or clinical concern."


def generate_fhir_observation(diagnosis, patient) -> Dict[str, Any]:
    """FHIR R4 screening Observation, per docs/specs/FHIR_export.md section 4.

    Only stored facts are exported: a local code (no invented SNOMED/LOINC code), the
    referral decision as valueCodeableConcept, the AI score 0-100, and no
    `interpretation` (H/L/A would read as a diagnosis). Rows whose text is not one of the
    device labels (pre-V2 data) and NO RESULT get no value and a dataAbsentReason.
    """
    from utils.device_registry import STATUS_OF_LABEL

    status = STATUS_OF_LABEL.get(diagnosis.diagnosis_result or "")
    obs = {
        "resourceType": "Observation",
        "id": f"obs-{diagnosis.id}",
        "status": "final",
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
            "code": "exam", "display": "Exam"}]}],
        "code": {"coding": [{"system": SCREEN_CS, "code": "ishtiraf-heart-sound-referral-screen",
                             "display": "AI heart-sound referral screen"}],
                 "text": "AI heart-sound referral screen"},
        "subject": {"reference": f"Patient/patient-{patient.id}", "display": patient.name},
        "effectiveDateTime": diagnosis.timestamp.isoformat() if diagnosis.timestamp else None,
        "issued": datetime.utcnow().isoformat() + "Z",
        "device": {"display": diagnosis.device_id or "IshtirafAI-Steth"},
        "note": [{"text": SCREEN_NOTE}],
    }
    if status in RESULT_CODES:
        code, display = RESULT_CODES[status]
        obs["valueCodeableConcept"] = {"coding": [{"system": RESULT_CS, "code": code, "display": display}],
                                       "text": diagnosis.diagnosis_result}
        if diagnosis.risk_score is not None:
            obs["component"] = [{
                "code": {"coding": [{"system": SCREEN_CS, "code": "score", "display": "AI screening score (0-100)"}]},
                "valueQuantity": {"value": int(round(diagnosis.risk_score * 10)), "unit": "{score}",
                                  "system": "http://unitsofmeasure.org", "code": "{score}"},
            }]
        if diagnosis.recommendation:
            obs["note"].append({"text": diagnosis.recommendation})
    else:
        obs["dataAbsentReason"] = {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
            "code": "error" if status == "NO RESULT" else "unknown"}],
            "text": diagnosis.diagnosis_result or "No result"}
    return obs


def generate_fhir_bundle(patient, diagnoses: list) -> Dict[str, Any]:
    """Generate FHIR R4 Bundle containing patient and all observations."""
    
    entries = []
    
    # Add patient
    patient_resource = generate_fhir_patient(patient)
    entries.append({
        "fullUrl": f"urn:uuid:patient-{patient.id}",
        "resource": patient_resource
    })
    
    # Add observations
    for diag in diagnoses:
        obs_resource = generate_fhir_observation(diag, patient)
        entries.append({
            "fullUrl": f"urn:uuid:obs-{diag.id}",
            "resource": obs_resource
        })
    
    return {
        "resourceType": "Bundle",
        "id": f"bundle-{patient.id}-{int(datetime.now().timestamp())}",
        "meta": {
            "lastUpdated": datetime.utcnow().isoformat() + "Z"
        },
        "type": "collection",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "entry": entries
    }


def export_to_fhir_json(patient, diagnoses: list = None) -> str:
    """Export patient data to FHIR JSON string."""
    if diagnoses is None:
        diagnoses = patient.diagnoses
    
    bundle = generate_fhir_bundle(patient, diagnoses)
    return json.dumps(bundle, indent=2)
