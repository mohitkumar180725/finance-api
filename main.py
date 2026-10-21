import bcrypt
import jwt
from datetime import datetime, timedelta, timezone, date as DateType
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Float, ForeignKey, Date, func
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase, Mapped, mapped_column

# ---------- 1. Database ----------
engine = create_engine("sqlite:///finance.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)


class TransactionDB(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    amount: Mapped[float] = mapped_column(Float)
    type: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String)
    note: Mapped[str] = mapped_column(String, default="")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    date: Mapped[DateType] = mapped_column(Date, default=DateType.today)


Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------- 2. Data shapes (validation) ----------
class TransactionIn(BaseModel):
    amount: float = Field(gt=0)
    type: Literal["income", "expense"]
    category: str
    note: str = ""
    date: DateType = Field(default_factory=DateType.today)


class TransactionOut(TransactionIn):
    id: int
    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    model_config = {"from_attributes": True}


# ---------- 3. Auth helpers ----------
SECRET_KEY = "change-this-later-to-a-long-random-string"
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def create_token(user_id: int):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(UserDB, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ---------- 4. Month helper (filters aur summary dono use karte hain) ----------
def month_range(month: str):
    try:
        year, mon = map(int, month.split("-"))
        start = DateType(year, mon, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be in YYYY-MM format")
    end = DateType(year + 1, 1, 1) if mon == 12 else DateType(year, mon + 1, 1)
    return start, end


# ---------- 5. Endpoints ----------
app = FastAPI()


@app.get("/")
def home():
    return {"message": "Finance API is running!"}


@app.post("/auth/register", response_model=UserOut)
def register(u: UserCreate, db: Session = Depends(get_db)):
    email = u.email.lower()
    existing = db.query(UserDB).filter(UserDB.email == email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = bcrypt.hashpw(u.password.encode(), bcrypt.gensalt()).decode()
    user = UserDB(name=u.name, email=email, password_hash=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == form.username.lower()).first()
    if user is None or not bcrypt.checkpw(form.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user.id)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/auth/me", response_model=UserOut)
def me(current_user: UserDB = Depends(get_current_user)):
    return current_user


@app.post("/transactions", response_model=TransactionOut)
def add_transaction(
    t: TransactionIn,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    row = TransactionDB(**t.model_dump(), user_id=current_user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/transactions", response_model=list[TransactionOut])
def list_transactions(
    month: str | None = None,
    category: str | None = None,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    query = db.query(TransactionDB).filter(TransactionDB.user_id == current_user.id)
    if category:
        query = query.filter(TransactionDB.category == category)
    if month:
        start, end = month_range(month)
        query = query.filter(TransactionDB.date >= start, TransactionDB.date < end)
    return query.order_by(TransactionDB.date.desc()).all()


@app.put("/transactions/{id}", response_model=TransactionOut)
def update_transaction(
    id: int,
    t: TransactionIn,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    row = db.get(TransactionDB, id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    row.amount = t.amount
    row.type = t.type
    row.category = t.category
    row.note = t.note
    row.date = t.date
    db.commit()
    db.refresh(row)
    return row


@app.delete("/transactions/{id}")
def delete_transaction(
    id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    row = db.get(TransactionDB, id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(row)
    db.commit()
    return {"message": "Transaction deleted"}


@app.get("/summary/monthly")
def monthly_summary(
    month: str,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    start, end = month_range(month)
    rows = (
        db.query(TransactionDB.type, func.sum(TransactionDB.amount))
        .filter(
            TransactionDB.user_id == current_user.id,
            TransactionDB.date >= start,
            TransactionDB.date < end,
        )
        .group_by(TransactionDB.type)
        .all()
    )
    totals = {t: total for t, total in rows}
    income = totals.get("income", 0)
    expense = totals.get("expense", 0)
    return {
        "month": month,
        "total_income": income,
        "total_expense": expense,
        "balance": income - expense,
    }