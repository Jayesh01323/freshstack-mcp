"""Version A: Intentionally legacy / incorrect FastAPI application."""

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, validator
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# SQLAlchemy legacy model using declarative_base()
Base = declarative_base()


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String)


# Pydantic legacy request model with inner Config and @validator
class UserCreate(BaseModel):
    username: str
    email: str

    @validator("email")
    def validate_email(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("Invalid email format")
        return value

    class Config:
        orm_mode = True


# Application startup logic using deprecated @app.on_event("startup")
app = FastAPI(title="Legacy Acceptance App")


@app.on_event("startup")
def startup_event():
    print("Initializing legacy database connection pool...")


# Database setup
engine = create_engine("sqlite:///./acceptance_legacy.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# API endpoint with database operation using legacy session.query, .dict(), and parse_obj()
@app.post("/users", response_model=UserCreate)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    # Legacy .dict() usage
    raw_data = user_in.dict()

    # Legacy parse_obj() usage
    validated_copy = UserCreate.parse_obj(raw_data)

    # Legacy SQLAlchemy session.query() usage
    existing = db.query(UserModel).filter(UserModel.email == validated_copy.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = UserModel(username=validated_copy.username, email=validated_copy.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
