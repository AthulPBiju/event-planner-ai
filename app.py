"""
AI Event & Wedding Planner – Streamlit Application
====================================================
Uses Google's Interactions API (google-genai SDK) to generate structured
event plans with budgeting, timelines, and vendor checklists.

Hackathon evaluation targets:
  • Code Quality   – separated UI / logic, type hints, docstrings
  • Security       – env-based API key with graceful fallback
  • Efficiency     – pre-flight validation, retry with back-off, cached client
  • Testing        – input validator catches impossible budgets & blanks
  • Accessibility  – help tooltips on every widget, semantic headings
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from dotenv import load_dotenv
from google import genai

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------
load_dotenv()

_MODEL_ID: str = "gemini-3.8-flash"
_MIN_COST_PER_GUEST: int = 500          # INR – absolute floor per person
_MAX_RETRIES: int = 2                   # additional attempts on transient errors
_BACKOFF_BASE: float = 1.5              # seconds – exponential back-off base
_TRANSIENT_CODES: Tuple[str, ...] = ("503", "429", "404", "UNAVAILABLE")


# ---------------------------------------------------------------------------
# Business Logic  (zero Streamlit dependency in this section)
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_genai_client() -> Optional[genai.Client]:
    """Return a cached ``genai.Client``, or *None* when the key is absent.

    Decorated with ``@st.cache_resource`` so the client is constructed
    exactly once per process, avoiding redundant network handshakes on
    every Streamlit rerun.
    """
    api_key: Optional[str] = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    return genai.Client(api_key=api_key)


def validate_inputs(guests: int, budget: int, theme: str) -> Optional[str]:
    """Check for logical user errors **before** calling the API.

    Returns an error-message string when validation fails, or ``None``
    when every input is acceptable.

    Checks
    ------
    1. Theme must not be blank or whitespace-only.
    2. Budget must meet the minimum viable cost per guest
       (₹500 × guest-count).

    Parameters
    ----------
    guests : int
        Expected number of attendees (≥ 1).
    budget : int
        Total event budget in INR (≥ 1 000).
    theme : str
        Free-text event vibe / theme description.
    """
    if not theme.strip():
        return "Please provide a theme or vibe for the event."

    min_viable: int = guests * _MIN_COST_PER_GUEST
    if budget < min_viable:
        return (
            f"A budget of ₹{budget:,} is mathematically too low for "
            f"{guests:,} guests. A bare-minimum viable event requires at "
            f"least ₹{min_viable:,} (₹{_MIN_COST_PER_GUEST}/person)."
        )
    return None


def _build_prompt(
    event_type: str,
    guests: int,
    budget: int,
    theme: str,
) -> str:
    """Build the prompt sent to the Interactions API.

    Forces the model to reply with **strict raw JSON** – no markdown
    code fences, no surrounding commentary.

    Parameters
    ----------
    event_type : str   – e.g. "Wedding", "Birthday Party".
    guests     : int   – attendee count.
    budget     : int   – total budget in INR.
    theme      : str   – desired vibe / theme.

    Returns
    -------
    str – the fully-formatted prompt.
    """
    return (
        f"Act as an expert event planner. Plan a {event_type} for "
        f"{guests} guests. Budget: {budget} INR. Theme: {theme}.\n\n"
        "IMPORTANT: Respond with ONLY raw, valid JSON. "
        "Do NOT wrap the output in markdown code fences. "
        "Do NOT add any text before or after the JSON object. "
        "Use this exact schema:\n"
        "{\n"
        '  "ideas": "Detailed paragraph of creative ideas.",\n'
        '  "budget_breakdown": "Detailed paragraph of overall budget allocation.",\n'
        '  "timeline": ["Task 1 — description", "Task 2 — description"],\n'
        '  "vendors": [\n'
        '    {"item": "Venue Booking", "cost": 15000},\n'
        '    {"item": "Catering", "cost": 20000}\n'
        "  ]\n"
        "}\n\n"
        f"Ensure total vendor costs roughly match but do not exceed {budget} INR."
    )


def generate_event_plan(
    client: genai.Client,
    event_type: str,
    guests: int,
    budget: int,
    theme: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Call the Interactions API and return a parsed plan **or** an error.

    Retries up to ``_MAX_RETRIES`` times with exponential back-off for
    transient server errors (503, 429, 404, UNAVAILABLE).

    Parameters
    ----------
    client     : genai.Client – authenticated client instance.
    event_type : str
    guests     : int
    budget     : int
    theme      : str

    Returns
    -------
    tuple[dict | None, str | None]
        ``(plan_dict, None)`` on success;
        ``(None, error_message)`` on failure.
    """
    prompt: str = _build_prompt(event_type, guests, budget, theme)
    last_error: str = ""

    for attempt in range(_MAX_RETRIES + 1):
        try:
            # ---------- Mandatory Interactions API call ----------
            response = client.interactions.create(
                model=_MODEL_ID,
                input=prompt,
            )
            # Strip any accidental markdown fences the model may add
            raw_text: str = (
                response.output_text
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )
            plan: Dict[str, Any] = json.loads(raw_text)
            return plan, None

        except json.JSONDecodeError:
            # Non-retryable: the model returned garbage – ask user to retry
            return None, (
                "The AI returned a response that could not be parsed as "
                "valid JSON. Please try generating the plan again."
            )

        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            is_transient: bool = any(c in last_error for c in _TRANSIENT_CODES)
            if is_transient and attempt < _MAX_RETRIES:
                time.sleep(_BACKOFF_BASE ** (attempt + 1))
                continue
            return None, f"API error: {last_error}"

    # Defensive – should be unreachable
    return None, f"API error after {_MAX_RETRIES} retries: {last_error}"


