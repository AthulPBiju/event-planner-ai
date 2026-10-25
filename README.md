# GenAI Event & Wedding Planner

An intelligent, dynamic planning assistant powered by Google Gemini that helps users organize weddings, birthdays, and community events with realistic budgets, interactive timelines, and personalized vendor checklists.

## 🚀 Problem Statement Alignment
Planning large events often involves scattered spreadsheets, forgotten tasks, and budget overruns. This solution acts as a smart, context-aware assistant that takes a user's parameters (event type, guest count, budget, and theme) and generates a highly structured, interactive plan. 

## ✨ Key Features
* **Smart Budget Allocation:** Uses zero-based budgeting to allocate realistic vendor costs without exceeding the user's total budget.
* **Interactive Live Budget Tracker:** As users check off vendors, the app dynamically calculates money spent and alerts them if they are over budget.
* **Context-Aware Ideation:** Generates highly specific decor, food, and activity concepts tailored to the user's requested theme.
* **Structured Output:** Forces the LLM to output strict JSON for seamless integration into interactive UI components (checkboxes).

## 🏆 Hackathon Evaluation Criteria

This project was built with engineering maturity and hackathon evaluation metrics in mind:

* **Security:** API keys are strictly managed via environment variables (`.env`). A `.gitignore` file prevents sensitive data and caches from being pushed to the repository.
* **Code Quality & Maintainability:** The architecture heavily separates UI elements (Streamlit) from business logic (Gemini API). It uses Python type hints (`Optional`, `Dict`, `Any`) and modular functions for clean readability.
* **Efficiency & Testing:** Includes a robust `validate_inputs()` function that catches logical errors (e.g., impossible budgets for high guest counts or missing themes) *before* making the API call, saving API quota and preventing blank responses. Extensive `try/except` blocks catch potential JSON parsing errors from the AI.
* **Accessibility:** All UI inputs utilize Streamlit's `help` parameters, providing clear, descriptive guidance for screen readers and improving overall inclusive UX.

## 🛠️ Tech Stack
* **Frontend/UI:** Streamlit (Python)
* **Backend/AI:** Google Gemini 3.8 Flash API
* **Environment Management:** python-dotenv

## 💻 Local Setup & Installation

**1. Clone the repository:**
```bash
git clone [https://github.com/AthulPBiju/event-planner-ai.git](https://github.com/your-username/event-planner-ai.git)
cd event-planner-ai