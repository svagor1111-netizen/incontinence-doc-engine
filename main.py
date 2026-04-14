import os
import re
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from docx import Document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "generated")
VN_TEMPLATE_PATH = os.path.join(BASE_DIR, "MASTER_VN.docx")
ORDER_TEMPLATE_PATH = os.path.join(BASE_DIR, "MASTER_INCONTINENCE.docx")

os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="Incontinence Document Generator")
app.mount("/generated", StaticFiles(directory=OUTPUT_DIR), name="generated")


# -----------------------------
# SCHEMA
# -----------------------------

class Vitals(BaseModel):
    height: str
    weight: str
    blood_pressure: str
    pulse: str
    respiration: str
    temperature: str


class Diagnosis(BaseModel):
    code: str
    label: str


class EquipmentDetail(BaseModel):
    name: str
    dx: str
    medical_necessity: str


class IncontinenceOrder(BaseModel):
    underpads_chux: bool = False
    disposable_brief: bool = False
    disposable_pullup: bool = False
    absorbent_pads_liners: bool = False
    reusable_underpants: bool = False
    waterproof_mattress_cover: bool = False
    incontinence_wash: bool = False
    incontinence_cream: bool = False
    gloves: bool = False

    sex_male: bool = False
    sex_female: bool = False

    length_6_months: bool = False
    length_12_months: bool = True

    size_s: bool = False
    size_m: bool = False
    size_l: bool = False
    size_xl_xxl: bool = False


class IncontinenceRequest(BaseModel):
    mode: str = Field(default="incontinence")
    patient_name: str
    dob: str
    age: str
    sex: str
    patient_phone: str
    patient_address: str
    insurance_id: str

    physician_name: str
    practice_name: Optional[str] = ""
    practice_address: str
    practice_phone: str
    practice_fax: str
    npi: str

    facility_name: str
    facility_address: str
    facility_phone: str

    city: str
    state: str
    zip: str

    exam_date: str
    signature_date: str

    vitals: Vitals
    diagnoses: List[Diagnosis]

    primary_diagnosis: str
    secondary_diagnoses: str

    functional_status: str
    cognitive_status: str
    ambulatory_status: str
    general_health_status: str

    equipment_list: List[str]
    equipment_details: List[EquipmentDetail]

    equipment_1: Optional[str] = ""
    equipment_2: Optional[str] = ""
    equipment_3: Optional[str] = ""
    equipment_4: Optional[str] = ""
    equipment_5: Optional[str] = ""
    equipment_6: Optional[str] = ""
    equipment_7: Optional[str] = ""
    equipment_8: Optional[str] = ""

    incontinence_order: IncontinenceOrder


# -----------------------------
# CONSTANTS
# -----------------------------

ALLOWED_ITEMS = [
    "Under Pads / Chux",
    "Disposable Brief (Diapers)",
    "Disposable Pull-Up",
    "Absorbent Pads / Liners",
    "Reusable Underpants",
    "Waterproof Mattress Cover",
    "Incontinence Wash",
    "Incontinence Cream",
    "Gloves",
]

ITEM_TO_ORDER_FIELD = {
    "Under Pads / Chux": "underpads_chux",
    "Disposable Brief (Diapers)": "disposable_brief",
    "Disposable Pull-Up": "disposable_pullup",
    "Absorbent Pads / Liners": "absorbent_pads_liners",
    "Reusable Underpants": "reusable_underpants",
    "Waterproof Mattress Cover": "waterproof_mattress_cover",
    "Incontinence Wash": "incontinence_wash",
    "Incontinence Cream": "incontinence_cream",
    "Gloves": "gloves",
}


# -----------------------------
# HELPERS
# -----------------------------

def sanitize_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value[:80] or "document"


def checkbox(value: bool) -> str:
    return "☑" if value else "☐"


def order_field_to_item(field_name: str) -> Optional[str]:
    for item_name, mapped_field in ITEM_TO_ORDER_FIELD.items():
        if mapped_field == field_name:
            return item_name
    return None


