from app import create_app, db
from app.models import User, Product, Category, Order, OrderItem, Notification, PaymentRecord, AuditLog, LoginAttempt
from werkzeug.security import generate_password_hash
import os
import secrets

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

def init_db():
    """Initialize the database with default admin user"""
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Create default categories
        categories = [
            'Electronics', 'Clothing', 'Food', 'Home & Living',
            'Beauty', 'Books', 'Sports', 'Toys', 'Auto', 'Phones'
        ]
        
        for cat_name in categories:
            if not Category.query.filter_by(name=cat_name).first():
                category = Category(name=cat_name)
                db.session.add(category)
        
        # Create super admin (MCM)
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
            print("✅ Super Admin created: MCM / 08800Mcm!")
        
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
        
        db.session.commit()
        print("✅ Database initialized successfully!")
        print("✅ Super Admin: MCM")
        print("✅ Password: 08800Mcm!")

if __name__ == '__main__':
    # Initialize database
    with app.app_context():
        db.create_all()
        init_db()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
