from app import create_app, db
from app.models import User, Product, Category, Order, OrderItem, Notification, PaymentRecord, AuditLog, LoginAttempt
from werkzeug.security import generate_password_hash
import os
import sys
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {
        'db': db,
        'User': User,
        'Product': Product,
        'Category': Category,
        'Order': Order,
        'OrderItem': OrderItem,
        'Notification': Notification,
        'PaymentRecord': PaymentRecord,
        'AuditLog': AuditLog,
        'LoginAttempt': LoginAttempt
    }

def ensure_database():
    """Ensure database tables exist on startup"""
    try:
        with app.app_context():
            # Check if we can query the users table
            try:
                User.query.first()
                logger.info("✅ Database tables already exist")
            except Exception as e:
                logger.info("Creating database tables...")
                db.create_all()
                logger.info("✅ Database tables created")
                
                # Initialize default data if needed
                init_default_data()
                
    except Exception as e:
        logger.error(f"Database check failed: {str(e)}")
        # Try to create tables anyway
        try:
            with app.app_context():
                db.create_all()
                logger.info("✅ Database tables created on retry")
        except Exception as e2:
            logger.error(f"Failed to create tables: {str(e2)}")

def init_default_data():
    """Initialize default data"""
    try:
        with app.app_context():
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
            logger.info("✅ Default data initialized")
            
    except Exception as e:
        logger.error(f"Error initializing default data: {str(e)}")
        db.session.rollback()

# Ensure database is ready on startup
ensure_database()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting BuShop on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
