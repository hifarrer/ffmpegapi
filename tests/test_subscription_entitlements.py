from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager

from admin_routes import admin_bp
from models import StripeSettings, SubscriptionPlan, User, UserSubscription, db
from stripe_routes import handle_checkout_session_completed, handle_subscription_created, stripe_bp


class StripeObject(dict):
    __getattr__ = dict.__getitem__


@pytest.fixture()
def app():
    root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(root / 'templates'))
    app.config.update(
        SECRET_KEY='test-secret',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    db.init_app(app)

    login_manager = LoginManager(app)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @app.route('/dashboard')
    def dashboard():
        return 'dashboard'

    @app.route('/pricing')
    def pricing():
        return 'pricing'

    @app.route('/')
    def index():
        return 'index'

    app.register_blueprint(stripe_bp, url_prefix='/api/stripe')
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
        free = SubscriptionPlan(
            name='Free',
            api_calls_per_month=10,
            monthly_price=0,
            yearly_price=0,
        )
        premium = SubscriptionPlan(
            name='Premium',
            api_calls_per_month=100,
            monthly_price=10,
            yearly_price=100,
            stripe_monthly_price_id='price_premium_monthly',
        )
        unlimited = SubscriptionPlan(
            name='Unlimited',
            api_calls_per_month=1000,
            monthly_price=20,
            yearly_price=200,
            stripe_monthly_price_id='price_unlimited_monthly',
        )
        user = User(username='paid-test', email='paid@example.com', email_verified=True)
        user.set_password('password')
        db.session.add_all([free, premium, unlimited, user, StripeSettings(secret_key='sk_test_fake')])
        db.session.flush()
        db.session.add(UserSubscription(
            user_id=user.id,
            plan_id=free.id,
            status='active',
            billing_cycle='monthly',
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=30),
        ))
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


def stripe_subscription(status='active', price_id='price_premium_monthly'):
    return StripeObject(
        id='sub_verified',
        status=status,
        customer='cus_verified',
        items={'data': [{
            'price': {'id': price_id},
            'current_period_start': 1_800_000_000,
            'current_period_end': 1_802_592_000,
        }]},
        metadata={'user_id': '1'},
    )


def test_incomplete_subscription_created_does_not_assign_paid_plan(app):
    with app.app_context():
        user = User.query.filter_by(email='paid@example.com').one()
        payload = stripe_subscription(status='incomplete')
        payload['metadata']['user_id'] = str(user.id)

        handle_subscription_created(payload)

        subscription = UserSubscription.query.filter_by(user_id=user.id).one()
        assert subscription.plan.name == 'Free'
        assert subscription.status == 'active'
        assert subscription.stripe_subscription_id is None


def test_checkout_webhook_uses_verified_stripe_price_not_plan_metadata(app):
    with app.app_context():
        user = User.query.filter_by(email='paid@example.com').one()
        unlimited = SubscriptionPlan.query.filter_by(name='Unlimited').one()
        session = StripeObject(
            id='cs_paid',
            mode='subscription',
            payment_status='paid',
            subscription='sub_verified',
            customer='cus_verified',
            metadata={
                'user_id': str(user.id),
                'plan_id': str(unlimited.id),
                'billing_cycle': 'yearly',
            },
        )

        with patch('stripe_routes.stripe.Subscription.retrieve', return_value=stripe_subscription()):
            handle_checkout_session_completed(session)

        subscription = UserSubscription.query.filter_by(user_id=user.id).one()
        assert subscription.plan.name == 'Premium'
        assert subscription.billing_cycle == 'monthly'
        assert subscription.stripe_subscription_id == 'sub_verified'
        assert subscription.status == 'active'


def test_success_url_cannot_apply_another_users_checkout_session(app):
    client = app.test_client()
    with app.app_context():
        user = User.query.filter_by(email='paid@example.com').one()
        user_id = user.id

    with client.session_transaction() as browser_session:
        browser_session['_user_id'] = str(user_id)
        browser_session['_fresh'] = True

    checkout_session = StripeObject(
        id='cs_foreign',
        mode='subscription',
        payment_status='paid',
        subscription='sub_foreign',
        customer='cus_foreign',
        amount_total=1000,
        metadata={'user_id': str(user_id + 1), 'plan_id': '2'},
    )
    with patch('stripe_routes.stripe.checkout.Session.retrieve', return_value=checkout_session), \
         patch('stripe_routes.stripe.Subscription.retrieve') as retrieve_subscription:
        response = client.get('/api/stripe/subscription-success?session_id=cs_foreign')

    assert response.status_code == 302
    retrieve_subscription.assert_not_called()
    with app.app_context():
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert subscription.plan.name == 'Free'


def test_admin_paid_plan_change_is_labeled_as_admin_grant(app):
    client = app.test_client()
    with app.app_context():
        user = User.query.filter_by(email='paid@example.com').one()
        premium = SubscriptionPlan.query.filter_by(name='Premium').one()
        user_id = user.id
        premium_id = premium.id

    with client.session_transaction() as browser_session:
        browser_session['admin_authenticated'] = True

    response = client.post(
        f'/admin/users/{user_id}/change-plan',
        data={'plan_id': premium_id},
    )

    assert response.status_code == 302
    with app.app_context():
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert subscription.plan.name == 'Premium'
        assert subscription.status == 'admin_granted'
        assert subscription.stripe_subscription_id is None
        assert subscription.can_make_api_call()


def test_admin_mutation_rejects_missing_csrf_token_when_enabled(app):
    app.config['WTF_CSRF_ENABLED'] = True
    client = app.test_client()
    with app.app_context():
        user_id = User.query.filter_by(email='paid@example.com').one().id
        premium_id = SubscriptionPlan.query.filter_by(name='Premium').one().id
    with client.session_transaction() as browser_session:
        browser_session['admin_authenticated'] = True

    response = client.post(
        f'/admin/users/{user_id}/change-plan',
        data={'plan_id': premium_id},
    )

    assert response.status_code == 400


def test_legacy_active_paid_row_without_stripe_id_is_not_entitled(app):
    with app.app_context():
        user = User.query.filter_by(email='paid@example.com').one()
        premium = SubscriptionPlan.query.filter_by(name='Premium').one()
        subscription = UserSubscription.query.filter_by(user_id=user.id).one()
        subscription.plan_id = premium.id
        subscription.status = 'active'
        subscription.stripe_subscription_id = None
        db.session.commit()

        assert not subscription.has_entitlement_source()
        assert not subscription.can_make_api_call()


def test_admin_users_page_labels_effective_entitlements(app):
    client = app.test_client()
    with client.session_transaction() as browser_session:
        browser_session['admin_authenticated'] = True

    response = client.get('/admin/users')

    assert response.status_code == 200
    assert b'Free' in response.data
    assert b'No paid entitlement' not in response.data
