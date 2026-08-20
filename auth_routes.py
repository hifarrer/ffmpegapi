from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, ApiKey, SubscriptionPlan, UserSubscription
from forms import RegistrationForm, LoginForm, ApiKeyForm
from datetime import datetime, timedelta
from urllib.parse import urlencode
from sqlalchemy import func
import logging
import resend
import requests
import os
import re
import secrets

auth = Blueprint('auth', __name__)

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_OAUTH_SCOPES = "openid email profile"
SESSION_GOOGLE_OAUTH_STATE = "google_oauth_state"
SESSION_POST_OAUTH_REDIRECT = "post_oauth_redirect"

RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


def _verify_recaptcha_response(token: str) -> bool:
    """POST to Google siteverify. Caller must only invoke when RECAPTCHA_SECRET_KEY is set."""
    secret = (os.environ.get("RECAPTCHA_SECRET_KEY") or "").strip()
    if not secret:
        return True
    if not (token or "").strip():
        return False
    try:
        resp = requests.post(
            RECAPTCHA_VERIFY_URL,
            data={
                "secret": secret,
                "response": token.strip(),
                "remoteip": (request.remote_addr or ""),
            },
            timeout=10,
        )
        return bool(resp.json().get("success"))
    except (requests.RequestException, ValueError) as e:
        logging.error("reCAPTCHA verification request failed: %s", e, exc_info=True)
        return False


