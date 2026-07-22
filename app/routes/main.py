from flask import Blueprint, render_template, request, jsonify
from app.models import Product, Category
from sqlalchemy import or_

bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    products = Product.query.filter_by(is_active=True).limit(12).all()
    categories = Category.query.all()
    return render_template('index.html', products=products, categories=categories)

@bp.route('/products')
def products():
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

@bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

@bp.route('/about')
def about():
    return render_template('about.html')

@bp.route('/contact')
def contact():
    return render_template('contact.html')

@bp.route('/api/categories')
def get_categories():
    categories = Category.query.all()
    return jsonify([{'id': c.id, 'name': c.name} for c in categories])

@bp.route('/api/search')
def search_products():
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
