import os
import re
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "generated")
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
# HELPERS
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


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return value[:80] or "document"


def checkbox(value: bool) -> str:
    return "☑" if value else "☐"


def set_default_font(doc: Document, size: int = 11):
    styles = doc.styles
    for style_name in ["Normal"]:
        if style_name in styles:
            style = styles[style_name]
            style.font.name = "Times New Roman"
            style.font.size = Pt(size)


def add_line(doc: Document, text: str = "", bold: bool = False, size: int = 11, align=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    run = p.add_run(text)
    run.bold = bold
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    return p


def normalize_equipment(payload: IncontinenceRequest) -> List[str]:
    items = [x for x in payload.equipment_list if x in ALLOWED_ITEMS]

    # Under Pads always
    if "Under Pads / Chux" not in items:
        items.insert(0, "Under Pads / Chux")

    # unique preserve order
    seen = set()
    normalized = []
    for item in items:
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


def add_two_col_line(doc: Document, left: str, right: str = "", size: int = 11):
    table = doc.add_table(rows=1, cols=2)
    table.autofit = True
    table.columns[0].width = Pt(320)
    table.columns[1].width = Pt(200)

    row = table.rows[0]
    c1 = row.cells[0]
    c2 = row.cells[1]

    p1 = c1.paragraphs[0]
    r1 = p1.add_run(left)
    r1.font.name = "Times New Roman"
    r1.font.size = Pt(size)

    p2 = c2.paragraphs[0]
    r2 = p2.add_run(right)
    r2.font.name = "Times New Roman"
    r2.font.size = Pt(size)


# -----------------------------
# VN GENERATION
# -----------------------------

def generate_vn_docx(payload: IncontinenceRequest, items: List[str], details: List[EquipmentDetail], file_id: str) -> str:
    doc = Document()
    set_default_font(doc, 11)

    add_line(doc, "VISITING NOTE", bold=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_line(doc, f"Date of Examination: {payload.exam_date}", size=11)
    add_line(doc, "")

    add_line(doc, "PATIENT INFORMATION", bold=True, size=12)
    add_two_col_line(doc, f"Patient Name: {payload.patient_name}", f"DOB: {payload.dob}")
    add_two_col_line(doc, f"Age: {payload.age}", f"Sex: {payload.sex}")
    add_two_col_line(doc, f"Insurance ID: {payload.insurance_id}", f"Phone: {payload.patient_phone}")
    add_line(doc, f"Address: {payload.patient_address}")
    if payload.facility_name or payload.facility_address:
        add_line(doc, f"Facility: {payload.facility_name}")
        add_line(doc, f"Facility Address: {payload.facility_address}")
        if payload.facility_phone:
            add_line(doc, f"Facility Phone: {payload.facility_phone}")
    add_line(doc, "")

    add_line(doc, "PHYSICIAN INFORMATION", bold=True, size=12)
    add_line(doc, f"Physician: {payload.physician_name}")
    if payload.practice_name:
        add_line(doc, f"Practice: {payload.practice_name}")
    add_line(doc, f"Practice Address: {payload.practice_address}")
    add_two_col_line(doc, f"Phone: {payload.practice_phone}", f"Fax: {payload.practice_fax}")
    add_line(doc, f"NPI: {payload.npi}")
    add_line(doc, "")

    add_line(doc, "VITAL SIGNS", bold=True, size=12)
    add_two_col_line(doc, f"Height: {payload.vitals.height}", f"Weight: {payload.vitals.weight}")
    add_two_col_line(doc, f"Blood Pressure: {payload.vitals.blood_pressure}", f"Pulse: {payload.vitals.pulse}")
    add_two_col_line(doc, f"Respiration: {payload.vitals.respiration}", f"Temperature: {payload.vitals.temperature}")
    add_line(doc, "")

    add_line(doc, "DIAGNOSES", bold=True, size=12)
    for dx in payload.diagnoses:
        add_line(doc, f"{dx.code} - {dx.label}")
    add_line(doc, "")

    add_line(doc, "FUNCTIONAL STATUS", bold=True, size=12)
    add_line(doc, payload.functional_status)
    add_line(doc, "")

    add_line(doc, "COGNITIVE STATUS", bold=True, size=12)
    add_line(doc, payload.cognitive_status)
    add_line(doc, "")

    add_line(doc, "AMBULATORY STATUS", bold=True, size=12)
    add_line(doc, payload.ambulatory_status)
    add_line(doc, "")

    add_line(doc, "GENERAL HEALTH STATUS", bold=True, size=12)
    add_line(doc, payload.general_health_status)
    add_line(doc, "")

    add_line(doc, "INCONTINENCE ASSESSMENT", bold=True, size=12)
    add_line(
        doc,
        "Patient demonstrates bladder and/or bowel control impairment that is documented or clinically supported by existing diagnoses, with resulting limitation in toileting, hygiene, and related MRADLs. "
        "The patient requires structured incontinence management to reduce leakage exposure, maintain cleanliness, protect skin integrity, and reduce caregiver burden. "
        "Functional weakness and impaired mobility contribute to difficulty reaching the toilet safely and completing post-episode hygiene independently."
    )
    add_line(doc, "")

    add_line(doc, "REQUIRED MEDICAL EQUIPMENT & MEDICAL NECESSITY", bold=True, size=12)
    for i, detail in enumerate(details, start=1):
        add_line(doc, f"{i}. {detail.name}", bold=True, size=11)
        add_line(doc, f"Diagnosis: {detail.dx}")
        add_line(doc, f"Medical Necessity: {detail.medical_necessity}")
        add_line(doc, "")

    add_line(doc, "CLINICAL SUMMARY", bold=True, size=12)
    add_line(
        doc,
        "Based on the documented diagnoses and current functional limitations, the above incontinence supplies are medically necessary for safe management of urinary and/or bowel incontinence, hygiene dependency, MRADL limitation, skin protection, and caregiver-assisted care. "
        "The selected items are limited to clinically justified supplies and are consistent with the patient's documented condition and functional needs."
    )
    add_line(doc, "")

    add_line(doc, f"Physician Signature: ________________________________    Date: {payload.signature_date}")
    add_line(doc, f"{payload.physician_name}")

    filename = f"{sanitize_filename(payload.patient_name)}_{file_id}_VN.docx"
    path = os.path.join(OUTPUT_DIR, filename)
    doc.save(path)
    return path


# -----------------------------
# ORDER GENERATION
# -----------------------------

def generate_order_docx(payload: IncontinenceRequest, order: IncontinenceOrder, file_id: str) -> str:
    doc = Document()
    set_default_font(doc, 11)

    add_line(doc, "Incontinence Rx", bold=True, size=14, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_line(doc, "*** CONFIDENTIAL INCONTINENCE SUPPLIES PRESCRIPTION ***", bold=True, size=11, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_line(doc, "")

    add_two_col_line(doc, f"Patient Name: {payload.patient_name}", f"D.O.B: {payload.dob}")
    add_line(doc, f"Medical / LA Care ID: {payload.insurance_id}")
    add_line(doc, f"Male {checkbox(order.sex_male)}    Female {checkbox(order.sex_female)}")
    add_two_col_line(doc, f"Height: {payload.vitals.height}", f"Weight: {payload.vitals.weight}")
    add_line(doc, f"DIAGNOSIS: {payload.primary_diagnosis}")
    add_line(doc, f"Secondary: {payload.secondary_diagnoses}")
    add_line(doc, "")

    add_line(doc, "Qty / Description / Sizes / Allowable", bold=True, size=11)

    add_line(
        doc,
        f"{checkbox(order.disposable_brief)} Disposable Brief (Diapers)     "
        f"S {checkbox(order.size_s)}  M {checkbox(order.size_m)}  L {checkbox(order.size_l)}  XL-XXL {checkbox(order.size_xl_xxl)}"
    )

    add_line(
        doc,
        f"{checkbox(order.disposable_pullup)} Disposable Pull-Up            "
        f"S {checkbox(order.size_s)}  M {checkbox(order.size_m)}  L {checkbox(order.size_l)}  XL-XXL {checkbox(order.size_xl_xxl)}"
    )

    add_line(doc, f"{checkbox(order.underpads_chux)} Under Pads / Chux (Up to 120/month)")
    add_line(doc, f"{checkbox(order.absorbent_pads_liners)} Absorbent Pads / Liners (Up to 300/month)")
    add_line(
        doc,
        f"{checkbox(order.reusable_underpants)} Reusable Underpants          "
        f"S {checkbox(order.size_s)}  M {checkbox(order.size_m)}  L {checkbox(order.size_l)}  XL-XXL {checkbox(order.size_xl_xxl)}"
    )
    add_line(doc, f"{checkbox(order.waterproof_mattress_cover)} Waterproof Mattress Cover (2/year)")
    add_line(doc, f"{checkbox(order.incontinence_wash)} Incontinence Wash")
    add_line(doc, f"{checkbox(order.incontinence_cream)} Incontinence Cream")
    add_line(doc, f"{checkbox(order.gloves)} Gloves")
    add_line(doc, "")

    add_line(doc, f"Length of Need: 6 Months {checkbox(order.length_6_months)}    12 Months {checkbox(order.length_12_months)}")
    add_line(doc, f"Physician: {payload.physician_name}")
    add_line(doc, f"Address: {payload.practice_address}")
    add_line(doc, f"City: {payload.city}   State: {payload.state}   Zip: {payload.zip}")
    add_line(doc, f"Telephone: {payload.practice_phone}   Fax: {payload.practice_fax}   NPI #: {payload.npi}")
    add_line(doc, f"Signature: ________________________________    Date: {payload.signature_date}")

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

    items = normalize_equipment(payload)
    details = build_equipment_details(payload, items)
    order = synced_order(payload, items)

    file_id = datetime.utcnow().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:8]

    vn_path = generate_vn_docx(payload, items, details, file_id)
    order_path = generate_order_docx(payload, order, file_id)

    base_url = os.getenv("PUBLIC_BASE_URL", "https://incontinence-doc-engine.onrender.com")
    vn_url = f"{base_url}/generated/{os.path.basename(vn_path)}"
    order_url = f"{base_url}/generated/{os.path.basename(order_path)}"

    return {
        "status": "success",
        "vn_docx": vn_url,
        "order_docx": order_url,
        "equipment_list": items
    }
