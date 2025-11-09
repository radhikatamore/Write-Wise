import os
import streamlit as st
import google.generativeai as genai
import uuid
import json
import firebase_client
from datetime import datetime
from typing import List, Optional

st.set_page_config(page_title="Write Wise - AI Content Generator", layout="wide", page_icon="✍️")


def _ensure_firebase_config_from_secrets():
    """Populate environment variables from Streamlit secrets if available."""
    firebase_env_keys = [
        "FIREBASE_API_KEY",
        "FIREBASE_AUTH_DOMAIN",
        "FIREBASE_DATABASE_URL",
        "FIREBASE_PROJECT_ID",
        "FIREBASE_STORAGE_BUCKET",
        "FIREBASE_MESSAGING_SENDER_ID",
        "FIREBASE_APP_ID",
    ]

    secrets_sources = [st.secrets]
    if "firebase" in st.secrets and isinstance(st.secrets["firebase"], dict):
        secrets_sources.append(st.secrets["firebase"])

    updated = False
    for key in firebase_env_keys:
        value = None
        for source in secrets_sources:
            if key in source:
                value = source[key]
                break
        if value is not None and os.environ.get(key) != str(value):
            os.environ[key] = str(value)
            updated = True

    if updated:
        firebase_client.client = firebase_client.FirebaseClient()


_ensure_firebase_config_from_secrets()

# ------------------------------
# Configure Gemini API Key
# ------------------------------
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", None)
if not GEMINI_API_KEY:
    st.error("GEMINI_API_KEY not found in Streamlit secrets.")
    st.stop()

genai.configure(api_key=GEMINI_API_KEY)

# ------------------------------
# Initialize Session State
# ------------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "do_not_store" not in st.session_state:
    st.session_state.do_not_store = False
if "private_session_enabled" not in st.session_state:
    st.session_state.private_session_enabled = st.session_state.do_not_store
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
if "persistent_session_token" not in st.session_state:
    st.session_state.persistent_session_token = None
if "persistent_session_checked" not in st.session_state:
    st.session_state.persistent_session_checked = False
if "structure_selection_message" not in st.session_state:
    st.session_state.structure_selection_message = None

def _get_query_param(name: str) -> Optional[str]:
    value = st.query_params.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _set_query_param(name: str, value: str) -> None:
    try:
        st.query_params[name] = value
    except Exception:
        pass


def _remove_query_param(name: str) -> None:
    try:
        del st.query_params[name]
    except Exception:
        pass


if not st.session_state.user and not st.session_state.persistent_session_checked:
    session_token = _get_query_param("session")
    if session_token:
        restored_user, message = firebase_client.resume_session(session_token)
        warning_msg = firebase_client.pop_last_error()
        if warning_msg:
            st.warning(warning_msg)
        if restored_user:
            st.session_state.user = restored_user
            st.session_state.persistent_session_token = session_token
        else:
            _remove_query_param("session")
            st.session_state.persistent_session_token = None
            if message:
                st.warning(f"Session refresh required: {message}")
    st.session_state.persistent_session_checked = True


