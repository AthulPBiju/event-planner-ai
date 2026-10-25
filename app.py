import streamlit as st
from google import genai
import os
import json
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Configuration & Setup
# -----------------------------------------------------------------------------
load_dotenv()

# NEW SDK INITIALIZATION
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# -----------------------------------------------------------------------------
# Business Logic
# -----------------------------------------------------------------------------
def validate_inputs(guests: int, budget: int, theme: str) -> Optional[str]:
    if not theme.strip():
        return "Please provide a theme or vibe for the event."
    
    minimum_cost_per_person = 500
    if budget < (guests * minimum_cost_per_person):
        return f"Budget is too low for {guests} guests. Consider at least ₹{guests * minimum_cost_per_person} for a viable event."
    
    return None

def generate_event_plan(event_type: str, guests: int, budget: int, theme: str) -> Optional[Dict[str, Any]]:
    prompt = f"""
    Act as an expert event planner. Plan a {event_type} for {guests} guests. Budget: {budget} INR. Theme: {theme}.
    
    You MUST respond ONLY in valid JSON format without markdown code blocks. Use this exact structure:
    {{
        "ideas": "Detailed paragraph of creative ideas.",
        "budget_breakdown": "Detailed paragraph of overall budget allocation.",
        "timeline": ["Task 1", "Task 2"],
        "vendors": [
            {{"item": "Venue Booking", "cost": 15000}},
            {{"item": "Catering", "cost": 20000}}
        ]
    }}
    Ensure the total vendor costs roughly match but do not exceed {budget}.
    """
    try:
        # Removed the 'config' parameter to fix the unexpected keyword argument error
        response = client.interactions.create(
            model='gemini-3.8-flash',
            input=prompt
        )
        raw_text = response.output_text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw_text)
    except json.JSONDecodeError:
        st.error("Failed to parse the AI's response into structured data. Please try again.")
        return None
    except Exception as e:
        st.error(f"An unexpected API error occurred: {e}")
        return None

# -----------------------------------------------------------------------------
# User Interface 
# -----------------------------------------------------------------------------
st.set_page_config(page_title="AI Event Planner", page_icon="🎉", layout="wide")

st.title("🎉 GenAI Event & Wedding Planner")
st.markdown("Organize events dynamically with logical budgeting, timelines, and ideas.")
st.divider()

if "event_data" not in st.session_state:
    st.session_state.event_data = None

col1, col2 = st.columns(2)
with col1:
    event_type = st.selectbox("Event Type", ["Wedding", "Birthday Party", "Community Event", "Corporate Meetup"], help="Select the category that best matches your event.")
    guests = st.number_input("Estimated Guests", min_value=1, value=50, help="The total number of people attending.")
with col2:
    budget = st.number_input("Total Budget (in INR)", min_value=1000, value=50000, step=5000, help="Your maximum spending limit in Indian Rupees.")
    theme = st.text_input("Theme / Vibe", placeholder="e.g., Rustic, Traditional, Modern Minimalist", help="Describe the visual style or specific requirements for the event.")

st.write("")

if st.button("Generate Complete Event Plan", type="primary"):
    if not os.getenv("GEMINI_API_KEY"):
        st.error("System Error: GEMINI_API_KEY is missing from environment variables.")
    else:
        validation_error = validate_inputs(guests, budget, theme)
        
        if validation_error:
            st.warning(validation_error)
        else:
            with st.spinner("Our AI event planner is validating and organizing your details..."):
                plan_data = generate_event_plan(event_type, guests, budget, theme)
                if plan_data:
                    st.session_state.event_data = plan_data

if st.session_state.event_data:
    data = st.session_state.event_data
    
    st.success("Plan successfully generated and validated!")
    
    st.subheader("🎨 Creative Ideas")
    st.write(data.get("ideas", "No ideas generated."))
    
    st.subheader("💰 Budget Breakdown")
    st.write(data.get("budget_breakdown", "No budget breakdown generated."))
    st.divider()
    
    st.sidebar.header("📊 Live Budget Tracker")
    st.sidebar.write(f"**Total Budget:** ₹{budget:,}")
    
    total_spent = 0
    col3, col4 = st.columns(2)
    
    with col3:
        st.subheader("📅 Interactive Timeline")
        with st.container(border=True):
            for i, task in enumerate(data.get("timeline", [])):
                st.checkbox(task, key=f"task_{i}")
                
    with col4:
        st.subheader("✅ Vendor Checklist & Costs")
        with st.container(border=True):
            for i, vendor in enumerate(data.get("vendors", [])):
                v_name = vendor.get("item", "Unknown")
                v_cost = vendor.get("cost", 0)
                
                is_checked = st.checkbox(f"{v_name} (₹{v_cost:,})", key=f"vendor_{i}")
                if is_checked:
                    total_spent += v_cost

    remaining = budget - total_spent
    st.sidebar.metric("Money Spent", f"₹{total_spent:,}")
    st.sidebar.metric("Remaining Budget", f"₹{remaining:,}")
    
    if remaining < 0:
        st.sidebar.error("⚠️ Over Budget Warning: You have exceeded your limit!")