def _google_oauth_credentials():
    client_id = (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()
    client_secret = (os.environ.get("GOOGLE_CLIENT_SECRET") or "").strip()
    return client_id, client_secret


def _google_oauth_redirect_uri():
    """
    Build redirect_uri from the incoming request (scheme + host).

    Using url_for(..., _external=True) alone follows SERVER_NAME (e.g. www),
    while the Flask session cookie is scoped to the host the user actually
    used (e.g. apex). Google then sends them to www without the session cookie,
    and OAuth state validation fails. This keeps authorize, callback, and
    token exchange aligned with the cookie host.
    """
    root = f"{request.scheme}://{request.host}".rstrip("/")
    path = url_for("auth.google_callback", _external=False)
    return root + path


def _unique_username_from_email(email: str) -> str:
    """Pick a username (4–80 chars) from email local-part; ensure uniqueness."""
    local = email.split("@", 1)[0] if "@" in email else email
    base = re.sub(r"[^a-zA-Z0-9_]", "_", local).strip("_") or "user"
    if len(base) < 4:
        base = (base + "_user")[:80]
    if len(base) < 4:
        base = "user_" + secrets.token_hex(4)
    base = base[:80]
    for n in range(5000):
        suffix = "" if n == 0 else "_" + str(n + 1)
        candidate = (base[: max(1, 80 - len(suffix))] + suffix)[:80]
        if not User.query.filter_by(username=candidate).first():
            return candidate
    while True:
        candidate = ("g_" + secrets.token_hex(16))[:80]
        if not User.query.filter_by(username=candidate).first():
            return candidate


def _provision_free_plan_and_api_key(user):
    """Mirror post-registration defaults from register() for new OAuth users."""
    if not ApiKey.query.filter_by(user_id=user.id, is_active=True).first():
        user.generate_api_key("My First API Key")
    existing_sub = UserSubscription.query.filter(
        UserSubscription.user_id == user.id,
        UserSubscription.status.in_(("active", "trialing", "admin_granted")),
    ).first()
    if existing_sub:
        return
    free_plan = SubscriptionPlan.query.filter_by(name="Free", is_active=True).first()
    if free_plan:
        subscription = UserSubscription()
        subscription.user_id = user.id
        subscription.plan_id = free_plan.id
        subscription.status = "active"
        subscription.billing_cycle = "monthly"
        subscription.current_period_start = datetime.utcnow()
        subscription.current_period_end = datetime.utcnow() + timedelta(days=30)
        subscription.api_calls_used = 0
        db.session.add(subscription)
        db.session.commit()

def get_resend_credentials():
    """Get Resend API credentials from env vars or Replit connector."""
    try:
        # Prefer standard environment variables so email works outside Replit.
        env_api_key = (os.environ.get('RESEND_API_KEY') or '').strip()
        env_from_email = (os.environ.get('RESEND_FROM_EMAIL') or '').strip()
        if env_api_key:
            return env_api_key, env_from_email or None

        hostname = os.environ.get('REPLIT_CONNECTORS_HOSTNAME')
        
        # Get authentication token
        x_replit_token = None
        if os.environ.get('REPL_IDENTITY'):
            x_replit_token = 'repl ' + os.environ.get('REPL_IDENTITY')
        elif os.environ.get('WEB_REPL_RENEWAL'):
            x_replit_token = 'depl ' + os.environ.get('WEB_REPL_RENEWAL')
        
        if not x_replit_token or not hostname:
            logging.error("Missing Replit connector credentials")
            return None, None
        
        # Fetch connection settings
        response = requests.get(
            f'https://{hostname}/api/v2/connection?include_secrets=true&connector_names=resend',
            headers={
                'Accept': 'application/json',
                'X_REPLIT_TOKEN': x_replit_token
            }
        )
        
        if response.status_code != 200:
            logging.error(f"Failed to fetch Resend credentials: {response.status_code}")
            return None, None
        
        data = response.json()
        items = data.get('items', [])
        
        if not items:
            logging.error("No Resend connection found")
            return None, None
        
        settings = items[0].get('settings', {})
        api_key = settings.get('api_key')
        from_email = settings.get('from_email')
        
        if not api_key:
            logging.error("Resend API key not found")
            return None, None
        
        return api_key, from_email
        
    except Exception as e:
        logging.error(f"Error getting Resend credentials: {str(e)}")
        return None, None

def send_verification_email(user_email, username, verification_token):
    """Send email verification email using Resend"""
    try:
        # Get Resend credentials
        api_key, from_email = get_resend_credentials()
        
        if not api_key:
            logging.error("Cannot send verification email - Resend not configured")
            return False
        
        # Use configured from_email or fallback
        sender_email = from_email if from_email else 'noreply@ffmpegapi.net'
        
        # Initialize Resend client
        resend.api_key = api_key
        
        # Build verification URL
        verification_url = url_for('auth.verify_email', token=verification_token, _external=True)
        
        # Prepare email content
        email_subject = "Verify your FFMPEG API account"
        email_html = f"""
        <h2>Welcome to FFMPEG API, {username}!</h2>
        <p>Thank you for registering. Please verify your email address to activate your account.</p>
        <p>Click the button below to verify your email:</p>
        <p style="margin: 30px 0;">
            <a href="{verification_url}" 
               style="background-color: #007bff; color: white; padding: 12px 30px; 
                      text-decoration: none; border-radius: 5px; display: inline-block;">
                Verify Email Address
            </a>
        </p>
        <p>Or copy and paste this link into your browser:</p>
        <p><a href="{verification_url}">{verification_url}</a></p>
        <p>This verification link will expire in 24 hours.</p>
        <p>If you didn't create an account with FFMPEG API, please ignore this email.</p>
        <hr style="margin: 30px 0; border: none; border-top: 1px solid #eee;">
        <p style="color: #666; font-size: 12px;">FFMPEG API - Video Processing Made Easy</p>
        """
        
        # Send email
        params = {
            "from": sender_email,
            "to": [user_email],
            "subject": email_subject,
            "html": email_html
        }
        
        email = resend.Emails.send(params)
        logging.info(f"Verification email sent to {user_email}")
        return True
        
    except Exception as e:
        logging.error(f"Error sending verification email: {str(e)}", exc_info=True)
        return False


def _safe_post_oauth_redirect():
    next_page = session.pop(SESSION_POST_OAUTH_REDIRECT, None)
    if (
        next_page
        and isinstance(next_page, str)
        and next_page.startswith("/")
        and not next_page.startswith("//")
    ):
        return next_page
    return url_for("dashboard")


@auth.route("/login/google")
def google_login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    client_id, client_secret = _google_oauth_credentials()
    if not client_id or not client_secret:
        flash("Google sign-in is not configured.", "warning")
        return redirect(url_for("auth.login"))
    next_raw = request.args.get("next")
    if (
        next_raw
        and isinstance(next_raw, str)
        and next_raw.startswith("/")
        and not next_raw.startswith("//")
    ):
        session[SESSION_POST_OAUTH_REDIRECT] = next_raw
    state = secrets.token_urlsafe(32)
    session[SESSION_GOOGLE_OAUTH_STATE] = state
    redirect_uri = _google_oauth_redirect_uri()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    return redirect(GOOGLE_AUTH_ENDPOINT + "?" + urlencode(params))


@auth.route("/callback/google")
def google_callback():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    client_id, client_secret = _google_oauth_credentials()
    if not client_id or not client_secret:
        flash("Google sign-in is not configured.", "warning")
        return redirect(url_for("auth.login"))
    if request.args.get("error"):
        logging.warning(
            "Google OAuth error: %s %s",
            request.args.get("error"),
            request.args.get("error_description"),
        )
        flash("Google sign-in was cancelled or failed.", "danger")
        return redirect(url_for("auth.login"))
    state = request.args.get("state")
    if not state or state != session.get(SESSION_GOOGLE_OAUTH_STATE):
        flash("Invalid sign-in state. Please try again.", "danger")
        return redirect(url_for("auth.login"))
    session.pop(SESSION_GOOGLE_OAUTH_STATE, None)
    code = request.args.get("code")
    if not code:
        flash("Missing authorization code from Google.", "danger")
        return redirect(url_for("auth.login"))
    redirect_uri = _google_oauth_redirect_uri()
    try:
        tok_resp = requests.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        logging.error("Google token exchange request failed: %s", e, exc_info=True)
        flash("Could not reach Google to complete sign-in.", "danger")
        return redirect(url_for("auth.login"))
    if tok_resp.status_code != 200:
        logging.error(
            "Google token HTTP %s: %s",
            tok_resp.status_code,
            tok_resp.text[:500],
        )
        flash("Could not complete Google sign-in.", "danger")
        return redirect(url_for("auth.login"))
    access_token = tok_resp.json().get("access_token")
    if not access_token:
        flash("Google did not return an access token.", "danger")
        return redirect(url_for("auth.login"))
    try:
        ui_resp = requests.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except requests.RequestException as e:
        logging.error("Google userinfo request failed: %s", e, exc_info=True)
        flash("Could not load your Google profile.", "danger")
        return redirect(url_for("auth.login"))
    if ui_resp.status_code != 200:
        logging.error(
            "Google userinfo HTTP %s: %s",
            ui_resp.status_code,
            ui_resp.text[:500],
        )
        flash("Could not load your Google profile.", "danger")
        return redirect(url_for("auth.login"))
    profile = ui_resp.json()
    google_sub = profile.get("id")
    email = (profile.get("email") or "").strip().lower()
    if not google_sub or not email:
        flash("Google did not return a usable account id or email.", "danger")
        return redirect(url_for("auth.login"))
    if not profile.get("verified_email"):
        flash(
            "Your Google account email must be verified to use Google sign-in.",
            "warning",
        )
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(google_id=google_sub).first()
    if user:
        if not user.active:
            flash("This account is disabled.", "danger")
            return redirect(url_for("auth.login"))
        login_user(user, remember=True)
        flash("Signed in with Google.", "success")
        return redirect(_safe_post_oauth_redirect())

    user = User.query.filter(func.lower(User.email) == email).first()
    if user:
        if not user.active:
            flash("This account is disabled.", "danger")
            return redirect(url_for("auth.login"))
        if user.google_id and user.google_id != google_sub:
            flash(
                "This email is already linked to a different Google account.",
                "danger",
            )
            return redirect(url_for("auth.login"))
        user.google_id = google_sub
        user.email = email
        user.email_verified = True
        user.verification_token = None
        user.verification_token_expiry = None
        db.session.commit()
        login_user(user, remember=True)
        flash("Signed in with Google. Your account has been linked.", "success")
        return redirect(_safe_post_oauth_redirect())

    username = _unique_username_from_email(email)
    new_user = User()
    new_user.username = username
    new_user.email = email
    new_user.google_id = google_sub
    new_user.email_verified = True
    new_user.password_hash = None
    db.session.add(new_user)
    db.session.commit()
    _provision_free_plan_and_api_key(new_user)
    login_user(new_user, remember=True)
    flash("Welcome! Your account was created with Google.", "success")
    return redirect(_safe_post_oauth_redirect())


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    recaptcha_site_key = (os.environ.get("RECAPTCHA_SITE_KEY") or "").strip()
    recaptcha_secret = (os.environ.get("RECAPTCHA_SECRET_KEY") or "").strip()

    form = RegistrationForm()
    if form.validate_on_submit():
        if recaptcha_secret:
            recaptcha_token = request.form.get("g-recaptcha-response", "")
            if not _verify_recaptcha_response(recaptcha_token):
                flash(
                    "reCAPTCHA verification failed. Please complete the check and try again.",
                    "danger",
                )
                return render_template(
                    "register.html",
                    form=form,
                    recaptcha_site_key=recaptcha_site_key,
                )

        user = User()
        user.username = form.username.data
        user.email = form.email.data
        user.set_password(form.password.data)
        user.email_verified = False
        
        db.session.add(user)
        db.session.commit()
        
        # Generate verification token
        token = user.generate_verification_token()
        
        # Send verification email
        email_sent = send_verification_email(user.email, user.username, token)
        
        if email_sent:
            flash('Registration successful! Please check your email to verify your account.', 'success')
        else:
            flash('Registration successful! However, we could not send the verification email. Please contact support.', 'warning')
        
        # Generate initial API key for new user (will be usable after verification)
        user.generate_api_key("My First API Key")
        
        # Assign free plan to new user
        free_plan = SubscriptionPlan.query.filter_by(name='Free', is_active=True).first()
        if free_plan:
            subscription = UserSubscription()
            subscription.user_id = user.id
            subscription.plan_id = free_plan.id
            subscription.status = 'active'
            subscription.billing_cycle = 'monthly'
            subscription.current_period_start = datetime.utcnow()
            subscription.current_period_end = datetime.utcnow() + timedelta(days=30)
            subscription.api_calls_used = 0
            
            db.session.add(subscription)
            db.session.commit()
        
        return redirect(url_for('auth.login'))
    
    return render_template(
        "register.html",
        form=form,
        recaptcha_site_key=recaptcha_site_key,
    )

@auth.route('/verify-email/<token>')
def verify_email(token):
    """Verify user email with token"""
    user = User.query.filter_by(verification_token=token).first()
    
    if not user:
        flash('Invalid verification link.', 'danger')
        return redirect(url_for('auth.login'))
    
    if user.email_verified:
        flash('Your email is already verified. You can log in.', 'info')
        return redirect(url_for('auth.login'))
    
    if user.verify_email(token):
        flash('Your email has been verified! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    else:
        flash('Verification link has expired. Please request a new one.', 'danger')
        return redirect(url_for('auth.resend_verification'))

@auth.route('/resend-verification', methods=['GET', 'POST'])
def resend_verification():
    """Resend verification email"""
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user and not user.email_verified:
            token = user.generate_verification_token()
            email_sent = send_verification_email(user.email, user.username, token)
            
            if email_sent:
                flash('Verification email has been sent. Please check your inbox.', 'success')
            else:
                flash('Could not send verification email. Please try again later.', 'danger')
        elif user and user.email_verified:
            flash('Your email is already verified.', 'info')
        else:
            flash('No account found with that email address.', 'danger')
        
        return redirect(url_for('auth.login'))
    
    return render_template('resend_verification.html')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        
        if user and user.check_password(form.password.data):
            if not user.email_verified:
                flash('Please verify your email address before logging in. Check your inbox for the verification link.', 'warning')
                return render_template('login.html', form=form, show_resend=True, user_email=user.email)
            
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'danger')
    
    return render_template('login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@auth.route('/dashboard')
@login_required
def dashboard():
    api_keys = [key for key in current_user.api_keys if key.is_active]
    
    # Get user's subscription plan
    user_subscription = UserSubscription.query.filter(
        UserSubscription.user_id == current_user.id,
        UserSubscription.status.in_(('active', 'trialing', 'admin_granted')),
    ).first()
    if user_subscription and not user_subscription.has_entitlement_source():
        user_subscription = None
    
    # Check if user is on free plan
    is_free_plan = True  # Default to free plan if no subscription
    plan_name = 'Free'
    if user_subscription and user_subscription.plan:
        plan_name = user_subscription.plan.name
        # Consider plan as "free" if named "Free" or has $0 monthly price
        monthly_price = user_subscription.plan.monthly_price
        is_free_plan = (
            user_subscription.plan.name.lower() == 'free' or 
            (monthly_price is not None and float(monthly_price) == 0.0)
        )
    
    # Determine if user can create more API keys
    can_create_more_keys = True
    if is_free_plan and len(api_keys) >= 1:
        can_create_more_keys = False
    
    return render_template('dashboard.html', 
                         api_keys=api_keys, 
                         is_free_plan=is_free_plan,
                         plan_name=plan_name,
                         can_create_more_keys=can_create_more_keys)

@auth.route('/generate-api-key', methods=['GET', 'POST'])
@login_required
def generate_api_key():
    form = ApiKeyForm()
    if form.validate_on_submit():
        # Check user's subscription plan
        user_subscription = UserSubscription.query.filter(
            UserSubscription.user_id == current_user.id,
            UserSubscription.status.in_(('active', 'trialing', 'admin_granted')),
        ).first()
        if user_subscription and not user_subscription.has_entitlement_source():
            user_subscription = None
        
        # Count active API keys
        active_keys = ApiKey.query.filter_by(
            user_id=current_user.id, 
            is_active=True
        ).count()
        
        # Check if user is on free plan
        is_free_plan = True  # Default to free plan if no subscription
        if user_subscription and user_subscription.plan:
            # Consider plan as "free" if it's named "Free" or has $0 monthly price
            monthly_price = user_subscription.plan.monthly_price
            is_free_plan = (
                user_subscription.plan.name.lower() == 'free' or 
                (monthly_price is not None and float(monthly_price) == 0.0)
            )
        
        # Enforce limit for free users
        if is_free_plan and active_keys >= 1:
            flash('Free plan users can only have 1 API key. Please upgrade to a paid plan to create multiple API keys.', 'warning')
            return redirect(url_for('auth.dashboard'))
        
        # Generate API key
        api_key = current_user.generate_api_key(form.name.data)
        flash(f'New API key generated: {api_key.key}', 'success')
        return redirect(url_for('auth.dashboard'))
    
    return render_template('generate_api_key.html', form=form)

@auth.route('/delete-api-key/<int:key_id>', methods=['POST'])
@login_required
def delete_api_key(key_id):
    api_key = ApiKey.query.filter_by(id=key_id, user_id=current_user.id).first()
    if api_key:
        api_key.is_active = False
        db.session.commit()
        flash('API key deactivated successfully.', 'success')
    else:
        flash('API key not found.', 'danger')
    
    return redirect(url_for('auth.dashboard'))
