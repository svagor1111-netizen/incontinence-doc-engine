from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "incontinence backend running"}

@app.post("/create_dme_documents")
def create_dme_documents(data: dict):
    return {
        "vn_docx": "https://example.com/vn.docx",
        "order_docx": "https://example.com/order.docx"
    }
