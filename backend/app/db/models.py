from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    contact_number = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    appointments = relationship("Appointment", back_populates="user")
    conversation_summaries = relationship("ConversationSummary", back_populates="user")

class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    appointment_date = Column(String, nullable=False)
    appointment_time = Column(String, nullable=False)
    status = Column(String, default="scheduled")  # scheduled, cancelled, completed
    purpose = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    user = relationship("User", back_populates="appointments")

class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String, nullable=True, index=True)
    summary = Column(String, nullable=False)
    appointments_discussed = Column(String, nullable=True)
    user_preferences = Column(String, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    total_cost = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    user = relationship("User", back_populates="conversation_summaries")
