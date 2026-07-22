from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.models import User, LoginAttempt, AuditLog
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import re
import hashlib
import hmac
import secrets
from functools import wraps
from flask_wtf.csrf import CSRFProtect

bp = Blueprint('auth', __name__)

# Rate limiting
login_attempts = {}

def rate_limit_check(username, ip):
    """Check if login attempts exceed rate limit"""
    key = f"{username}_{ip}"
    now = datetime.utcnow()
    
    if key in login_attempts:
        attempts, first_attempt = login_attempts[key]
        # Reset after 15 minutes
        if (now - first_attempt) > timedelta(minutes=15):
            login_attempts[key] = (1, now)
            return True
        
        if attempts >= 5:
            return False
        login_attempts[key] = (attempts + 1, first_attempt)
    else:
        login_attempts[key] = (1, now)
    return True

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain at least one special character"
    return True, "Password is valid"

def validate_username(username):
    """Validate username format"""
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, "Username is valid"

def log_audit(user_id, action, details, ip):
    """Log audit trail"""
    try:
        log = AuditLog(
            user_id=user_id,
            action=action,
            details=details,
            ip_address=ip
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Audit log error: {str(e)}")

@bp.route('/register', methods=['GET', 'POST'])
def register():
    # Registration is disabled - only admin can create accounts
    flash('Registration is currently disabled. Please contact the administrator.', 'warning')
    return redirect(url_for('auth.login'))

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = True if request.form.get('remember') else False
        ip = request.remote_addr
        
        # Rate limiting
        if not rate_limit_check(username, ip):
            flash('Too many login attempts. Please try again later.', 'danger')
            return render_template('login.html')
        
        try:
            # Check if account is locked
            user = User.query.filter_by(username=username).first()
            if user and user.locked_until and user.locked_until > datetime.utcnow():
                flash('Account is temporarily locked. Please try again later.', 'danger')
                return render_template('login.html')
            
            # Validate credentials
            if not user or not check_password_hash(user.password_hash, password):
                # Log failed attempt
                login_attempt = LoginAttempt(
                    username=username,
                    ip_address=ip,
                    success=False,
                    user_agent=request.user_agent.string[:200] if request.user_agent else ''
                )
                db.session.add(login_attempt)
                
                # Increment failed attempts
                if user:
                    user.failed_login_attempts += 1
                    if user.failed_login_attempts >= 5:
                        user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                    db.session.commit()
                
                flash('Invalid username or password.', 'danger')
                return render_template('login.html')
            
            # Check if account is active
            if not user.is_active:
                flash('Account is deactivated. Please contact support.', 'danger')
                return render_template('login.html')
            
            # Successful login
            user.failed_login_attempts = 0
            user.locked_until = None
            user.last_login = datetime.utcnow()
            user.last_ip = ip
            user.user_agent = request.user_agent.string[:200] if request.user_agent else ''
            
            # Log successful login
            login_attempt = LoginAttempt(
                username=username,
                ip_address=ip,
                success=True,
                user_agent=request.user_agent.string[:200] if request.user_agent else ''
            )
            db.session.add(login_attempt)
            db.session.commit()
            
            # Log audit
            log_audit(user.id, 'LOGIN', f'User logged in from IP {ip}', ip)
            
            login_user(user, remember=remember)
            
            # Clear rate limiting
            key = f"{username}_{ip}"
            if key in login_attempts:
                del login_attempts[key]
            
            session.permanent = True
            
            next_page = request.args.get('next')
            if user.is_admin:
                flash(f'Welcome back, {user.full_name}!', 'success')
                return redirect(next_page or url_for('admin.dashboard'))
            flash(f'Welcome back, {user.full_name}!', 'success')
            return redirect(next_page or url_for('customer.dashboard'))
            
        except Exception as e:
            current_app.logger.error(f"Login error: {str(e)}")
            flash('An error occurred during login. Please try again.', 'danger')
            return render_template('login.html')
    
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    try:
        ip = request.remote_addr
        log_audit(current_user.id, 'LOGOUT', f'User logged out from IP {ip}', ip)
        logout_user()
        flash('You have been logged out.', 'info')
    except Exception as e:
        current_app.logger.error(f"Logout error: {str(e)}")
    return redirect(url_for('main.index'))

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        try:
            # Validate inputs
            full_name = request.form.get('full_name', '').strip()
            phone = request.form.get('phone', '').strip()
            address = request.form.get('address', '').strip()
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Update profile
            if full_name:
                current_user.full_name = full_name
            if phone:
                current_user.phone = phone
            if address:
                current_user.address = address
            
            # Change password if requested
            if new_password:
                if not check_password_hash(current_user.password_hash, current_password):
                    flash('Current password is incorrect.', 'danger')
                    return render_template('profile.html', user=current_user)
                
                valid, msg = validate_password(new_password)
                if not valid:
                    flash(msg, 'danger')
                    return render_template('profile.html', user=current_user)
                
                if new_password != confirm_password:
                    flash('Passwords do not match.', 'danger')
                    return render_template('profile.html', user=current_user)
                
                current_user.password_hash = generate_password_hash(new_password)
                flash('Password updated successfully.', 'success')
            
            db.session.commit()
            flash('Profile updated successfully.', 'success')
        except Exception as e:
            current_app.logger.error(f"Profile update error: {str(e)}")
            flash('An error occurred while updating profile.', 'danger')
        return redirect(url_for('auth.profile'))
    
    return render_template('profile.html', user=current_user)
