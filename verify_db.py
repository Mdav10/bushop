#!/usr/bin/env python
import os
import sys
from app import create_app, db
from app.models import User, Product, Category

def verify_database():
    """Verify database connection and tables"""
    app = create_app()
    
    with app.app_context():
        try:
            # Check database connection
            db.session.execute('SELECT 1')
            print("✅ Database connection successful")
            
            # Check if tables exist
            tables = ['users', 'categories', 'products', 'orders', 'order_items', 'notifications', 'payment_records', 'login_attempts', 'audit_logs']
            existing_tables = db.session.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
            existing_table_names = [t[0] for t in existing_tables]
            
            for table in tables:
                if table in existing_table_names:
                    print(f"✅ Table '{table}' exists")
                else:
                    print(f"❌ Table '{table}' missing")
            
            # Check if admin exists
            admin = User.query.filter_by(username='MCM').first()
            if admin:
                print("✅ Admin user exists: MCM")
            else:
                print("❌ Admin user missing")
            
            # Check if products exist
            product_count = Product.query.count()
            print(f"✅ {product_count} products in database")
            
            return True
            
        except Exception as e:
            print(f"❌ Database verification failed: {str(e)}")
            return False

if __name__ == '__main__':
    success = verify_database()
    sys.exit(0 if success else 1)
