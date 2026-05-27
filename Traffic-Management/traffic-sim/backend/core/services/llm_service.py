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

    prompt = f"""You are the Explainable AI (XAI) engine for a Smart Traffic Signal. The system operates in a fixed CYCLIC rotation, so your task is to justify the DURATION assigned to the {current_lane.upper()} lane.

Intersection Snapshot:
- Active Lane: {current_lane.upper()} ({lane_counts.get(current_lane, 0)} vehicles, {wait_times.get(current_lane, 0):.1f}s avg wait)
- Next Lanes in Cycle: {', '.join([f"{l.upper()} (Queue: {lane_counts.get(l, 0)})" for l in lane_counts if l != current_lane])}
- Emergency Status: {', '.join(l.upper() for l, v in ambulance.items() if v) or 'No ambulances'}

Decision: Assigned {duration:.1f}s of Green time to {current_lane.upper()}.

Guidelines:
1. Explain how the assigned duration ({duration:.1f}s) balances clearing the current queue against the building pressure in the next lanes.
2. Use technical terms like 'Saturation Flow', 'Queue Dissipation', or 'Wait Time Penalty'.
3. If an ambulance is present in {current_lane.upper()}, emphasize that the duration was extended/held to ensure priority clearance.
4. Format your response exactly as: [Observation] <Briefly state current load> [Rationale] <Technical justification for the specific duration>."""

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
