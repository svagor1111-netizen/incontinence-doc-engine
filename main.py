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
    selection_mode: str = Field(default="max")
    command: Optional[str] = ""
    explicit_items: List[str] = Field(default_factory=list)

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
# HELPERS (НЕ ТРОГАЛ)
# -----------------------------

def clean_text(text: str) -> str:
    return (text or "").strip()


def checkbox(value: bool) -> str:
    return "☑" if value else "☐"


def determine_selection_mode(payload: IncontinenceRequest) -> str:
    for v in [payload.selection_mode, payload.command, payload.mode]:
        v = clean_text(v).lower()
        if v in {"lvn", "list_only"}:
            return "list_only"
    return "max"


# -----------------------------
# LOGIC (НЕ ТРОГАЛ)
# -----------------------------

def normalize_equipment(payload: IncontinenceRequest) -> List[str]:
    mode = determine_selection_mode(payload)

    if mode == "list_only":
        return payload.explicit_items

    items = list(payload.equipment_list)
    if "Under Pads / Chux" not in items:
        items.insert(0, "Under Pads / Chux")

    return items


# -----------------------------
# 🔥 FIX ТОЛЬКО ЗДЕСЬ
# -----------------------------

def synced_order(payload: IncontinenceRequest, items: List[str]) -> IncontinenceOrder:
    order = payload.incontinence_order.model_copy(deep=True)

    # SIZE FIX
    size_specified = any([
        order.size_s,
        order.size_m,
        order.size_l,
        order.size_xl_xxl
    ])

    if not size_specified:
        order.size_s = False
        order.size_m = False
        order.size_l = False
        order.size_xl_xxl = False

    for item, field_name in ITEM_TO_ORDER_FIELD.items():
        setattr(order, field_name, item in items)

    sex = clean_text(payload.sex).lower()
    order.sex_male = sex == "male"
    order.sex_female = sex == "female"

    order.length_6_months = False
    order.length_12_months = True

    return order


# -----------------------------
# ROUTE
# -----------------------------

@app.post("/create_dme_documents")
def create_dme_documents(payload: IncontinenceRequest):
    mode = determine_selection_mode(payload)
    items = normalize_equipment(payload)

    if mode == "list_only" and not items:
        return {"error": "No item list provided for LIST ONLY mode."}

    order = synced_order(payload, items)

    return {
        "status": "ok",
        "mode": mode,
        "items": items,
        "sizes": {
            "S": order.size_s,
            "M": order.size_m,
            "L": order.size_l,
            "XL": order.size_xl_xxl
        }
    }
