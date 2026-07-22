#!/usr/bin/env python
import os
import sys
import time
from app import create_app, db
from app.models import User, Product, Category, Order, OrderItem, Notification, PaymentRecord, AuditLog, LoginAttempt
from werkzeug.security import generate_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_database():
    """Initialize database with tables and demo data"""
    app = create_app()
    
    try:
        with app.app_context():
            logger.info("Creating database tables...")
            db.create_all()
            logger.info("✅ Tables created successfully")
            
            # Create categories
            categories = [
                'Electronics', 'Clothing', 'Food', 'Home & Living',
                'Beauty', 'Books', 'Sports', 'Toys', 'Auto', 'Phones'
            ]
            
            for cat_name in categories:
                if not Category.query.filter_by(name=cat_name).first():
                    category = Category(name=cat_name)
                    db.session.add(category)
                    logger.info(f"Added category: {cat_name}")
            
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
                logger.info("✅ Super Admin created: MCM / 08800Mcm!")
            
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
                        logger.info(f"Added demo product: {product.name}")
            
            db.session.commit()
            logger.info("✅ Database initialization complete!")
            logger.info("✅ Super Admin: MCM")
            logger.info("✅ Password: 08800Mcm!")
            return True
            
    except Exception as e:
        logger.error(f"❌ Database initialization error: {str(e)}")
        db.session.rollback()
        return False

if __name__ == '__main__':
    # Try multiple times
    max_retries = 3
    for attempt in range(max_retries):
        logger.info(f"Attempt {attempt + 1}/{max_retries}...")
        if init_database():
            sys.exit(0)
        if attempt < max_retries - 1:
            logger.info("Waiting 5 seconds before retry...")
            time.sleep(5)
    
    logger.error("All initialization attempts failed!")
    sys.exit(1)
