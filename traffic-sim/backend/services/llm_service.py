"""
LLM Service — Groq API integration for:
  1. Explaining signal controller decisions in plain English
  2. Parsing natural language configuration commands into structured params

Groq is used for ultra-low latency inference.
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

_client = None


def _get_client():
    global _client
    if _client:
        return _client
    
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("[LLMService] WARNING: GROQ_API_KEY not set. LLM features disabled.")
        return None
        
    _client = Groq(api_key=api_key)
    return _client


async def explain_decision(
    lane_counts: dict,
    wait_times: dict,
    ambulance: dict,
    current_lane: str,
    duration: float,
) -> str:
    """
    Ask Groq to explain why the signal controller chose this duration.
    """
    client = _get_client()
    if not client:
        return _fallback_explanation(lane_counts, wait_times, current_lane, duration)

    prompt = f"""You are an AI traffic signal controller assistant.

The adaptive signal controller just decided to give the {current_lane.upper()} lane {duration:.0f} seconds of green time.

Current intersection state:
- Vehicle counts: North={lane_counts.get('north', 0)}, South={lane_counts.get('south', 0)}, East={lane_counts.get('east', 0)}, West={lane_counts.get('west', 0)}
- Average wait times (seconds): North={wait_times.get('north', 0):.1f}s, South={wait_times.get('south', 0):.1f}s, East={wait_times.get('east', 0):.1f}s, West={wait_times.get('west', 0):.1f}s
- Ambulance present: {', '.join(l.upper() for l, v in ambulance.items() if v) or 'None'}

In 1-2 short sentences, explain why {current_lane.upper()} received {duration:.0f} seconds. Be specific, reference the numbers. Do NOT use bullet points."""

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            max_tokens=100,
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[LLMService] Groq explain_decision error: {exc}")
        return _fallback_explanation(lane_counts, wait_times, current_lane, duration)


async def parse_config_command(command: str) -> dict:
    """
    Ask Groq to parse a natural language configuration command.
    """
    client = _get_client()
    if not client:
        return {
            "params": {},
            "acknowledged": "LLM unavailable (GROQ_API_KEY not set). Command not applied."
        }

    prompt = f"""You are a traffic signal controller configuration assistant.
Parse the following natural language command into structured JSON parameters for a traffic signal controller.

Command: "{command}"

Available parameters:
- "max_green": integer 8 to 30
- "min_green": integer 4 to 15
- "yellow_time": integer 3 to 10
- "ambulance_preempt_immediately": boolean

Also include:
- "acknowledged": a short 1-sentence plain English confirmation.

Respond ONLY with a valid JSON object. No markdown.

Example:
{{"params": {{"max_green": 20}}, "acknowledged": "Maximum green time reduced to 20 seconds."}}"""

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
        )
        text = chat_completion.choices[0].message.content.strip()
        parsed = json.loads(text)
        return {
            "params": parsed.get("params", {}),
            "acknowledged": parsed.get("acknowledged", "Configuration updated.")
        }
    except Exception as exc:
        print(f"[LLMService] Groq parse_config_command error: {exc}")
        return {
            "params": {},
            "acknowledged": "Could not parse command. Please try rephrasing."
        }


def _fallback_explanation(lane_counts, wait_times, current_lane, duration):
    """Rule-based fallback explanation."""
    count = lane_counts.get(current_lane, 0)
    wait  = wait_times.get(current_lane, 0)
    if count == 0:
        return f"{current_lane.capitalize()} lane received {duration:.0f}s as it currently has no vehicles."
    return f"{current_lane.capitalize()} lane received {duration:.0f}s based on {count} vehicles with {wait:.1f}s avg wait."
