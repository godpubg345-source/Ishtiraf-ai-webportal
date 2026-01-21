
import random
from datetime import datetime

class AIExpertSystem:
    """
    Simulates a Generative AI Expert for Medical Diagnosis Explanation.
    Maps diagnosis codes to detailed, verifiable clinical reports.
    """

    KNOWLEDGE_BASE = {
        'MURMUR': {
            'explanation': "The AI detected a distinct **systolic murmur** pattern. This acoustic anomaly suggests non-laminar blood flow through the cardiac valves. The spectrogram reveals energy concentration in the **200-500Hz** range, consistent with Grade II/VI intensity.",
            'advice': [
                "Immediate referral for **Echocardiogram** to assess valve function.",
                "Monitor for symptoms like shortness of breath or chest pain.",
                "Avoid strenuous physical activity until cleared by a cardiologist."
            ],
            'acoustic_metrics': {
                'Primary Frequency': '345 Hz',
                'Signal Intensity': 'High (-23dB)',
                'Murmur Duration': '0.32s (Systolic)',
                'Pattern Type': 'Crescendo-Decrescendo'
            }
        },
        'AORTIC STENOSIS': {
            'explanation': "The Audio Transformer identified a characteristic **diamond-shaped systolic murmur**. This pattern is highly specific to **Aortic Stenosis**, indicating narrowing of the aortic valve opening. The signal shows a delayed carotid upstroke correlation.",
            'advice': [
                "URGENT: Cardiology consultation required.",
                "Echocardiogram to measure valve area and pressure gradient.",
                "Blood pressure management is critical."
            ],
            'acoustic_metrics': {
                'Primary Frequency': '420 Hz',
                'Signal Intensity': 'Very High (-15dB)',
                'Timing': 'Mid-Systolic',
                'S2 Splitting': 'Paradoxical'
            }
        },
        'MITRAL REGURGITATION': {
            'explanation': "A **holosystolic murmur** was detected with radiation to the axilla. This sound profile is indicative of **Mitral Regurgitation**, suggesting incomplete closure of the mitral valve during systole.",
            'advice': [
                "Schedule Echocardiogram to assess regurgitant volume.",
                "Monitor for signs of heart failure (edema, fatigue).",
                "Antibiotic prophylaxis discussion for dental procedures."
            ],
            'acoustic_metrics': {
                'Primary Frequency': '280 Hz',
                'Signal Intensity': 'Moderate (-30dB)',
                'Timing': 'Holosystolic',
                'S3 Gallop': 'Present'
            }
        },
        'NORMAL': {
            'explanation': "The AI analysis confirms **normal S1 and S2 heart sounds** with clear distinct timing. No murmurs, gallops, or adventitious sounds were detected. The rhythm is regular with a consistent amplitude profile.",
            'advice': [
                "Maintain a heart-healthy diet and regular exercise.",
                "Routine annual checkup recommended.",
                "No immediate intervention required."
            ],
            'acoustic_metrics': {
                'Primary Frequency': '60-120 Hz',
                'Signal Intensity': 'Normal',
                'S1/S2 Ratio': '1.2 (Normal)',
                'Murmurs': 'None Detected'
            }
        },
         'ABNORMAL': {
            'explanation': "An **unspecified acoustic anomaly** was flagged by the Neural Network. While not matching a specific classic murmur profile perfectly, the signal deviates significantly from the normal S1-S2 cadence, suggesting potential arrhythmia or valve irregularity.",
            'advice': [
                "Clinical auscultation by a specialist recommended.",
                "ECG (Electrocardiogram) to rule out arrhythmia.",
                "Follow-up scan in 2 weeks."
            ],
            'acoustic_metrics': {
                'Primary Frequency': 'Variable',
                'Signal Intensity': 'Irregular',
                'Rhythm': 'Arrhythmic',
                'Artifacts': 'Low'
            }
        }
    }

    @staticmethod
    def generate_report(diagnosis, status, risk, organ="Heart"):
        """
        Generates a rich AI report based on input parameters.
        """
        diag_key = "NORMAL"
        
        # Match diagnosis to knowledge base
        d_upper = diagnosis.upper()
        if "MURMUR" in d_upper:
            diag_key = "MURMUR"
        elif "AORTIC" in d_upper:
            diag_key = "AORTIC STENOSIS"
        elif "MITRAL" in d_upper:
            diag_key = "MITRAL REGURGITATION"
        elif status == "A" or risk >= 5:
            diag_key = "ABNORMAL"
        
        # Override if specific key exists
        if d_upper in AIExpertSystem.KNOWLEDGE_BASE:
            diag_key = d_upper
            
        base_data = AIExpertSystem.KNOWLEDGE_BASE.get(diag_key, AIExpertSystem.KNOWLEDGE_BASE['ABNORMAL'])
        
        # Add dynamic elements based on risk score (simulation)
        report = base_data.copy()
        
        # Adjust confidence/intensity text based on risk
        if risk > 8 and "High" not in report['acoustic_metrics'].get('Signal Intensity', ''):
             report['acoustic_metrics']['Signal Intensity'] += " (Severe)"
             
        return report
