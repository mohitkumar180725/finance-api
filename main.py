import jwt
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordRequestForm, OAuth2PasswordBearer
import bcrypt
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, String, Float , ForeignKey
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
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class UserDB(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)

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

class UserCreate(BaseModel):
    name: str
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    model_config = {"from_attributes": True}
# 4. Har request ko ek database session dena
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

SECRET_KEY = "change-this-later-to-a-long-random-string"
ALGORITHM = "HS256"


def create_token(user_id: int):
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


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
app = FastAPI()


@app.get("/")
def home():
    return {"message": "Finance API is running!"}

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
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    return db.query(TransactionDB).filter(TransactionDB.user_id == current_user.id).all()


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
    db.commit()
    db.refresh(row)
    return row

@app.post("/auth/register",response_model = UserOut)
def register(u: UserCreate,db:session= Depends(get_db)):
    existing = db.query(UserDB).filter(UserDB.email== u.email).first()
    if existing:
        raise HTTPException(status_code= 400,detail="Email already registered")
    hashed= bcrypt.hashpw(u.password.encode(), bcrypt.gensalt()).decode()
    user = UserDB(name=u.name, email=u.email, password_hash=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/auth/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.email == form.username).first()
    if user is None or not bcrypt.checkpw(form.password.encode(), user.password_hash.encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user.id)
    return {"access_token": token, "token_type": "bearer"}

@app.get("/auth/me", response_model=UserOut)
def me(current_user: UserDB = Depends(get_current_user)):
    return current_user

    
