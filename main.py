from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, String, Float
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase, Mapped, mapped_column

# 1. Database connection (finance.db file ban jayegi)
engine = create_engine("sqlite:///finance.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


# 2. Table ka design
class TransactionDB(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(String, default="")


Base.metadata.create_all(engine)  # table nahi hai to bana do


# 3. API ka data shape
class TransactionIn(BaseModel):
    amount: float
    type: str
    category: str
    note: str = ""


class TransactionOut(TransactionIn):
    id: int
    model_config = {"from_attributes": True}


# 4. Har request ko ek database session dena
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI()


@app.get("/")
def home():
    return {"message": "Finance API is running!"}


@app.post("/transactions", response_model=TransactionOut)
def add_transaction(t: TransactionIn, db: Session = Depends(get_db)):
    row = TransactionDB(**t.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/transactions", response_model=list[TransactionOut])
def list_transactions(db: Session = Depends(get_db)):
    return db.query(TransactionDB).all()


@app.delete("/transactions/{id}")
def delete_transaction(id: int, db: Session = Depends(get_db)):
    row = db.get(TransactionDB, id)
    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(row)
    db.commit()
    return {"message": "Transaction deleted"}


@app.put("/transaction/{id}",response_model = TransactionOut)
def update_transactions(id:int,t: TransactionIn, db: Session = Depends(get_db)):
    row = db.get(TransactionDB, id)
    if row is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    row.amount = t.amount
    row.type = t.type
    row.category = t.category
    row.note = t.note
    db.commit()
    db.refresh(row)
    return row