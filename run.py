from app import create_app, db
from app.models import User, Product, Category
from werkzeug.security import generate_password_hash
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = create_app()

def init_db():
    """Initialize database if needed"""
    with app.app_context():
        try:
            # Check if users table exists
            db.session.execute('SELECT 1 FROM users LIMIT 1')
            logger.info("✅ Database already initialized")
        except Exception:
            logger.info("Creating database tables...")
            db.create_all()
            logger.info("✅ Database tables created")
            
            # Create default categories
            categories = ['Electronics', 'Clothing', 'Food', 'Home & Living', 
                         'Beauty', 'Books', 'Sports', 'Toys', 'Auto', 'Phones']
            for cat_name in categories:
                if not Category.query.filter_by(name=cat_name).first():
                    category = Category(name=cat_name)
                    db.session.add(category)
            
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
                logger.info("✅ Super Admin created")
            
            db.session.commit()
            logger.info("✅ Database initialized")

# Initialize on startup
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
