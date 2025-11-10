import os
import streamlit as st
import google.generativeai as genai
import uuid
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

st.set_page_config(page_title="Write Wise - AI Content Generator", layout="wide", page_icon="✍️")

# ------------------------------
# Configure Gemini API Key
# ------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in Streamlit secrets.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# ------------------------------
# Local Storage Helper Functions
# ------------------------------
def init_local_storage():
    """Initialize local storage using Streamlit's session state and HTML5 localStorage."""
    # JavaScript to sync localStorage with Streamlit
    storage_js = """
    <script>
    // Function to save data to localStorage
    function saveToLocalStorage(key, value) {
        localStorage.setItem(key, JSON.stringify(value));
    }
    
    // Function to load data from localStorage
    function loadFromLocalStorage(key) {
        const item = localStorage.getItem(key);
        return item ? JSON.parse(item) : null;
    }
    
    // Load data on page load
    window.addEventListener('load', function() {
        const sessions = loadFromLocalStorage('writewise_sessions');
        const templates = loadFromLocalStorage('writewise_templates');
        const currentSession = loadFromLocalStorage('writewise_current_session');
        
        // Send data to Streamlit
        if (sessions) {
            window.parent.postMessage({
                type: 'streamlit:setComponentValue',
                data: { sessions: sessions }
            }, '*');
        }
    });
    </script>
    """
    st.components.v1.html(storage_js, height=0)

def save_to_local_storage(key: str, data: Any):
    """Save data to browser's localStorage via JavaScript."""
    json_data = json.dumps(data)
    escaped_data = json_data.replace("'", "\\'").replace('"', '\\"')
    
    js_code = f"""
    <script>
    localStorage.setItem('{key}', '{escaped_data}');
    </script>
    """
    st.components.v1.html(js_code, height=0)

def get_from_session_or_init(key: str, default: Any) -> Any:
    """Get data from session state or initialize with default."""
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]

# ------------------------------
# Initialize Session State
# ------------------------------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "templates" not in st.session_state:
    st.session_state.templates = {}
if "current_page" not in st.session_state:
    st.session_state.current_page = "generator"
if "selected_template" not in st.session_state:
    st.session_state.selected_template = None
if "custom_sections" not in st.session_state:
    st.session_state.custom_sections = None
if "main_topic" not in st.session_state:
    st.session_state.main_topic = None
if "additional_context" not in st.session_state:
    st.session_state.additional_context = None
if "section_results" not in st.session_state:
    st.session_state.section_results = {}
if "generation_mode" not in st.session_state:
    st.session_state.generation_mode = None
if "structure_selection_message" not in st.session_state:
    st.session_state.structure_selection_message = None
if "initialized" not in st.session_state:
    st.session_state.initialized = False

# Load from localStorage on first run
if not st.session_state.initialized:
    # Try to load persisted data
    load_js = """
    <script>
    function loadData() {
        const sessions = localStorage.getItem('writewise_sessions');
        const templates = localStorage.getItem('writewise_templates');
        
        if (sessions || templates) {
            const data = {
                sessions: sessions ? JSON.parse(sessions) : {},
                templates: templates ? JSON.parse(templates) : {}
            };
            
            // Pass data to Streamlit via query params or session
            console.log('Loaded data:', data);
        }
    }
    loadData();
    </script>
    """
    st.components.v1.html(load_js, height=0)
    st.session_state.initialized = True

# ------------------------------
# Data Persistence Functions
# ------------------------------
def save_message(role: str, content: str, metadata: Optional[Dict[str, Any]] = None):
    """Save a message to the chat history."""
    timestamp = datetime.now().timestamp()
    message = {
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "metadata": metadata or {}
    }
    
    # Add to chat history
    st.session_state.chat_history.append(message)
    
    # Persist to localStorage
    persist_chat_history()


def persist_chat_history():
    """Persist chat history to localStorage."""
    chat_json = json.dumps(st.session_state.chat_history)
    js_code = f"""
    <script>
    localStorage.setItem('writewise_chat_history', '{chat_json.replace("'", "\\'")}');
    </script>
    """
    st.components.v1.html(js_code, height=0)

def persist_templates():
    """Persist templates to localStorage."""
    templates_json = json.dumps(st.session_state.templates)
    js_code = f"""
    <script>
    localStorage.setItem('writewise_templates', '{templates_json.replace("'", "\\'")}');
    </script>
    """
    st.components.v1.html(js_code, height=0)

