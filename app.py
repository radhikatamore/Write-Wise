import streamlit as st
import google.generativeai as genai
from datetime import datetime
import json
import os
from pathlib import Path

# ------------------------------
# Configure Gemini API Key
# ------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in Streamlit secrets.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# ------------------------------
# Initialize Session State for History
# ------------------------------
# Define history file path
HISTORY_FILE = Path.home() / ".writewise_history.json"

def load_history():
    """Load history from JSON file"""
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        st.error(f"Error loading history: {e}")
    return []

def save_history(history):
    """Save history to JSON file"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Error saving history: {e}")

# Load history from file on startup
if "history" not in st.session_state:
    st.session_state.history = load_history()

# Constants for history display
PROMPT_PREVIEW_LENGTH = 100
CONTENT_PREVIEW_LENGTH = 300

# ------------------------------
# Streamlit App UI
# ------------------------------
st.set_page_config(page_title="Write Wise- AI Content Generator", layout="wide")

# ------------------------------
# Sidebar - History Feature
# ------------------------------
with st.sidebar:
    st.header("📜 History")
    
    if st.session_state.history:
        st.caption(f"Total entries: {len(st.session_state.history)}")
        
        # Clear history button
        if st.button("🗑️ Clear All History", use_container_width=True):
            st.session_state.history = []
            save_history([])  # Save empty history to file
            st.rerun()
        
        st.markdown("---")
        
        # Display history items
        for idx, item in enumerate(reversed(st.session_state.history)):
            # Use timestamp as unique key component
            entry_key = f"{item['timestamp']}_{idx}"
            with st.expander(f"📝 {item['timestamp']} - {item['model']}", expanded=False):
                st.markdown(f"**Prompt:** {item['prompt'][:PROMPT_PREVIEW_LENGTH]}{'...' if len(item['prompt']) > PROMPT_PREVIEW_LENGTH else ''}")
                st.markdown(f"**Depth:** {item['depth']}")
                st.markdown("**Generated Content:**")
                st.markdown(item['content'][:CONTENT_PREVIEW_LENGTH] + "..." if len(item['content']) > CONTENT_PREVIEW_LENGTH else item['content'])
                
                # View full content button
                if st.button(f"View Full Content", key=f"view_{entry_key}"):
                    st.session_state[f"viewing_{entry_key}"] = True
                
                # Show full content if button was clicked
                if st.session_state.get(f"viewing_{entry_key}", False):
                    st.markdown("**Full Content:**")
                    st.markdown(item['content'])
                    if st.button(f"Hide", key=f"hide_{entry_key}"):
                        st.session_state[f"viewing_{entry_key}"] = False
                        st.rerun()
    else:
        st.info("No history yet. Generate content to see it here!")

st.title("Write Wise - AI Content Generator")
st.subheader("Generate high-quality content from your prompts!")

# User input
user_prompt = st.text_area("Enter your prompt:", height=150)

# Model selection
model_choice = st.selectbox(
    "Choose AI model:",
    [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
    index=0,
)

# Content depth selection
depth_choice = st.selectbox(
    "Select Content Depth (level of detail):",
    [
        "Shallow (high-level overview)",
        "Medium (moderate detail with examples)",
        "Deep (very detailed, nuanced, in-depth analysis)"
    ],
    index=1
)

# Map depth to system instructions
depth_instruction_map = {
    "Shallow (high-level overview)": "Provide a clear and simple overview. Focus on key points, avoid unnecessary details.",
    "Medium (moderate detail with examples)": "Provide a moderately detailed explanation with examples and supporting points.",
    "Deep (very detailed, nuanced, in-depth analysis)": "Provide an in-depth, thorough, and nuanced explanation. Include examples, multiple perspectives, reasoning, and insights."
}

depth_instruction = depth_instruction_map[depth_choice]

# ------------------------------
# Generate Content
# ------------------------------
if st.button("Generate Content"):
    if not user_prompt.strip():
        st.warning("Please enter a prompt to generate content.")
    else:
        with st.spinner("Generating content..."):
            try:
                # Combine base system prompt with depth instruction
                system_prompt = f"""
                You are AiGuru, a professional AI content generator. 
                Your task is to generate high-quality content based on the user's prompt.
                {depth_instruction}
                Use proper grammar and structure, adapt tone appropriately, include headings or examples if needed, and avoid filler or repetition.
                """

                model = genai.GenerativeModel(
                    model_name=model_choice,
                    system_instruction=system_prompt
                )

                # Generate content with increased token limit
                response = model.generate_content(
                    user_prompt,
                    generation_config={
                        "max_output_tokens": 20000,  
                        "temperature": 0.35
                    },
                )

                # ------------------------------
                # Robust Text Extraction
                # ------------------------------
                output_text = ""

                # Safe extraction: check candidates and parts
                if hasattr(response, "candidates") and response.candidates:
                    for candidate in response.candidates:
                        content = getattr(candidate, "content", None)
                        if content and getattr(content, "parts", None):
                            for part in content.parts:
                                output_text += getattr(part, "text", "")
                
                # Fallback to response.text only if valid
                if not output_text and getattr(response, "text", None):
                    output_text = response.text

                # ------------------------------
                # Display Results
                # ------------------------------
                if output_text.strip():
                    st.success("✅ Content Generated Successfully!")
                    st.markdown("---")
                    st.markdown(output_text)
                    
                    # Save to history
                    history_entry = {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "prompt": user_prompt,
                        "model": model_choice,
                        "depth": depth_choice,
                        "content": output_text
                    }
                    st.session_state.history.append(history_entry)
                    save_history(st.session_state.history)  # Persist to file
                else:
                    st.error("⚠️ No content returned by the model. Try a different prompt or model.")

            except Exception as e:
                st.error(f"❌ Error generating content: {e}")

# ------------------------------
# Footer
# ------------------------------
st.markdown("---")
st.caption("Powered by Google Gemini. Set GEMINI_API_KEY in Streamlit secrets to override.")
st.markdown("Developed by Write Wise Team")
