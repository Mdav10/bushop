from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session, abort, current_app
from flask_login import login_required, current_user
from app.models import Product, Category, Order, User, Notification, OrderItem, PaymentRecord, AuditLog
from app import db
from datetime import datetime, timedelta
from sqlalchemy import func, and_
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os
import re
import logging

bp = Blueprint('admin', __name__)

# Admin required decorator with enhanced security
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin:
            abort(403)
        
        # Check if admin is active
        if not current_user.is_active:
            flash('Your admin account is inactive.', 'danger')
            return redirect(url_for('auth.logout'))
        
        # Log admin access
        ip = request.remote_addr
        log_audit(current_user.id, 'ADMIN_ACCESS', f'Admin accessed {request.path}', ip)
        
        return f(*args, **kwargs)
    return decorated_function

# Super admin required for creating other admins
def super_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_super_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

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

@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    try:
        total_customers = User.query.filter_by(is_admin=False).count()
        total_orders = Order.query.count()
        total_revenue = db.session.query(func.sum(Order.total_amount)).filter_by(status='completed').scalar() or 0
        pending_payments = Order.query.filter_by(payment_status='pending').count()
        pending_orders = Order.query.filter_by(status='pending').count()
        
        # Admin statistics
        admin_count = User.query.filter_by(is_admin=True).count()
        super_admin_count = User.query.filter_by(is_super_admin=True).count()
        
        recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
        
        top_products = db.session.query(
            Product.id,
            Product.name,
            func.sum(OrderItem.quantity).label('total_sold')
        ).join(OrderItem).join(Order).filter(Order.status == 'completed').group_by(Product.id).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
        
        monthly_sales = db.session.query(
            func.to_char(Order.created_at, 'YYYY-MM').label('month'),
            func.sum(Order.total_amount).label('total')
        ).filter(Order.status == 'completed').group_by('month').order_by('month').limit(6).all()
        
        return render_template('admin/dashboard.html',
                             total_customers=total_customers,
                             total_orders=total_orders,
                             total_revenue=total_revenue,
                             pending_payments=pending_payments,
                             pending_orders=pending_orders,
                             recent_orders=recent_orders,
                             top_products=top_products,
                             monthly_sales=monthly_sales,
                             admin_count=admin_count,
                             super_admin_count=super_admin_count)
    except Exception as e:
        current_app.logger.error(f"Dashboard error: {str(e)}")
        flash('Error loading dashboard. Please try again.', 'danger')
        return render_template('admin/dashboard.html')

@bp.route('/admins')
@login_required
@admin_required
def manage_admins():
    # Only super admin can manage admins
    if not current_user.is_super_admin:
        abort(403)
    
    try:
        admins = User.query.filter_by(is_admin=True).all()
        return render_template('admin/manage_admins.html', admins=admins)
    except Exception as e:
        current_app.logger.error(f"Manage admins error: {str(e)}")
        flash('Error loading admin list.', 'danger')
        return redirect(url_for('admin.dashboard'))

@bp.route('/admins/create', methods=['GET', 'POST'])
@login_required
@super_admin_required
def create_admin():
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '')
            full_name = request.form.get('full_name', '').strip()
            phone = request.form.get('phone', '').strip()
            is_super_admin = bool(request.form.get('is_super_admin'))
            ip = request.remote_addr
            
            # Validate inputs
            if User.query.filter_by(username=username).first():
                flash('Username already exists.', 'danger')
                return render_template('admin/create_admin.html')
            
            if User.query.filter_by(email=email).first():
                flash('Email already registered.', 'danger')
                return render_template('admin/create_admin.html')
            
            valid, msg = validate_password(password)
            if not valid:
                flash(msg, 'danger')
                return render_template('admin/create_admin.html')
            
            # Create admin
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
            
            log_audit(current_user.id, 'CREATE_ADMIN', 
                     f'Created admin {username} with super_admin={is_super_admin}', ip)
            
            flash(f'Admin {username} created successfully!', 'success')
            return redirect(url_for('admin.manage_admins'))
        except Exception as e:
            current_app.logger.error(f"Create admin error: {str(e)}")
            flash('Error creating admin. Please try again.', 'danger')
    
    return render_template('admin/create_admin.html')

@bp.route('/admins/toggle/<int:admin_id>')
@login_required
@super_admin_required
def toggle_admin_status(admin_id):
    try:
        admin = User.query.get_or_404(admin_id)
        
        # Prevent deactivating self
        if admin.id == current_user.id:
            flash('You cannot deactivate your own account.', 'danger')
            return redirect(url_for('admin.manage_admins'))
        
        admin.is_active = not admin.is_active
        db.session.commit()
        
        ip = request.remote_addr
        log_audit(current_user.id, 'TOGGLE_ADMIN', 
                 f"{'Activated' if admin.is_active else 'Deactivated'} admin {admin.username}", ip)
        
        flash(f'Admin {admin.username} {"activated" if admin.is_active else "deactivated"}.', 'success')
    except Exception as e:
        current_app.logger.error(f"Toggle admin error: {str(e)}")
        flash('Error updating admin status.', 'danger')
    
    return redirect(url_for('admin.manage_admins'))

