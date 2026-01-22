from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db import models
from app.schemas import schemas
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token,
    get_current_user
)
from datetime import timedelta

router = APIRouter()

@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: schemas.UserRegister, db: Session = Depends(get_db)):
    """
    Register a new user
    
    - **contact_number**: Unique phone number (required)
    - **name**: User's name (optional)
    - **email**: User's email (optional)
    - **password**: User's password (required)
    """
    # Check if user already exists
    existing_user = db.query(models.User).filter(
        models.User.contact_number == user_data.contact_number
    ).first()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this contact number already exists"
        )
    
    # Check if email already exists (if provided)
    if user_data.email:
        existing_email = db.query(models.User).filter(
            models.User.email == user_data.email
        ).first()
        
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = models.User(
        contact_number=user_data.contact_number,
        name=user_data.name,
        email=user_data.email,
        hashed_password=hashed_password,
        is_active=True
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@router.post("/login", response_model=schemas.Token)
def login_user(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    """
    Login user and return JWT token
    
    - **contact_number**: User's phone number
    - **password**: User's password
    """
    # Find user by contact number
    user = db.query(models.User).filter(
        models.User.contact_number == user_credentials.contact_number
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.contact_number},
        expires_delta=access_token_expires
    )
    
    # Create refresh token
    refresh_token = create_refresh_token(
        data={"sub": user.contact_number}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=schemas.Token)
def refresh_access_token(refresh_data: schemas.RefreshToken, db: Session = Depends(get_db)):
    """
    Refresh access token using a valid refresh token
    
    - **refresh_token**: The refresh token received during login
    """
    # Verify the refresh token
    payload = verify_refresh_token(refresh_data.refresh_token)
    
    contact_number: str = payload.get("sub")
    if contact_number is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user still exists and is active
    user = db.query(models.User).filter(
        models.User.contact_number == contact_number
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create new access token
    access_token_expires = timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.contact_number},
        expires_delta=access_token_expires
    )
    
    # Create new refresh token (token rotation for security)
    new_refresh_token = create_refresh_token(
        data={"sub": user.contact_number}
    )
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }

@router.get("/me", response_model=schemas.UserResponse)
def get_current_user_info(current_user: models.User = Depends(get_current_user)):
    """
    Get current authenticated user information
    
    Requires: Bearer token in Authorization header
    """
    return current_user

@router.post("/logout")
def logout_user(current_user: models.User = Depends(get_current_user)):
    """
    Logout user (client should discard the token)
    
    Requires: Bearer token in Authorization header
    """
    return {
        "message": "Successfully logged out",
        "detail": "Please discard your token on the client side"
    }
