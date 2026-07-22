#!/usr/bin/env python
"""
One-time database reset script - runs during deployment
"""
import os
import sys
from app import create_app, db
from app.models import User, Product, Category, Order, OrderItem, Notification, PaymentRecord, AuditLog, LoginAttempt
from werkzeug.security import generate_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def reset_database():
    """Drop all tables and recreate with correct schema"""
    app = create_app()
    
    with app.app_context():
        try:
            logger.info("🔄 Starting database reset...")
            
            # Drop all tables
            logger.info("Dropping all tables...")
            db.drop_all()
            logger.info("✅ All tables dropped")
            
            # Create fresh tables
            logger.info("Creating fresh tables with correct schema...")
            db.create_all()
            logger.info("✅ Tables created with correct schema")
            
            # Create default categories
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
                            description='Latest flagship smartphone with 108MP camera',
                            price=350000,
                            stock=15,
                            category_id=electronics.id,
                            is_active=True,
                            whatsapp_link='https://wa.me/25770000000'
                        ),
                        Product(
                            name='Laptop Ultra 15"',
                            description='High-performance laptop with 16GB RAM',
                            price=850000,
                            stock=8,
                            category_id=electronics.id,
                            is_active=True,
                            whatsapp_link='https://wa.me/25770000000'
                        ),
                        Product(
                            name='Wireless Headphones Pro',
                            description='Premium noise-cancelling headphones',
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
            logger.info("✅ Database reset complete!")
            logger.info("✅ Super Admin: MCM")
            logger.info("✅ Password: 08800Mcm!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Database reset failed: {str(e)}")
            db.session.rollback()
            return False

if __name__ == '__main__':
    success = reset_database()
    sys.exit(0 if success else 1)
