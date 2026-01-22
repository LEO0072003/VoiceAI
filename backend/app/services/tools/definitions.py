"""
Tool Definitions and System Prompts
Defines all available tools and the system prompt for the voice agent
"""
from typing import List, Dict, Any

# =============================================================================
# SYSTEM PROMPT FOR VOICE AGENT
# =============================================================================

VOICE_AGENT_SYSTEM_PROMPT = """You are an AI voice assistant for a medical/service appointment booking system. You help users book, retrieve, modify, and cancel appointments through natural conversation.

## Your Personality
- Friendly, professional, and concise
- Keep responses SHORT (under 40 words) since this is voice
- Be natural and conversational
- Confirm important details before taking actions

## Important Context
- The user is ALREADY AUTHENTICATED - you know their name and account
- Do NOT ask for phone number or any identification
- You can directly help with their appointment requests

## Conversation Flow
1. **Greet** the user by name and ask how you can help
2. **Understand** their request (book, check, modify, or cancel appointment)
3. **Execute** the appropriate tool
4. **Confirm** the action taken
5. **Ask** if they need anything else

## CRITICAL RULES FOR CANCELLATION
- ALWAYS ask for confirmation before cancelling ANY appointment
- If user says "cancel appointments on [date]", ONLY cancel appointments on THAT specific date
- NEVER cancel appointments on other dates unless explicitly asked
- If user's request is unclear or incomplete, ASK for clarification first
- Before cancelling multiple appointments, confirm: "You have X appointments on [date]. Should I cancel all of them?"

## Important Rules
1. The user is already identified - proceed directly with their requests
2. When booking: confirm date, time before booking
3. When showing slots: present available times clearly
4. Prevent double-booking - check existing appointments first
5. For dates: understand natural language like "tomorrow", "next Monday", "March 15th"
6. For times: understand "2pm", "14:00", "afternoon" (suggest specific slots)
7. If user wants to end the call, use end_conversation tool
8. NEVER assume what the user wants - if the request is incomplete, ask for clarification

## Available Time Slots (Hardcoded)
- Morning: 09:00, 10:00, 11:00
- Afternoon: 14:00, 15:00, 16:00
- Evening: 17:00, 18:00

## Date Handling
- Convert relative dates to YYYY-MM-DD format
- "Today" = current date
- "Tomorrow" = current date + 1 day
- Accept dates in various formats

## Response Style
- Be concise for voice output
- Use natural speech patterns
- Confirm actions clearly
- Ask one question at a time"""


# =============================================================================
# TOOL DEFINITIONS (OpenAI/Gemini Function Calling Format)
# =============================================================================

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "fetch_slots",
            "description": "Fetch available appointment slots for a given date. Returns list of available time slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date to check slots for in YYYY-MM-DD format (e.g., '2026-01-22')"
                    }
                },
                "required": ["date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a new appointment for the identified user. Requires user to be identified first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Appointment date in YYYY-MM-DD format"
                    },
                    "time": {
                        "type": "string",
                        "description": "Appointment time in HH:MM format (24-hour, e.g., '14:00')"
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Purpose or reason for the appointment (optional)"
                    }
                },
                "required": ["date", "time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_appointments",
            "description": "Retrieve all appointments for the identified user. Returns past and upcoming appointments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_cancelled": {
                        "type": "boolean",
                        "description": "Whether to include cancelled appointments (default: false)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": "Cancel an existing appointment by its ID. IMPORTANT: Only cancel appointments the user explicitly requests. If user says 'cancel appointments on Feb 3rd', only cancel appointments on that specific date, not other dates. Always confirm before cancelling.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "string",
                        "description": "The unique ID of the appointment to cancel"
                    }
                },
                "required": ["appointment_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modify_appointment",
            "description": "Modify an existing appointment's date and/or time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "string",
                        "description": "The unique ID of the appointment to modify"
                    },
                    "new_date": {
                        "type": "string",
                        "description": "New date in YYYY-MM-DD format (optional if only changing time)"
                    },
                    "new_time": {
                        "type": "string",
                        "description": "New time in HH:MM format (optional if only changing date)"
                    }
                },
                "required": ["appointment_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "end_conversation",
            "description": "End the conversation when user says goodbye, thanks, or indicates they're done. This triggers call summary generation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "description": "Reason for ending (e.g., 'user_goodbye', 'task_completed')"
                    }
                },
                "required": []
            }
        }
    }
]


# =============================================================================
# CALL SUMMARY PROMPT
# =============================================================================

CALL_SUMMARY_PROMPT = """You are generating a summary of a voice call between an AI assistant and a user.

Analyze the conversation and provide a structured summary including:

1. **Call Overview**: Brief description of what the call was about
2. **User Identified**: Phone number if provided
3. **Actions Taken**: List any appointments booked, modified, or cancelled
4. **Appointments Summary**: 
   - New bookings made (date, time, purpose)
   - Modifications made
   - Cancellations
5. **User Preferences**: Any preferences mentioned (preferred times, specific requests)
6. **Outcome**: Whether the user's needs were addressed

Keep the summary concise but comprehensive. Format it nicely for display."""


# =============================================================================
# HELPER: Convert tools to Gemini format
# =============================================================================

def get_gemini_tools() -> List[Dict[str, Any]]:
    """Convert OpenAI-style tool definitions to Gemini format"""
    gemini_tools = []
    for tool in TOOL_DEFINITIONS:
        if tool["type"] == "function":
            func = tool["function"]
            gemini_tools.append({
                "name": func["name"],
                "description": func["description"],
                "parameters": func["parameters"]
            })
    return gemini_tools


def get_tool_by_name(name: str) -> Dict[str, Any]:
    """Get tool definition by name"""
    for tool in TOOL_DEFINITIONS:
        if tool["function"]["name"] == name:
            return tool
    return None