def normalize_equipment(payload: IncontinenceRequest) -> List[str]:
    candidates: List[str] = []

    # 1) explicit equipment_list
    candidates.extend([x for x in payload.equipment_list if x in ALLOWED_ITEMS])

    # 2) equipment_details names
    candidates.extend([d.name for d in payload.equipment_details if d.name in ALLOWED_ITEMS])

    # 3) legacy equipment_1..8
    for value in [
        payload.equipment_1,
        payload.equipment_2,
        payload.equipment_3,
        payload.equipment_4,
        payload.equipment_5,
        payload.equipment_6,
        payload.equipment_7,
        payload.equipment_8,
    ]:
        if value in ALLOWED_ITEMS:
            candidates.append(value)

    # 4) checked boxes from incoming order
    order = payload.incontinence_order
    for field_name in ITEM_TO_ORDER_FIELD.values():
        if getattr(order, field_name, False):
            item_name = order_field_to_item(field_name)
            if item_name:
                candidates.append(item_name)

    # Under Pads always
    if "Under Pads / Chux" not in candidates:
        candidates.insert(0, "Under Pads / Chux")

    seen = set()
    normalized = []
    for item in candidates:
        if item not in seen:
            normalized.append(item)
            seen.add(item)

    return normalized


def synced_order(payload: IncontinenceRequest, items: List[str]) -> IncontinenceOrder:
    order = payload.incontinence_order.model_copy(deep=True)

    for item, field_name in ITEM_TO_ORDER_FIELD.items():
        setattr(order, field_name, item in items)

    sex = (payload.sex or "").strip().lower()
    order.sex_male = sex == "male"
    order.sex_female = sex == "female"

    # hard default
    order.length_6_months = False
    order.length_12_months = True

    return order


def build_equipment_details(payload: IncontinenceRequest, items: List[str]) -> List[EquipmentDetail]:
    by_name = {d.name: d for d in payload.equipment_details if d.name in ALLOWED_ITEMS}
    result = []

    for item in items:
        if item in by_name:
            result.append(by_name[item])
        else:
            result.append(
                EquipmentDetail(
                    name=item,
                    dx=payload.primary_diagnosis,
                    medical_necessity="Medically necessary for management of incontinence-related hygiene needs, MRADL limitation, skin protection, and caregiver-assisted care."
                )
            )
    return result


def text_has_incontinence(text: str) -> bool:
    value = (text or "").lower()
    phrases = [
        "urinary incontinence",
        "fecal incontinence",
        "bowel/bladder incontinence",
        "bladder incontinence",
        "bowel incontinence",
        "incontinence",
    ]
    return any(p in value for p in phrases)


def has_documented_incontinence(payload: IncontinenceRequest) -> bool:
    for dx in payload.diagnoses:
        if text_has_incontinence(dx.label) or text_has_incontinence(dx.code):
            return True

    if text_has_incontinence(payload.primary_diagnosis):
        return True
    if text_has_incontinence(payload.secondary_diagnoses):
        return True
    if text_has_incontinence(payload.functional_status):
        return True
    if text_has_incontinence(payload.general_health_status):
        return True

    for detail in payload.equipment_details:
        if text_has_incontinence(detail.dx) or text_has_incontinence(detail.medical_necessity):
            return True

    return False


def incontinence_assessment_text(payload: IncontinenceRequest) -> str:
    if has_documented_incontinence(payload):
        return (
            "Patient demonstrates documented bladder and/or bowel control impairment with resulting limitation "
            "in toileting, hygiene, and related MRADLs. The patient requires structured incontinence management "
            "to reduce leakage exposure, maintain cleanliness, protect skin integrity, and reduce caregiver burden. "
            "Functional weakness and impaired mobility contribute to difficulty reaching the toilet safely and "
            "completing post-episode hygiene independently."
        )
    return (
        "Patient demonstrates functional bladder and/or bowel control impairment clinically supported by existing "
        "diagnoses, with resulting limitation in toileting, hygiene, and related MRADLs. The patient requires "
        "structured incontinence management to reduce leakage exposure, maintain cleanliness, protect skin integrity, "
        "and reduce caregiver burden. Functional weakness and impaired mobility contribute to difficulty reaching the "
        "toilet safely and completing post-episode hygiene independently."
    )


def clinical_summary_text(payload: IncontinenceRequest) -> str:
    if has_documented_incontinence(payload):
        return (
            "Based on the documented diagnoses and current functional limitations, the above incontinence supplies are "
            "medically necessary for safe management of urinary and/or bowel incontinence, hygiene dependency, MRADL "
            "limitation, skin protection, and caregiver-assisted care. The selected items are limited to clinically "
            "justified supplies and are consistent with the patient's documented condition and functional needs."
        )
    return (
        "Based on the documented diagnoses and current functional limitations, the above incontinence supplies are "
        "medically necessary for safe management of functional incontinence, hygiene dependency, MRADL limitation, "
        "skin protection, and caregiver-assisted care. The selected items are limited to clinically justified supplies "
        "and are consistent with the patient's documented condition and functional needs."
    )


def order_address_value(payload: IncontinenceRequest) -> str:
    return (
        (payload.practice_address or "").strip()
        or (payload.patient_address or "").strip()
        or (payload.facility_address or "").strip()
    )


