"""
OAuth 2.0 with PKCE authentication handler for X API.
Handles user authorization, token storage, and automatic token refresh.
"""

import os
import json
import time
import hashlib
import base64
import re
import webbrowser
import multiprocessing
import requests
from pathlib import Path
from typing import Optional, Dict
from flask import Flask, request, session, redirect
from requests.auth import HTTPBasicAuth
from requests_oauthlib import OAuth2Session
from werkzeug.serving import run_simple
from threading import Timer
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# OAuth 2.0 Configuration
FLASK_PORT = 8080
X_REDIRECT_URI = f"http://localhost:{FLASK_PORT}/oauth/callback"
X_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
X_TOKEN_URL = "https://api.x.com/2/oauth2/token"
X_SCOPES = ["tweet.read", "users.read", "tweet.write", "offline.access"]

# Token storage file
TOKEN_FILE = Path(__file__).parent / "oauth_tokens.json"


def run_token_server(
    q: multiprocessing.Queue,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    auth_url: str,
    token_url: str,
    scopes: list,
    port: int,
) -> None:
    """Run a minimal Flask server to capture OAuth callback and token."""
    app = Flask(__name__)
    # Use a fixed secret key for session persistence
    app.secret_key = b'oauth2_pkce_session_key_'
    # Store PKCE values globally within this process
    pkce_storage = {}

    def _generate_pkce():
        """Generate PKCE code verifier and challenge."""
        code_verifier = base64.urlsafe_b64encode(os.urandom(30)).decode("utf-8")
        code_verifier = re.sub(r"[^a-zA-Z0-9]+", "", code_verifier)
        challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = (
            base64.urlsafe_b64encode(challenge).decode("utf-8").replace("=", "")
        )
        return code_verifier, code_challenge

    @app.route("/")
    def auth_start():
        """Start the OAuth authorization flow."""
        oauth = OAuth2Session(client_id, redirect_uri=redirect_uri, scope=scopes)
        code_verifier, code_challenge = _generate_pkce()
        authorization_url, state = oauth.authorization_url(
            auth_url, code_challenge=code_challenge, code_challenge_method="S256"
        )
        # Store PKCE values globally (not in session)
        pkce_storage["oauth_state"] = state
        pkce_storage["code_verifier"] = code_verifier
        return redirect(authorization_url)

    @app.route("/oauth/callback")
    def auth_callback():
        """Handle OAuth callback and exchange code for tokens."""
        code = request.args.get("code")
        if not code:
            return "Error: No code provided", 400

        # Retrieve code verifier from global storage
        code_verifier = pkce_storage.get("code_verifier")
        if not code_verifier:
            return "Error: No code verifier found. Please restart the authorization flow.", 400

        try:
            # Make direct POST request with Basic Auth header
            
            token_data = {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
            }
            
            response = requests.post(
                token_url,
                data=token_data,
                auth=HTTPBasicAuth(client_id, client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            
            if response.status_code != 200:
                return f"❌ Error during token exchange: HTTP error! status: {response.status_code}, body: {response.json()}", 400
            
            token = response.json()
            token["expires_at"] = time.time() + token["expires_in"]

            # Send token to main process
            q.put(token)

            # Schedule server shutdown after response is sent
            Timer(1.0, lambda: os._exit(0)).start()
            
            return "✅ Authentication successful! You can now close this window.", 200
        except Exception as e:
            return f"❌ Error during token exchange: {str(e)}", 400

    # Run the Flask server
    run_simple("localhost", port, app, use_reloader=False, use_debugger=False)


class OAuth2Handler:
    """Handles OAuth 2.0 authentication with PKCE for X API."""

    def __init__(self):
        """Initialize OAuth 2.0 handler with credentials from environment."""
        load_dotenv()
        
        self.client_id = os.getenv("X_CLIENT_ID")
        self.client_secret = os.getenv("X_CLIENT_SECRET")
        
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "X_CLIENT_ID and X_CLIENT_SECRET must be set in .env file"
            )
        
        self.redirect_uri = X_REDIRECT_URI
        self.auth_url = X_AUTH_URL
        self.token_url = X_TOKEN_URL
        self.scopes = X_SCOPES

    def _load_token(self) -> Optional[Dict]:
        """Load token from storage file."""
        if TOKEN_FILE.exists():
            try:
                with open(TOKEN_FILE, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.warning("Corrupted token file, deleting...")
                TOKEN_FILE.unlink()
        return None

    def _save_token(self, token: Dict) -> None:
        """Save token to storage file."""
        with open(TOKEN_FILE, "w") as f:
            json.dump(token, f, indent=2)
        logger.info("✅ Token saved to storage")

    def _refresh_token(self) -> Optional[Dict]:
        """Refresh the access token using the refresh token."""
        token = self._load_token()
        
        if not token or "refresh_token" not in token:
            logger.warning("No refresh token found. Re-authentication required.")
            return None

        logger.info("🔄 Refreshing access token...")
        
        try:
            token_data = {
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
            }
            
            response = requests.post(
                self.token_url,
                data=token_data,
                auth=HTTPBasicAuth(self.client_id, self.client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return None
            
            new_token = response.json()
            new_token["expires_at"] = time.time() + new_token["expires_in"]
            self._save_token(new_token)
            
            logger.info("✅ Token refreshed successfully")
            return new_token
            
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return None

    def _start_auth_flow(self) -> Dict:
        """Start the OAuth authorization flow in a separate process."""
        logger.info("🔐 No token found. Starting OAuth 2.0 authorization flow...")
        logger.info(f"📱 Visit http://localhost:{FLASK_PORT} to authorize the app")
        
        # Create a queue to receive the token from the subprocess
        q = multiprocessing.Queue()
        
        # Start the Flask server in a separate process
        p = multiprocessing.Process(
            target=run_token_server,
            args=(
                q,
                self.client_id,
                self.client_secret,
                self.redirect_uri,
                self.auth_url,
                self.token_url,
                self.scopes,
                FLASK_PORT,
            ),
        )
        p.start()
        
        # Open browser automatically
        time.sleep(1)  # Give server time to start
        webbrowser.open(f"http://localhost:{FLASK_PORT}")
        
        # Wait for token from callback
        logger.info("⏳ Waiting for authorization...")
        token = q.get(block=True)
        
        # Give the browser time to receive the success message
        time.sleep(2)
        p.terminate()
        
        self._save_token(token)
        logger.info("✅ OAuth 2.0 authorization complete!")
        
        return token

    def get_access_token(self) -> str:
        """
        Get a valid access token.
        Handles first-time auth, token refresh, and token validation.
        
        Returns:
            str: Valid OAuth 2.0 access token
        """
        token = self._load_token()
        
        # No token - start auth flow
        if not token:
            token = self._start_auth_flow()
            return token["access_token"]
        
        # Token expired - refresh it
        if time.time() >= token.get("expires_at", 0):
            logger.info("Token expired, refreshing...")
            token = self._refresh_token()
            
            # Refresh failed - start new auth flow
            if not token:
                token = self._start_auth_flow()
        
        return token["access_token"]

    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        token = self._load_token()
        return token is not None and time.time() < token.get("expires_at", 0)
