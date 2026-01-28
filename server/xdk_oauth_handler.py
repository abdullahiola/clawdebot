"""
XDK-based OAuth 2.0 with PKCE authentication handler for X API.
Uses manual token exchange with proper Basic Auth (Client ID:Client Secret).
"""

import os
import json
import time
import webbrowser
import multiprocessing
import base64
import hashlib
import re
import requests
from pathlib import Path
from typing import Optional, Dict
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv
import logging
from threading import Timer

from xdk import Client
from flask import Flask, request, redirect
from werkzeug.serving import run_simple

logger = logging.getLogger(__name__)

# Token storage file
TOKEN_FILE = Path(__file__).parent / "oauth_tokens.json"
FLASK_PORT = 8080
TOKEN_URL = "https://api.x.com/2/oauth2/token"


def run_callback_server(
    q: multiprocessing.Queue,
    auth_url: str,
    port: int,
) -> None:
    """Run a minimal Flask server to capture OAuth callback URL."""
    app = Flask(__name__)
    
    @app.route("/")
    def auth_start():
        """Redirect to the authorization URL."""
        return redirect(auth_url)
    
    @app.route("/oauth/callback")
    def auth_callback():
        """Capture the authorization code and send it to the main process."""
        code = request.args.get("code")
        if not code:
            return "❌ Error: No authorization code received", 400
        
        # Send the code to main process
        q.put(code)
        
        # Schedule server shutdown
        Timer(1.0, lambda: os._exit(0)).start()
        
        return "✅ Authorization received! Processing tokens...", 200
    
    # Run the Flask server
    run_simple("localhost", port, app, use_reloader=False, use_debugger=False)


class XDKOAuth2Handler:
    """Handles OAuth 2.0 authentication with manual token exchange using proper Basic Auth."""

    def __init__(self):
        """Initialize OAuth 2.0 handler with credentials from environment."""
        load_dotenv()
        
        self.client_id = os.getenv("X_CLIENT_ID")
        self.client_secret = os.getenv("X_CLIENT_SECRET")
        
        if not self.client_id or not self.client_secret:
            raise ValueError("X_CLIENT_ID and X_CLIENT_SECRET must be set in .env file")
        
        self.redirect_uri = f"http://localhost:{FLASK_PORT}/oauth/callback"
        self.scopes = ["tweet.read", "users.read", "tweet.write", "offline.access"]
        
        # Store PKCE code verifier for token exchange
        self.code_verifier = None

    def _generate_pkce(self) -> tuple:
        """Generate PKCE code verifier and challenge."""
        # Generate code verifier (43-128 characters)
        code_verifier = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
        code_verifier = re.sub(r"[^a-zA-Z0-9\-._~]+", "", code_verifier)
        
        # Generate code challenge (SHA256 hash of verifier)
        challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
        code_challenge = base64.urlsafe_b64encode(challenge).decode("utf-8").rstrip("=")
        
        return code_verifier, code_challenge

    def _get_basic_auth_header(self) -> str:
        """Generate Basic Auth header using Client ID and Client Secret."""
        # Encode as: Base64(client_id:client_secret)
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
        return f"Basic {encoded}"

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

    def _exchange_code_for_tokens(self, code: str) -> Dict:
        """Exchange authorization code for tokens using proper Basic Auth."""
        logger.info("🔄 Exchanging authorization code for tokens...")
        
        # Build request with Basic Auth header (Client ID:Client Secret)
        headers = {
            "Authorization": self._get_basic_auth_header(),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": self.code_verifier,
        }
        
        response = requests.post(TOKEN_URL, headers=headers, data=data)
        
        if response.status_code != 200:
            error_body = response.text
            try:
                error_body = response.json()
            except:
                pass
            raise Exception(f"Token exchange failed: {response.status_code} - {error_body}")
        
        tokens = response.json()
        
        # Add expires_at timestamp
        if "expires_in" in tokens:
            tokens["expires_at"] = time.time() + tokens["expires_in"]
        
        return tokens

    def _start_auth_flow(self) -> Dict:
        """Start the OAuth authorization flow with Flask callback server."""
        logger.info("🔐 No token found. Starting OAuth 2.0 authorization flow...")
        logger.info(f"📱 Visit http://localhost:{FLASK_PORT} to authorize the app")
        
        # Generate PKCE values
        self.code_verifier, code_challenge = self._generate_pkce()
        
        # Build authorization URL manually
        auth_url = (
            f"https://twitter.com/i/oauth2/authorize"
            f"?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&scope={'+'.join(self.scopes)}"
            f"&state=state"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )
        
        # Create a queue to receive auth code from the subprocess
        q = multiprocessing.Queue()
        
        # Start the Flask server in a separate process
        p = multiprocessing.Process(
            target=run_callback_server,
            args=(q, auth_url, FLASK_PORT),
        )
        p.start()
        
        # Open browser automatically after server starts
        time.sleep(1)
        webbrowser.open(f"http://localhost:{FLASK_PORT}")
        
        # Wait for authorization code from subprocess
        logger.info("⏳ Waiting for authorization...")
        code = q.get(block=True)
        
        # Give browser time to receive success message
        time.sleep(2)
        p.terminate()
        
        # Exchange code for tokens with proper Basic Auth
        tokens = self._exchange_code_for_tokens(code)
        
        self._save_token(tokens)
        logger.info("✅ OAuth 2.0 authorization complete!")
        
        return tokens

    def _refresh_token(self) -> Optional[Dict]:
        """Refresh the access token using the refresh token."""
        token = self._load_token()
        
        if not token or "refresh_token" not in token:
            logger.warning("No refresh token found. Re-authentication required.")
            return None

        logger.info("🔄 Refreshing access token...")
        
        try:
            # Build request with Basic Auth header
            headers = {
                "Authorization": self._get_basic_auth_header(),
                "Content-Type": "application/x-www-form-urlencoded",
            }
            
            data = {
                "grant_type": "refresh_token",
                "refresh_token": token["refresh_token"],
            }
            
            response = requests.post(TOKEN_URL, headers=headers, data=data)
            
            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return None
            
            new_tokens = response.json()
            
            # Add expires_at timestamp
            if "expires_in" in new_tokens:
                new_tokens["expires_at"] = time.time() + new_tokens["expires_in"]
            
            self._save_token(new_tokens)
            logger.info("✅ Token refreshed successfully")
            
            return new_tokens
            
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            return None

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

    def get_client(self) -> Client:
        """
        Get an authenticated XDK Client instance.
        
        Returns:
            Client: Authenticated XDK client ready to use
        """
        access_token = self.get_access_token()
        
        # Create XDK client with access_token for OAuth2 user context authentication
        # Note: access_token is for OAuth2UserToken, bearer_token is for app-only auth
        return Client(access_token=access_token)

    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        token = self._load_token()
        return token is not None and time.time() < token.get("expires_at", 0)
