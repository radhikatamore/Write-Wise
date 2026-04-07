# Write Wise - AI Content Generator

**Developed by Write Wise Team**

A comprehensive AI-powered content generation platform built with Streamlit and Google Gemini. Generate structured documents, reports, blog posts, and more with customizable templates.

## ✨ Features

### 🔐 Authentication & User Management
- **User Registration & Login**: Secure account creation with bcrypt password hashing
- **Google Sign-In**: Quick authentication with your Google account
- **Guest Mode**: Try the application without creating an account
- **Session Management**: Automatic session tracking and user state management

### 📝 Smart Content Generation
- **Custom Structure Builder**: Define your own document structure/outline
  - Specify sections like Introduction, Methodology, Implementation, etc.
  - AI generates content for each section based on your topic
  - Generate all sections at once or one-by-one
- **Pre-built Structure Templates**:
  - Research Report (Intro, Methodology, Implementation, Demo, Requirements, Conclusion, etc.)
  - Blog Post (Hook, Background, Main Content, Examples, Takeaways, CTA)
  - Presentation/PPT (Title, Agenda, Problem, Solution, Demo, Q&A)
  - Technical Documentation (Overview, Features, Installation, API, FAQ)
  - Business Proposal (Executive Summary, Problem, Solution, ROI, Timeline)
- **Template Library Management**:
  - Search and filter saved templates by visibility or keyword
  - Edit, share, and download templates for reuse across teams

### 🎨 Customization Options
- **Tone/Theme Selection**: Academic, Blog, Technical, Marketing, Casual
- **Output Format Options**: Paragraph, Bulleted, Tabular, Mixed
- **Content Depth**: Shallow (overview), Medium (detailed), Deep (in-depth analysis)

### 📚 History & Export
- **Session History**: View all your past conversations and generated content
- **Search Functionality**: Find specific sessions quickly
- **Export Options**: 
  - Download individual documents as text/markdown
  - Export complete history as JSON
- **Privacy Mode**: "Do Not Store" toggle for ephemeral sessions

### 📈 Telemetry & Monitoring (Opt-in)
- Anonymous usage statistics
- Error tracking and performance metrics
- Helps improve the application

## 🚀 Getting Started

### Prerequisites
- Python 3.8 or higher
- Google Gemini API key
- Firebase project (for authentication and history storage)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/radhikatamore/Write-Wise.git
cd Write-Wise
```

2. **Create and activate virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure secrets**
```bash
mkdir -p .streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` and add your API keys:
```toml
# Required
GEMINI_API_KEY = "your_gemini_api_key_here"

# Required: Firebase Configuration
FIREBASE_API_KEY = "your_firebase_api_key"
FIREBASE_AUTH_DOMAIN = "your-project.firebaseapp.com"
FIREBASE_PROJECT_ID = "your-firebase-project-id"
FIREBASE_STORAGE_BUCKET = "your-project.appspot.com"
FIREBASE_MESSAGING_SENDER_ID = "your_sender_id"
FIREBASE_APP_ID = "your_app_id"
FIREBASE_DATABASE_URL = "https://your-project-default-rtdb.firebaseio.com"

# Optional: Google OAuth (for Google Sign-In)
GOOGLE_CLIENT_ID = "your_google_client_id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "your_google_client_secret"
GOOGLE_REDIRECT_URI = "http://localhost:8501"

```

5. **Run the application**
```bash
streamlit run app.py
```

The application will open in your default browser at `http://localhost:8501`

## 📖 Usage Guide

### Creating Structured Documents

1. **Navigate to Structure Builder** (📋 in sidebar)
2. **Choose a template** or create your own:
   - Use pre-built templates for common document types
   - Or define custom sections for your specific needs
3. **Enter your main topic** (e.g., "AI in Healthcare")
4. **Define sections** (e.g., Introduction, Methodology, Results, Conclusion)
5. **Add context** (optional): Target audience, focus areas, tone preferences
6. **Click "Use This Structure"** to proceed to generator

### Generating Content

#### Generate All Sections at Once
1. Select "Generate All Sections at Once" mode
2. Configure generation settings (model, depth, tone, format)
3. Click "✨ Generate Content"
4. Download the complete document