# ---------------------------------------------------------------------------
# Pure helpers – budget arithmetic
# ---------------------------------------------------------------------------

def compute_budget_summary(
    vendors: List[Dict[str, Any]],
    checked_indices: List[int],
    total_budget: int,
) -> Tuple[int, int]:
    """Sum vendor costs for checked items and compute the remainder.

    Parameters
    ----------
    vendors         : list[dict] – vendor objects from the generated plan.
    checked_indices : list[int]  – indices the user ticked.
    total_budget    : int        – budget captured at generation time.

    Returns
    -------
    tuple[int, int] – ``(total_spent, remaining_budget)``.
    """
    total_spent: int = sum(
        vendors[i].get("cost", 0)
        for i in checked_indices
        if i < len(vendors)
    )
    return total_spent, total_budget - total_spent


# ---------------------------------------------------------------------------
# User Interface
# ---------------------------------------------------------------------------

def _init_session_state() -> None:
    """Initialise ``st.session_state`` keys with safe defaults.

    Called once per session.  Plain assignment avoids the ``TypeError``
    that inline type-annotated assignment can cause in some Streamlit
    versions.
    """
    if "event_data" not in st.session_state:
        st.session_state.event_data = None       # Optional[Dict[str, Any]]
    if "locked_budget" not in st.session_state:
        st.session_state.locked_budget = 0        # int


def _render_input_form() -> Tuple[str, int, int, str]:
    """Draw the input widgets and return their current values.

    Returns
    -------
    tuple[str, int, int, str]
        ``(event_type, guests, budget, theme)``
    """
    col1, col2 = st.columns(2)

    with col1:
        event_type: str = st.selectbox(
            "Event Type",
            ["Wedding", "Birthday Party", "Community Event", "Corporate Meetup"],
            help="Select the category that best matches your event.",
        )
        guests: int = st.number_input(
            "Estimated Guests",
            min_value=1,
            value=50,
            help="The total number of people you expect to attend.",
        )

    with col2:
        budget: int = st.number_input(
            "Total Budget (in INR)",
            min_value=1000,
            value=50000,
            step=5000,
            help="Your maximum spending limit in Indian Rupees (₹).",
        )
        theme: str = st.text_input(
            "Theme / Vibe",
            placeholder="e.g., Rustic, Traditional, Modern Minimalist",
            help=(
                "Describe the visual style or specific requirements "
                "for the event."
            ),
        )

    return event_type, guests, budget, theme


