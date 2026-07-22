#!/bin/bash
set -e

echo "🚀 Starting build process for BuShop..."

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Initialize database
echo "🗄️  Initializing database..."
python -c "
import os
import sys
from app import create_app, db
from app.models import User, Product, Category, Order, OrderItem, Notification, PaymentRecord, AuditLog, LoginAttempt
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    print('Creating database tables...')
    db.create_all()
    print('✅ Tables created successfully')
    
    # Create default categories
    categories = ['Electronics', 'Clothing', 'Food', 'Home & Living', 'Beauty', 'Books', 'Sports', 'Toys', 'Auto', 'Phones']
    for cat_name in categories:
        if not Category.query.filter_by(name=cat_name).first():
            category = Category(name=cat_name)
            db.session.add(category)
            print(f'Added category: {cat_name}')
    
    # Create super admin
    if not User.query.filter_by(username='MCM').first():
        admin = User(
            username='MCM',
            email='mcm@bushop.com',
            password_hash=generate_password_hash('08800Mcm!'),
            full_name='Master Administrator',
            is_admin=True,
            is_super_admin=True,
            is_active=True,
            phone='+25770000000'
        )
        db.session.add(admin)
        print('✅ Super Admin created: MCM / 08800Mcm!')
    
    # Create demo products
    if Product.query.count() == 0:
        electronics = Category.query.filter_by(name='Electronics').first()
        if electronics:
            products = [
                Product(
                    name='Smartphone X1 Pro',
                    description='Latest flagship smartphone with 108MP camera and 5000mAh battery',
                    price=350000,
                    stock=15,
                    category_id=electronics.id,
                    is_active=True,
                    whatsapp_link='https://wa.me/25770000000'
                ),
                Product(
                    name='Laptop Ultra 15"',
                    description='High-performance laptop with 16GB RAM and 512GB SSD',
                    price=850000,
                    stock=8,
                    category_id=electronics.id,
                    is_active=True,
                    whatsapp_link='https://wa.me/25770000000'
                ),
                Product(
                    name='Wireless Headphones Pro',
                    description='Premium noise-cancelling wireless headphones with 30hr battery',
                    price=120000,
                    stock=20,
                    category_id=electronics.id,
                    is_active=True,
                    whatsapp_link='https://wa.me/25770000000'
                )
            ]
            
            for product in products:
                db.session.add(product)
                print(f'Added demo product: {product.name}')
    
    db.session.commit()
    print('✅ Database initialization complete!')
"

echo "✅ Build completed successfully!"
