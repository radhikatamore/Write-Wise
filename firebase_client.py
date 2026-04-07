import os
import time
import uuid
import json
from urllib.parse import urlencode
from typing import List, Dict, Any, Optional, Tuple, Callable

try:
    import requests
    from requests import exceptions as requests_exceptions
except ImportError:
    requests = None
    requests_exceptions = None

try:
    from firebase import firebase as firebase_lib
except ImportError:
    firebase_lib = None


class FirebaseSnapshot:
    """Lightweight snapshot wrapper matching Pyrebase's interface."""

    def __init__(self, data: Any):
        self._data = data

    def val(self) -> Any:
        return self._data

    def each(self) -> List["FirebaseChildSnapshot"]:
        if isinstance(self._data, dict):
            return [FirebaseChildSnapshot(key, value) for key, value in self._data.items()]
        if isinstance(self._data, list):
            return [FirebaseChildSnapshot(str(index), value) for index, value in enumerate(self._data)]
        return []


class FirebaseChildSnapshot(FirebaseSnapshot):
    def __init__(self, key: str, data: Any):
        super().__init__(data)
        self._key = key

    def key(self) -> str:
        return self._key


class FirebaseApplicationAdapter:
    """Adapter to provide Pyrebase-like interface for firebase.FirebaseApplication."""

    def __init__(self, app: Any, path: Optional[List[str]] = None, error_callback: Optional[Callable[[str], None]] = None):
        self._app = app
        self._path = path or []
        self._error_callback = error_callback

    def child(self, name: str) -> "FirebaseApplicationAdapter":
        return FirebaseApplicationAdapter(self._app, self._path + [name], self._error_callback)

    def set(self, data: Any) -> None:
        parent_path, key = self._parent_path_and_key()
        try:
            self._app.put(parent_path, key, data)
        except Exception as exc:
            if self._handle_http_error(exc, action="set", path=self._full_path()):
                return
            if requests_exceptions and isinstance(exc, requests_exceptions.RequestException):
                self._emit_error(f"Firebase request failed while writing {self._full_path()}: {exc}")
                return
            raise

    def update(self, data: Dict[str, Any]) -> None:
        try:
            self._app.patch(self._full_path(), data)
        except Exception as exc:
            if requests_exceptions and isinstance(exc, requests_exceptions.HTTPError):
                response = getattr(exc, "response", None)
                if response is None or response.status_code == 404:
                    parent_path, key = self._parent_path_and_key()
                    existing = self._safe_get(parent_path, key)
                    if isinstance(existing, dict):
                        merged = dict(existing)
                        merged.update(data)
                    else:
                        merged = data
                    try:
                        self._app.put(parent_path, key, merged)
                        return
                    except Exception as put_exc:
                        if self._handle_http_error(put_exc, action="put", path=self._full_path()):
                            return
                        raise
            if self._handle_http_error(exc, action="patch", path=self._full_path()):
                return
            if requests_exceptions and isinstance(exc, requests_exceptions.RequestException):
                self._emit_error(f"Firebase request failed while updating {self._full_path()}: {exc}")
                return
            raise

    def get(self) -> FirebaseSnapshot:
        if not self._path:
            data = self._safe_get("/", None)
        elif len(self._path) == 1:
            data = self._safe_get(f"/{self._path[0]}", None)
        else:
            parent_path, key = self._parent_path_and_key()
            data = self._safe_get(parent_path, key)
        return FirebaseSnapshot(data)

    def remove(self) -> None:
        parent_path, key = self._parent_path_and_key()
        self._app.delete(parent_path, key)

    def _full_path(self) -> str:
        if not self._path:
            return "/"
        return "/" + "/".join(self._path)

    def _parent_path_and_key(self) -> Tuple[str, str]:
        if not self._path:
            raise ValueError("Cannot resolve parent path for root reference")
        if len(self._path) == 1:
            return "/", self._path[0]
        parent = "/" + "/".join(self._path[:-1])
        return parent, self._path[-1]

    def _safe_get(self, path: str, key: Optional[str]) -> Any:
        try:
            return self._app.get(path, key)
        except Exception as exc:
            if requests_exceptions and isinstance(exc, requests_exceptions.HTTPError):
                response = getattr(exc, "response", None)
                if response is None or response.status_code == 404:
                    return None
            if requests_exceptions and isinstance(exc, requests_exceptions.RequestException):
                self._emit_error(f"Firebase request failed while reading {path}: {exc}")
                return None
            raise

    def _handle_http_error(self, exc: Exception, action: str, path: str) -> bool:
        if not requests_exceptions or not isinstance(exc, requests_exceptions.HTTPError):
            return False
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code in {401, 403, 404}:
            self._emit_error(f"Firebase warning: {action} at {path} returned HTTP {status_code}. Operation skipped.")
            return True
        return False

    def _emit_error(self, message: str) -> None:
        if self._error_callback:
            self._error_callback(message)


