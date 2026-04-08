# Medical Data Extraction Prompts
# This file contains prompts for extracting structured data from medical reports

def get_natural_language_prompt(medical_report: str) -> str:
    """
    Natural language prompt - describes what to extract without explicit field names.
    Works well with powerful models like Claude Opus 4.5, but smaller models may struggle
    with inferring the correct JSON structure and field names.
    """
    return f"""Extract structured data from this medical report. Return a JSON object with the following sections:

**patient**: Include the patient's full legal name, date of birth (YYYY-MM-DD format), calculated age as a number, biological sex in lowercase, and their medical record number (the MRN).

**encounter**: Include the date of this visit (YYYY-MM-DD format), the type of encounter in lowercase, and nested objects for the hospital information (name, department, and specific unit) and the provider who is responsible for the patient's care during this admission (their name, specialty, and NPI number).

**diagnosis**: Include a primary diagnosis object with the condition name, ICD-10 code, and severity in lowercase. Include a secondary array with any additional active diagnoses for this visit, each having a condition name and ICD-10 code.

**treatment**: Include an array of medications that were ordered specifically for this admission (not home medications the patient was already taking). Each medication should have name, dose, route in lowercase, and frequency in lowercase. Include a procedures array with scheduled procedures, their dates (YYYY-MM-DD), and urgency level in lowercase. Include the disposition in lowercase.

Medical Report:
{medical_report}

Return only valid JSON, no other text or explanation.
"""


def get_optimized_prompt(medical_report: str) -> str:
    """
    Optimized prompt with markdown structure and explicit JSON template.
    Works well with both powerful models AND smaller models like Nova Lite.
    The markdown formatting and explicit field names guide the model to produce
    consistent, correctly-structured output.
    """
    return f"""
## TASK ##
Extract data from the medical report into a JSON object.

## IMPORTANT INSTRUCTIONS ##
- Extract ONLY medications ordered for THIS admission (not home medications)
- The ATTENDING physician is the one responsible for emergency care
- Use the visit/encounter date, not document creation date
- Use the MRN (Medical Record Number), not other IDs
- Encounter type only choices are **emergency** or **outpatient**

## EXACT JSON STRUCTURE ##
```json
{{
  "patient": {{
    "full_legal_name": "full legal name",
    "date_of_birth": "YYYY-MM-DD",
    "age": number,
    "biological_sex": "female" or "male",
    "medical_record_number": "MRN-XXXXXXX"
  }},
  "encounter": {{
    "date": "YYYY-MM-DD",
    "type": "emergency" or "outpatient",
    "hospital": {{
      "name": "hospital name",
      "department": "department name",
      "unit": "unit name"
    }},
    "provider": {{
      "name": "Dr. Full Name",
      "specialty": "specialty",
      "npi": "NPI number"
    }}
  }},
  "diagnosis": {{
    "primary": {{
      "condition": "diagnosis name",
      "icd_10_code": "ICD-10 code",
      "severity": "mild" or "moderate" or "severe"
    }},
    "secondary": [
      {{"condition": "name", "icd_10_code": "code"}}
    ]
  }},
  "treatment": {{
    "medications": [
      {{"name": "drug", "dose": "dose", "route": "oral/iv", "frequency": "frequency"}}
    ],
    "procedures": [
      {{"name": "procedure", "date": "YYYY-MM-DD", "urgency": "urgent/routine"}}
    ],
    "disposition": "disposition in lowercase"
  }}
}}
```

## MEDICAL REPORT ##
{medical_report}

## RESPONSE ##
Return ONLY the JSON object. No markdown, no explanation.
"""


# =============================================================================
# CONTRAINDICATION SCREENING PROMPTS (for Reasoning Model demonstration)
# =============================================================================

def get_simple_contraindication_prompt(patient_profile: str) -> str:
    """
    Simple/vague prompt for contraindication screening.
    Lets the reasoning model figure out the rules from its training.
    Results in more thinking tokens as the model must derive contraindication logic.
    """
    return f"""Review this patient's profile and check if the proposed medications are safe:

{patient_profile}

Identify any contraindications and provide recommendations.

Return a JSON object with status and recommendations for each medication.
"""


def get_optimized_contraindication_prompt(patient_profile: str) -> str:
    """
    Optimized prompt with explicit contraindication rules.
    Reduces thinking tokens by providing pattern-matching rules instead of
    requiring the model to derive medical knowledge from training.

    Key optimization: Rule-based pattern matching (CHECK rules) instead of
    decision-tree reasoning (DERIVE rules). Simple output format to minimize tokens.
    """
    return f"""Check medications against rules. One line per drug.

RULES:
- Metformin: CONTRAINDICATED if eGFR<30 or heart failure
- Ibuprofen/NSAIDs: CONTRAINDICATED if GI bleed or eGFR<30 or heart failure
- Sotalol: CONTRAINDICATED if QT prolonged or asthma or EF<40%
- Sulfa drugs: CONTRAINDICATED if sulfa allergy
- Spironolactone: CAUTION if eGFR<30

{patient_profile}

OUTPUT (one line each, no explanation):
DRUG | STATUS | REASON
"""