def clear_chat_history():
    """Clear all chat history."""
    st.session_state.chat_history = []
    js_code = """
    <script>
    localStorage.removeItem('writewise_chat_history');
    </script>
    """
    st.components.v1.html(js_code, height=0)

def save_template(template_name: str, sections: List[str], description: str = ""):
    """Save a custom template."""
    template_id = str(uuid.uuid4())
    timestamp = datetime.now().timestamp()
    
    st.session_state.templates[template_id] = {
        "template_id": template_id,
        "template_name": template_name,
        "sections": sections,
        "description": description,
        "created_at": timestamp,
        "updated_at": timestamp
    }
    
    persist_templates()
    return True, f"Template '{template_name}' saved successfully"

def delete_template(template_id: str):
    """Delete a template."""
    if template_id in st.session_state.templates:
        del st.session_state.templates[template_id]
        persist_templates()
        return True
    return False

def update_template(template_id: str, template_name: Optional[str] = None,
                   sections: Optional[List[str]] = None,
                   description: Optional[str] = None):
    """Update an existing template."""
    if template_id not in st.session_state.templates:
        return False, "Template not found"
    
    template = st.session_state.templates[template_id]
    template["updated_at"] = datetime.now().timestamp()
    
    if template_name is not None:
        template["template_name"] = template_name
    if sections is not None:
        template["sections"] = sections
    if description is not None:
        template["description"] = description
    
    persist_templates()
    return True, "Template updated successfully"

# ------------------------------
# Example Structure Templates
# ------------------------------
EXAMPLE_STRUCTURES = {
    "Research Report": [
        "Introduction",
        "Research Methodology",
        "Implementation",
        "Demo/Results",
        "Examples",
        "Software Requirements",
        "Hardware Requirements",
        "Conclusion",
        "Future Scope",
        "References"
    ],
    "Blog Post": [
        "Hook/Introduction",
        "Background Context",
        "Main Content (3-5 points)",
        "Practical Examples",
        "Key Takeaways",
        "Conclusion",
        "Call to Action"
    ],
    "Presentation/PPT": [
        "Title Slide",
        "Agenda/Overview",
        "Problem Statement",
        "Solution Approach",
        "Key Features/Benefits",
        "Demo/Case Study",
        "Implementation Plan",
        "Conclusion",
        "Q&A"
    ],
    "Technical Documentation": [
        "Overview",
        "Features",
        "Installation",
        "Configuration",
        "Usage Examples",
        "API Reference",
        "Troubleshooting",
        "FAQ"
    ],
    "Business Proposal": [
        "Executive Summary",
        "Problem Statement",
        "Proposed Solution",
        "Benefits & ROI",
        "Implementation Timeline",
        "Budget & Resources",
        "Risk Analysis",
        "Conclusion"
    ]
}

# ------------------------------
# Theme/Tone Presets
# ------------------------------
TONE_PRESETS = {
    "Academic": "Use formal, scholarly language with precise terminology. Maintain objectivity and support claims with logical reasoning.",
    "Blog": "Use conversational, engaging tone. Include storytelling elements, personal touches, and relatable examples.",
    "Technical": "Use clear, precise technical language. Focus on accuracy, include examples, and maintain professional tone.",
    "Marketing": "Use persuasive, benefit-focused language. Create urgency, highlight value propositions, and include calls to action.",
    "Casual": "Use friendly, approachable language. Keep it simple and relatable.",
}

# ------------------------------
# Output Format Options
# ------------------------------
FORMAT_OPTIONS = {
    "Paragraph": "Write in flowing paragraphs with clear topic sentences and transitions.",
    "Bulleted": "Organize information using bullet points and lists for easy scanning.",
    "Tabular": "Present information in structured tables when appropriate, with clear columns and rows.",
    "Mixed": "Use a combination of paragraphs, lists, and tables as appropriate for the content.",
}