def primary_diagnosis_string(payload: IncontinenceRequest) -> str:
    return (payload.primary_diagnosis or "").strip()


def secondary_diagnoses_string(payload: IncontinenceRequest) -> str:
    return (payload.secondary_diagnoses or "").strip()


def equipment_block_lines(details: List[EquipmentDetail]) -> List[str]:
    lines = []
    for i, detail in enumerate(details, start=1):
        block = (
            f"{i}. {detail.name}\n"
            f"Diagnosis: {detail.dx}\n"
            f"Medical Necessity: {detail.medical_necessity}"
        )
        lines.append(block)

    while len(lines) < 8:
        lines.append("")

    return lines[:8]


def replace_text_in_paragraph(paragraph, replacements: dict):
    full_text = paragraph.text
    new_text = full_text
    for key, value in replacements.items():
        new_text = new_text.replace(key, value)
    if new_text != full_text:
        paragraph.text = new_text


def replace_text_in_doc(doc: Document, replacements: dict):
    for paragraph in doc.paragraphs:
        replace_text_in_paragraph(paragraph, replacements)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    replace_text_in_paragraph(paragraph, replacements)


def replace_line_containing(doc: Document, needle: str, new_text: str):
    for paragraph in doc.paragraphs:
        if needle in paragraph.text:
            paragraph.text = new_text

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if needle in paragraph.text:
                        paragraph.text = new_text


# -----------------------------
# TEMPLATE RENDER
# -----------------------------

def fill_vn_template(payload: IncontinenceRequest, details: List[EquipmentDetail], file_id: str) -> str:
    if not os.path.exists(VN_TEMPLATE_PATH):
        raise FileNotFoundError(f"VN template not found: {VN_TEMPLATE_PATH}")

    doc = Document(VN_TEMPLATE_PATH)
    equipment_lines = equipment_block_lines(details)

    replacements = {
        "{{physician_name}}": payload.physician_name,
        "{{practice_address}}": payload.practice_address,
        "{{practice_phone}}": payload.practice_phone,
        "{{practice_fax}}": payload.practice_fax,
        "{{exam_date}}": payload.exam_date,
        "{{patient_name}}": payload.patient_name,
        "{{dob}}": payload.dob,
        "{{age}}": payload.age,
        "{{sex}}": payload.sex,
        "{{facility_name}}": payload.facility_name,
        "{{facility_address}}": payload.facility_address,
        "{{facility_phone}}": payload.facility_phone,
        "{{height}}": payload.vitals.height,
        "{{weight}}": payload.vitals.weight,
        "{{blood_pressure}}": payload.vitals.blood_pressure,
        "{{pulse}}": payload.vitals.pulse,
        "{{respiration}}": payload.vitals.respiration,
        "{{temperature}}": payload.vitals.temperature,
        "{{primary_diagnosis}}": primary_diagnosis_string(payload),
        "{{secondary_diagnoses}}": secondary_diagnoses_string(payload),
        "{{functional_status}}": payload.functional_status,
        "{{cognitive_status}}": payload.cognitive_status,
        "{{ambulatory_status}}": payload.ambulatory_status,
        "{{general_health_status}}": payload.general_health_status,
        "{{equipment_1}}": equipment_lines[0],
        "{{equipment_2}}": equipment_lines[1],
        "{{equipment_3}}": equipment_lines[2],
        "{{equipment_4}}": equipment_lines[3],
        "{{equipment_5}}": equipment_lines[4],
        "{{equipment_6}}": equipment_lines[5],
        "{{equipment_7}}": equipment_lines[6],
        "{{equipment_8}}": equipment_lines[7],
        "{{signature_date}}": payload.signature_date,
    }

    replace_text_in_doc(doc, replacements)

    filename = f"{sanitize_filename(payload.patient_name)}_{file_id}_VN.docx"
    path = os.path.join(OUTPUT_DIR, filename)
    doc.save(path)
    return path


