from flask import Blueprint, render_template, request, jsonify, current_app
from app.models import Product, Category
from app import db
from sqlalchemy import or_
from datetime import datetime

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    try:
        products = Product.query.filter_by(is_active=True).limit(12).all()
        categories = Category.query.all()
        return render_template('index.html', products=products, categories=categories)
    except Exception as e:
        current_app.logger.error(f"Index error: {str(e)}")
        return render_template('index.html', products=[], categories=[])

@bp.route('/products')
def products():
    try:
        page = request.args.get('page', 1, type=int)
        category = request.args.get('category')
        search = request.args.get('search')
        
        query = Product.query.filter_by(is_active=True)
        
        if category:
            query = query.filter_by(category_id=category)
        if search:
            query = query.filter(or_(
                Product.name.ilike(f'%{search}%'),
                Product.description.ilike(f'%{search}%')
            ))
        
        products = query.paginate(page=page, per_page=24)
        categories = Category.query.all()
        
        return render_template('products.html', products=products, categories=categories)
    except Exception as e:
        current_app.logger.error(f"Products error: {str(e)}")
        return render_template('products.html', products=[], categories=[])

@bp.route('/product/<int:product_id>')
def product_detail(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        return render_template('product_detail.html', product=product)
    except Exception as e:
        current_app.logger.error(f"Product detail error: {str(e)}")
        return render_template('404.html'), 404

@bp.route('/about')
def about():
    return render_template('about.html')

@bp.route('/contact')
def contact():
    return render_template('contact.html')

@bp.route('/api/categories')
def get_categories():
    try:
        categories = Category.query.all()
        return jsonify([{'id': c.id, 'name': c.name} for c in categories])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/api/search')
def search_products():
    try:
        query = request.args.get('q', '')
        products = Product.query.filter(
            Product.name.ilike(f'%{query}%'),
            Product.is_active == True
        ).limit(10).all()
        return jsonify([{
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'image': p.image
        } for p in products])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/health')
def health_check():
    """Health check endpoint for Render"""
    try:
        # Check database connection
        db.session.execute('SELECT 1')
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500