# ------------------------------
# History Viewer
# ------------------------------
def show_history_page():
    st.title("📚 Chat History")
    
    if not st.session_state.chat_history:
        st.info("No chat history yet. Generate content to build your history.")
        return
    
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        st.markdown(f"**Total Messages: {len(st.session_state.chat_history)}**")
    with col2:
        export_data = json.dumps(st.session_state.chat_history, indent=2)
        st.download_button(
            "⬇️ Export",
            export_data,
            file_name=f"writewise_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
        )
    with col3:
        if st.button("�️ Clear All"):
            if st.checkbox("Confirm clear all history"):
                clear_chat_history()
                st.success("Chat history cleared!")
                st.rerun()
    
    st.markdown("---")
    
    # Display chat history
    for idx, msg in enumerate(st.session_state.chat_history):
        role = msg.get("role", "assistant").lower()
        content = msg.get("content", "")
        timestamp = msg.get("timestamp")
        
        try:
            msg_timestamp = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M") if timestamp else ""
        except Exception:
            msg_timestamp = ""
        
        if role == "user":
            speaker = "🧑‍💻 You"
            if msg_timestamp:
                st.markdown(f"**{speaker}** ({msg_timestamp})")
            else:
                st.markdown(f"**{speaker}**")
            st.info(content)
        else:
            speaker = "🤖 AI"
            if msg_timestamp:
                st.markdown(f"**{speaker}** ({msg_timestamp})")
            else:
                st.markdown(f"**{speaker}**")
            st.success(content)
        
        st.markdown("---")

