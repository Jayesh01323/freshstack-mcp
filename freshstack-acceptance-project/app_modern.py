"""Version B: Modern FastAPI application conforming strictly to resolved versions."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Generator

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


# Modern SQLAlchemy 2.0 DeclarativeBase
class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    username: Mapped[str] = mapped_column(unique=True, index=True)
    email: Mapped[str] = mapped_column()


# Modern Pydantic v2 request model with ConfigDict and @field_validator
class UserCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        if "@" not in value:
            raise ValueError("Invalid email format")
        return value


# Application startup logic using modern lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    print("Initializing modern database connection pool via lifespan...")
    yield
    print("Shutting down database connections...")


app = FastAPI(title="Modern Acceptance App", lifespan=lifespan)

# Database setup
engine = create_engine("sqlite:///./acceptance_modern.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# API endpoint with database operation using modern select, model_dump, and model_validate
@app.post("/users", response_model=UserCreate)
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    # Modern Pydantic v2 model_dump() usage
    raw_data = user_in.model_dump()

    # Modern Pydantic v2 model_validate() usage
    validated_copy = UserCreate.model_validate(raw_data)

    # Modern SQLAlchemy 2.0 2.0-style select() and session.execute()
    stmt = select(UserModel).where(UserModel.email == validated_copy.email)
    existing = db.execute(stmt).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = UserModel(username=validated_copy.username, email=validated_copy.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user
