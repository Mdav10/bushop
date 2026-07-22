from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import re
import secrets
import json
from functools import wraps
from sqlalchemy import text, desc, func
import logging
import io

# Try to import reportlab, fallback if not available
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    print("⚠️ reportlab not installed. PDF invoice will use HTML fallback.")

print(f"Python version: {__import__('sys').version}")

app = Flask(__name__)

# Security Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(64))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = True
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)

# Database Configuration
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///mugistore.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 300,
    'pool_pre_ping': True,
    'pool_use_lifo': True
}

app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'warning'
login_manager.session_protection = 'strong'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'products'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'payments'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'), exist_ok=True)

# ==================== COMPLETE MODELS ====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    profile_image = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    last_ip = db.Column(db.String(45))
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    email_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(100))
    reset_token = db.Column(db.String(100))
    reset_token_expiry = db.Column(db.DateTime)
    
    orders = db.relationship('Order', backref='customer', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)
    wishlist = db.relationship('Wishlist', backref='user', lazy=True)
    reviews = db.relationship('Review', backref='user', lazy=True)
    recently_viewed = db.relationship('RecentlyViewed', backref='user', lazy=True)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    icon = db.Column(db.String(50))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(120), unique=True)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    compare_price = db.Column(db.Float)
    cost_price = db.Column(db.Float)
    stock = db.Column(db.Integer, default=0)
    sku = db.Column(db.String(50), unique=True)
    image = db.Column(db.String(200))
    whatsapp_link = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    sales_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    reviews = db.relationship('Review', backref='product', lazy=True)
    wishlist = db.relationship('Wishlist', backref='product', lazy=True)
    recently_viewed = db.relationship('RecentlyViewed', backref='product', lazy=True)
    
    def get_rating(self):
        reviews = Review.query.filter_by(product_id=self.id).all()
        if not reviews:
            return 0
        return sum(r.rating for r in reviews) / len(reviews)
    
    def get_review_count(self):
        return Review.query.filter_by(product_id=self.id).count()

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    image = db.Column(db.String(200), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product', backref='images')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float)
    tax = db.Column(db.Float, default=0)
    shipping_fee = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='pending')
    payment_status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(20), default='lumicash')
    payment_proof = db.Column(db.String(200))
    payment_date = db.Column(db.DateTime)
    delivery_address = db.Column(db.String(200))
    delivery_notes = db.Column(db.Text)
    estimated_delivery = db.Column(db.DateTime)
    tracking_number = db.Column(db.String(50))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    payment_records = db.relationship('PaymentRecord', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)
    product = db.relationship('Product')

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='info')
    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Wishlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    is_approved = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class RecentlyViewed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

class PaymentRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20), default='lumicash')
    reference = db.Column(db.String(50))
    status = db.Column(db.String(20), default='pending')
    verified_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    verified_at = db.Column(db.DateTime)
    proof_image = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LoginAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80))
    ip_address = db.Column(db.String(45))
    success = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='audit_logs')

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), default='percentage')
    discount_value = db.Column(db.Float, nullable=False)
    min_order = db.Column(db.Float, default=0)
    max_discount = db.Column(db.Float)
    usage_limit = db.Column(db.Integer)
    used_count = db.Column(db.Integer, default=0)
    expires_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ShippingMethod(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    cost = db.Column(db.Float, nullable=False)
    estimated_days = db.Column(db.Integer)
    is_active = db.Column(db.Boolean, default=True)

# ==================== HELPERS ====================

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('⚠️ Admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_super_admin:
            flash('⚠️ Super admin access required.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def validate_password(password):
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain an uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain a lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain a number"
    if not re.search(r'[!@#$%^&*]', password):
        return False, "Password must contain a special character"
    return True, "Valid password"

def log_audit(user_id, action, details, ip):
    try:
        log = AuditLog(user_id=user_id, action=action, details=details, ip_address=ip)
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.error(f"Audit log error: {str(e)}")

def notify_user(user_id, title, message, type='info', link=None):
    try:
        notification = Notification(user_id=user_id, title=title, message=message, type=type, link=link)
        db.session.add(notification)
        db.session.commit()
    except Exception as e:
        logger.error(f"Notification error: {str(e)}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def generate_order_number():
    return f"ORD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"

def generate_slug(text):
    slug = text.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = re.sub(r'^-+|-+$', '', slug)
    return slug

def generate_invoice_html(order):
    """Generate HTML invoice as fallback when reportlab is not available"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Invoice #{order.order_number}</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 40px; }}
            .header {{ text-align: center; border-bottom: 2px solid #667eea; padding-bottom: 20px; }}
            .header h1 {{ color: #667eea; margin: 0; }}
            .info {{ margin: 20px 0; }}
            .info table {{ width: 100%; }}
            .info td {{ padding: 5px; }}
            .items {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            .items th {{ background: #667eea; color: white; padding: 10px; text-align: left; }}
            .items td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
            .total {{ text-align: right; font-size: 18px; font-weight: bold; color: #667eea; }}
            .footer {{ text-align: center; margin-top: 40px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>MugiStore</h1>
            <p>Invoice #{order.order_number}</p>
            <p>Date: {order.created_at.strftime('%B %d, %Y at %H:%M')}</p>
        </div>
        <div class="info">
            <table>
                <tr>
                    <td><strong>Customer:</strong> {order.customer.full_name}</td>
                    <td><strong>Email:</strong> {order.customer.email}</td>
                </tr>
                <tr>
                    <td><strong>Phone:</strong> {order.customer.phone or 'N/A'}</td>
                    <td><strong>Address:</strong> {order.delivery_address or 'Not provided'}</td>
                </tr>
            </table>
        </div>
        <table class="items">
            <thead>
                <tr>
                    <th>Product</th>
                    <th>Quantity</th>
                    <th>Price</th>
                    <th>Subtotal</th>
                </tr>
            </thead>
            <tbody>
    """
    for item in order.items:
        html += f"""
                <tr>
                    <td>{item.product.name}</td>
                    <td>{item.quantity}</td>
                    <td>{item.price:,.0f} FBu</td>
                    <td>{item.subtotal:,.0f} FBu</td>
                </tr>
        """
    html += f"""
            </tbody>
        </table>
        <div class="total">
            <p>Total: {order.total_amount:,.0f} FBu</p>
        </div>
        <div class="footer">
            <p>Thank you for shopping with MugiStore!</p>
            <p>© {datetime.utcnow().year} MugiStore. All rights reserved.</p>
        </div>
    </body>
    </html>
    """
    return html

# ==================== PUBLIC ROUTES ====================

@app.route('/')
def index():
    featured = Product.query.filter_by(is_active=True, is_featured=True).limit(8).all()
    new_products = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).limit(8).all()
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('index.html', featured=featured, new_products=new_products, categories=categories)

@app.route('/products')
def products():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category')
    search = request.args.get('search')
    sort = request.args.get('sort', 'newest')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    in_stock = request.args.get('in_stock', type=bool)
    
    query = Product.query.filter_by(is_active=True)
    
    if category:
        query = query.filter_by(category_id=category)
    if search:
        query = query.filter(Product.name.contains(search) | Product.description.contains(search))
    if min_price:
        query = query.filter(Product.price >= min_price)
    if max_price:
        query = query.filter(Product.price <= max_price)
    if in_stock:
        query = query.filter(Product.stock > 0)
    
    if sort == 'price_low':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_high':
        query = query.order_by(Product.price.desc())
    elif sort == 'popular':
        query = query.order_by(Product.sales_count.desc())
    elif sort == 'rating':
        query = query.order_by(Product.views.desc())
    else:
        query = query.order_by(Product.created_at.desc())
    
    products = query.paginate(page=page, per_page=24)
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('products.html', products=products, categories=categories)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    
    product.views += 1
    db.session.commit()
    
    if current_user.is_authenticated:
        recent = RecentlyViewed.query.filter_by(user_id=current_user.id, product_id=product.id).first()
        if not recent:
            recent = RecentlyViewed(user_id=current_user.id, product_id=product.id)
            db.session.add(recent)
        else:
            recent.viewed_at = datetime.utcnow()
        db.session.commit()
    
    related = Product.query.filter_by(category_id=product.category_id, is_active=True).filter(Product.id != product.id).limit(4).all()
    reviews = Review.query.filter_by(product_id=product.id, is_approved=True).all()
    avg_rating = product.get_rating()
    
    return render_template('product_detail.html', product=product, related=related, reviews=reviews, avg_rating=avg_rating)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/search')
def search():
    q = request.args.get('q', '')
    if q:
        products = Product.query.filter(Product.name.contains(q), Product.is_active == True).limit(20).all()
    else:
        products = []
    return render_template('search.html', products=products, q=q)

# ==================== AUTH ROUTES ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin_dashboard' if current_user.is_admin else 'customer_dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = True if request.form.get('remember') else False
        ip = request.remote_addr
        
        attempts = LoginAttempt.query.filter_by(
            username=username, 
            ip_address=ip,
            success=False
        ).filter(LoginAttempt.timestamp > datetime.utcnow() - timedelta(minutes=15)).count()
        
        if attempts >= 5:
            flash('⚠️ Too many failed attempts. Please try again later.', 'danger')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            login_attempt = LoginAttempt(username=username, ip_address=ip, success=False)
            db.session.add(login_attempt)
            
            if user:
                user.failed_attempts += 1
                if user.failed_attempts >= 5:
                    user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                db.session.commit()
            
            flash('❌ Invalid username or password.', 'danger')
            return render_template('login.html')
        
        if user.locked_until and user.locked_until > datetime.utcnow():
            flash('🔒 Account is temporarily locked. Please try again later.', 'danger')
            return render_template('login.html')
        
        if not user.is_active:
            flash('❌ Account is deactivated. Please contact support.', 'danger')
            return render_template('login.html')
        
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login = datetime.utcnow()
        user.last_ip = ip
        db.session.commit()
        
        login_attempt = LoginAttempt(username=username, ip_address=ip, success=True)
        db.session.add(login_attempt)
        db.session.commit()
        
        log_audit(user.id, 'LOGIN', f'User logged in from IP {ip}', ip)
        login_user(user, remember=remember)
        
        flash(f'✅ Welcome back, {user.full_name}!', 'success')
        
        if user.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('customer_dashboard'))
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    ip = request.remote_addr
    log_audit(current_user.id, 'LOGOUT', f'User logged out from IP {ip}', ip)
    logout_user()
    flash('👋 You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        
        if User.query.filter_by(username=username).first():
            flash('❌ Username already exists.', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('❌ Email already registered.', 'danger')
            return render_template('register.html')
        
        valid, msg = validate_password(password)
        if not valid:
            flash(f'❌ {msg}', 'danger')
            return render_template('register.html')
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name,
            phone=phone,
            is_admin=False,
            is_super_admin=False,
            is_active=True
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash('✅ Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# ==================== CUSTOMER ROUTES ====================

@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(5).all()
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
    wishlist = Wishlist.query.filter_by(user_id=current_user.id).all()
    recent = RecentlyViewed.query.filter_by(user_id=current_user.id).order_by(RecentlyViewed.viewed_at.desc()).limit(5).all()
    cart_count = sum(session.get('cart', {}).values())
    
    return render_template('customer/dashboard.html', 
                         orders=orders, 
                         notifications=notifications,
                         wishlist=wishlist,
                         recent=recent,
                         cart_count=cart_count)

@app.route('/customer/orders')
@login_required
def customer_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('customer/orders.html', orders=orders)

@app.route('/customer/order/<int:order_id>')
@login_required
def customer_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('⚠️ Access denied.', 'danger')
        return redirect(url_for('customer_dashboard'))
    return render_template('customer/order_detail.html', order=order)

@app.route('/customer/order/cancel/<int:order_id>', methods=['POST'])
@login_required
def customer_order_cancel(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('⚠️ Access denied.', 'danger')
        return redirect(url_for('customer_dashboard'))
    
    if order.status in ['pending', 'processing']:
        order.status = 'cancelled'
        db.session.commit()
        notify_user(order.user_id, '⚠️ Order Cancelled', f'Order #{order.order_number} has been cancelled.')
        flash('✅ Order cancelled successfully.', 'success')
    else:
        flash('❌ Cannot cancel this order.', 'danger')
    
    return redirect(url_for('customer_order', order_id=order_id))

@app.route('/customer/order/reorder/<int:order_id>')
@login_required
def customer_order_reorder(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('⚠️ Access denied.', 'danger')
        return redirect(url_for('customer_dashboard'))
    
    cart = session.get('cart', {})
    for item in order.items:
        cart[str(item.product_id)] = cart.get(str(item.product_id), 0) + item.quantity
    session['cart'] = cart
    
    flash('✅ Items added to cart for reorder!', 'success')
    return redirect(url_for('checkout'))

@app.route('/customer/order/invoice/<int:order_id>')
@login_required
def customer_order_invoice(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('⚠️ Access denied.', 'danger')
        return redirect(url_for('customer_dashboard'))
    
    # Generate HTML invoice
    html = generate_invoice_html(order)
    return html

@app.route('/customer/payment/<int:order_id>', methods=['GET', 'POST'])
@login_required
def customer_payment(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('⚠️ Access denied.', 'danger')
        return redirect(url_for('customer_dashboard'))
    
    if order.payment_status == 'approved':
        flash('✅ Payment already approved.', 'info')
        return redirect(url_for('customer_order', order_id=order.id))
    
    if request.method == 'POST':
        if 'payment_proof' in request.files:
            file = request.files['payment_proof']
            if file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{order.order_number}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg")
                filepath = os.path.join('static/uploads/payments', filename)
                file.save(filepath)
                order.payment_proof = filepath
                order.payment_status = 'pending'
                
                payment = PaymentRecord(
                    order_id=order.id,
                    amount=order.total_amount,
                    method=request.form.get('payment_method', 'lumicash'),
                    status='pending',
                    proof_image=filepath,
                    notes=request.form.get('notes', '')
                )
                db.session.add(payment)
                db.session.commit()
                
                notify_user(order.user_id, '📤 Payment Uploaded', f'Payment proof for order #{order.order_number} uploaded. Waiting for verification.')
                flash('✅ Payment proof uploaded! Waiting for verification.', 'success')
                return redirect(url_for('customer_order', order_id=order.id))
            else:
                flash('❌ Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP', 'danger')
        else:
            flash('⚠️ Please select a file to upload.', 'warning')
    
    return render_template('customer/payment.html', order=order)

@app.route('/customer/wishlist')
@login_required
def customer_wishlist():
    wishlist = Wishlist.query.filter_by(user_id=current_user.id).all()
    return render_template('customer/wishlist.html', wishlist=wishlist)

@app.route('/customer/wishlist/add/<int:product_id>')
@login_required
def customer_wishlist_add(product_id):
    existing = Wishlist.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if not existing:
        wishlist = Wishlist(user_id=current_user.id, product_id=product_id)
        db.session.add(wishlist)
        db.session.commit()
        flash('❤️ Added to wishlist!', 'success')
    else:
        flash('⚠️ Already in wishlist.', 'info')
    return redirect(request.referrer or url_for('products'))

@app.route('/customer/wishlist/remove/<int:product_id>')
@login_required
def customer_wishlist_remove(product_id):
    wishlist = Wishlist.query.filter_by(user_id=current_user.id, product_id=product_id).first()
    if wishlist:
        db.session.delete(wishlist)
        db.session.commit()
        flash('🗑️ Removed from wishlist.', 'success')
    return redirect(url_for('customer_wishlist'))

@app.route('/customer/notifications')
@login_required
def customer_notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    return render_template('customer/notifications.html', notifications=notifications)

@app.route('/customer/notification/read/<int:notification_id>')
@login_required
def customer_notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id == current_user.id:
        notification.is_read = True
        db.session.commit()
    return redirect(request.referrer or url_for('customer_notifications'))

@app.route('/customer/notification/read-all')
@login_required
def customer_notification_read_all():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('✅ All notifications marked as read.', 'success')
    return redirect(url_for('customer_notifications'))

@app.route('/customer/notification/delete/<int:notification_id>')
@login_required
def customer_notification_delete(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id == current_user.id:
        db.session.delete(notification)
        db.session.commit()
    return redirect(url_for('customer_notifications'))

@app.route('/customer/profile', methods=['GET', 'POST'])
@login_required
def customer_profile():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        
        if full_name:
            current_user.full_name = full_name
        if phone:
            current_user.phone = phone
        if address:
            current_user.address = address
        
        db.session.commit()
        flash('✅ Profile updated successfully!', 'success')
        return redirect(url_for('customer_profile'))
    
    return render_template('customer/profile.html')

@app.route('/customer/change-password', methods=['GET', 'POST'])
@login_required
def customer_change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not check_password_hash(current_user.password_hash, current_password):
            flash('❌ Current password is incorrect.', 'danger')
            return render_template('customer/change_password.html')
        
        valid, msg = validate_password(new_password)
        if not valid:
            flash(f'❌ {msg}', 'danger')
            return render_template('customer/change_password.html')
        
        if new_password != confirm_password:
            flash('❌ Passwords do not match.', 'danger')
            return render_template('customer/change_password.html')
        
        current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('✅ Password changed successfully!', 'success')
        return redirect(url_for('customer_profile'))
    
    return render_template('customer/change_password.html')

@app.route('/customer/delete-account', methods=['POST'])
@login_required
def customer_delete_account():
    orders = Order.query.filter_by(user_id=current_user.id).count()
    if orders > 0:
        flash('❌ Cannot delete account with orders. Contact support.', 'danger')
        return redirect(url_for('customer_profile'))
    
    current_user.is_active = False
    db.session.commit()
    logout_user()
    flash('✅ Account deactivated successfully.', 'info')
    return redirect(url_for('index'))

# ==================== SHOPPING CART ====================

@app.route('/cart')
@login_required
def cart():
    cart = session.get('cart', {})
    items = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product and product.is_active:
            subtotal = product.price * quantity
            total += subtotal
            items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
        else:
            del cart[product_id]
            session['cart'] = cart
    
    return render_template('cart.html', items=items, total=total)

@app.route('/api/cart/add', methods=['POST'])
@login_required
def api_cart_add():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    product = Product.query.get(int(product_id))
    if not product or not product.is_active:
        return jsonify({'success': False, 'error': 'Product unavailable'})
    
    if product.stock < quantity:
        return jsonify({'success': False, 'error': 'Not enough stock'})
    
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + quantity
    session['cart'] = cart
    
    return jsonify({'success': True, 'message': 'Added to cart!', 'count': sum(cart.values())})

@app.route('/api/cart/update', methods=['POST'])
@login_required
def api_cart_update():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    if quantity < 0:
        return jsonify({'success': False, 'error': 'Invalid quantity'})
    
    cart = session.get('cart', {})
    if quantity == 0:
        if str(product_id) in cart:
            del cart[str(product_id)]
    else:
        cart[str(product_id)] = quantity
    
    session['cart'] = cart
    return jsonify({'success': True, 'count': sum(cart.values())})

@app.route('/api/cart/clear', methods=['POST'])
@login_required
def api_cart_clear():
    session['cart'] = {}
    return jsonify({'success': True})

@app.route('/api/cart/remove', methods=['POST'])
@login_required
def api_cart_remove():
    product_id = request.form.get('product_id')
    cart = session.get('cart', {})
    if str(product_id) in cart:
        del cart[str(product_id)]
        session['cart'] = cart
    return jsonify({'success': True})

@app.route('/api/cart/get')
@login_required
def api_cart_get():
    return jsonify(session.get('cart', {}))

@app.route('/api/cart/count')
@login_required
def api_cart_count():
    cart = session.get('cart', {})
    count = sum(cart.values())
    return jsonify({'count': count})

@app.route('/api/cart/total')
@login_required
def api_cart_total():
    cart = session.get('cart', {})
    total = 0
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product:
            total += product.price * quantity
    return jsonify({'total': total})

# ==================== CHECKOUT ====================

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash('🛒 Your cart is empty.', 'warning')
        return redirect(url_for('products'))
    
    items = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product and product.is_active:
            if product.stock < quantity:
                flash(f'⚠️ {product.name} has only {product.stock} in stock.', 'danger')
                return redirect(url_for('cart'))
            subtotal = product.price * quantity
            total += subtotal
            items.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
        else:
            flash(f'⚠️ Some items are no longer available.', 'danger')
            return redirect(url_for('cart'))
    
    shipping_methods = ShippingMethod.query.filter_by(is_active=True).all()
    
    if request.method == 'POST':
        shipping_method = request.form.get('shipping_method')
        shipping_fee = float(request.form.get('shipping_fee', 0))
        delivery_address = request.form.get('delivery_address', '').strip()
        notes = request.form.get('notes', '').strip()
        terms = request.form.get('terms')
        
        if not terms:
            flash('⚠️ Please accept the Terms & Conditions.', 'danger')
            return render_template('checkout.html', items=items, total=total, shipping_methods=shipping_methods)
        
        if not delivery_address:
            flash('⚠️ Please provide a delivery address.', 'danger')
            return render_template('checkout.html', items=items, total=total, shipping_methods=shipping_methods)
        
        order = Order(
            order_number=generate_order_number(),
            user_id=current_user.id,
            total_amount=total + shipping_fee,
            subtotal=total,
            shipping_fee=shipping_fee,
            delivery_address=delivery_address,
            delivery_notes=notes,
            status='pending',
            payment_status='pending',
            payment_method='lumicash'
        )
        
        db.session.add(order)
        db.session.commit()
        
        for item in items:
            order_item = OrderItem(
                order_id=order.id,
                product_id=item['product'].id,
                quantity=item['quantity'],
                price=item['product'].price,
                subtotal=item['subtotal']
            )
            db.session.add(order_item)
            
            item['product'].stock -= item['quantity']
        
        db.session.commit()
        
        session.pop('cart', None)
        
        flash(f'✅ Order #{order.order_number} created! Please complete payment.', 'success')
        return redirect(url_for('customer_payment', order_id=order.id))
    
    return render_template('checkout.html', items=items, total=total, shipping_methods=shipping_methods)

# ==================== ADMIN ROUTES ====================

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    total_customers = User.query.filter_by(is_admin=False).count()
    total_orders = Order.query.count()
    total_revenue = db.session.query(db.func.sum(Order.total_amount)).filter_by(status='completed').scalar() or 0
    pending_payments = Order.query.filter_by(payment_status='pending').count()
    pending_orders = Order.query.filter_by(status='pending').count()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
    total_products = Product.query.filter_by(is_active=True).count()
    out_of_stock = Product.query.filter_by(stock=0, is_active=True).count()
    low_stock = Product.query.filter(Product.stock <= 5, Product.stock > 0, Product.is_active == True).count()
    
    monthly_revenue = db.session.query(
        func.strftime('%Y-%m', Order.created_at).label('month'),
        func.sum(Order.total_amount).label('total')
    ).filter(Order.status == 'completed').group_by('month').order_by('month').limit(12).all()
    
    top_products = db.session.query(
        Product.id,
        Product.name,
        func.sum(OrderItem.quantity).label('sold')
    ).join(OrderItem).join(Order).filter(Order.status == 'completed').group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
    
    return render_template('admin/dashboard.html',
                         total_customers=total_customers,
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         pending_payments=pending_payments,
                         pending_orders=pending_orders,
                         recent_orders=recent_orders,
                         total_products=total_products,
                         out_of_stock=out_of_stock,
                         low_stock=low_stock,
                         monthly_revenue=monthly_revenue,
                         top_products=top_products)

@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    search = request.args.get('search')
    category = request.args.get('category')
    status = request.args.get('status')
    
    query = Product.query
    if search:
        query = query.filter(Product.name.contains(search))
    if category:
        query = query.filter_by(category_id=category)
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)
    
    products = query.order_by(Product.created_at.desc()).all()
    categories = Category.query.all()
    return render_template('admin/products.html', products=products, categories=categories)

@app.route('/admin/product/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_product_create():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            price = float(request.form.get('price', 0))
            compare_price = float(request.form.get('compare_price', 0)) or None
            stock = int(request.form.get('stock', 0))
            category_id = request.form.get('category_id')
            whatsapp_link = request.form.get('whatsapp_link', '').strip()
            is_featured = bool(request.form.get('is_featured'))
            
            product = Product(
                name=name,
                slug=generate_slug(name),
                description=description,
                price=price,
                compare_price=compare_price,
                stock=stock,
                category_id=category_id if category_id else None,
                whatsapp_link=whatsapp_link,
                is_featured=is_featured,
                is_active=True
            )
            
            if 'image' in request.files:
                file = request.files['image']
                if file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join('static/uploads/products', filename)
                    file.save(filepath)
                    product.image = filepath
            
            db.session.add(product)
            db.session.commit()
            log_audit(current_user.id, 'CREATE_PRODUCT', f'Created product: {name}', request.remote_addr)
            flash('✅ Product created successfully!', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'danger')
    
    categories = Category.query.all()
    return render_template('admin/product_form.html', categories=categories)

@app.route('/admin/product/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        try:
            product.name = request.form.get('name', '').strip()
            product.description = request.form.get('description', '').strip()
            product.price = float(request.form.get('price', 0))
            product.compare_price = float(request.form.get('compare_price', 0)) or None
            product.stock = int(request.form.get('stock', 0))
            product.category_id = request.form.get('category_id')
            product.whatsapp_link = request.form.get('whatsapp_link', '').strip()
            product.is_active = bool(request.form.get('is_active'))
            product.is_featured = bool(request.form.get('is_featured'))
            
            if 'image' in request.files:
                file = request.files['image']
                if file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join('static/uploads/products', filename)
                    file.save(filepath)
                    if product.image and os.path.exists(os.path.join('app', product.image)):
                        try:
                            os.remove(os.path.join('app', product.image))
                        except:
                            pass
                    product.image = filepath
            
            db.session.commit()
            log_audit(current_user.id, 'EDIT_PRODUCT', f'Edited product: {product.name}', request.remote_addr)
            flash('✅ Product updated successfully!', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            flash(f'❌ Error: {str(e)}', 'danger')
    
    categories = Category.query.all()
    return render_template('admin/product_form.html', product=product, categories=categories)

@app.route('/admin/product/delete/<int:product_id>')
@login_required
@admin_required
def admin_product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    if product.image and os.path.exists(os.path.join('app', product.image)):
        try:
            os.remove(os.path.join('app', product.image))
        except:
            pass
    db.session.delete(product)
    db.session.commit()
    log_audit(current_user.id, 'DELETE_PRODUCT', f'Deleted product: {name}', request.remote_addr)
    flash('🗑️ Product deleted.', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/product/duplicate/<int:product_id>')
@login_required
@admin_required
def admin_product_duplicate(product_id):
    original = Product.query.get_or_404(product_id)
    
    new_product = Product(
        name=f"{original.name} (Copy)",
        slug=generate_slug(f"{original.name} copy"),
        description=original.description,
        price=original.price,
        compare_price=original.compare_price,
        stock=0,
        category_id=original.category_id,
        whatsapp_link=original.whatsapp_link,
        is_active=False,
        is_featured=False
    )
    
    db.session.add(new_product)
    db.session.commit()
    log_audit(current_user.id, 'DUPLICATE_PRODUCT', f'Duplicated product: {original.name}', request.remote_addr)
    flash('✅ Product duplicated successfully!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    status = request.args.get('status', 'all')
    search = request.args.get('search')
    customer = request.args.get('customer')
    payment = request.args.get('payment')
    
    query = Order.query
    if status != 'all':
        query = query.filter_by(status=status)
    if search:
        query = query.filter(Order.order_number.contains(search))
    if customer:
        query = query.join(User).filter(User.username.contains(customer) | User.full_name.contains(customer))
    if payment:
        query = query.filter_by(payment_status=payment)
    
    orders = query.order_by(Order.created_at.desc()).all()
    return render_template('admin/orders.html', orders=orders, current_status=status)

@app.route('/admin/order/<int:order_id>')
@login_required
@admin_required
def admin_order(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template('admin/order_detail.html', order=order)

@app.route('/admin/order/update/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def admin_order_update(order_id):
    order = Order.query.get_or_404(order_id)
    action = request.form.get('action')
    reason = request.form.get('reason', '').strip()
    tracking = request.form.get('tracking', '').strip()
    
    if action == 'approve':
        order.status = 'processing'
        order.payment_status = 'approved'
        order.payment_date = datetime.utcnow()
        notify_user(order.user_id, '✅ Payment Approved', f'Your payment for order #{order.order_number} has been approved. Your order is being processed.', link=f'/customer/order/{order.id}')
        log_audit(current_user.id, 'APPROVE_PAYMENT', f'Approved payment for order {order.order_number}', request.remote_addr)
    
    elif action == 'reject':
        order.status = 'cancelled'
        order.payment_status = 'rejected'
        notify_user(order.user_id, '❌ Payment Rejected', f'Order #{order.order_number} rejected: {reason or "Payment verification failed"}', link=f'/customer/order/{order.id}')
        log_audit(current_user.id, 'REJECT_PAYMENT', f'Rejected payment for order {order.order_number}', request.remote_addr)
    
    elif action == 'complete':
        order.status = 'completed'
        order.tracking_number = tracking
        notify_user(order.user_id, '🎉 Order Completed', f'Your order #{order.order_number} has been completed. Tracking: {tracking or "N/A"}', link=f'/customer/order/{order.id}')
        log_audit(current_user.id, 'COMPLETE_ORDER', f'Completed order {order.order_number}', request.remote_addr)
    
    elif action == 'cancel':
        order.status = 'cancelled'
        notify_user(order.user_id, '⚠️ Order Cancelled', f'Order #{order.order_number} has been cancelled. Reason: {reason or "No reason provided"}', link=f'/customer/order/{order.id}')
        log_audit(current_user.id, 'CANCEL_ORDER', f'Cancelled order {order.order_number}', request.remote_addr)
    
    elif action == 'shipping':
        order.status = 'shipping'
        order.tracking_number = tracking
        notify_user(order.user_id, '📦 Order Shipped', f'Your order #{order.order_number} has been shipped. Tracking: {tracking or "N/A"}', link=f'/customer/order/{order.id}')
        log_audit(current_user.id, 'SHIP_ORDER', f'Shipped order {order.order_number}', request.remote_addr)
    
    db.session.commit()
    flash(f'✅ Order updated to {order.status}.', 'success')
    return redirect(url_for('admin_order', order_id=order_id))

@app.route('/admin/order/export/csv')
@login_required
@admin_required
def admin_order_export_csv():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    
    import csv
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Order #', 'Customer', 'Date', 'Total', 'Status', 'Payment'])
    for order in orders:
        writer.writerow([order.order_number, order.customer.full_name, order.created_at.strftime('%Y-%m-%d'), order.total_amount, order.status, order.payment_status])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), as_attachment=True, download_name='orders.csv', mimetype='text/csv')

@app.route('/admin/categories')
@login_required
@admin_required
def admin_categories():
    categories = Category.query.all()
    return render_template('admin/categories.html', categories=categories)

@app.route('/admin/category/create', methods=['POST'])
@login_required
@admin_required
def admin_category_create():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    
    if Category.query.filter_by(name=name).first():
        flash('❌ Category already exists.', 'danger')
        return redirect(url_for('admin_categories'))
    
    category = Category(name=name, description=description, is_active=True)
    db.session.add(category)
    db.session.commit()
    log_audit(current_user.id, 'CREATE_CATEGORY', f'Created category: {name}', request.remote_addr)
    flash('✅ Category created!', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/category/edit/<int:category_id>', methods=['POST'])
@login_required
@admin_required
def admin_category_edit(category_id):
    category = Category.query.get_or_404(category_id)
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    is_active = bool(request.form.get('is_active'))
    
    category.name = name
    category.description = description
    category.is_active = is_active
    db.session.commit()
    log_audit(current_user.id, 'EDIT_CATEGORY', f'Edited category: {name}', request.remote_addr)
    flash('✅ Category updated!', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/category/delete/<int:category_id>')
@login_required
@admin_required
def admin_category_delete(category_id):
    category = Category.query.get_or_404(category_id)
    if category.products.count() > 0:
        flash('❌ Cannot delete category with products. Move products first.', 'danger')
        return redirect(url_for('admin_categories'))
    
    name = category.name
    db.session.delete(category)
    db.session.commit()
    log_audit(current_user.id, 'DELETE_CATEGORY', f'Deleted category: {name}', request.remote_addr)
    flash('🗑️ Category deleted.', 'success')
    return redirect(url_for('admin_categories'))

@app.route('/admin/customers')
@login_required
@admin_required
def admin_customers():
    search = request.args.get('search')
    query = User.query.filter_by(is_admin=False)
    if search:
        query = query.filter(User.username.contains(search) | User.full_name.contains(search) | User.email.contains(search))
    customers = query.order_by(User.created_at.desc()).all()
    return render_template('admin/customers.html', customers=customers)

@app.route('/admin/customer/toggle/<int:customer_id>')
@login_required
@admin_required
def admin_customer_toggle(customer_id):
    customer = User.query.get_or_404(customer_id)
    if customer.is_admin:
        flash('⚠️ Cannot modify admin accounts here.', 'danger')
        return redirect(url_for('admin_customers'))
    
    customer.is_active = not customer.is_active
    db.session.commit()
    log_audit(current_user.id, 'TOGGLE_CUSTOMER', f"{'Activated' if customer.is_active else 'Deactivated'} customer: {customer.username}", request.remote_addr)
    flash(f'✅ Customer {"activated" if customer.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin_customers'))

@app.route('/admin/customer/delete/<int:customer_id>')
@login_required
@admin_required
def admin_customer_delete(customer_id):
    customer = User.query.get_or_404(customer_id)
    if customer.is_admin:
        flash('⚠️ Cannot delete admin accounts here.', 'danger')
        return redirect(url_for('admin_customers'))
    
    if customer.orders.count() > 0:
        flash('❌ Cannot delete customer with orders.', 'danger')
        return redirect(url_for('admin_customers'))
    
    username = customer.username
    db.session.delete(customer)
    db.session.commit()
    log_audit(current_user.id, 'DELETE_CUSTOMER', f'Deleted customer: {username}', request.remote_addr)
    flash('🗑️ Customer deleted.', 'success')
    return redirect(url_for('admin_customers'))

@app.route('/admin/admins')
@login_required
@super_admin_required
def admin_admins():
    admins = User.query.filter_by(is_admin=True).all()
    return render_template('admin/admins.html', admins=admins)

@app.route('/admin/admin/create', methods=['GET', 'POST'])
@login_required
@super_admin_required
def admin_admin_create():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        is_super_admin = bool(request.form.get('is_super_admin'))
        
        if User.query.filter_by(username=username).first():
            flash('❌ Username already exists.', 'danger')
            return render_template('admin/admin_form.html')
        
        valid, msg = validate_password(password)
        if not valid:
            flash(f'❌ {msg}', 'danger')
            return render_template('admin/admin_form.html')
        
        admin = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            full_name=full_name,
            phone=phone,
            is_admin=True,
            is_super_admin=is_super_admin,
            is_active=True
        )
        
        db.session.add(admin)
        db.session.commit()
        log_audit(current_user.id, 'CREATE_ADMIN', f'Created admin: {username}', request.remote_addr)
        flash('✅ Admin created successfully!', 'success')
        return redirect(url_for('admin_admins'))
    
    return render_template('admin/admin_form.html')

@app.route('/admin/admin/edit/<int:admin_id>', methods=['GET', 'POST'])
@login_required
@super_admin_required
def admin_admin_edit(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.id == current_user.id:
        flash('⚠️ Cannot edit your own account here.', 'danger')
        return redirect(url_for('admin_admins'))
    
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        phone = request.form.get('phone', '').strip()
        is_super_admin = bool(request.form.get('is_super_admin'))
        password = request.form.get('password', '')
        
        admin.full_name = full_name
        admin.phone = phone
        admin.is_super_admin = is_super_admin
        
        if password:
            valid, msg = validate_password(password)
            if valid:
                admin.password_hash = generate_password_hash(password)
            else:
                flash(f'❌ {msg}', 'danger')
                return render_template('admin/admin_edit.html', admin=admin)
        
        db.session.commit()
        log_audit(current_user.id, 'EDIT_ADMIN', f'Edited admin: {admin.username}', request.remote_addr)
        flash('✅ Admin updated!', 'success')
        return redirect(url_for('admin_admins'))
    
    return render_template('admin/admin_edit.html', admin=admin)

@app.route('/admin/admin/toggle/<int:admin_id>')
@login_required
@super_admin_required
def admin_admin_toggle(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.id == current_user.id:
        flash('⚠️ Cannot modify your own account.', 'danger')
        return redirect(url_for('admin_admins'))
    
    admin.is_active = not admin.is_active
    db.session.commit()
    log_audit(current_user.id, 'TOGGLE_ADMIN', f"{'Activated' if admin.is_active else 'Deactivated'} admin: {admin.username}", request.remote_addr)
    flash(f'✅ Admin {"activated" if admin.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin_admins'))

@app.route('/admin/admin/delete/<int:admin_id>')
@login_required
@super_admin_required
def admin_admin_delete(admin_id):
    admin = User.query.get_or_404(admin_id)
    if admin.id == current_user.id:
        flash('⚠️ Cannot delete your own account.', 'danger')
        return redirect(url_for('admin_admins'))
    
    if admin.is_super_admin and User.query.filter_by(is_super_admin=True).count() <= 1:
        flash('⚠️ Cannot delete the last super admin.', 'danger')
        return redirect(url_for('admin_admins'))
    
    username = admin.username
    db.session.delete(admin)
    db.session.commit()
    log_audit(current_user.id, 'DELETE_ADMIN', f'Deleted admin: {username}', request.remote_addr)
    flash('🗑️ Admin deleted.', 'success')
    return redirect(url_for('admin_admins'))

@app.route('/admin/audit-logs')
@login_required
@super_admin_required
def admin_audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
    return render_template('admin/audit_logs.html', logs=logs)

@app.route('/admin/shipping')
@login_required
@admin_required
def admin_shipping():
    methods = ShippingMethod.query.all()
    return render_template('admin/shipping.html', methods=methods)

@app.route('/admin/shipping/create', methods=['POST'])
@login_required
@admin_required
def admin_shipping_create():
    name = request.form.get('name', '').strip()
    description = request.form.get('description', '').strip()
    cost = float(request.form.get('cost', 0))
    estimated_days = int(request.form.get('estimated_days', 0))
    
    method = ShippingMethod(
        name=name,
        description=description,
        cost=cost,
        estimated_days=estimated_days,
        is_active=True
    )
    db.session.add(method)
    db.session.commit()
    flash('✅ Shipping method created!', 'success')
    return redirect(url_for('admin_shipping'))

@app.route('/admin/shipping/toggle/<int:method_id>')
@login_required
@admin_required
def admin_shipping_toggle(method_id):
    method = ShippingMethod.query.get_or_404(method_id)
    method.is_active = not method.is_active
    db.session.commit()
    flash(f'✅ Shipping method {"activated" if method.is_active else "deactivated"}.', 'success')
    return redirect(url_for('admin_shipping'))

@app.route('/admin/shipping/delete/<int:method_id>')
@login_required
@admin_required
def admin_shipping_delete(method_id):
    method = ShippingMethod.query.get_or_404(method_id)
    db.session.delete(method)
    db.session.commit()
    flash('🗑️ Shipping method deleted.', 'success')
    return redirect(url_for('admin_shipping'))

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html'), 403

@app.errorhandler(429)
def ratelimit_error(error):
    return render_template('429.html'), 429

# ==================== INITIALIZE DATABASE ====================

def init_db():
    with app.app_context():
        try:
            db.create_all()
            print("✅ Database tables created")
            
            categories = ['Electronics', 'Clothing', 'Food', 'Home & Living', 
                         'Beauty', 'Books', 'Sports', 'Toys', 'Auto', 'Phones']
            for cat_name in categories:
                if not Category.query.filter_by(name=cat_name).first():
                    category = Category(name=cat_name, is_active=True)
                    db.session.add(category)
                    print(f"Added category: {cat_name}")
            
            shipping_methods = [
                {'name': 'Standard Delivery', 'cost': 0, 'days': 3},
                {'name': 'Express Delivery', 'cost': 2000, 'days': 1},
                {'name': 'Same Day Delivery', 'cost': 5000, 'days': 0}
            ]
            for method in shipping_methods:
                if not ShippingMethod.query.filter_by(name=method['name']).first():
                    shipping = ShippingMethod(
                        name=method['name'],
                        cost=method['cost'],
                        estimated_days=method['days'],
                        is_active=True
                    )
                    db.session.add(shipping)
                    print(f"Added shipping method: {method['name']}")
            
            if not User.query.filter_by(username='MCM').first():
                admin = User(
                    username='MCM',
                    email='mcm@mugistore.com',
                    password_hash=generate_password_hash('08800Mcm!'),
                    full_name='Master Administrator',
                    is_admin=True,
                    is_super_admin=True,
                    is_active=True,
                    phone='+25770000000'
                )
                db.session.add(admin)
                print("✅ Super Admin created: MCM / 08800Mcm!")
            
            db.session.commit()
            print("=" * 50)
            print("✅ MugiStore Database Initialized!")
            print("=" * 50)
            print("🔐 Super Admin: MCM")
            print("🔑 Password: 08800Mcm!")
            print("=" * 50)
            print("📦 Categories and Shipping methods created.")
            print("=" * 50)
        except Exception as e:
            print(f"❌ Database initialization error: {str(e)}")
            db.session.rollback()
            raise

# ==================== RUN APPLICATION ====================

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
