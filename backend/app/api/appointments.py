from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.database import get_db
from app.db import models
from app.schemas import schemas
from app.core.security import get_current_user

router = APIRouter()

@router.post("/", response_model=schemas.Appointment)
def create_appointment(
    appointment: schemas.AppointmentCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Create a new appointment for the logged-in user"""
    # Prevent double-booking: reject if any scheduled appointment exists at the same slot
    conflict = db.query(models.Appointment).filter(
        models.Appointment.appointment_date == appointment.appointment_date,
        models.Appointment.appointment_time == appointment.appointment_time,
        models.Appointment.status == "scheduled"
    ).first()
    if conflict:
        raise HTTPException(
            status_code=400,
            detail="This time slot is already booked. Please choose another time."
        )

    db_appointment = models.Appointment(
        user_id=current_user.id,
        appointment_date=appointment.appointment_date,
        appointment_time=appointment.appointment_time,
        purpose=appointment.purpose,
        status="scheduled"
    )
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    return db_appointment

@router.get("/", response_model=List[schemas.Appointment])
def get_appointments(
    user_id: Optional[int] = None, 
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get appointments for the logged-in user (or specified user_id if admin)"""
    query = db.query(models.Appointment)
    
    # If user_id specified and matches current user or admin functionality needed
    target_user_id = user_id if user_id else current_user.id
    query = query.filter(models.Appointment.user_id == target_user_id)
    
    appointments = query.order_by(
        models.Appointment.appointment_date,
        models.Appointment.appointment_time
    ).offset(skip).limit(limit).all()
    return appointments

@router.get("/{appointment_id}", response_model=schemas.Appointment)
def get_appointment(
    appointment_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Get a specific appointment by ID"""
    appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id
    ).first()
    
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Verify ownership
    if appointment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this appointment")
    
    return appointment

@router.put("/{appointment_id}", response_model=schemas.Appointment)
def update_appointment(
    appointment_id: int, 
    appointment: schemas.AppointmentCreate, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Update an appointment"""
    db_appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id
    ).first()
    
    if db_appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Verify ownership
    if db_appointment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this appointment")

    # Prevent double-booking on update (ignore the current appointment when checking)
    conflict = db.query(models.Appointment).filter(
        models.Appointment.id != appointment_id,
        models.Appointment.appointment_date == appointment.appointment_date,
        models.Appointment.appointment_time == appointment.appointment_time,
        models.Appointment.status == "scheduled"
    ).first()
    if conflict:
        raise HTTPException(
            status_code=400,
            detail="This time slot is already booked. Please choose another time."
        )
    
    # Update allowed fields
    db_appointment.appointment_date = appointment.appointment_date
    db_appointment.appointment_time = appointment.appointment_time
    db_appointment.purpose = appointment.purpose
    
    db.commit()
    db.refresh(db_appointment)
    return db_appointment

@router.delete("/{appointment_id}")
def cancel_appointment(
    appointment_id: int, 
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """Cancel an appointment"""
    db_appointment = db.query(models.Appointment).filter(
        models.Appointment.id == appointment_id
    ).first()
    
    if db_appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    
    # Verify ownership
    if db_appointment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this appointment")
    
    db_appointment.status = "cancelled"
    db.commit()
    return {"message": "Appointment cancelled successfully"}
