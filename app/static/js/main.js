document.addEventListener('DOMContentLoaded', function() {
    updateCartCount();
    
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            const closeBtn = alert.querySelector('.btn-close');
            if (closeBtn) {
                closeBtn.click();
            }
        });
    }, 5000);
});

function updateCartCount() {
    fetch('/customer/api/get-cart')
        .then(response => response.json())
        .then(data => {
            const count = Object.values(data).reduce((a, b) => a + b, 0);
            const badge = document.getElementById('cart-count');
            if (badge) {
                badge.textContent = count;
                badge.style.display = count > 0 ? 'inline' : 'none';
            }
        })
        .catch(error => console.log('Error fetching cart:', error));
}

function addToCart(productId, quantity = 1) {
    fetch('/customer/api/add-to-cart', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `product_id=${productId}&quantity=${quantity}`
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateCartCount();
            showToast('Product added to cart!');
        }
    })
    .catch(error => console.log('Error adding to cart:', error));
}

function removeFromCart(productId) {
    fetch('/customer/api/remove-from-cart', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: `product_id=${productId}`
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            updateCartCount();
            location.reload();
        }
    })
    .catch(error => console.log('Error removing from cart:', error));
}

function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'alert alert-success alert-dismissible fade show position-fixed bottom-0 end-0 m-3';
    toast.style.zIndex = '9999';
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function previewPaymentProof(input) {
    if (input.files && input.files[0]) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const preview = document.getElementById('payment-proof-preview');
            if (preview) {
                preview.src = e.target.result;
                preview.style.display = 'block';
            }
        };
        reader.readAsDataURL(input.files[0]);
    }
}

function confirmAction(message) {
    return confirm(message || 'Are you sure?');
}

function searchProducts() {
    const query = document.getElementById('search-input').value;
    if (query.length > 0) {
        window.location.href = `/products?search=${encodeURIComponent(query)}`;
    }
}

function filterProducts(categoryId) {
    window.location.href = `/products?category=${categoryId}`;
}
