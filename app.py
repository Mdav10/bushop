from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import re
import secrets
from functools import wraps
from sqlalchemy import text
import logging
import sys

print(f"Python version: {sys.version}")

app = Flask(__name__)

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(64))
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_SECURE'] = True
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=7)

database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///mugistore.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 5,
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

# ==================== MODELS ====================

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    last_ip = db.Column(db.String(45))
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    orders = db.relationship('Order', backref='customer', lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy=True)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200))
    products = db.relationship('Product', backref='category', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(200))
    whatsapp_link = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_status = db.Column(db.String(20), default='pending')
    payment_proof = db.Column(db.String(200))
    delivery_address = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

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

def notify_user(user_id, title, message, type='info'):
    try:
        notification = Notification(user_id=user_id, title=title, message=message, type=type)
        db.session.add(notification)
        db.session.commit()
    except Exception as e:
        logger.error(f"Notification error: {str(e)}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# ==================== PUBLIC ROUTES ====================

@app.route('/')
def index():
    products = Product.query.filter_by(is_active=True).limit(12).all()
    categories = Category.query.all()
    return render_template('index.html', products=products, categories=categories)

@app.route('/products')
def products():
    page = request.args.get('page', 1, type=int)
    category = request.args.get('category')
    search = request.args.get('search')
    
    query = Product.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category_id=category)
    if search:
        query = query.filter(Product.name.contains(search))
    
    products = query.paginate(page=page, per_page=24)
    categories = Category.query.all()
    return render_template('products.html', products=products, categories=categories)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

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
            flash('❌ Account is deactivated.', 'danger')
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
    
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(10).all()
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
    cart_count = sum(session.get('cart', {}).values())
    
    return render_template('customer/dashboard.html', 
                         orders=orders, 
                         notifications=notifications,
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

@app.route('/customer/notifications')
@login_required
def customer_notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    for n in notifications:
        n.is_read = True
    db.session.commit()
    return render_template('customer/notifications.html', notifications=notifications)

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

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if request.method == 'POST':
        cart = session.get('cart', {})
        if not cart:
            flash('🛒 Your cart is empty.', 'warning')
            return redirect(url_for('products'))
        
        order = Order(
            order_number=f"ORD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{current_user.id}",
            user_id=current_user.id,
            total_amount=0,
            delivery_address=request.form.get('delivery_address', '').strip(),
            notes=request.form.get('notes', '').strip(),
            status='pending',
            payment_status='pending'
        )
        
        total = 0
        for product_id, quantity in cart.items():
            product = Product.query.get(int(product_id))
            if product and product.is_active:
                subtotal = product.price * quantity
                item = OrderItem(
                    product_id=product.id,
                    quantity=quantity,
                    price=product.price,
                    subtotal=subtotal
                )
                db.session.add(item)
                total += subtotal
        
        order.total_amount = total
        db.session.add(order)
        db.session.commit()
        
        session.pop('cart', None)
        
        flash(f'✅ Order #{order.order_number} created! Please upload payment proof.', 'success')
        return redirect(url_for('customer_order', order_id=order.id))
    
    cart = session.get('cart', {})
    products = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product:
            subtotal = product.price * quantity
            total += subtotal
            products.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    
    return render_template('checkout.html', products=products, total=total)

# ==================== API ROUTES ====================

@app.route('/api/cart/add', methods=['POST'])
@login_required
def api_cart_add():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + quantity
    session['cart'] = cart
    
    return jsonify({'success': True, 'message': 'Added to cart!'})

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

@app.route('/health')
def health():
    try:
        db.session.execute(text('SELECT 1'))
        return jsonify({'status': 'healthy', 'database': 'connected'})
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

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
    
    return render_template('admin/dashboard.html',
                         total_customers=total_customers,
                         total_orders=total_orders,
                         total_revenue=total_revenue,
                         pending_payments=pending_payments,
                         pending_orders=pending_orders,
                         recent_orders=recent_orders,
                         total_products=total_products,
                         out_of_stock=out_of_stock)

@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    products = Product.query.all()
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
            stock = int(request.form.get('stock', 0))
            category_id = request.form.get('category_id')
            whatsapp_link = request.form.get('whatsapp_link', '').strip()
            
            product = Product(
                name=name,
                description=description,
                price=price,
                stock=stock,
                category_id=category_id if category_id else None,
                whatsapp_link=whatsapp_link,
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
            flash(f'❌ Error creating product: {str(e)}', 'danger')
    
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
            product.stock = int(request.form.get('stock', 0))
            product.category_id = request.form.get('category_id')
            product.whatsapp_link = request.form.get('whatsapp_link', '').strip()
            product.is_active = bool(request.form.get('is_active'))
            
            if 'image' in request.files:
                file = request.files['image']
                if file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    filepath = os.path.join('static/uploads/products', filename)
                    file.save(filepath)
                    product.image = filepath
            
            db.session.commit()
            log_audit(current_user.id, 'EDIT_PRODUCT', f'Edited product: {product.name}', request.remote_addr)
            flash('✅ Product updated successfully!', 'success')
            return redirect(url_for('admin_products'))
        except Exception as e:
            flash(f'❌ Error updating product: {str(e)}', 'danger')
    
    categories = Category.query.all()
    return render_template('admin/product_form.html', product=product, categories=categories)

@app.route('/admin/product/delete/<int:product_id>')
@login_required
@admin_required
def admin_product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    db.session.delete(product)
    db.session.commit()
    log_audit(current_user.id, 'DELETE_PRODUCT', f'Deleted product: {name}', request.remote_addr)
    flash('🗑️ Product deleted.', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@login_required
@admin_required
def admin_orders():
    status = request.args.get('status', 'all')
    query = Order.query
    if status != 'all':
        query = query.filter_by(status=status)
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
    
    if action == 'approve':
        order.status = 'processing'
        order.payment_status = 'approved'
        notify_user(order.user_id, '✅ Payment Approved', f'Your payment for order #{order.order_number} has been approved.')
        log_audit(current_user.id, 'APPROVE_PAYMENT', f'Approved payment for order {order.order_number}', request.remote_addr)
    
    elif action == 'reject':
        order.status = 'cancelled'
        order.payment_status = 'rejected'
        notify_user(order.user_id, '❌ Payment Rejected', f'Order #{order.order_number} rejected: {reason or "Payment verification failed"}')
        log_audit(current_user.id, 'REJECT_PAYMENT', f'Rejected payment for order {order.order_number}', request.remote_addr)
    
    elif action == 'complete':
        order.status = 'completed'
        notify_user(order.user_id, '🎉 Order Completed', f'Your order #{order.order_number} has been completed.')
        log_audit(current_user.id, 'COMPLETE_ORDER', f'Completed order {order.order_number}', request.remote_addr)
    
    elif action == 'cancel':
        order.status = 'cancelled'
        notify_user(order.user_id, '⚠️ Order Cancelled', f'Order #{order.order_number} has been cancelled.')
        log_audit(current_user.id, 'CANCEL_ORDER', f'Cancelled order {order.order_number}', request.remote_addr)
    
    db.session.commit()
    flash(f'✅ Order updated to {order.status}.', 'success')
    return redirect(url_for('admin_order', order_id=order_id))

@app.route('/admin/customers')
@login_required
@admin_required
def admin_customers():
    customers = User.query.filter_by(is_admin=False).all()
    return render_template('admin/customers.html', customers=customers)

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
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('admin/audit_logs.html', logs=logs)

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
                    category = Category(name=cat_name)
                    db.session.add(category)
                    print(f"Added category: {cat_name}")
            
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
        except Exception as e:
            print(f"❌ Database initialization error: {str(e)}")
            db.session.rollback()
            raise

# ==================== RUN APPLICATION ====================

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