@bp.route('/admins/delete/<int:admin_id>')
@login_required
@super_admin_required
def delete_admin(admin_id):
    try:
        admin = User.query.get_or_404(admin_id)
        
        # Prevent deleting self
        if admin.id == current_user.id:
            flash('You cannot delete your own account.', 'danger')
            return redirect(url_for('admin.manage_admins'))
        
        # Prevent deleting last super admin
        if admin.is_super_admin:
            super_admins = User.query.filter_by(is_super_admin=True).count()
            if super_admins <= 1:
                flash('Cannot delete the last super admin.', 'danger')
                return redirect(url_for('admin.manage_admins'))
        
        username = admin.username
        ip = request.remote_addr
        log_audit(current_user.id, 'DELETE_ADMIN', f'Deleted admin {username}', ip)
        
        db.session.delete(admin)
        db.session.commit()
        
        flash(f'Admin {username} deleted.', 'success')
    except Exception as e:
        current_app.logger.error(f"Delete admin error: {str(e)}")
        flash('Error deleting admin.', 'danger')
    
    return redirect(url_for('admin.manage_admins'))

# Rest of admin routes remain the same...
# (Products, Orders, Payments, Customers management routes)

@bp.route('/products')
@login_required
@admin_required
def manage_products():
    try:
        products = Product.query.all()
        categories = Category.query.all()
        return render_template('admin/products.html', products=products, categories=categories)
    except Exception as e:
        current_app.logger.error(f"Manage products error: {str(e)}")
        flash('Error loading products.', 'danger')
        return redirect(url_for('admin.dashboard'))