#### Generate Section by Section
1. Select "Generate Sections One by One" mode
2. Click "Generate" for each section individually
3. Review and regenerate specific sections as needed
4. Click "Compile All Sections" to create final document

### Example: Research Report

```
Topic: Sustainable Energy Solutions

Structure:
1. Introduction
2. Research Methodology
3. Implementation
4. Demo/Results
5. Software Requirements
6. Hardware Requirements
7. Conclusion
8. Future Scope
9. References

Context: Academic paper for university research project, 
target audience: professors and peers
```

The AI will generate comprehensive content for each section tailored to your topic and context.

## 🔧 Configuration

### Firebase Setup

1. **Create a Firebase project** at [console.firebase.google.com](https://console.firebase.google.com)

2. **Enable Authentication**:
   - Go to Authentication > Sign-in method
   - Enable **Email/Password**
   - Enable **Google** (if you want Google Sign-In)
   - For Google Sign-In, you'll get the OAuth client credentials

3. **Enable Realtime Database**:
   - Go to Realtime Database
   - Create database (start in test mode for development)
   - Set up security rules:
   ```json
   {
     "rules": {
       "users": {
         "$uid": {
           ".read": "$uid === auth.uid",
           ".write": "$uid === auth.uid"
         }
       },
       "messages": {
         ".read": "auth != null",
         ".write": "auth != null"
       },
       "sessions": {
         ".read": "auth != null",
         ".write": "auth != null"
       },
       "telemetry": {
         ".write": "auth != null"
       }
     }
   }
   ```

4. **Get Firebase Configuration**:
   - Go to Project Settings > General
   - Scroll to "Your apps" section
   - Click on the web app icon (</>) or add a new web app
   - Copy all the config values to your `secrets.toml`

5. **Get Google OAuth Credentials** (optional, for Google Sign-In):
   - Go to [Google Cloud Console](https://console.cloud.google.com)
   - Select your Firebase project
   - Go to APIs & Services > Credentials
   - Find your OAuth 2.0 Client ID (created automatically by Firebase)
   - Copy Client ID and Client Secret to `secrets.toml`
   - Add `http://localhost:8501` to Authorized redirect URIs

### Environment Variables

Alternatively, you can set environment variables instead of using `secrets.toml`:

```bash
export GEMINI_API_KEY="your_key"
export FIREBASE_API_KEY="your_firebase_key"
export FIREBASE_PROJECT_ID="your_project_id"
# ... etc
```

## 🧪 Testing

Run the test suite to verify functionality:

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_firebase_client.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

### Test Structure
- `tests/test_firebase_client.py`: In-memory unit and integration coverage for Firebase storage and history export

### Manual QA
- Follow the end-to-end checklist in `docs/manual_test_plan.md` for regression and release verification.

## 📝 Features in Detail

### Structure-Based Content Generation

The core feature of Write Wise is the ability to define custom document structures:

**How it works:**
1. User defines sections/parts of their document
2. User provides a main topic and context
3. AI generates content for each section individually
4. Sections maintain consistency in tone and style
5. Final document is compiled with proper formatting

**Benefits:**
- Consistent document structure
- Targeted content generation
- Easy regeneration of specific sections
- Flexible for any document type

### Privacy & Data Control

- **Guest Mode**: No data stored, completely ephemeral
- **Private Sessions**: Toggle "Do Not Store" for logged-in users
- **Data Export**: Full control over your data with JSON export
- **Secure Storage**: Passwords hashed with bcrypt

## 🏗️ Architecture

```
Write-Wise/
├── app.py                      # Main Streamlit application
├── firebase_client.py          # Firebase integration & authentication
├── requirements.txt            # Python dependencies
├── .streamlit/
│   ├── config.toml            # Streamlit configuration
│   └── secrets.toml           # API keys and secrets (not in git)
├── tests/
│   └── test_firebase_client.py   # Firebase storage unit/integration tests
└── docs/
  └── manual_test_plan.md    # Manual QA scenarios
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is developed by the Write Wise Team.

## 🙏 Acknowledgments

- Powered by Google Gemini AI
- Built with Streamlit
- Storage and authentication via Firebase
- Google Sign-In for easy authentication

## 📞 Support

For issues, questions, or suggestions, please open an issue on GitHub.

---

**Made with ❤️ by Write Wise Team**
