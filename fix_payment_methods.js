// Run this in the browser console on the subscriptions page to fix payment method storage
// Open browser Developer Tools (F12) → Console tab → paste this code → press Enter

async function fixPaymentMethods() {
    try {
        console.log('🔧 Attempting to fix payment method storage...');
        
        const response = await fetch('/subscriptions/fix-customer-ids/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        });
        
        const result = await response.json();
        console.log('📊 Result:', result);
        
        if (result.status === 'already_fixed') {
            console.log('✅ Customer ID already exists:', result.customer_id);
        } else if (result.status === 'fixed_via_subscription') {
            console.log('✅ Fixed via subscription:', result.customer_id);
        } else if (result.status === 'fixed_via_email') {
            console.log('✅ Fixed via email search:', result.customer_id);
            console.log('💳 Payment methods found:', result.payment_methods_count);
        } else if (result.status === 'not_found') {
            console.log('❌ No Stripe customer found for your email');
        } else if (result.status === 'error') {
            console.log('❌ Error:', result.message);
        }
        
        // Reload payment methods
        console.log('🔄 Refreshing payment methods...');
        if (typeof loadPaymentMethods === 'function') {
            loadPaymentMethods();
        } else {
            console.log('⚠️ Refresh the page to see updated payment methods');
        }
        
    } catch (error) {
        console.error('❌ Failed to fix payment methods:', error);
    }
}

// Run the fix
fixPaymentMethods();