def _surface_firebase_warning() -> None:
    """Display any pending Firebase warning to the user."""
    message = firebase_client.pop_last_error()
    if message:
        st.warning(message)

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
# Authentication Functions
# ------------------------------
def show_auth_page():
    st.title("🔐 Welcome to Write Wise")

    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        st.subheader("Login to Your Account")
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")

            if submit:
                if not email or not password:
                    st.error("Please provide both email and password")
                else:
                    user, message = firebase_client.authenticate_user(email, password)
                    if user and isinstance(user, dict):
                        st.session_state.user = user
                        if st.session_state.persistent_session_token:
                            firebase_client.delete_persistent_session(st.session_state.persistent_session_token)
                            residual_warning = firebase_client.pop_last_error()
                            if residual_warning:
                                st.warning(residual_warning)
                        st.session_state.persistent_session_token = None

                        refresh_token = user.get("refresh_token")
                        session_token, session_message = firebase_client.create_persistent_session(
                            user.get("uid"),
                            refresh_token,
                            metadata={"email": user.get("email")}
                        ) if refresh_token else (None, "")
                        warning_msg = firebase_client.pop_last_error()
                        if warning_msg:
                            st.warning(warning_msg)

                        if session_token:
                            st.session_state.persistent_session_token = session_token
                            _set_query_param("session", session_token)
                        elif session_message:
                            st.info(f"Login succeeded, but session won't persist: {session_message}")

                        st.success(f"Welcome back! {message}")
                        st.rerun()
                    else:
                        st.error(f"Login failed: {message}")

        st.markdown("---")
        if st.button("Continue as Guest"):
            if st.session_state.persistent_session_token:
                firebase_client.delete_persistent_session(st.session_state.persistent_session_token)
                warning_msg = firebase_client.pop_last_error()
                if warning_msg:
                    st.warning(warning_msg)
            st.session_state.persistent_session_token = None
            _remove_query_param("session")
            st.session_state.structure_selection_message = None
            st.session_state.user = {"guest": True, "email": "guest"}
            st.session_state.do_not_store = True
            st.info("Continuing as guest - your sessions will not be saved")
            st.rerun()

    with register_tab:
        st.subheader("Create New Account")
        with st.form("register_form"):
            new_email = st.text_input("Email", key="register_email")
            new_password = st.text_input("Password", type="password", key="register_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="register_confirm_password")
            submit_reg = st.form_submit_button("Register")

            if submit_reg:
                if not new_email or not new_password:
                    st.error("Please provide both email and password")
                elif new_password != confirm_password:
                    st.error("Passwords do not match")
                elif len(new_password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    success, message = firebase_client.register_user(new_email, new_password)
                    if success:
                        st.success(f"✅ {message} Please login with your credentials.")
                    else:
                        st.error(f"Registration failed: {message}")
# ------------------------------
# History Viewer
# ------------------------------
def show_history_page():
    st.title("📚 Session History")

    if not firebase_client.is_configured():
        st.warning("History is unavailable because Firebase is not configured.")
        return

    if not st.session_state.user or st.session_state.user.get("guest"):
        st.info("Login with your Write Wise account to view saved sessions.")
        return

    user_id = st.session_state.user.get("uid") or st.session_state.user.get("$id")
    if not user_id:
        st.error("Unable to determine user ID. Please log out and log in again.")
        return

    search_col, export_col, refresh_col = st.columns([3, 1, 1])
    with search_col:
        search_term = st.text_input("Search sessions", placeholder="Search by title...", key="history_search_term")
    with export_col:
        export_data = firebase_client.export_history(user_id)
        st.download_button(
            "⬇️ Export JSON",
            export_data,
            file_name=f"writewise_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json",
            key="history_export_button",
        )
    with refresh_col:
        if st.button("🔄 Refresh", key="history_refresh_button"):
            st.rerun()

    sessions = firebase_client.list_sessions(user_id, search_term=search_term or None)
    _surface_firebase_warning()

    if not sessions:
        st.info("No saved sessions yet. Generate content to build your history.")
        return

    for session in sessions:
        session_id = session.get("session_id")
        title = session.get("title", "Untitled Session")
        updated_at = session.get("updated_at")
        created_at = session.get("created_at")
        message_count = session.get("message_count", 0)

        subtitle_parts = []
        if created_at:
            try:
                subtitle_parts.append(f"Created {datetime.fromtimestamp(created_at).strftime('%Y-%m-%d %H:%M')}")
            except Exception:
                pass
        if updated_at:
            try:
                subtitle_parts.append(f"Updated {datetime.fromtimestamp(updated_at).strftime('%Y-%m-%d %H:%M')}")
            except Exception:
                pass
        subtitle = " • ".join(subtitle_parts)

        with st.expander(f"🗂️ {title}"):
            if subtitle:
                st.caption(subtitle)
            st.caption(f"Messages: {message_count}")

            messages = firebase_client.get_messages(session_id, user_id=user_id)
            _surface_firebase_warning()
            if not messages:
                st.info("No messages stored for this session.")
            else:
                for msg in messages:
                    role = (msg.get("role") or "assistant").lower()
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

            action_col1, action_col2 = st.columns(2)
            with action_col1:
                if st.button("📂 Load Session", key=f"load_{session_id}"):
                    st.session_state.session_id = session_id
                    st.session_state.current_page = "generator"
                    st.rerun()
            with action_col2:
                if st.button("🗑️ Delete Session", key=f"delete_{session_id}"):
                    if firebase_client.delete_session(session_id, user_id):
                        st.success(f"Session '{title}' deleted!")
                        st.rerun()
                    else:
                        st.error("Failed to delete session")

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
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🚀 Open in Generator", type="primary", disabled=not custom_sections or not main_topic):
                _load_structure_into_generator(main_topic or "Custom Structure", custom_sections, main_topic=main_topic, description=description)
        
        with col2:
            if st.button("💾 Save Template", disabled=not custom_sections or not main_topic):
                if st.session_state.user and not st.session_state.user.get("guest"):
                    user_id = st.session_state.user.get("uid") or st.session_state.user.get("$id")
                    success, message = firebase_client.save_template(
                        user_id=user_id,
                        template_name=main_topic,
                        sections=custom_sections,
                        description=description,
                        is_public=False
                    )
                    if success:
                        st.success(f"✅ {message}")
                        _surface_firebase_warning()
                    else:
                        st.error(f"❌ {message}")
                        _surface_firebase_warning()
                elif not st.session_state.user or st.session_state.user.get("guest"):
                    st.warning("Please login to save templates")
                else:
                    st.error("Please define template name and sections")
        
        with col3:
            if st.button("🌐 Save as Public Template", disabled=not custom_sections or not main_topic):
                if st.session_state.user and not st.session_state.user.get("guest"):
                    user_id = st.session_state.user.get("uid") or st.session_state.user.get("$id")
                    success, message = firebase_client.save_template(
                        user_id=user_id,
                        template_name=main_topic,
                        sections=custom_sections,
                        description=description,
                        is_public=True
                    )
                    if success:
                        st.success(f"✅ {message} - Shared publicly!")
                        _surface_firebase_warning()
                    else:
                        st.error(f"❌ {message}")
                        _surface_firebase_warning()
                elif not st.session_state.user or st.session_state.user.get("guest"):
                    st.warning("Please login to save templates")
                else:
                    st.error("Please define template name and sections")
    
    with tab3:
        st.subheader("My Saved Templates")
        
        if not st.session_state.user or st.session_state.user.get("guest"):
            st.warning("Please login to view saved templates")
            return
        
        user_id = st.session_state.user.get("uid") or st.session_state.user.get("$id")
        
        filter_col, visibility_col, refresh_col = st.columns([3, 2, 1])
        with filter_col:
            search_term = st.text_input(
                "Search templates",
                placeholder="Search by name, description, or section keyword...",
                key="template_search_term",
            )
        visibility_options = ["Private", "Public", "Community"]
        with visibility_col:
            selected_visibility = st.multiselect(
                "Visibility",
                visibility_options,
                default=visibility_options,
                key="template_visibility_filter",
                help="Filter between your private templates, templates you shared publicly, and community templates.",
            )
        with refresh_col:
            if st.button("🔄 Refresh"):
                st.rerun()

        include_public = any(option in selected_visibility for option in ("Public", "Community"))
        templates = firebase_client.list_templates(user_id, include_public=include_public)
        _surface_firebase_warning()

        if not templates:
            st.info("No saved templates found. Create one in the 'Create Custom Structure' tab!")
            return

        sort_col, _ = st.columns([2, 3])
        with sort_col:
            sort_option = st.selectbox(
                "Sort by",
                ["Recently updated", "Name (A-Z)"]
            )

        def _visibility_label(tmpl: dict) -> str:
            if tmpl.get("is_public_shared"):
                return "Community"
            if tmpl.get("is_public"):
                return "Public"
            return "Private"

        filtered_templates = []
        query = (search_term or "").strip().lower()
        for template in templates:
            visibility_label = _visibility_label(template)
            if selected_visibility and visibility_label not in selected_visibility:
                continue

            if query:
                haystacks = [
                    template.get("template_name", ""),
                    template.get("description", ""),
                    " ".join(template.get("sections", [])),
                ]
                if not any(query in (value or "").lower() for value in haystacks):
                    continue

            filtered_templates.append(template)

        if not filtered_templates:
            st.info("No templates match the current filters.")
            return

        if sort_option == "Name (A-Z)":
            filtered_templates.sort(key=lambda t: (t.get("template_name") or "").lower())
        else:
            filtered_templates.sort(key=lambda t: t.get("updated_at", 0), reverse=True)

        st.markdown(f"**Found {len(filtered_templates)} template(s)**")
        st.markdown("---")

        # Display templates
        for template in filtered_templates:
            template_id = template.get("template_id", "")
            template_name = template.get("template_name", "Untitled")
            description = template.get("description", "")
            sections = template.get("sections", [])
            is_public = template.get("is_public", False)
            is_public_shared = template.get("is_public_shared", False)
            template_user_id = template.get("user_id", "")
            updated_at = template.get("updated_at", 0)
            
            # Determine template type icon
            if is_public_shared:
                icon = "🌐"
                type_label = "Public Template"
            elif is_public:
                icon = "🌐"
                type_label = "Your Public Template"
            else:
                icon = "📋"
                type_label = "Private Template"
            
            with st.expander(f"{icon} {template_name} - {type_label}"):
                if description:
                    st.markdown(f"**Description:** {description}")
                if updated_at:
                    try:
                        last_updated = datetime.fromtimestamp(updated_at).strftime("%Y-%m-%d %H:%M:%S")
                        st.caption(f"Last updated: {last_updated}")
                    except Exception:
                        pass
                if is_public_shared and template_user_id:
                    st.caption("Community share")
                
                st.markdown(f"**Sections ({len(sections)}):**")
                for i, section in enumerate(sections, 1):
                    st.markdown(f"{i}. {section}")

                download_payload = json.dumps(template, indent=2)
                owner = template_user_id == user_id
                action_cols = st.columns(4 if owner else 2)
                
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

                if owner:
                    with action_cols[2]:
                        if st.button(f"🗑️ Delete", key=f"delete_template_{template_id}"):
                            if firebase_client.delete_template(template_id, user_id):
                                st.success(f"Template '{template_name}' deleted!")
                                _surface_firebase_warning()
                                st.rerun()
                            else:
                                st.error("Failed to delete template")
                                _surface_firebase_warning()

                    with action_cols[3]:
                        new_visibility = "🔒 Make Private" if is_public else "🌐 Make Public"
                        if st.button(new_visibility, key=f"toggle_visibility_{template_id}"):
                            success, message = firebase_client.update_template(
                                template_id=template_id,
                                user_id=user_id,
                                is_public=not is_public
                            )
                            if success:
                                st.success(message)
                                _surface_firebase_warning()
                                st.rerun()
                            else:
                                st.error(message)
                                _surface_firebase_warning()

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
                            new_public_state = st.checkbox(
                                "Share publicly",
                                value=is_public,
                                help="When enabled, this template is available to other Write Wise users."
                            )
                            submitted = st.form_submit_button("Save Changes")
                            if submitted:
                                new_sections = [line.strip() for line in new_sections_raw.splitlines() if line.strip()]
                                if not new_name.strip():
                                    st.error("Template name is required.")
                                elif not new_sections:
                                    st.error("Please provide at least one section.")
                                else:
                                    success, message = firebase_client.update_template(
                                        template_id=template_id,
                                        user_id=user_id,
                                        template_name=new_name.strip(),
                                        sections=new_sections,
                                        description=new_description.strip(),
                                        is_public=new_public_state,
                                    )
                                    if success:
                                        st.success(message)
                                        _surface_firebase_warning()
                                        st.rerun()
                                    else:
                                        st.error(message)
                                        _surface_firebase_warning()

# ------------------------------
# Main Generator Page
# ------------------------------
def show_generator_page():
    st.title("Write Wise - AI Content Generator")
    st.subheader("Generate high-quality content from your prompts!")
    
    # User info display
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.session_state.user:
            if st.session_state.user.get("guest"):
                st.caption("🌐 Guest Mode (not saved)")
            else:
                st.caption(f"👤 Logged in as: {st.session_state.user.get('email', 'User')}")
    with col2:
        if st.button("🚪 Logout" if st.session_state.user and not st.session_state.user.get("guest") else "🏠 Exit Guest"):
            if st.session_state.persistent_session_token:
                firebase_client.delete_persistent_session(st.session_state.persistent_session_token)
                warning_msg = firebase_client.pop_last_error()
                if warning_msg:
                    st.warning(warning_msg)
            st.session_state.persistent_session_token = None
            _remove_query_param("session")
            st.session_state.structure_selection_message = None
            st.session_state.user = None
            st.session_state.session_id = str(uuid.uuid4())
            st.rerun()
    
    # Privacy toggle for logged-in users
    if st.session_state.user and not st.session_state.user.get("guest"):
        st.session_state.do_not_store = st.checkbox(
            "🔒 Private Session (do not save this session)",
            value=st.session_state.do_not_store,
            help="Enable to keep this session ephemeral - it won't be saved to your history"
        )
    
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
            ["gemini-2.5-flash", "gemini-2.5-pro"],
            index=["gemini-2.5-flash", "gemini-2.5-pro"].index(st.session_state.model_choice) if st.session_state.model_choice in ["gemini-2.5-flash", "gemini-2.5-pro"] else 0,
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
                
                section_prompt = f"""Topic: {main_topic}

Section to generate: {section}

Context: {additional_context}

Please generate detailed, comprehensive content specifically for the "{section}" section of this document. 
Make sure the content is relevant, well-structured, and appropriate for this section."""
                
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
                user_id = st.session_state.user.get("uid") or st.session_state.user.get("$id") if st.session_state.user and not st.session_state.user.get("guest") else None
                if not st.session_state.do_not_store and user_id:
                    try:
                        firebase_client.save_message(
                            st.session_state.session_id,
                            "assistant",
                            final_document,
                            metadata={"title": f"{st.session_state.get('main_topic', 'Document')} - Compiled"},
                            user_id=user_id,
                            do_not_store=st.session_state.do_not_store
                        )
                    except Exception:
                        pass
                
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
                    user_id = st.session_state.user.get("uid") or st.session_state.user.get("$id") if st.session_state.user and not st.session_state.user.get("guest") else None
                    
                    if not st.session_state.do_not_store:
                        try:
                            firebase_client.save_message(
                                st.session_state.session_id,
                                "user",
                                user_prompt,
                                metadata={"title": user_prompt[:50] + "..."},
                                user_id=user_id,
                                do_not_store=st.session_state.do_not_store
                            )
                        except Exception:
                            pass
                    
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
                        if not st.session_state.do_not_store:
                            try:
                                firebase_client.save_message(
                                    st.session_state.session_id,
                                    "assistant",
                                    output_text,
                                    metadata={"title": user_prompt[:50] + "..."},
                                    user_id=user_id,
                                    do_not_store=st.session_state.do_not_store
                                )
                            except Exception:
                                pass
                        
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
# Check if user is authenticated
if not st.session_state.user:
    show_auth_page()
else:
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
        
        st.markdown("---")
        st.caption("Write Wise v2.0")
        st.caption("Powered by Google Gemini")
    
    # Show appropriate page
    if st.session_state.current_page == "generator":
        show_generator_page()
    elif st.session_state.current_page == "history":
        show_history_page()
    elif st.session_state.current_page == "templates":
        show_template_page()

# Footer
st.markdown("---")
st.caption("Developed by Write Wise Team")