# ------------------------------
# Template Builder
# ------------------------------
def show_template_page():
    st.title("📋 Structure Builder")
    st.markdown("Define your document structure and let AI generate content for each section!")
    
    if st.session_state.structure_selection_message:
        st.success(st.session_state.structure_selection_message)
    
    def _load_structure_into_generator(template_label: str, sections: List[str], *, main_topic: Optional[str] = None, description: str = "") -> None:
        """Persist the selected structure and cue the user to generate content."""
        st.session_state.selected_template = template_label or "Custom Structure"
        st.session_state.custom_sections = sections.copy()
        st.session_state.main_topic = main_topic or template_label or "Custom Structure"
        st.session_state.additional_context = description
        st.session_state.section_results = {}
        st.session_state.structure_selection_message = (
            f"Structure '{st.session_state.selected_template}' selected. Open the Generator tab to start creating content."
        )
        st.session_state.structured_prompt_input = ""
        st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["Use Example Structures", "Create Custom Structure", "My Saved Templates"])
    
    with tab1:
        st.subheader("Pre-built Structure Templates")
        st.info("💡 Select a template to see example sections, then customize or use as-is")
        
        for structure_name, sections in EXAMPLE_STRUCTURES.items():
            with st.expander(f"📄 {structure_name}"):
                st.markdown("**Sections:**")
                for i, section in enumerate(sections, 1):
                    st.markdown(f"{i}. {section}")
                
                if st.button(f"Open \"{structure_name}\" in Generator", key=f"open_{structure_name}"):
                    _load_structure_into_generator(structure_name, sections, main_topic=structure_name)
    
    with tab2:
        st.subheader("Create Your Own Document Structure")
        st.markdown("Define the sections/parts of your document below:")
        
        # Main topic input
        main_topic = st.text_input(
            "📌 Template Name:",
            placeholder="e.g., Research Paper, Marketing Report, Project Proposal",
            help="Give your template a memorable name",
            key="template_name_input"
        )
        
        # Description
        description = st.text_area(
            "📝 Template Description (Optional):",
            placeholder="Describe when to use this template...",
            height=80,
            key="template_desc_input"
        )
        
        # Number of sections
        num_sections = st.number_input(
            "Number of Sections:",
            min_value=2,
            max_value=20,
            value=5,
            help="How many sections will your document have?"
        )
        
        # Section input
        st.markdown("### Define Each Section:")
        custom_sections = []
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("**Section Name**")
        with col2:
            st.markdown("**Order**")
        
        for i in range(int(num_sections)):
            col1, col2 = st.columns([3, 1])
            with col1:
                section_name = st.text_input(
                    f"Section {i+1}",
                    placeholder=f"e.g., Introduction, Methodology, Results...",
                    key=f"section_{i}",
                    label_visibility="collapsed"
                )
                if section_name.strip():
                    custom_sections.append(section_name.strip())
            with col2:
                st.text(f"{i+1}")
        
        # Preview
        if custom_sections:
            st.markdown("---")
            st.markdown("### 📋 Structure Preview:")
            if main_topic:
                st.markdown(f"**Template Name:** {main_topic}")
            if description:
                st.markdown(f"**Description:** {description}")
            st.markdown("**Sections:**")
            for i, section in enumerate(custom_sections, 1):
                st.markdown(f"{i}. {section}")
        
        # Save and use buttons
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🚀 Open in Generator", type="primary", disabled=not custom_sections or not main_topic):
                _load_structure_into_generator(main_topic or "Custom Structure", custom_sections, main_topic=main_topic, description=description)
        
        with col2:
            if st.button("💾 Save Template", disabled=not custom_sections or not main_topic):
                if custom_sections and main_topic:
                    success, message = save_template(main_topic, custom_sections, description)
                    if success:
                        st.success(f"✅ {message}")
                    else:
                        st.error(f"❌ {message}")
                else:
                    st.error("Please define template name and sections")
    
    with tab3:
        st.subheader("My Saved Templates")
        
        if not st.session_state.templates:
            st.info("No saved templates found. Create one in the 'Create Custom Structure' tab!")
            return
        
        search_col, refresh_col = st.columns([4, 1])
        with search_col:
            search_term = st.text_input(
                "Search templates",
                placeholder="Search by name or description...",
                key="template_search_term",
            )
        with refresh_col:
            if st.button("🔄 Refresh", key="template_refresh"):
                st.rerun()
        
        templates = list(st.session_state.templates.values())
        
        # Filter by search term
        if search_term:
            query = search_term.strip().lower()
            templates = [
                t for t in templates
                if query in t.get("template_name", "").lower() or query in t.get("description", "").lower()
            ]
        
        if not templates:
            st.info("No templates match the current filters.")
            return
        
        # Sort by updated_at
        templates.sort(key=lambda t: t.get("updated_at", 0), reverse=True)
        
        st.markdown(f"**Found {len(templates)} template(s)**")
        st.markdown("---")
        
        # Display templates
        for template in templates:
            template_id = template.get("template_id", "")
            template_name = template.get("template_name", "Untitled")
            description = template.get("description", "")
            sections = template.get("sections", [])
            updated_at = template.get("updated_at", 0)
            
            with st.expander(f"📋 {template_name}"):
                if description:
                    st.markdown(f"**Description:** {description}")
                if updated_at:
                    try:
                        last_updated = datetime.fromtimestamp(updated_at).strftime("%Y-%m-%d %H:%M:%S")
                        st.caption(f"Last updated: {last_updated}")
                    except Exception:
                        pass
                
                st.markdown(f"**Sections ({len(sections)}):**")
                for i, section in enumerate(sections, 1):
                    st.markdown(f"{i}. {section}")
                
                download_payload = json.dumps(template, indent=2)
                action_cols = st.columns(3)
                
                with action_cols[0]:
                    if st.button(f"✅ Use Template", key=f"use_template_{template_id}"):
                        _load_structure_into_generator(template_name, sections, main_topic=template_name, description=description)
                
                with action_cols[1]:
                    st.download_button(
                        "⬇️ Download",
                        download_payload,
                        file_name=f"writewise_template_{template_name.replace(' ', '_').lower() or 'template'}.json",
                        mime="application/json",
                        key=f"download_template_{template_id}"
                    )
                
                with action_cols[2]:
                    if st.button(f"🗑️ Delete", key=f"delete_template_{template_id}"):
                        if delete_template(template_id):
                            st.success(f"Template '{template_name}' deleted!")
                            st.rerun()
                        else:
                            st.error("Failed to delete template")
                
                # Edit template
                with st.expander("✏️ Edit Template", expanded=False):
                    sections_text = "\n".join(sections)
                    with st.form(f"edit_template_form_{template_id}"):
                        new_name = st.text_input("Template Name", value=template_name)
                        new_description = st.text_area("Description", value=description or "", height=100)
                        new_sections_raw = st.text_area(
                            "Sections (one per line)",
                            value=sections_text,
                            height=160
                        )
                        submitted = st.form_submit_button("Save Changes")
                        if submitted:
                            new_sections = [line.strip() for line in new_sections_raw.splitlines() if line.strip()]
                            if not new_name.strip():
                                st.error("Template name is required.")
                            elif not new_sections:
                                st.error("Please provide at least one section.")
                            else:
                                success, message = update_template(
                                    template_id=template_id,
                                    template_name=new_name.strip(),
                                    sections=new_sections,
                                    description=new_description.strip(),
                                )
                                if success:
                                    st.success(message)
                                    st.rerun()
                                else:
                                    st.error(message)