class FirebaseClient:
    def __init__(self, db: Optional[Any] = None, auth: Optional[Any] = None, auto_initialize: bool = True):
        # Firebase configuration
        self.api_key = os.environ.get("FIREBASE_API_KEY")
        self.auth_domain = os.environ.get("FIREBASE_AUTH_DOMAIN")
        self.database_url = os.environ.get("FIREBASE_DATABASE_URL")
        self.project_id = os.environ.get("FIREBASE_PROJECT_ID")
        self.storage_bucket = os.environ.get("FIREBASE_STORAGE_BUCKET")
        self.messaging_sender_id = os.environ.get("FIREBASE_MESSAGING_SENDER_ID")
        self.app_id = os.environ.get("FIREBASE_APP_ID")

        # Google OAuth credentials
        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

        self._db = db
        self._auth = auth
        self._initialized = self._db is not None
        self._last_error: Optional[str] = None

        if auto_initialize and not self._initialized:
            self._initialize_firebase()

    # ---------------------------------------------------------
    # Initialization
    # ---------------------------------------------------------

    def _initialize_firebase(self):
        """Initialize Firebase using the firebase (python-firebase) package."""
        if not self.api_key or not self.database_url:
            self._record_error("Firebase configuration is incomplete. Please provide API key and database URL.")
            return

        placeholder_tokens = {"your-project", "your_firebase", "your-firebase", "<"}
        target_strings = [self.api_key or "", self.database_url or "", self.project_id or ""]
        if any(any(token in value for token in placeholder_tokens) for value in target_strings):
            self._record_error("Firebase initialization skipped: placeholder configuration detected.")
            self._initialized = False
            return

        if not firebase_lib:
            self._record_error("Firebase initialization failed: 'firebase' package not installed.")
            self._initialized = False
            return

        try:
            firebase_app = firebase_lib.FirebaseApplication(self.database_url, None)
            self._db = FirebaseApplicationAdapter(firebase_app, error_callback=self._record_error)
            self._initialized = True
            self._record_error(None)
        except Exception as e:
            self._record_error(f"Firebase initialization failed: {e}")
            self._initialized = False

    def is_configured(self) -> bool:
        return self._initialized and self._db is not None

    def set_backend(self, db: Any, auth: Optional[Any] = None) -> None:
        """Override the Firebase backend (useful for tests)."""
        self._db = db
        self._auth = auth
        self._initialized = db is not None

    def supports_google_auth(self) -> bool:
        if not self.api_key or not requests:
            return False
        if self.google_client_id and self.google_client_secret:
            return True
        return True

    # ---------------------------------------------------------
    # Firebase Authentication (via REST API)
    # ---------------------------------------------------------

    def _firebase_auth_request(self, endpoint: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.api_key or not requests:
            return None
        try:
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:{endpoint}?key={self.api_key}"
            response = requests.post(url, json=payload, timeout=10)
            return response.json() if response.status_code == 200 else {"error": response.json()}
        except requests_exceptions.Timeout:
            return {"error": "Request timed out while contacting Firebase."}
        except Exception as e:
            return {"error": str(e)}

    def _refresh_id_token(self, refresh_token: str) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.api_key or not requests:
            return None, "Firebase not configured."
        if not refresh_token:
            return None, "Missing refresh token."

        try:
            response = requests.post(
                f"https://securetoken.googleapis.com/v1/token?key={self.api_key}",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                timeout=10,
            )
            data = response.json()
            if response.status_code != 200:
                error_detail = data.get("error", {}) if isinstance(data, dict) else {}
                if isinstance(error_detail, dict):
                    message = error_detail.get("message") or json.dumps(error_detail)
                else:
                    message = str(error_detail) if error_detail else "Failed to refresh session."
                return None, message
            return data, "Token refreshed."
        except requests_exceptions.Timeout:
            return None, "Request timed out while refreshing session."
        except Exception as exc:
            return None, str(exc)

    def create_persistent_session(self, user_id: str, refresh_token: str, metadata: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], str]:
        if not self.is_configured():
            return None, "Firebase not configured."
        if not refresh_token:
            return None, "Missing refresh token."

        session_token = uuid.uuid4().hex
        session_payload: Dict[str, Any] = {
            "user_id": user_id,
            "refresh_token": refresh_token,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        if metadata:
            session_payload["metadata"] = metadata

        try:
            self._db.child("auth_sessions").child(session_token).set(session_payload)
            self._record_error(None)
            return session_token, "Persistent session created."
        except Exception as exc:
            self._record_error(f"Failed to create persistent session: {exc}")
            return None, "Unable to create persistent session."

    def resume_session(self, session_token: str) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.is_configured():
            return None, "Firebase not configured."
        if not session_token:
            return None, "Missing session token."

        record = self._db.child("auth_sessions").child(session_token).get().val()
        if not record:
            return None, "Session not found."
        if not isinstance(record, dict):
            return None, "Session data is corrupted."

        refresh_token = record.get("refresh_token")
        if not refresh_token:
            return None, "Session missing refresh token."
        refresh_result, message = self._refresh_id_token(refresh_token)
        if not refresh_result:
            return None, message or "Failed to refresh session."

        user_id = refresh_result.get("user_id") or record.get("user_id")
        if not user_id:
            return None, "Session missing user information."

        user_data = self._db.child("users").child(user_id).get().val() or {}
        id_token = refresh_result.get("id_token")
        if not id_token:
            return None, "Failed to refresh authentication token."
        new_refresh_token = refresh_result.get("refresh_token") or refresh_token
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        email = user_data.get("email") or metadata.get("email")
        if email:
            user_data["email"] = email

        user_data.update({
            "uid": user_id,
            "id_token": id_token,
            "refresh_token": new_refresh_token,
            "last_login": int(time.time()),
        })

        try:
            update_payload = {
                "refresh_token": new_refresh_token,
                "updated_at": int(time.time()),
                "expires_in": refresh_result.get("expires_in"),
            }
            self._db.child("auth_sessions").child(session_token).update(update_payload)
            self._db.child("users").child(user_id).update({"last_login": int(time.time())})
            self._record_error(None)
        except Exception as exc:
            self._record_error(f"Failed to update session metadata: {exc}")

        return user_data, "Session restored."

    def delete_persistent_session(self, session_token: Optional[str]) -> bool:
        if not self.is_configured() or not session_token:
            return False
        try:
            self._db.child("auth_sessions").child(session_token).remove()
            self._record_error(None)
            return True
        except Exception as exc:
            self._record_error(f"Failed to delete session token: {exc}")
            return False

    def register_user(self, email: str, password: str) -> Tuple[bool, str]:
        if not self.is_configured():
            return False, "Firebase not configured."
        if not email or not password:
            return False, "Email and password required."
        result = self._firebase_auth_request("signUp", {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        })

        if not result or "error" in result:
            error_detail = result.get("error") if isinstance(result, dict) else "Unknown"
            if isinstance(error_detail, dict):
                message = error_detail.get("message") or error_detail.get("errors") or "Registration failed."
            else:
                message = error_detail
            return False, f"Registration failed: {message}"

        user_id = result.get("localId")
        self._db.child("users").child(user_id).set({
            "email": email.lower(),
            "created_at": int(time.time()),
            "last_login": None,
            "auth_provider": "email",
        })
        return True, "Account created successfully."

    def authenticate_user(self, email: str, password: str) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.is_configured():
            return None, "Firebase not configured."

        result = self._firebase_auth_request("signInWithPassword", {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        })

        if not result or "error" in result:
            error_detail = result.get("error") if isinstance(result, dict) else None
            if isinstance(error_detail, dict):
                message = error_detail.get("message") or error_detail.get("errors") or "Invalid credentials."
            else:
                message = error_detail or "Invalid credentials."
            return None, message

        user_id = result.get("localId")
        id_token = result.get("idToken")
        refresh_token = result.get("refreshToken")
        user_data = self._db.child("users").child(user_id).get().val() or {}
        
        # Ensure email is always present
        if "email" not in user_data:
            user_data["email"] = email.lower()
        
        user_data.update({"uid": user_id, "id_token": id_token, "last_login": int(time.time())})
        if refresh_token:
            user_data["refresh_token"] = refresh_token
        self._db.child("users").child(user_id).update({"last_login": int(time.time()), "email": user_data["email"]})
        return user_data, "Authenticated successfully."

    def authenticate_with_google(self, token_payload: Any) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self.is_configured():
            return None, "Firebase not configured."

        if isinstance(token_payload, dict):
            if "localId" in token_payload:
                return self._process_google_sign_in_result(token_payload)
            id_token_candidate = token_payload.get("id_token") or token_payload.get("idToken")
            if id_token_candidate:
                token_payload = id_token_candidate
            else:
                return None, "Google authentication payload missing ID token."

        id_token = token_payload
        payload = {
            "postBody": f"id_token={id_token}&providerId=google.com",
            "requestUri": "http://localhost",
            "returnIdpCredential": True,
            "returnSecureToken": True,
        }

        result = self._firebase_auth_request("signInWithIdp", payload)
        if not result or "error" in result:
            return None, "Google authentication failed."

        return self._process_google_sign_in_result(result)

    def _process_google_sign_in_result(self, result: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], str]:
        try:
            user_id = result.get("localId")
            if not user_id:
                return None, "Missing Firebase user ID."

            email = (result.get("email") or "").lower()
            id_token = result.get("idToken")
            refresh_token = result.get("refreshToken")

            user_data = {
                "email": email,
                "uid": user_id,
                "auth_provider": "google",
                "last_login": int(time.time()),
            }
            if id_token:
                user_data["id_token"] = id_token
            if refresh_token:
                user_data["refresh_token"] = refresh_token

            self._db.child("users").child(user_id).update(user_data)
            return user_data, "Authenticated with Google."
        except Exception as exc:
            self._record_error(f"Error processing Google sign-in result: {exc}")
            return None, "Google authentication failed."

    # ---------------------------------------------------------
    # Google OAuth Helpers
    # ---------------------------------------------------------

    def get_google_auth_url(self, redirect_uri: str, state: Optional[str] = None) -> Tuple[str, Optional[str], Optional[str]]:
        if not self.supports_google_auth():
            return "", None, "Firebase is not fully configured for Google Sign-In."

        if self.google_client_id and self.google_client_secret:
            params = {
                "client_id": self.google_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "access_type": "online",
            }
            if state:
                params["state"] = state
            query = "&".join([f"{k}={v}" for k, v in params.items()])
            return f"https://accounts.google.com/o/oauth2/v2/auth?{query}", None, None

        if not requests:
            return "", None, "The 'requests' package is required for Google Sign-In."

        try:
            payload: Dict[str, Any] = {
                "providerId": "google.com",
                "continueUri": redirect_uri,
            }
            if state:
                payload["state"] = state

            response = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:createAuthUri?key={self.api_key}",
                json=payload,
                timeout=10,
            )
            if response.status_code != 200:
                error_message = ""
                try:
                    data = response.json()
                    error_info = data.get("error", {})
                    if isinstance(error_info, dict):
                        error_message = error_info.get("message") or json.dumps(error_info)
                    else:
                        error_message = str(error_info)
                except Exception:
                    error_message = response.text
                return "", None, error_message or "Failed to initialize Google Sign-In."
            data = response.json()
            return data.get("authUri", ""), data.get("sessionId"), None
        except Exception as exc:
            self._record_error(f"Failed to create Google auth URI: {exc}")
            return "", None, str(exc)

    def exchange_code_for_token(self, code: str, redirect_uri: str, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.supports_google_auth() or not requests:
            return None

        if self.google_client_id and self.google_client_secret:
            try:
                response = requests.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": self.google_client_id,
                        "client_secret": self.google_client_secret,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                    timeout=10,
                )
                if response.status_code != 200:
                    return None
                return response.json()
            except Exception as exc:
                self._record_error(f"Failed to exchange code via Google OAuth: {exc}")
                return None

        try:
            post_body = urlencode({
                "code": code,
                "providerId": "google.com",
            })
            payload: Dict[str, Any] = {
                "postBody": post_body,
                "requestUri": redirect_uri,
                "returnSecureToken": True,
                "returnIdpCredential": True,
            }
            if session_id:
                payload["sessionId"] = session_id

            response = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithIdp?key={self.api_key}",
                json=payload,
                timeout=10,
            )
            if response.status_code != 200:
                self._record_error(f"signInWithIdp failed: {response.text}")
                return None
            return response.json()
        except Exception as exc:
            self._record_error(f"Failed to exchange code via Identity Toolkit: {exc}")
            return None

    # ---------------------------------------------------------
    # Message Storage
    # ---------------------------------------------------------

    def save_message(self, session_id: str, role: str, content: str,
                     metadata: Optional[Dict[str, Any]] = None,
                     user_id: Optional[str] = None,
                     do_not_store: bool = False) -> Optional[Dict[str, Any]]:
        if not self.is_configured() or do_not_store:
            return None
        msg_id = str(uuid.uuid4())
        timestamp = int(time.time())
        message = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "timestamp": timestamp,
            "user_id": user_id or "anonymous",
        }
        self._db.child("messages").child(msg_id).set(message)
        
        # Update session metadata
        self._update_session_metadata(session_id, user_id, metadata, timestamp)
        
        return message

    def get_messages(self, session_id: str, limit: int = 200, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_configured():
            return []
        try:
            all_msgs = self._db.child("messages").get()
            if not all_msgs.each():
                return []
            
            # Filter messages by session_id and optionally by user_id
            msgs = []
            for m in all_msgs.each():
                msg_val = m.val()
                if msg_val.get("session_id") == session_id:
                    if user_id is None or msg_val.get("user_id") == user_id:
                        msgs.append(msg_val)
            
            msgs.sort(key=lambda x: x.get("timestamp", 0))
            self._record_error(None)
            return msgs[:limit]
        except Exception as e:
            self._record_error(f"Error getting messages: {e}")
            return []

    def _update_session_metadata(self, session_id: str, user_id: Optional[str], 
                                  metadata: Optional[Dict[str, Any]], timestamp: int) -> None:
        """Update or create session metadata for tracking sessions."""
        if not user_id or user_id == "anonymous":
            return
        
        try:
            session_path = self._db.child("sessions").child(user_id).child(session_id)
            existing = session_path.get()
            
            if existing.val():
                # Update existing session - only update specific fields to avoid race conditions
                update_data = {
                    "updated_at": timestamp,
                }
                # Only update title if metadata has a new title
                if metadata and "title" in metadata:
                    update_data["title"] = metadata["title"]
                
                # Get current message count and increment it
                current_count = existing.val().get("message_count", 0)
                update_data["message_count"] = current_count + 1
                
                session_path.update(update_data)
            else:
                # Create new session
                session_data = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "title": metadata.get("title", "Untitled") if metadata else "Untitled",
                    "message_count": 1
                }
                session_path.set(session_data)
        except Exception as e:
            self._record_error(f"Error updating session metadata: {e}")

    # ---------------------------------------------------------
    # Session Management
    # ---------------------------------------------------------

    def list_sessions(self, user_id: str, search_term: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all sessions for a user, optionally filtered by search term."""
        if not self.is_configured():
            return []
        if not user_id or user_id == "anonymous":
            return []
        
        try:
            sessions_data = self._db.child("sessions").child(user_id).get()
            if not sessions_data.each():
                return []
            
            sessions = []
            for session in sessions_data.each():
                session_val = session.val()
                if session_val:
                    # Filter by search term if provided
                    if search_term:
                        title = session_val.get("title", "").lower()
                        if search_term.lower() not in title:
                            continue
                    sessions.append(session_val)
            
            # Sort by updated_at (most recent first)
            sessions.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            self._record_error(None)
            return sessions
        except Exception as e:
            self._record_error(f"Error listing sessions: {e}")
            return []

    def export_history(self, user_id: str) -> str:
        """Export complete chat history for a user as JSON."""
        if not self.is_configured():
            return json.dumps({"error": "Firebase not configured"}, indent=2)
        if not user_id or user_id == "anonymous":
            return json.dumps({"error": "Invalid user ID"}, indent=2)
        
        try:
            # Get all sessions for the user
            sessions = self.list_sessions(user_id)
            
            export_data = {
                "user_id": user_id,
                "export_timestamp": int(time.time()),
                "total_sessions": len(sessions),
                "sessions": []
            }
            
            # Get messages for each session
            for session in sessions:
                session_id = session.get("session_id")
                messages = self.get_messages(session_id, user_id=user_id)
                
                export_data["sessions"].append({
                    "session_id": session_id,
                    "title": session.get("title", "Untitled"),
                    "created_at": session.get("created_at", 0),
                    "updated_at": session.get("updated_at", 0),
                    "message_count": len(messages),
                    "messages": messages
                })
            
            return json.dumps(export_data, indent=2)
        except Exception as e:
            self._record_error(f"Error exporting history: {e}")
            return json.dumps({"error": str(e)}, indent=2)

    def delete_session(self, session_id: str, user_id: str) -> bool:
        """Delete a session and all its messages."""
        if not self.is_configured():
            return False
        if not user_id or user_id == "anonymous":
            return False
        
        try:
            # Delete session metadata
            self._db.child("sessions").child(user_id).child(session_id).remove()
            
            # Delete all messages in the session
            all_msgs = self._db.child("messages").get()
            if all_msgs.each():
                for m in all_msgs.each():
                    msg_val = m.val()
                    if msg_val.get("session_id") == session_id and msg_val.get("user_id") == user_id:
                        self._db.child("messages").child(m.key()).remove()
            
            self._record_error(None)
            return True
        except Exception as e:
            self._record_error(f"Error deleting session: {e}")
            return False

    # ---------------------------------------------------------
    # Template Management
    # ---------------------------------------------------------

    def save_template(self, user_id: str, template_name: str, 
                     sections: List[str], description: str = "",
                     is_public: bool = False) -> Tuple[bool, str]:
        """Save a custom template for a user."""
        if not self.is_configured():
            return False, "Firebase not configured"
        if not user_id or user_id == "anonymous":
            return False, "Please login to save templates"
        if not template_name or not sections:
            return False, "Template name and sections are required"
        
        try:
            template_id = str(uuid.uuid4())
            template_data = {
                "template_id": template_id,
                "template_name": template_name,
                "sections": sections,
                "description": description,
                "user_id": user_id,
                "is_public": is_public,
                "created_at": int(time.time()),
                "updated_at": int(time.time()),
            }
            
            self._db.child("templates").child(user_id).child(template_id).set(template_data)
            
            # If public, also add to public templates
            if is_public:
                self._db.child("public_templates").child(template_id).set(template_data)
            
            self._record_error(None)
            return True, f"Template '{template_name}' saved successfully"
        except Exception as e:
            self._record_error(f"Error saving template: {e}")
            return False, f"Failed to save template: {str(e)}"

    def list_templates(self, user_id: str, include_public: bool = True) -> List[Dict[str, Any]]:
        """List all templates for a user, optionally including public templates."""
        if not self.is_configured():
            return []
        
        templates = []
        
        try:
            # Get user's private templates
            if user_id and user_id != "anonymous":
                user_templates = self._db.child("templates").child(user_id).get()
                if user_templates.each():
                    for template in user_templates.each():
                        template_val = template.val()
                        if template_val:
                            templates.append(template_val)
            
            # Get public templates
            if include_public:
                public_templates = self._db.child("public_templates").get()
                if public_templates.each():
                    for template in public_templates.each():
                        template_val = template.val()
                        # Don't include user's own public templates twice
                        if template_val and template_val.get("user_id") != user_id:
                            template_val["is_public_shared"] = True
                            templates.append(template_val)
            
            # Sort by updated_at (most recent first)
            templates.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
            self._record_error(None)
            return templates
        except Exception as e:
            self._record_error(f"Error listing templates: {e}")
            return []

    def get_template(self, template_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a specific template by ID."""
        if not self.is_configured():
            return None
        
        try:
            # Try user's templates first
            if user_id and user_id != "anonymous":
                template = self._db.child("templates").child(user_id).child(template_id).get()
                if template.val():
                    return template.val()
            
            # Try public templates
            public_template = self._db.child("public_templates").child(template_id).get()
            if public_template.val():
                return public_template.val()
            
            return None
        except Exception as e:
            self._record_error(f"Error getting template: {e}")
            return None

    def delete_template(self, template_id: str, user_id: str) -> bool:
        """Delete a user's template."""
        if not self.is_configured():
            return False
        if not user_id or user_id == "anonymous":
            return False
        
        try:
            # Get the template to check if it's public
            template = self._db.child("templates").child(user_id).child(template_id).get()
            if template.val() and template.val().get("is_public"):
                # Also delete from public templates
                self._db.child("public_templates").child(template_id).remove()
            
            # Delete from user's templates
            self._db.child("templates").child(user_id).child(template_id).remove()
            return True
        except Exception as e:
            self._record_error(f"Error deleting template: {e}")
            return False

    def update_template(self, template_id: str, user_id: str, 
                       template_name: Optional[str] = None,
                       sections: Optional[List[str]] = None,
                       description: Optional[str] = None,
                       is_public: Optional[bool] = None) -> Tuple[bool, str]:
        """Update an existing template."""
        if not self.is_configured():
            return False, "Firebase not configured"
        if not user_id or user_id == "anonymous":
            return False, "Invalid user ID"
        
        try:
            template_path = self._db.child("templates").child(user_id).child(template_id)
            existing = template_path.get()
            
            if not existing.val():
                return False, "Template not found"
            
            template_data = existing.val()
            template_data["updated_at"] = int(time.time())
            
            if template_name is not None:
                template_data["template_name"] = template_name
            if sections is not None:
                template_data["sections"] = sections
            if description is not None:
                template_data["description"] = description
            if is_public is not None:
                template_data["is_public"] = is_public
                
                # Update public templates accordingly
                if is_public:
                    self._db.child("public_templates").child(template_id).set(template_data)
                else:
                    self._db.child("public_templates").child(template_id).remove()
            
            template_path.set(template_data)
            self._record_error(None)
            return True, "Template updated successfully"
        except Exception as e:
            self._record_error(f"Error updating template: {e}")
            return False, f"Failed to update template: {str(e)}"

    def _record_error(self, message: Optional[str]) -> None:
        self._last_error = message

    def pop_last_error(self) -> Optional[str]:
        err = self._last_error
        self._last_error = None
        return err


# ---------------------------------------------------------
# Global instance and helper wrappers
# ---------------------------------------------------------

client = FirebaseClient()

# Authentication wrappers
def register_user(*args, **kwargs): return client.register_user(*args, **kwargs)
def authenticate_user(*args, **kwargs): return client.authenticate_user(*args, **kwargs)
def authenticate_with_google(*args, **kwargs): return client.authenticate_with_google(*args, **kwargs)
def supports_google_auth(): return client.supports_google_auth()
def get_google_auth_url(*args, **kwargs): return client.get_google_auth_url(*args, **kwargs)
def exchange_code_for_token(*args, **kwargs): return client.exchange_code_for_token(*args, **kwargs)
def create_persistent_session(*args, **kwargs): return client.create_persistent_session(*args, **kwargs)
def resume_session(*args, **kwargs): return client.resume_session(*args, **kwargs)
def delete_persistent_session(*args, **kwargs): return client.delete_persistent_session(*args, **kwargs)

# Message and session wrappers
def save_message(*args, **kwargs): return client.save_message(*args, **kwargs)
def get_messages(*args, **kwargs): return client.get_messages(*args, **kwargs)
def list_sessions(*args, **kwargs): return client.list_sessions(*args, **kwargs)
def export_history(*args, **kwargs): return client.export_history(*args, **kwargs)
def delete_session(*args, **kwargs): return client.delete_session(*args, **kwargs)

# Template management wrappers
def save_template(*args, **kwargs): return client.save_template(*args, **kwargs)
def list_templates(*args, **kwargs): return client.list_templates(*args, **kwargs)
def get_template(*args, **kwargs): return client.get_template(*args, **kwargs)
def delete_template(*args, **kwargs): return client.delete_template(*args, **kwargs)
def update_template(*args, **kwargs): return client.update_template(*args, **kwargs)

# Configuration check
def is_configured(): return client.is_configured()
def pop_last_error(): return client.pop_last_error()
