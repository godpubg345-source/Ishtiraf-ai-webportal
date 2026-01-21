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


def generate_fhir_observation(diagnosis, patient) -> Dict[str, Any]:
    """Generate FHIR R4 Observation resource for diagnosis."""
    
    # Map diagnosis to SNOMED CT codes
    snomed_codes = {
        "Normal": {"code": "17621005", "display": "Normal heart sounds"},
        "Aortic Stenosis": {"code": "60573004", "display": "Aortic valve stenosis"},
        "Mitral Regurgitation": {"code": "48724000", "display": "Mitral valve regurgitation"},
        "Abnormal": {"code": "271807003", "display": "Abnormal heart sound"},
        "Crackles": {"code": "48409008", "display": "Crackles"},
        "Wheeze": {"code": "56018004", "display": "Wheezing"},
    }
    
    # Find matching code or default
    code_info = {"code": "271807003", "display": "Abnormal finding"}
    for key, value in snomed_codes.items():
        if key.lower() in (diagnosis.diagnosis_result or "").lower():
            code_info = value
            break
    
    return {
        "resourceType": "Observation",
        "id": f"obs-{diagnosis.id}",
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Observation"]
        },
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "exam",
                "display": "Exam"
            }]
        }],
        "code": {
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": code_info["code"],
                "display": code_info["display"]
            }],
            "text": diagnosis.diagnosis_result
        },
        "subject": {
            "reference": f"Patient/patient-{patient.id}",
            "display": patient.name
        },
        "effectiveDateTime": diagnosis.timestamp.isoformat() if diagnosis.timestamp else None,
        "issued": datetime.utcnow().isoformat() + "Z",
        "performer": [{
            "display": "IshtirafAI Diagnostic System"
        }],
        "device": {
            "display": diagnosis.device_id or "IshtirafAI-Steth"
        },
        "interpretation": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                "code": "N" if "normal" in (diagnosis.diagnosis_result or "").lower() else "A",
                "display": "Normal" if "normal" in (diagnosis.diagnosis_result or "").lower() else "Abnormal"
            }]
        }],
        "component": [
            {
                "code": {
                    "coding": [{
                        "system": "http://ishtirafai.local/codes",
                        "code": "confidence",
                        "display": "AI Confidence Score"
                    }]
                },
                "valueQuantity": {
                    "value": round((diagnosis.confidence or 0) * 100, 2),
                    "unit": "%",
                    "system": "http://unitsofmeasure.org",
                    "code": "%"
                }
            },
            {
                "code": {
                    "coding": [{
                        "system": "http://ishtirafai.local/codes",
                        "code": "risk-score",
                        "display": "Risk Score"
                    }]
                },
                "valueQuantity": {
                    "value": diagnosis.risk_score or 0,
                    "unit": "score",
                    "system": "http://unitsofmeasure.org"
                }
            }
        ],
        "note": [{
            "text": diagnosis.recommendation or ""
        }]
    }


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
