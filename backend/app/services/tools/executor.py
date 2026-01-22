"""
Tool Executor
Handles execution of tools called by the LLM
Appointments are stored in PostgreSQL database for persistence
"""
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.redis_client import redis_client
from app.core.session_manager import session_manager
from app.db.database import SessionLocal
from app.db.models import Appointment, User

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Executes tools called by the LLM and returns results.
    Appointments are stored in PostgreSQL for persistence.
    Session state is stored in Redis.
    
    When user_id is provided (from JWT auth), the executor operates
    in "authenticated mode" - no need to identify user during call.
    """
    
    # Hardcoded available time slots (as per assignment requirements)
    AVAILABLE_SLOTS = ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00", "17:00", "18:00"]
    
    def __init__(self, session_id: str, user_id: Optional[int] = None, user_name: Optional[str] = None):
        self.session_id = session_id
        self.user_id = user_id  # Authenticated user ID from JWT
        self.user_name = user_name  # User's name for personalization
        
        logger.info(f"[ToolExecutor] Initialized for session={session_id}, user_id={user_id}, user_name={user_name}")
        
        # If user_id provided, mark session as pre-identified
        if user_id:
            session_manager.set_metadata(self.session_id, "authenticated_user_id", user_id)
            session_manager.set_metadata(self.session_id, "authenticated_user_name", user_name or "User")
            logger.info(f"[ToolExecutor] Session metadata set for authenticated user_id={user_id}")
    
    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool and return the result.
        
        Returns:
            Result dict from tool execution
        """
        logger.info(f"[TOOL CALL] ========================================")
        logger.info(f"[TOOL CALL] Tool: {tool_name}")
        logger.info(f"[TOOL CALL] Session: {self.session_id}")
        logger.info(f"[TOOL CALL] User ID: {self.user_id}")
        logger.info(f"[TOOL CALL] Arguments: {json.dumps(arguments, indent=2)}")
        
        method = getattr(self, f"_execute_{tool_name}", None)
        if not method:
            logger.error(f"[TOOL CALL] Unknown tool: {tool_name}")
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        try:
            result = await method(arguments)
            logger.info(f"[TOOL RESULT] Success: {result.get('success', False)}")
            logger.info(f"[TOOL RESULT] Data: {json.dumps(result, indent=2, default=str)}")
            logger.info(f"[TOOL CALL] ========================================")
            return result
        except Exception as e:
            logger.error(f"[TOOL ERROR] {tool_name} failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_current_user_id(self) -> Optional[int]:
        """Get the current user ID - either from constructor or session metadata"""
        if self.user_id:
            return self.user_id
        # Fallback to session metadata (for backwards compatibility)
        return session_manager.get_metadata(self.session_id, "authenticated_user_id")
    
    # =========================================================================
    # TOOL IMPLEMENTATIONS
    # =========================================================================
    
    async def _execute_identify_user(self, args: Dict[str, Any]) -> Dict:
        """
        Identify user by phone number - for backwards compatibility.
        In authenticated mode, this is not needed but can still work.
        """
        # If already authenticated via JWT, just confirm
        if self.user_id:
            return {
                "success": True,
                "message": f"User already authenticated as {self.user_name or 'User'}",
                "user_id": self.user_id,
                "already_authenticated": True
            }
        
        contact_number = args.get("contact_number", "").strip()
        
        # Validate phone number (basic validation)
        contact_number = ''.join(filter(str.isdigit, contact_number))
        if len(contact_number) < 10:
            return {
                "success": False,
                "error": "Invalid phone number. Please provide a 10-digit number."
            }
        
        # Look up user by phone number in database
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.contact_number == contact_number).first()
            if user:
                # Store user_id in session
                session_manager.set_metadata(self.session_id, "authenticated_user_id", user.id)
                session_manager.set_metadata(self.session_id, "authenticated_user_name", user.name)
                self.user_id = user.id
                self.user_name = user.name
                
                # Check existing appointments
                existing = self._get_user_appointments_from_db(user.id)
                
                return {
                    "success": True,
                    "user_id": user.id,
                    "user_name": user.name,
                    "message": f"Welcome back, {user.name or 'User'}!",
                    "existing_appointments_count": len(existing)
                }
            else:
                return {
                    "success": False,
                    "error": "No user found with that phone number. Please register first."
                }
        finally:
            db.close()
    
    async def _execute_fetch_slots(self, args: Dict[str, Any]) -> Dict:
        """Fetch available slots for a date - checks DB for already booked slots"""
        date_str = args.get("date", "")
        logger.info(f"[FETCH_SLOTS] Requested date: {date_str}")
        
        # Parse and validate date
        try:
            date = self._parse_date(date_str)
            date_formatted = date.strftime("%Y-%m-%d")
            logger.info(f"[FETCH_SLOTS] Parsed date: {date_formatted}")
        except ValueError as e:
            logger.error(f"[FETCH_SLOTS] Invalid date format: {e}")
            return {
                "success": False,
                "error": f"Invalid date format: {e}"
            }
        
        # Get booked slots for this date from DATABASE
        logger.info(f"[FETCH_SLOTS] Querying DB for booked slots on {date_formatted}")
        booked_slots = self._get_booked_slots_from_db(date_formatted)
        logger.info(f"[FETCH_SLOTS] DB returned booked_slots: {booked_slots}")
        
        # Calculate available slots (exclude already booked)
        available = [slot for slot in self.AVAILABLE_SLOTS if slot not in booked_slots]
        logger.info(f"[FETCH_SLOTS] Available slots: {available}")
        
        return {
            "success": True,
            "date": date_formatted,
            "date_display": date.strftime("%A, %B %d, %Y"),
            "available_slots": available,
            "booked_slots": booked_slots,
            "message": f"Found {len(available)} available slots on {date_formatted}"
        }
    
    async def _execute_book_appointment(self, args: Dict[str, Any]) -> Dict:
        """Book a new appointment - saves to PostgreSQL database"""
        # Get authenticated user
        user_id = self._get_current_user_id()
        logger.info(f"[BOOK_APPT] Starting booking for user_id={user_id}")
        
        if not user_id:
            logger.error("[BOOK_APPT] No authenticated user found")
            return {
                "success": False,
                "error": "User not authenticated. Please log in first."
            }
        
        date_str = args.get("date", "")
        time_str = args.get("time", "")
        purpose = args.get("purpose", "General appointment")
        logger.info(f"[BOOK_APPT] Request: date={date_str}, time={time_str}, purpose={purpose}")
        
        # Parse date
        try:
            date = self._parse_date(date_str)
            date_formatted = date.strftime("%Y-%m-%d")
            logger.info(f"[BOOK_APPT] Parsed date: {date_formatted}")
        except ValueError as e:
            logger.error(f"[BOOK_APPT] Invalid date: {e}")
            return {
                "success": False,
                "error": f"Invalid date: {e}"
            }
        
        # Validate time
        time_str = self._normalize_time(time_str)
        logger.info(f"[BOOK_APPT] Normalized time: {time_str}")
        if time_str not in self.AVAILABLE_SLOTS:
            logger.error(f"[BOOK_APPT] Invalid time slot: {time_str}")
            return {
                "success": False,
                "error": f"Invalid time slot. Available slots are: {', '.join(self.AVAILABLE_SLOTS)}"
            }
        
        # Check if slot is available (from DATABASE to prevent double booking)
        logger.info(f"[BOOK_APPT] Checking slot availability in DB for {date_formatted} {time_str}")
        booked_slots = self._get_booked_slots_from_db(date_formatted)
        logger.info(f"[BOOK_APPT] Currently booked slots: {booked_slots}")
        if time_str in booked_slots:
            logger.warning(f"[BOOK_APPT] Slot {time_str} already booked")
            return {
                "success": False,
                "error": f"Sorry, {time_str} on {date_formatted} is already booked. Please choose another slot."
            }
        
        # Check for double booking by same user at same date/time
        logger.info(f"[BOOK_APPT] Fetching existing appointments for user_id={user_id}")
        user_appointments = self._get_user_appointments_from_db(user_id)
        logger.info(f"[BOOK_APPT] User has {len(user_appointments)} existing appointments")
        for appt in user_appointments:
            if appt["date"] == date_formatted and appt["time"] == time_str and appt["status"] == "scheduled":
                logger.warning(f"[BOOK_APPT] User already has appointment at {date_formatted} {time_str}")
                return {
                    "success": False,
                    "error": "You already have an appointment at this date and time."
                }
        
        # Create appointment in DATABASE
        logger.info(f"[BOOK_APPT] Creating appointment in DB: user_id={user_id}, date={date_formatted}, time={time_str}")
        db = SessionLocal()
        try:
            new_appointment = Appointment(
                user_id=user_id,
                appointment_date=date_formatted,
                appointment_time=time_str,
                status="scheduled",
                purpose=purpose
            )
            db.add(new_appointment)
            db.commit()
            db.refresh(new_appointment)
            appointment_id = new_appointment.id
            logger.info(f"[BOOK_APPT] SUCCESS! Created appointment id={appointment_id}")
        except Exception as e:
            logger.error(f"[BOOK_APPT] DB error: {e}", exc_info=True)
            raise
        finally:
            db.close()
        
        return {
            "success": True,
            "appointment_id": str(appointment_id),
            "date": date_formatted,
            "date_display": date.strftime("%A, %B %d, %Y"),
            "time": time_str,
            "purpose": purpose,
            "message": f"Appointment booked for {date.strftime('%A, %B %d')} at {time_str}"
        }
    
    async def _execute_retrieve_appointments(self, args: Dict[str, Any]) -> Dict:
        """Retrieve user's appointments from database"""
        user_id = self._get_current_user_id()
        logger.info(f"[RETRIEVE_APPTS] Request for user_id={user_id}")
        
        if not user_id:
            logger.error("[RETRIEVE_APPTS] No authenticated user")
            return {
                "success": False,
                "error": "User not authenticated. Please log in first."
            }
        
        include_cancelled = args.get("include_cancelled", False)
        logger.info(f"[RETRIEVE_APPTS] include_cancelled={include_cancelled}")
        
        appointments = self._get_user_appointments_from_db(user_id)
        logger.info(f"[RETRIEVE_APPTS] DB returned {len(appointments)} appointments")
        
        # Filter cancelled if needed
        if not include_cancelled:
            appointments = [a for a in appointments if a.get("status") != "cancelled"]
            logger.info(f"[RETRIEVE_APPTS] After filter: {len(appointments)} appointments")
        
        # Sort by date and time
        appointments.sort(key=lambda x: (x.get("date", ""), x.get("time", "")))
        
        # Categorize
        today = datetime.now().strftime("%Y-%m-%d")
        upcoming = [a for a in appointments if a.get("date", "") >= today and a.get("status") == "scheduled"]
        past = [a for a in appointments if a.get("date", "") < today or a.get("status") != "scheduled"]
        logger.info(f"[RETRIEVE_APPTS] Upcoming: {len(upcoming)}, Past: {len(past)}")
        
        return {
            "success": True,
            "user_id": user_id,
            "total_count": len(appointments),
            "upcoming": upcoming,
            "upcoming_count": len(upcoming),
            "past": past,
            "past_count": len(past),
            "message": f"Found {len(upcoming)} upcoming and {len(past)} past appointments"
        }
    
    async def _execute_cancel_appointment(self, args: Dict[str, Any]) -> Dict:
        """Cancel an appointment in database"""
        user_id = self._get_current_user_id()
        logger.info(f"[CANCEL_APPT] Request for user_id={user_id}")
        
        if not user_id:
            logger.error("[CANCEL_APPT] No authenticated user")
            return {
                "success": False,
                "error": "User not authenticated. Please log in first."
            }
        
        appointment_id = args.get("appointment_id", "")
        logger.info(f"[CANCEL_APPT] Appointment ID: {appointment_id}")
        
        # Get appointment from database
        db = SessionLocal()
        try:
            appointment = db.query(Appointment).filter(Appointment.id == int(appointment_id)).first()
            if not appointment:
                logger.error(f"[CANCEL_APPT] Appointment {appointment_id} not found")
                return {
                    "success": False,
                    "error": f"Appointment {appointment_id} not found."
                }
            
            logger.info(f"[CANCEL_APPT] Found appointment: user_id={appointment.user_id}, date={appointment.appointment_date}, status={appointment.status}")
            
            # Verify ownership
            if appointment.user_id != user_id:
                logger.error(f"[CANCEL_APPT] Ownership mismatch: appt.user_id={appointment.user_id}, request.user_id={user_id}")
                return {
                    "success": False,
                    "error": "This appointment doesn't belong to you."
                }
            
            if appointment.status == "cancelled":
                logger.warning(f"[CANCEL_APPT] Appointment already cancelled")
                return {
                    "success": False,
                    "error": "This appointment is already cancelled."
                }
            
            # Cancel in database
            appointment.status = "cancelled"
            db.commit()
            logger.info(f"[CANCEL_APPT] SUCCESS - Appointment {appointment_id} cancelled")
            
            return {
                "success": True,
                "appointment_id": appointment_id,
                "date": appointment.appointment_date,
                "time": appointment.appointment_time,
                "message": f"Appointment on {appointment.appointment_date} at {appointment.appointment_time} has been cancelled."
            }
        except ValueError:
            logger.error(f"[CANCEL_APPT] Invalid appointment ID: {appointment_id}")
            return {
                "success": False,
                "error": f"Invalid appointment ID: {appointment_id}"
            }
        finally:
            db.close()
    
    async def _execute_modify_appointment(self, args: Dict[str, Any]) -> Dict:
        """Modify an appointment in database"""
        user_id = self._get_current_user_id()
        logger.info(f"[MODIFY_APPT] Request for user_id={user_id}")
        
        if not user_id:
            logger.error("[MODIFY_APPT] No authenticated user")
            return {
                "success": False,
                "error": "User not authenticated. Please log in first."
            }
        
        appointment_id = args.get("appointment_id", "")
        new_date = args.get("new_date")
        new_time = args.get("new_time")
        logger.info(f"[MODIFY_APPT] appointment_id={appointment_id}, new_date={new_date}, new_time={new_time}")
        
        if not new_date and not new_time:
            logger.error("[MODIFY_APPT] No new date or time provided")
            return {
                "success": False,
                "error": "Please specify a new date or time to modify."
            }
        
        db = SessionLocal()
        try:
            # Get appointment from database
            appointment = db.query(Appointment).filter(Appointment.id == int(appointment_id)).first()
            if not appointment:
                logger.error(f"[MODIFY_APPT] Appointment {appointment_id} not found")
                return {
                    "success": False,
                    "error": f"Appointment {appointment_id} not found."
                }
            
            logger.info(f"[MODIFY_APPT] Found appointment: user_id={appointment.user_id}, date={appointment.appointment_date}, time={appointment.appointment_time}")
            
            # Verify ownership
            if appointment.user_id != user_id:
                logger.error(f"[MODIFY_APPT] Ownership mismatch: appt.user_id={appointment.user_id}, request.user_id={user_id}")
                return {
                    "success": False,
                    "error": "This appointment doesn't belong to you."
                }
            
            if appointment.status == "cancelled":
                return {
                    "success": False,
                    "error": "Cannot modify a cancelled appointment."
                }
            
            # Parse new date if provided
            target_date = appointment.appointment_date
            if new_date:
                try:
                    date_obj = self._parse_date(new_date)
                    target_date = date_obj.strftime("%Y-%m-%d")
                except ValueError as e:
                    return {
                        "success": False,
                        "error": f"Invalid new date: {e}"
                    }
            
            # Parse new time if provided
            target_time = appointment.appointment_time
            if new_time:
                target_time = self._normalize_time(new_time)
                if target_time not in self.AVAILABLE_SLOTS:
                    return {
                        "success": False,
                        "error": f"Invalid time. Available: {', '.join(self.AVAILABLE_SLOTS)}"
                    }
            
            # Check slot availability (exclude current appointment)
            logger.info(f"[MODIFY_APPT] Checking availability for {target_date} {target_time}")
            booked_slots = self._get_booked_slots_from_db(target_date, exclude_appointment_id=int(appointment_id))
            logger.info(f"[MODIFY_APPT] Booked slots: {booked_slots}")
            
            if target_time in booked_slots:
                logger.warning(f"[MODIFY_APPT] Slot {target_time} already booked")
                return {
                    "success": False,
                    "error": f"Sorry, {target_time} on {target_date} is already booked."
                }
            
            # Update appointment in database
            old_date, old_time = appointment.appointment_date, appointment.appointment_time
            appointment.appointment_date = target_date
            appointment.appointment_time = target_time
            db.commit()
            logger.info(f"[MODIFY_APPT] SUCCESS - Changed from {old_date} {old_time} to {target_date} {target_time}")
            
            return {
                "success": True,
                "appointment_id": appointment_id,
                "old_date": old_date,
                "old_time": old_time,
                "new_date": target_date,
                "new_time": target_time,
                "message": f"Appointment changed from {old_date} {old_time} to {target_date} {target_time}"
            }
        except ValueError:
            logger.error(f"[MODIFY_APPT] Invalid appointment ID: {appointment_id}")
            return {
                "success": False,
                "error": f"Invalid appointment ID: {appointment_id}"
            }
        finally:
            db.close()
    
    async def _execute_end_conversation(self, args: Dict[str, Any]) -> Dict:
        """End the conversation"""
        reason = args.get("reason", "user_request")
        
        return {
            "success": True,
            "reason": reason,
            "message": "Ending conversation. Goodbye!"
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse various date formats including relative dates"""
        date_str = date_str.lower().strip()
        today = datetime.now()
        
        # Handle relative dates
        if date_str in ["today", "now"]:
            return today
        elif date_str == "tomorrow":
            return today + timedelta(days=1)
        elif date_str == "day after tomorrow":
            return today + timedelta(days=2)
        elif "next" in date_str:
            # Handle "next monday", "next week", etc.
            days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
            for i, day in enumerate(days):
                if day in date_str:
                    current_day = today.weekday()
                    days_ahead = i - current_day
                    if days_ahead <= 0:
                        days_ahead += 7
                    return today + timedelta(days=days_ahead)
            if "week" in date_str:
                return today + timedelta(days=7)
        
        # Try parsing standard formats
        formats = ["%Y-%m-%d", "%d-%m-%Y", "%m/%d/%Y", "%d/%m/%Y", "%B %d", "%b %d", "%d %B", "%d %b"]
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                # If year not in format, use current year
                if parsed.year == 1900:
                    parsed = parsed.replace(year=today.year)
                    # If date is in past, use next year
                    if parsed < today:
                        parsed = parsed.replace(year=today.year + 1)
                return parsed
            except ValueError:
                continue
        
        raise ValueError(f"Could not parse date: {date_str}")
    
    def _normalize_time(self, time_str: str) -> str:
        """Normalize time to HH:MM format"""
        time_str = time_str.lower().strip()
        
        # Remove spaces
        time_str = time_str.replace(" ", "")
        
        # Handle am/pm
        is_pm = "pm" in time_str or "p.m" in time_str
        is_am = "am" in time_str or "a.m" in time_str
        time_str = time_str.replace("pm", "").replace("am", "").replace("p.m.", "").replace("a.m.", "").replace(".", "")
        
        # Try to parse
        try:
            if ":" in time_str:
                hour, minute = time_str.split(":")
                hour = int(hour)
                minute = int(minute) if minute else 0
            else:
                hour = int(time_str)
                minute = 0
            
            # Adjust for PM
            if is_pm and hour < 12:
                hour += 12
            elif is_am and hour == 12:
                hour = 0
            
            return f"{hour:02d}:{minute:02d}"
        except:
            return time_str
    
    def _get_booked_slots_from_db(self, date: str, exclude_appointment_id: Optional[int] = None) -> List[str]:
        """Get all booked slots for a date from PostgreSQL database"""
        logger.info(f"[DB_QUERY] Fetching booked slots for date={date}, exclude_id={exclude_appointment_id}")
        db = SessionLocal()
        try:
            query = db.query(Appointment).filter(
                Appointment.appointment_date == date,
                Appointment.status == "scheduled"
            )
            if exclude_appointment_id:
                query = query.filter(Appointment.id != exclude_appointment_id)
            
            appointments = query.all()
            booked_slots = [appt.appointment_time for appt in appointments]
            logger.info(f"[DB_QUERY] Found {len(appointments)} booked appointments: {booked_slots}")
            return booked_slots
        finally:
            db.close()
    
    def _get_user_appointments_from_db(self, user_id: int) -> List[Dict]:
        """Get appointments for a specific user from PostgreSQL database by user_id"""
        logger.info(f"[DB_QUERY] Fetching appointments for user_id={user_id}")
        db = SessionLocal()
        try:
            appointments = db.query(Appointment).filter(
                Appointment.user_id == user_id
            ).order_by(Appointment.appointment_date, Appointment.appointment_time).all()
            
            result = [
                {
                    "id": str(appt.id),
                    "date": appt.appointment_date,
                    "time": appt.appointment_time,
                    "status": appt.status,
                    "purpose": appt.purpose or "",
                    "created_at": appt.created_at.isoformat() if appt.created_at else None
                }
                for appt in appointments
            ]
            logger.info(f"[DB_QUERY] Found {len(result)} appointments for user_id={user_id}")
            for appt in result:
                logger.info(f"[DB_QUERY]   - id={appt['id']}, date={appt['date']}, time={appt['time']}, status={appt['status']}")
            return result
        finally:
            db.close()
    
    def get_session_appointments(self) -> List[Dict]:
        """
        Get appointments for the authenticated user in this session.
        Returns list of appointment details for the session summary.
        """
        user_id = self._get_current_user_id()
        if not user_id:
            return []
        
        appointments = self._get_user_appointments_from_db(user_id)
        # Return only scheduled appointments
        return [
            {
                "id": a.get("id"),
                "date": a.get("date"),
                "time": a.get("time"),
                "status": a.get("status"),
                "purpose": a.get("purpose", "")
            }
            for a in appointments
            if a.get("status") == "scheduled"
        ]
