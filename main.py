from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

transactions = []  


class Transaction(BaseModel):
    amount: float
    type: str       
    category: str
    note: str = ""


@app.get("/")
def home():
    return {"message": "Finance API is running!"}


@app.post("/transactions")
def add_transaction(t: Transaction):
    data = t.model_dump()
    data["id"] = len(transactions) + 1
    transactions.append(data)
    return data


@app.get("/transactions")
def list_transactions():
    return transactions