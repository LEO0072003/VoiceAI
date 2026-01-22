from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    contact_number: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None

class UserRegister(BaseModel):
    contact_number: str
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: str

class UserLogin(BaseModel):
    contact_number: str
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

class RefreshToken(BaseModel):
    refresh_token: str

class TokenData(BaseModel):
    contact_number: Optional[str] = None

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class AppointmentBase(BaseModel):
    user_id: Optional[int] = None  # New - FK to users table
    appointment_date: str
    appointment_time: str
    purpose: Optional[str] = None  # Renamed from notes

class AppointmentCreate(AppointmentBase):
    pass

class Appointment(AppointmentBase):
    id: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class ConversationSummaryCreate(BaseModel):
    user_id: Optional[int] = None  # New - FK to users table
    session_id: Optional[str] = None  # New - Tavus session ID
    summary: str
    appointments_discussed: Optional[str] = None
    user_preferences: Optional[str] = None
    duration_seconds: Optional[int] = None  # New - call duration
    total_cost: Optional[float] = None  # New - total cost in USD

class ConversationSummary(ConversationSummaryCreate):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True