def fill_order_template(payload: IncontinenceRequest, order: IncontinenceOrder, file_id: str) -> str:
    if not os.path.exists(ORDER_TEMPLATE_PATH):
        raise FileNotFoundError(f"Order template not found: {ORDER_TEMPLATE_PATH}")

    doc = Document(ORDER_TEMPLATE_PATH)

    replacements = {
        "{{patient_name}}": payload.patient_name,
        "{{dob}}": payload.dob,
        "{{insurance_id}}": payload.insurance_id,
        "{{height}}": payload.vitals.height,
        "{{weight}}": payload.vitals.weight,
        "{{primary_diagnosis}}": primary_diagnosis_string(payload),
        "{{secondary_diagnoses}}": secondary_diagnoses_string(payload),
        "{{physician_name}}": payload.physician_name,
        "{{practice_address}}": order_address_value(payload),
        "{{city}}": payload.city,
        "{{state}}": payload.state,
        "{{zip}}": payload.zip,
        "{{practice_phone}}": payload.practice_phone,
        "{{practice_fax}}": payload.practice_fax,
        "{{npi}}": payload.npi,
        "{{signature_date}}": payload.signature_date,
    }

    replace_text_in_doc(doc, replacements)

    replace_line_containing(
        doc,
        "Male ☐",
        f"Male {checkbox(order.sex_male)}   Female {checkbox(order.sex_female)}",
    )

    replace_line_containing(
        doc,
        "Length of Need:",
        f"Length of Need: 6 Months {checkbox(order.length_6_months)}   12 Months {checkbox(order.length_12_months)}",
    )

    replace_line_containing(
        doc,
        "Disposable Brief (Diapers)",
        f"{checkbox(order.disposable_brief)} Disposable Brief (Diapers)      {checkbox(order.size_s)} S   {checkbox(order.size_m)} M   {checkbox(order.size_l)} L   {checkbox(order.size_xl_xxl)} XL-XXL",
    )

    replace_line_containing(
        doc,
        "Disposable Pull-Up",
        f"{checkbox(order.disposable_pullup)} Disposable Pull-Up              {checkbox(order.size_s)} S   {checkbox(order.size_m)} M   {checkbox(order.size_l)} L   {checkbox(order.size_xl_xxl)} XL-XXL",
    )

    replace_line_containing(
        doc,
        "Under Pads / Chux",
        f"{checkbox(order.underpads_chux)} Under Pads / Chux               (Up to 120/month)",
    )

    replace_line_containing(
        doc,
        "Absorbent Pads / Liners",
        f"{checkbox(order.absorbent_pads_liners)} Absorbent Pads / Liners         (Up to 300/month)",
    )

    replace_line_containing(
        doc,
        "Reusable Underpants",
        f"{checkbox(order.reusable_underpants)} Reusable Underpants             {checkbox(order.size_s)} S   {checkbox(order.size_m)} M   {checkbox(order.size_l)} L   {checkbox(order.size_xl_xxl)} XL-XXL",
    )

    replace_line_containing(
        doc,
        "Waterproof Mattress Cover",
        f"{checkbox(order.waterproof_mattress_cover)} Waterproof Mattress Cover       (2/year)",
    )

    replace_line_containing(
        doc,
        "Incontinence Wash",
        f"{checkbox(order.incontinence_wash)} Incontinence Wash",
    )

    replace_line_containing(
        doc,
        "Incontinence Cream",
        f"{checkbox(order.incontinence_cream)} Incontinence Cream",
    )

    replace_line_containing(
        doc,
        "Gloves",
        f"{checkbox(order.gloves)} Gloves",
    )

    filename = f"{sanitize_filename(payload.patient_name)}_{file_id}_ORDER.docx"
    path = os.path.join(OUTPUT_DIR, filename)
    doc.save(path)
    return path


# -----------------------------
# ROUTES
# -----------------------------

@app.get("/")
def root():
    return {"status": "incontinence backend running"}


@app.get("/health")
def health():
    return {"ok": True, "service": "incontinence-doc-engine"}


@app.post("/create_dme_documents")
def create_dme_documents(payload: IncontinenceRequest):
    if payload.mode != "incontinence":
        return {"error": "Only incontinence mode is supported."}

    if not os.path.exists(VN_TEMPLATE_PATH):
        return {"error": "MASTER_VN.docx not found in backend root."}

    if not os.path.exists(ORDER_TEMPLATE_PATH):
        return {"error": "MASTER_INCONTINENCE.docx not found in backend root."}

    items = normalize_equipment(payload)
    details = build_equipment_details(payload, items)
    order = synced_order(payload, items)

    file_id = datetime.utcnow().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]

    vn_path = fill_vn_template(payload, details, file_id)
    order_path = fill_order_template(payload, order, file_id)

    base_url = os.getenv("PUBLIC_BASE_URL", "https://incontinence-doc-engine.onrender.com")
    vn_url = f"{base_url}/generated/{os.path.basename(vn_path)}"
    order_url = f"{base_url}/generated/{os.path.basename(order_path)}"

    return {
        "status": "success",
        "vn_docx": vn_url,
        "order_docx": order_url,
        "equipment_list": items
    }
