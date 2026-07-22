from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session
from flask_login import login_required, current_user
from app.models import Product, Order, OrderItem, Notification, PaymentRecord
from app import db
from datetime import datetime
import os
from werkzeug.utils import secure_filename

bp = Blueprint('customer', __name__)

@bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(10).all()
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).all()
    
    return render_template('customer/dashboard.html', 
                         orders=orders, 
                         notifications=notifications)

@bp.route('/orders')
@login_required
def orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('customer/orders.html', orders=orders)

@bp.route('/orders/create', methods=['GET', 'POST'])
@login_required
def create_order():
    if request.method == 'POST':
        cart = session.get('cart', {})
        if not cart:
            flash('Your cart is empty.', 'warning')
            return redirect(url_for('main.products'))
        
        order = Order(
            order_number=f"ORD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{current_user.id}",
            user_id=current_user.id,
            total_amount=0,
            delivery_address=request.form.get('delivery_address'),
            notes=request.form.get('notes'),
            status='pending',
            payment_status='pending'
        )
        
        total = 0
        for product_id, quantity in cart.items():
            product = Product.query.get(int(product_id))
            if product and product.is_active:
                subtotal = product.price * quantity
                item = OrderItem(
                    product_id=product.id,
                    quantity=quantity,
                    price=product.price,
                    subtotal=subtotal
                )
                order.items.append(item)
                total += subtotal
        
        order.total_amount = total
        db.session.add(order)
        db.session.commit()
        
        session.pop('cart', None)
        
        flash(f'Order #{order.order_number} created! Please make payment.', 'success')
        return redirect(url_for('customer.payment', order_id=order.id))
    
    cart = session.get('cart', {})
    products = []
    total = 0
    for product_id, quantity in cart.items():
        product = Product.query.get(int(product_id))
        if product:
            subtotal = product.price * quantity
            total += subtotal
            products.append({'product': product, 'quantity': quantity, 'subtotal': subtotal})
    
    return render_template('customer/checkout.html', products=products, total=total)

@bp.route('/orders/<int:order_id>')
@login_required
def view_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id and not current_user.is_admin:
        flash('Access denied.', 'danger')
        return redirect(url_for('customer.dashboard'))
    return render_template('customer/order_detail.html', order=order)

@bp.route('/orders/cancel/<int:order_id>')
@login_required
def cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('customer.dashboard'))
    
    if order.status in ['pending']:
        order.status = 'cancelled'
        db.session.commit()
        flash('Order cancelled.', 'success')
    else:
        flash('Cannot cancel this order.', 'danger')
    
    return redirect(url_for('customer.view_order', order_id=order_id))

@bp.route('/payment/<int:order_id>', methods=['GET', 'POST'])
@login_required
def payment(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('customer.dashboard'))
    
    if request.method == 'POST':
        if 'payment_proof' in request.files:
            file = request.files['payment_proof']
            if file.filename:
                filename = secure_filename(f"{order.order_number}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.jpg")
                filepath = os.path.join('static/uploads/payments', filename)
                file.save(os.path.join('app', filepath))
                order.payment_proof = filepath
                order.payment_status = 'pending'
                order.notes = request.form.get('notes', '')
                
                payment = PaymentRecord(
                    order_id=order.id,
                    amount=order.total_amount,
                    method='lumicash',
                    status='pending',
                    proof_image=filepath,
                    notes=request.form.get('notes', '')
                )
                db.session.add(payment)
                db.session.commit()
                
                flash('Payment proof uploaded. Waiting for verification.', 'success')
                return redirect(url_for('customer.dashboard'))
        
        flash('Please upload payment proof.', 'warning')
    
    return render_template('customer/payment.html', order=order)

@bp.route('/notifications')
@login_required
def notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).all()
    for n in notifications:
        n.is_read = True
    db.session.commit()
    return render_template('customer/notifications.html', notifications=notifications)

@bp.route('/api/add-to-cart', methods=['POST'])
@login_required
def add_to_cart():
    product_id = request.form.get('product_id')
    quantity = int(request.form.get('quantity', 1))
    
    cart = session.get('cart', {})
    cart[str(product_id)] = cart.get(str(product_id), 0) + quantity
    session['cart'] = cart
    
    return jsonify({'success': True, 'cart': cart})

@bp.route('/api/remove-from-cart', methods=['POST'])
@login_required
def remove_from_cart():
    product_id = request.form.get('product_id')
    cart = session.get('cart', {})
    
    if str(product_id) in cart:
        del cart[str(product_id)]
        session['cart'] = cart
    
    return jsonify({'success': True, 'cart': cart})

@bp.route('/api/get-cart')
@login_required
def get_cart():
    cart = session.get('cart', {})
    return jsonify(cart)
