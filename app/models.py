from app import db
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import func, Index
import hashlib
import hmac
import secrets

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(200), nullable=False)
    password_salt = db.Column(db.String(64))
    full_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20))
    address = db.Column(db.String(200))
    is_admin = db.Column(db.Boolean, default=False)
    is_super_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    last_ip = db.Column(db.String(45))
    user_agent = db.Column(db.String(200))
    two_factor_secret = db.Column(db.String(32))
    two_factor_enabled = db.Column(db.Boolean, default=False)
    
    orders = db.relationship('Order', backref='customer', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_user_username_email', 'username', 'email'),
        Index('idx_user_active', 'is_active'),
    )
    
    def get_total_spent(self):
        return db.session.query(func.sum(Order.total_amount)).filter(
            Order.user_id == self.id,
            Order.status == 'completed'
        ).scalar() or 0
    
    def get_order_count(self):
        return self.orders.filter(Order.status == 'completed').count()
    
    def get_lifetime_value(self):
        return self.get_total_spent()
    
    def is_vip(self):
        return self.get_total_spent() > 500000
    
    def is_loyal(self):
        return self.get_order_count() >= 5
    
    def can_create_admin(self):
        return self.is_super_admin or (self.is_admin and self.is_super_admin)
    
    def __repr__(self):
        return f'<User {self.username}>'

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, index=True)
    description = db.Column(db.String(200))
    icon = db.Column(db.String(50))
    products = db.relationship('Product', backref='category', lazy='dynamic')
    
    def __repr__(self):
        return f'<Category {self.name}>'

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    image = db.Column(db.String(200))
    whatsapp_link = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    
    order_items = db.relationship('OrderItem', backref='product', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_product_name_active', 'name', 'is_active'),
        Index('idx_product_category_active', 'category_id', 'is_active'),
    )
    
    def __repr__(self):
        return f'<Product {self.name}>'

class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending', index=True)
    payment_status = db.Column(db.String(20), default='pending', index=True)
    payment_proof = db.Column(db.String(200))
    payment_notes = db.Column(db.Text)
    delivery_address = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    payments = db.relationship('PaymentRecord', backref='order', lazy='dynamic')
    
    __table_args__ = (
        Index('idx_order_user_status', 'user_id', 'status'),
        Index('idx_order_status_created', 'status', 'created_at'),
    )
    
    def calculate_total(self):
        return sum(item.quantity * item.price for item in self.items)

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    subtotal = db.Column(db.Float, nullable=False)

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='info')
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    link = db.Column(db.String(200))
    
    __table_args__ = (
        Index('idx_notification_user_read', 'user_id', 'is_read'),
    )

class PaymentRecord(db.Model):
    __tablename__ = 'payment_records'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20), default='lumicash')
    reference = db.Column(db.String(50))
    status = db.Column(db.String(20), default='pending', index=True)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    verified_at = db.Column(db.DateTime)
    proof_image = db.Column(db.String(200))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_payment_order_status', 'order_id', 'status'),
    )

class LoginAttempt(db.Model):
    __tablename__ = 'login_attempts'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), index=True)
    ip_address = db.Column(db.String(45), index=True)
    success = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_agent = db.Column(db.String(200))

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    user = db.relationship('User', backref='audit_logs')