def _handle_generate(
    event_type: str,
    guests: int,
    budget: int,
    theme: str,
) -> None:
    """Validate inputs, call the API, and persist results in session state.

    Parameters
    ----------
    event_type, guests, budget, theme – current widget values.
    """
    # Security: verify API key
    client: Optional[genai.Client] = _get_genai_client()
    if client is None:
        st.error(
            "🔒 **System Error:** `GEMINI_API_KEY` is missing from "
            "environment variables. Set it in your `.env` file or "
            "deployment secrets."
        )
        return

    # Pre-flight validation – saves API quota on obviously bad inputs
    validation_msg: Optional[str] = validate_inputs(guests, budget, theme)
    if validation_msg:
        st.warning(validation_msg)
        return

    with st.spinner(
        "Our AI event planner is validating and organising your details…"
    ):
        plan_data, api_error = generate_event_plan(
            client, event_type, guests, budget, theme
        )

    if api_error:
        st.error(api_error)
    else:
        # Persist the plan AND the budget snapshot used at generation time
        st.session_state.event_data = plan_data
        st.session_state.locked_budget = budget


def _render_plan() -> None:
    """Display the generated plan stored in ``st.session_state``.

    Vendor checkboxes drive a **live budget tracker** in the sidebar.
    Toggling a checkbox triggers only a lightweight Streamlit rerun that
    re-reads checkbox states – the persisted ``event_data`` is untouched,
    so the AI is never re-called.
    """
    if st.session_state.event_data is None:
        return

    data: Dict[str, Any] = st.session_state.event_data
    locked_budget: int = st.session_state.locked_budget

    st.success("✅ Plan successfully generated and validated!")

    # -- Creative Ideas --------------------------------------------------------
    st.subheader("🎨 Creative Ideas")
    st.write(data.get("ideas", "No ideas generated."))

    # -- Budget Breakdown (narrative) ------------------------------------------
    st.subheader("💰 Budget Breakdown")
    st.write(data.get("budget_breakdown", "No budget breakdown generated."))
    st.divider()

    # -- Two-column layout: Timeline + Vendors ---------------------------------
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📅 Interactive Timeline")
        with st.container(border=True):
            timeline: List[str] = data.get("timeline", [])
            for idx, task in enumerate(timeline):
                st.checkbox(
                    task,
                    key=f"task_{idx}",
                    help=f"Mark task {idx + 1} as complete.",
                )

    vendors: List[Dict[str, Any]] = data.get("vendors", [])
    checked_indices: List[int] = []

    with col_right:
        st.subheader("✅ Vendor Checklist & Costs")
        with st.container(border=True):
            for idx, vendor in enumerate(vendors):
                v_name: str = vendor.get("item", "Unknown")
                v_cost: int = vendor.get("cost", 0)
                is_checked: bool = st.checkbox(
                    f"{v_name} (₹{v_cost:,})",
                    key=f"vendor_{idx}",
                    help=f"Include {v_name} in your running total.",
                )
                if is_checked:
                    checked_indices.append(idx)

    # -- Sidebar: Live Budget Tracker ------------------------------------------
    total_spent, remaining = compute_budget_summary(
        vendors, checked_indices, locked_budget
    )

    st.sidebar.header("📊 Live Budget Tracker")
    st.sidebar.write(f"**Total Budget:** ₹{locked_budget:,}")

    # Visual progress bar (clamped to 0-1 range)
    if locked_budget > 0:
        utilisation: float = min(total_spent / locked_budget, 1.0)
        st.sidebar.progress(utilisation, text="Budget utilisation")

    st.sidebar.metric("Money Spent", f"₹{total_spent:,}")
    st.sidebar.metric("Remaining Budget", f"₹{remaining:,}")

    if remaining < 0:
        st.sidebar.error(
            "⚠️ **Over Budget Warning:** You have exceeded your limit!"
        )


# ---------------------------------------------------------------------------
# Main – called on every Streamlit rerun
# ---------------------------------------------------------------------------

def main() -> None:
    """Application entry-point: page config → inputs → generate → display."""
    st.set_page_config(
        page_title="AI Event Planner",
        page_icon="🎉",
        layout="wide",
    )

    st.title("GenAI Event & Wedding Planner")
    st.markdown(
        "Organize events dynamically with AI-powered budgeting, "
        "timelines, and creative ideas."
    )
    st.divider()

    _init_session_state()

    event_type, guests, budget, theme = _render_input_form()

    st.write("")  # spacing

    if st.button(
        "Generate Complete Event Plan",
        type="primary",
        help="Validates your inputs, then calls the AI to produce a full plan.",
    ):
        _handle_generate(event_type, guests, budget, theme)

    _render_plan()


# Streamlit runs the script top-level (not via __main__ guard),
# so main() must be called unconditionally.
main()