@bp.route('/products/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_product():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            description = request.form.get('description', '').strip()
            price = float(request.form.get('price', 0))
            stock = int(request.form.get('stock', 0))
            category_id = request.form.get('category_id')
            whatsapp_link = request.form.get('whatsapp_link', '').strip()
            
            if not name:
                flash('Product name is required.', 'danger')
                return render_template('admin/product_form.html', categories=Category.query.all())
            
            product = Product(
                name=name,
                description=description,
                price=price,
                stock=stock,
                category_id=category_id,
                whatsapp_link=whatsapp_link,
                is_active=True
            )
            
            if 'image' in request.files:
                file = request.files['image']
                if file.filename:
                    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed:
                        filename = secure_filename(file.filename)
                        filepath = os.path.join('static/uploads/products', filename)
                        file.save(os.path.join('app', filepath))
                        product.image = filepath
                    else:
                        flash('Invalid file type. Allowed: PNG, JPG, JPEG, GIF, WEBP', 'warning')
            
            db.session.add(product)
            db.session.commit()
            
            ip = request.remote_addr
            log_audit(current_user.id, 'CREATE_PRODUCT', f'Created product {name}', ip)
            
            flash('Product created successfully.', 'success')
            return redirect(url_for('admin.manage_products'))
        except Exception as e:
            current_app.logger.error(f"Create product error: {str(e)}")
            flash('Error creating product.', 'danger')
    
    categories = Category.query.all()
    return render_template('admin/product_form.html', categories=categories)

@bp.route('/products/edit/<int:product_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_product(product_id):
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
                if file.filename:
                    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed:
                        filename = secure_filename(file.filename)
                        filepath = os.path.join('static/uploads/products', filename)
                        file.save(os.path.join('app', filepath))
                        if product.image:
                            old_path = os.path.join('app', product.image)
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        product.image = filepath
            
            db.session.commit()
            
            ip = request.remote_addr
            log_audit(current_user.id, 'EDIT_PRODUCT', f'Edited product {product.name}', ip)
            
            flash('Product updated successfully.', 'success')
            return redirect(url_for('admin.manage_products'))
        except Exception as e:
            current_app.logger.error(f"Edit product error: {str(e)}")
            flash('Error updating product.', 'danger')
    
    categories = Category.query.all()
    return render_template('admin/product_form.html', product=product, categories=categories)

@bp.route('/products/delete/<int:product_id>')
@login_required
@admin_required
def delete_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        name = product.name
        
        if product.image:
            path = os.path.join('app', product.image)
            if os.path.exists(path):
                os.remove(path)
        
        db.session.delete(product)
        db.session.commit()
        
        ip = request.remote_addr
        log_audit(current_user.id, 'DELETE_PRODUCT', f'Deleted product {name}', ip)
        
        flash('Product deleted.', 'success')
    except Exception as e:
        current_app.logger.error(f"Delete product error: {str(e)}")
        flash('Error deleting product.', 'danger')
    
    return redirect(url_for('admin.manage_products'))

@bp.route('/orders')
@login_required
@admin_required
def manage_orders():
    try:
        status = request.args.get('status', 'all')
        query = Order.query
        
        if status != 'all':
            query = query.filter_by(status=status)
        
        orders = query.order_by(Order.created_at.desc()).all()
        return render_template('admin/orders.html', orders=orders, current_status=status)
    except Exception as e:
        current_app.logger.error(f"Manage orders error: {str(e)}")
        flash('Error loading orders.', 'danger')
        return redirect(url_for('admin.dashboard'))

@bp.route('/orders/<int:order_id>')
@login_required
@admin_required
def view_order(order_id):
    try:
        order = Order.query.get_or_404(order_id)
        return render_template('admin/order_detail.html', order=order)
    except Exception as e:
        current_app.logger.error(f"View order error: {str(e)}")
        flash('Error loading order.', 'danger')
        return redirect(url_for('admin.manage_orders'))

@bp.route('/orders/update/<int:order_id>', methods=['POST'])
@login_required
@admin_required
def update_order(order_id):
    try:
        order = Order.query.get_or_404(order_id)
        action = request.form.get('action')
        ip = request.remote_addr
        
        if action == 'approve':
            order.status = 'processing'
            order.payment_status = 'approved'
            notify_user(order.user_id, 'Payment Approved', 
                       f'Your payment for order #{order.order_number} has been approved.',
                       'success')
            log_audit(current_user.id, 'APPROVE_PAYMENT', f'Approved payment for order {order.order_number}', ip)
        
        elif action == 'reject':
            order.status = 'cancelled'
            order.payment_status = 'rejected'
            reason = request.form.get('reason', 'Payment verification failed.')
            notify_user(order.user_id, 'Payment Rejected', 
                       f'Your payment for order #{order.order_number} was rejected. Reason: {reason}',
                       'error')
            log_audit(current_user.id, 'REJECT_PAYMENT', f'Rejected payment for order {order.order_number}', ip)
        
        elif action == 'complete':
            order.status = 'completed'
            notify_user(order.user_id, 'Order Completed', 
                       f'Your order #{order.order_number} has been completed.',
                       'success')
            log_audit(current_user.id, 'COMPLETE_ORDER', f'Completed order {order.order_number}', ip)
        
        elif action == 'cancel':
            order.status = 'cancelled'
            notify_user(order.user_id, 'Order Cancelled', 
                       f'Your order #{order.order_number} has been cancelled.',
                       'error')
            log_audit(current_user.id, 'CANCEL_ORDER', f'Cancelled order {order.order_number}', ip)
        
        db.session.commit()
        flash(f'Order updated to {order.status}.', 'success')
    except Exception as e:
        current_app.logger.error(f"Update order error: {str(e)}")
        flash('Error updating order.', 'danger')
    
    return redirect(url_for('admin.view_order', order_id=order_id))

@bp.route('/payments')
@login_required
@admin_required
def manage_payments():
    try:
        pending_payments = Order.query.filter_by(payment_status='pending').all()
        approved_payments = Order.query.filter_by(payment_status='approved').limit(20).all()
        return render_template('admin/payments.html', 
                             pending_payments=pending_payments,
                             approved_payments=approved_payments)
    except Exception as e:
        current_app.logger.error(f"Manage payments error: {str(e)}")
        flash('Error loading payments.', 'danger')
        return redirect(url_for('admin.dashboard'))

@bp.route('/customers')
@login_required
@admin_required
def manage_customers():
    try:
        customers = User.query.filter_by(is_admin=False).all()
        
        customer_data = []
        for customer in customers:
            customer_data.append({
                'user': customer,
                'total_spent': customer.get_total_spent(),
                'order_count': customer.get_order_count(),
                'last_order': customer.orders.order_by(Order.created_at.desc()).first(),
                'is_vip': customer.is_vip(),
                'is_loyal': customer.is_loyal()
            })
        
        return render_template('admin/customers.html', customers=customer_data)
    except Exception as e:
        current_app.logger.error(f"Manage customers error: {str(e)}")
        flash('Error loading customers.', 'danger')
        return redirect(url_for('admin.dashboard'))

@bp.route('/audit-logs')
@login_required
@admin_required
def audit_logs():
    try:
        logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(100).all()
        return render_template('admin/audit_logs.html', logs=logs)
    except Exception as e:
        current_app.logger.error(f"Audit logs error: {str(e)}")
        flash('Error loading audit logs.', 'danger')
        return redirect(url_for('admin.dashboard'))

def notify_user(user_id, title, message, type='info'):
    try:
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=type
        )
        db.session.add(notification)
        db.session.commit()
    except Exception as e:
        current_app.logger.error(f"Notify user error: {str(e)}")
