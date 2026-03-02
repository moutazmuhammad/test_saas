/** @odoo-module **/

(function () {
    'use strict';

    // State
    let currentPeriod = 'monthly';
    let currentUserCount = 1;
    let currentCouponCode = '';
    let couponValid = false;
    let debounceTimer = null;

    // DOM references (set on DOMContentLoaded)
    let billingToggle, userCountSlider, userCountDisplay;
    let couponInput, applyCouponBtn, couponFeedback;
    let priceSummary, summarySubtotal, summaryDiscount, summaryTotal;
    let planCards;

    function init() {
        billingToggle = document.getElementById('billingToggle');
        userCountSlider = document.getElementById('userCountSlider');
        userCountDisplay = document.getElementById('userCountDisplay');
        couponInput = document.getElementById('couponCodeInput');
        applyCouponBtn = document.getElementById('applyCouponBtn');
        couponFeedback = document.getElementById('couponFeedback');
        priceSummary = document.getElementById('priceSummary');
        summarySubtotal = document.getElementById('summarySubtotal');
        summaryDiscount = document.getElementById('summaryDiscount');
        summaryTotal = document.getElementById('summaryTotal');
        planCards = document.querySelectorAll('.saas-plan-card');

        if (!billingToggle || !planCards.length) {
            return; // Not on pricing page
        }

        setupBillingToggle();
        setupUserSlider();
        setupCouponHandler();
        updatePricesLocal(); // Initial local price display
    }

    // ----------------------------------------------------------------
    // Billing period toggle
    // ----------------------------------------------------------------
    function setupBillingToggle() {
        const buttons = billingToggle.querySelectorAll('button');
        buttons.forEach(function (btn) {
            btn.addEventListener('click', function () {
                buttons.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                currentPeriod = btn.dataset.period;
                updatePricesLocal();
                updateSubscribeLinks();
                if (couponValid) {
                    recalculateDebounced();
                }
            });
        });
    }

    // ----------------------------------------------------------------
    // User count slider
    // ----------------------------------------------------------------
    function setupUserSlider() {
        userCountSlider.addEventListener('input', function () {
            currentUserCount = parseInt(this.value, 10);
            userCountDisplay.textContent = currentUserCount;
            updatePricesLocal();
            updateSubscribeLinks();
            if (couponValid) {
                recalculateDebounced();
            }
        });
    }

    // ----------------------------------------------------------------
    // Update prices locally (no server call needed when no coupon)
    // ----------------------------------------------------------------
    function updatePricesLocal() {
        planCards.forEach(function (card) {
            var planId = card.dataset.planId;
            var monthlyPrice = parseFloat(card.dataset.monthlyPrice);
            var yearlyPrice = parseFloat(card.dataset.yearlyPrice);

            var unitPrice = currentPeriod === 'yearly' ? yearlyPrice : monthlyPrice;
            var total = unitPrice * currentUserCount;

            // Update price display
            var priceEl = card.querySelector('.plan-price[data-plan-id="' + planId + '"]');
            if (priceEl) {
                priceEl.textContent = '$' + unitPrice.toFixed(2);
            }

            // Update total display
            var totalEl = card.querySelector('.plan-total[data-plan-id="' + planId + '"]');
            if (totalEl) {
                var suffix = currentPeriod === 'yearly' ? '/yr' : '/mo';
                totalEl.textContent = 'Total: $' + total.toFixed(2) + suffix;
            }
        });
    }

    // ----------------------------------------------------------------
    // Update subscribe links with current parameters
    // ----------------------------------------------------------------
    function updateSubscribeLinks() {
        var links = document.querySelectorAll('.plan-subscribe-btn');
        links.forEach(function (link) {
            var planId = link.dataset.planId;
            var params = new URLSearchParams({
                plan_id: planId,
                billing_period: currentPeriod,
                user_count: currentUserCount,
            });
            if (currentCouponCode && couponValid) {
                params.set('coupon_code', currentCouponCode);
            }
            link.href = '/subscribe?' + params.toString();
        });
    }

    // ----------------------------------------------------------------
    // Coupon handler
    // ----------------------------------------------------------------
    function setupCouponHandler() {
        if (!applyCouponBtn) return;

        applyCouponBtn.addEventListener('click', function () {
            var code = couponInput.value.trim();
            if (!code) {
                showCouponFeedback('Please enter a coupon code.', false);
                return;
            }

            // Use first plan for validation (general validation)
            var firstCard = planCards[0];
            if (!firstCard) return;
            var planId = firstCard.dataset.planId;

            applyCouponBtn.disabled = true;
            applyCouponBtn.textContent = 'Checking...';

            jsonRpc('/pricing/validate-coupon', {
                coupon_code: code,
                plan_id: parseInt(planId, 10),
            }).then(function (result) {
                applyCouponBtn.disabled = false;
                applyCouponBtn.textContent = 'Apply';

                if (result.valid) {
                    couponValid = true;
                    currentCouponCode = code;
                    showCouponFeedback(result.message, true);
                    recalculateFromServer();
                    updateSubscribeLinks();
                } else {
                    couponValid = false;
                    currentCouponCode = '';
                    showCouponFeedback(result.message, false);
                    hidePriceSummary();
                    updateSubscribeLinks();
                }
            }).catch(function () {
                applyCouponBtn.disabled = false;
                applyCouponBtn.textContent = 'Apply';
                showCouponFeedback('An error occurred. Please try again.', false);
            });
        });

        // Allow Enter key on coupon input
        couponInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                applyCouponBtn.click();
            }
        });
    }

    function showCouponFeedback(message, success) {
        couponFeedback.style.display = 'block';
        couponFeedback.className = 'mt-2 small ' + (success ? 'text-success' : 'text-danger');
        couponFeedback.textContent = message;
    }

    // ----------------------------------------------------------------
    // Server-side price recalculation (when coupon is active)
    // ----------------------------------------------------------------
    function recalculateDebounced() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(recalculateFromServer, 300);
    }

    function recalculateFromServer() {
        // Recalculate for each visible plan
        var firstCard = planCards[0];
        if (!firstCard) return;

        var planId = firstCard.dataset.planId;

        jsonRpc('/pricing/calculate', {
            plan_id: parseInt(planId, 10),
            billing_period: currentPeriod,
            user_count: currentUserCount,
            coupon_code: currentCouponCode,
        }).then(function (result) {
            if (result.error) return;
            showPriceSummary(result);
        });
    }

    function showPriceSummary(data) {
        if (!priceSummary) return;
        priceSummary.style.display = '';
        summarySubtotal.textContent = '$' + data.subtotal.toFixed(2);
        summaryDiscount.textContent = '-$' + data.discount_amount.toFixed(2);
        summaryTotal.textContent = '$' + data.total.toFixed(2);
    }

    function hidePriceSummary() {
        if (priceSummary) {
            priceSummary.style.display = 'none';
        }
    }

    // ----------------------------------------------------------------
    // JSON-RPC helper (Odoo 18 compatible)
    // ----------------------------------------------------------------
    function jsonRpc(url, params) {
        var body = JSON.stringify({
            jsonrpc: '2.0',
            method: 'call',
            id: new Date().getTime(),
            params: params || {},
        });

        return fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: body,
        }).then(function (response) {
            return response.json();
        }).then(function (data) {
            if (data.error) {
                return Promise.reject(data.error);
            }
            return data.result;
        });
    }

    // ----------------------------------------------------------------
    // Initialize on DOM ready
    // ----------------------------------------------------------------
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