# ------------------------------
# Main Generator Page
# ------------------------------
def show_generator_page():
    st.title("Write Wise - AI Content Generator")
    st.subheader("Generate high-quality content from your prompts!")
    
    # Show chat history count
    col1, col2 = st.columns([3, 1])
    with col1:
        message_count = len(st.session_state.chat_history)
        st.caption(f"� Chat messages: {message_count}")
    with col2:
        if st.button("🗑️ Clear Chat"):
            if message_count > 0:
                clear_chat_history()
                st.success("Chat cleared!")
                st.rerun()
    
    # Template selection
    if st.session_state.selected_template:
        st.success(f"✅ Using structure: {st.session_state.selected_template}")
        if st.button("❌ Clear Structure"):
            st.session_state.selected_template = None
            st.session_state.custom_sections = None
            st.session_state.main_topic = None
            st.session_state.additional_context = None
            st.session_state.structure_selection_message = None
            st.session_state.pop("structured_prompt_input", None)
            st.rerun()
    
    # Structure-based input
    if st.session_state.selected_template and hasattr(st.session_state, 'custom_sections') and st.session_state.custom_sections:
        st.markdown("---")
        st.markdown("### 📋 Document Structure")
        
        # Show main topic
        if hasattr(st.session_state, 'main_topic') and st.session_state.main_topic:
            st.markdown(f"**Topic:** {st.session_state.main_topic}")
            main_topic = st.session_state.main_topic
        else:
            main_topic = st.text_input("📌 Enter your main topic:", key="topic_input")
        
        # Show structure
        st.markdown("**Sections to be generated:**")
        sections = st.session_state.custom_sections
        for i, section in enumerate(sections, 1):
            st.markdown(f"{i}. {section}")
        
        # Additional context
        if hasattr(st.session_state, 'additional_context') and st.session_state.additional_context:
            st.markdown(f"**Additional Context:** {st.session_state.additional_context}")
            additional_context = st.session_state.additional_context
        else:
            additional_context = st.text_area(
                "Additional context or instructions (optional):",
                placeholder="Any specific requirements, focus areas, or guidelines...",
                height=80,
                key="context_input"
            )
        
        custom_prompt_input = st.text_area(
            "Enter your prompt:",
            height=150,
            key="structured_prompt_input",
            placeholder="Describe the angle, audience, or specifics you want reflected in the content..."
        )
        
        # Build structured prompt
        user_prompt = f"Topic: {main_topic}\n\n"
        if custom_prompt_input:
            user_prompt += f"Prompt: {custom_prompt_input}\n\n"
        if additional_context:
            user_prompt += f"Context: {additional_context}\n\n"
        user_prompt += "Please generate comprehensive content for the following document structure:\n\n"
        for i, section in enumerate(sections, 1):
            user_prompt += f"{i}. {section}\n"
        
        st.markdown("---")
        with st.expander("👁️ View Generated Prompt"):
            st.code(user_prompt)
        
        base_system_instruction = f"""You are a professional content generator. Generate a comprehensive, well-structured document based on the provided structure.

For each section:
- Write detailed, relevant content specific to that section
- Maintain consistency in tone and style throughout
- Use proper formatting with clear headings
- Include examples, data, or explanations as appropriate for each section
- Ensure smooth transitions between sections

Format your response with clear section headers (use ## for section titles) so each part is easily identifiable."""
        
        # Option to generate all sections or one at a time
        generation_mode = st.radio(
            "Generation Mode:",
            ["Generate All Sections at Once", "Generate Sections One by One"],
            help="Choose whether to generate the entire document or section by section"
        )
        
        st.session_state.generation_mode = generation_mode
        
    else:
        # Standard prompt input
        user_prompt = st.text_area("Enter your prompt:", height=150, key="main_prompt")
        base_system_instruction = "You are AiGuru, a professional AI content generator."
        st.session_state.generation_mode = None
    
    # Model selection
    if "model_choice" not in st.session_state:
        st.session_state.model_choice = "gemini-2.5-flash"
    
    col1, col2 = st.columns(2)
    with col1:
        model_choice = st.selectbox(
            "Choose AI model:",
            ["gemini-2.5-pro", "gemini-2.5-flash"],
            index=0,
            key="model_choice",
        )
    
    with col2:
        depth_choice = st.selectbox(
            "Content Depth:",
            [
                "Shallow (high-level overview)",
                "Medium (moderate detail with examples)",
                "Deep (very detailed, nuanced, in-depth analysis)"
            ],
            index=1
        )
    
    # Tone selection
    tone_choice = st.selectbox(
        "🎭 Choose Tone/Theme:",
        list(TONE_PRESETS.keys()),
        help="Select the tone and style for your content"
    )
    
    # Format selection
    format_choice = st.selectbox(
        "📐 Output Format:",
        list(FORMAT_OPTIONS.keys()),
        index=3,  # Default to "Mixed"
        help="Choose how you want the content structured"
    )
    
    # Map depth to instructions
    depth_instruction_map = {
        "Shallow (high-level overview)": "Provide a clear and simple overview. Focus on key points, avoid unnecessary details.",
        "Medium (moderate detail with examples)": "Provide a moderately detailed explanation with examples and supporting points.",
        "Deep (very detailed, nuanced, in-depth analysis)": "Provide an in-depth, thorough, and nuanced explanation. Include examples, multiple perspectives, reasoning, and insights."
    }
    
    depth_instruction = depth_instruction_map[depth_choice]
    tone_instruction = TONE_PRESETS[tone_choice]
    format_instruction = FORMAT_OPTIONS[format_choice]
    
    # Generate button
    if st.session_state.generation_mode == "Generate Sections One by One":
        st.markdown("---")
        st.markdown("### Generate Sections")
        
        # Initialize section results storage
        if "section_results" not in st.session_state:
            st.session_state.section_results = {}
        
        # Generate individual sections
        sections = st.session_state.custom_sections
        for i, section in enumerate(sections, 1):
            col1, col2, col3 = st.columns([2, 1, 1])
            with col1:
                st.markdown(f"**{i}. {section}**")
            with col2:
                generate_section = st.button(f"Generate", key=f"gen_section_{i}")
            with col3:
                if section in st.session_state.section_results:
                    st.success("✅ Done")
            
            if generate_section:
                main_topic = st.session_state.get('main_topic', '')
                additional_context = st.session_state.get('additional_context', '')
                custom_prompt_input = st.session_state.get('structured_prompt_input', '')
                
                if not additional_context:
                    additional_context = st.session_state.get('context_input', '')
                
                if custom_prompt_input:
                    user_requirements = f"User Requirements/Prompt: {custom_prompt_input}\n\n"
                else:
                    user_requirements = ""
                
                section_prompt = (
                    f"Topic: {main_topic}\n\n"
                    f"{user_requirements}"
                    f"Section to generate: {section}\n\n"
                    f"Context: {additional_context}\n\n"
                    "Please generate detailed, comprehensive content specifically for this section. "
                    "Ensure the response reflects the user's requirements and stays tightly aligned with the section focus."
                )
                
                with st.spinner(f"Generating {section}..."):
                    try:
                        system_prompt = f"""
{base_system_instruction}

CONTENT DEPTH: {depth_instruction}
TONE & STYLE: {tone_instruction}
OUTPUT FORMAT: {format_instruction}

Generate high-quality content for this specific section. Focus on relevance, clarity, and completeness.
"""
                        model = genai.GenerativeModel(
                            model_name=model_choice,
                            system_instruction=system_prompt
                        )
                        
                        response = model.generate_content(
                            section_prompt,
                            generation_config={
                                "max_output_tokens": 8000,
                                "temperature": 0.35
                            },
                        )
                        
                        # Extract text
                        output_text = ""
                        if hasattr(response, "candidates") and response.candidates:
                            for candidate in response.candidates:
                                content = getattr(candidate, "content", None)
                                if content and getattr(content, "parts", None):
                                    for part in content.parts:
                                        output_text += getattr(part, "text", "")
                        
                        if not output_text and getattr(response, "text", None):
                            output_text = response.text
                        
                        if output_text.strip():
                            st.session_state.section_results[section] = output_text
                            st.success(f"✅ {section} generated!")
                            st.markdown(output_text)
                        else:
                            st.error(f"Failed to generate {section}")
                    
                    except Exception as e:
                        st.error(f"Error generating {section}: {e}")
            
            # Show existing content if available
            elif section in st.session_state.section_results:
                with st.expander(f"View {section} content"):
                    st.markdown(st.session_state.section_results[section])
        
        # Compile all sections button
        st.markdown("---")
        if len(st.session_state.section_results) > 0:
            if st.button("📄 Compile All Sections into Final Document", type="primary"):
                final_document = f"# {st.session_state.get('main_topic', 'Document')}\n\n"
                
                for i, section in enumerate(sections, 1):
                    if section in st.session_state.section_results:
                        final_document += f"## {i}. {section}\n\n"
                        final_document += st.session_state.section_results[section] + "\n\n"
                    else:
                        final_document += f"## {i}. {section}\n\n[Content not generated yet]\n\n"
                
                st.markdown("---")
                st.markdown("### 📄 Complete Document")
                st.markdown(final_document)
                
                # Save compiled document
                save_message(
                    "assistant",
                    final_document,
                    metadata={"title": f"{st.session_state.get('main_topic', 'Document')} - Compiled"}
                )
                
                # Download option
                st.download_button(
                    "📥 Download Complete Document",
                    final_document,
                    file_name=f"{st.session_state.get('main_topic', 'document').replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                )
                
                # Clear sections button
                if st.button("🔄 Start Over (Clear All Sections)"):
                    st.session_state.section_results = {}
                    st.rerun()
        
        generate_btn = False
    else:
        generate_btn = st.button("✨ Generate Content", type="primary", use_container_width=True)
    
    if generate_btn:
        if not user_prompt.strip():
            st.warning("Please enter a prompt to generate content.")
        else:
            with st.spinner("Generating content..."):
                start_time = datetime.now()
                
                try:
                    # Save user message
                    save_message(
                        "user",
                        user_prompt,
                        metadata={"title": user_prompt[:50] + "..."}
                    )
                    
                    # Build comprehensive system prompt
                    system_prompt = f"""
{base_system_instruction}

CONTENT DEPTH: {depth_instruction}
TONE & STYLE: {tone_instruction}
OUTPUT FORMAT: {format_instruction}

Your task is to generate high-quality content based on the user's prompt.
Use proper grammar and structure, adapt tone appropriately, include headings or examples if needed, and avoid filler or repetition.
"""
                    
                    model = genai.GenerativeModel(
                        model_name=model_choice,
                        system_instruction=system_prompt
                    )
                    
                    # Generate content
                    response = model.generate_content(
                        user_prompt,
                        generation_config={
                            "max_output_tokens": 20000,
                            "temperature": 0.35
                        },
                    )
                    
                    # Extract text
                    output_text = ""
                    if hasattr(response, "candidates") and response.candidates:
                        for candidate in response.candidates:
                            content = getattr(candidate, "content", None)
                            if content and getattr(content, "parts", None):
                                for part in content.parts:
                                    output_text += getattr(part, "text", "")
                    
                    if not output_text and getattr(response, "text", None):
                        output_text = response.text
                    
                    # Display results
                    if output_text.strip():
                        # Save assistant response
                        save_message(
                            "assistant",
                            output_text,
                            metadata={"title": user_prompt[:50] + "..."}
                        )
                        
                        st.success("✅ Content Generated Successfully!")
                        
                        # Calculate generation time
                        elapsed_time = (datetime.now() - start_time).total_seconds()
                        st.caption(f"⏱️ Generated in {elapsed_time:.2f} seconds")
                        
                        st.markdown("---")
                        st.markdown(output_text)
                        
                        # Download options
                        st.markdown("---")
                        download_col, info_col = st.columns([2, 3])
                        with download_col:
                            st.download_button(
                                "📥 Download as Text",
                                output_text,
                                file_name=f"writewise_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                mime="text/plain",
                            )
                        with info_col:
                            st.caption("Download the generated content to share or edit further.")
                    else:
                        st.error("⚠️ No content returned by the model. Try a different prompt or model.")
                
                except Exception as e:
                    st.error(f"❌ Error generating content: {e}")

# ------------------------------
# Navigation & Main App
# ------------------------------
# Sidebar navigation
with st.sidebar:
    st.title("🧭 Navigation")
    
    page = st.radio(
        "Go to:",
        ["✨ Generator", "📚 History", "📋 Structure Builder"],
        index=["generator", "history", "templates"].index(st.session_state.current_page) if st.session_state.current_page in ["generator", "history", "templates"] else 0,
    )
    
    # Update current page
    if page == "✨ Generator":
        st.session_state.current_page = "generator"
    elif page == "📚 History":
        st.session_state.current_page = "history"
    elif page == "📋 Structure Builder":
        st.session_state.current_page = "templates"
    
# Show appropriate page
if st.session_state.current_page == "generator":
    show_generator_page()
elif st.session_state.current_page == "history":
    show_history_page()
elif st.session_state.current_page == "templates":
    show_template_page()

# Footer
st.markdown("---")
st.caption("💡 Your data is stored locally in your browser")
st.caption("Developed by Write Wise Team")
