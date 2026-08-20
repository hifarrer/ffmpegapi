from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import stripe as stripe_sdk
from flask import Flask
from flask_login import LoginManager

from admin_routes import admin_bp
from models import ApiKey, ApiLog, SiteSettings, SubscriptionPlan, User, UserSubscription, db


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

    @app.route('/')
    def index():
        return 'index'

    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
        plan = SubscriptionPlan(
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
            stripe_yearly_price_id='price_premium_yearly',
        )
        user = User(
            username='activity-user',
            email='activity@example.com',
            created_at=datetime(2026, 8, 1, 12, 0),
            email_verified=True,
        )
        user.set_password('password')
        db.session.add_all([plan, premium, user])
        db.session.flush()
        db.session.add(UserSubscription(
            user_id=user.id,
            plan_id=plan.id,
            status='active',
            billing_cycle='monthly',
        ))
        db.session.commit()

    yield app

    with app.app_context():
        db.drop_all()


def log_in_admin(client):
    with client.session_transaction() as browser_session:
        browser_session['admin_authenticated'] = True


def edit_payload(**overrides):
    payload = {
        'username': 'activity-user',
        'email': 'activity@example.com',
        'active': '1',
        'email_verified': '1',
        'stripe_customer_id': '',
        'stripe_subscription_id': '',
    }
    payload.update(overrides)
    return payload


def stripe_subscription(
    subscription_id='sub_verified',
    customer_id='cus_verified',
    price_id='price_premium_monthly',
    status='active',
):
    return {
        'id': subscription_id,
        'customer': customer_id,
        'status': status,
        'items': {'data': [{
            'price': {'id': price_id},
            'current_period_start': 1_800_000_000,
            'current_period_end': 1_802_592_000,
        }]},
    }


def test_site_settings_validates_concurrent_jobs_range(app):
    client = app.test_client()
    log_in_admin(client)

    response = client.post('/admin/settings', data={
        'site_name': 'FFmpeg API',
        'concurrent_jobs': '8',
    })
    assert response.status_code == 200
    with app.app_context():
        assert SiteSettings.get_settings().concurrent_jobs == 8

    response = client.post('/admin/settings', data={
        'site_name': 'FFmpeg API',
        'concurrent_jobs': '9',
    })
    assert response.status_code == 302
    with app.app_context():
        assert SiteSettings.get_settings().concurrent_jobs == 8


def test_user_management_edit_modal_uses_inactive_stored_subscription(app):
    with app.app_context():
        subscription = UserSubscription.query.join(User).filter(
            User.username == 'activity-user'
        ).one()
        subscription.status = 'canceled'
        subscription.stripe_customer_id = 'cus_inactive'
        subscription.stripe_subscription_id = 'sub_inactive'
        db.session.commit()

    client = app.test_client()
    log_in_admin(client)
    response = client.get('/admin/users')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'title="Edit user"' in body
    assert 'action="/admin/users/1/edit"' in body
    assert 'value="cus_inactive"' in body
    assert 'value="sub_inactive"' in body
    assert 'status: canceled' in body


def test_admin_can_edit_account_fields_without_changing_password(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        user_id = user.id
        password_hash = user.password_hash

    client = app.test_client()
    log_in_admin(client)
    with patch('admin_routes.get_stripe_config') as get_config:
        response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(
                username='renamed-user',
                email='RENAMED@EXAMPLE.COM',
                active=None,
            ),
        )

    assert response.status_code == 302
    get_config.assert_not_called()
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.username == 'renamed-user'
        assert user.email == 'renamed@example.com'
        assert not user.active
        assert user.email_verified
        assert user.password_hash == password_hash


def test_invalid_or_duplicate_identity_rolls_back_all_changes(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        user_id = user.id
        other = User(username='duplicate-user', email='duplicate@example.com')
        other.set_password('password')
        db.session.add(other)
        db.session.commit()

    client = app.test_client()
    log_in_admin(client)
    duplicate_response = client.post(
        f'/admin/users/{user_id}/edit',
        data=edit_payload(
            username='DUPLICATE-USER',
            email='changed@example.com',
            stripe_customer_id='cus_should_not_save',
        ),
        follow_redirects=True,
    )
    invalid_email_response = client.post(
        f'/admin/users/{user_id}/edit',
        data=edit_payload(email='not-an-email'),
        follow_redirects=True,
    )

    assert b'username is already in use' in duplicate_response.data
    assert b'valid email address' in invalid_email_response.data
    with app.app_context():
        user = db.session.get(User, user_id)
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert user.username == 'activity-user'
        assert user.email == 'activity@example.com'
        assert subscription.stripe_customer_id is None


def test_customer_only_link_is_verified_and_preserves_subscription_state(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        user_id = user.id
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        original_plan_id = subscription.plan_id
        subscription.api_calls_used = 4
        db.session.commit()

    client = app.test_client()
    log_in_admin(client)
    with patch('admin_routes.get_stripe_config', return_value=object()), \
         patch('admin_routes.stripe.Customer.retrieve', return_value={'id': 'cus_verified'}), \
         patch('admin_routes.stripe.Subscription.retrieve') as retrieve_subscription:
        response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(stripe_customer_id='cus_verified'),
        )

    assert response.status_code == 302
    retrieve_subscription.assert_not_called()
    with app.app_context():
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert subscription.stripe_customer_id == 'cus_verified'
        assert subscription.stripe_subscription_id is None
        assert subscription.plan_id == original_plan_id
        assert subscription.status == 'active'
        assert subscription.api_calls_used == 4


def test_customer_only_link_creates_missing_free_subscription(app):
    with app.app_context():
        user = User(username='no-subscription', email='no-subscription@example.com')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    log_in_admin(client)
    with patch('admin_routes.get_stripe_config', return_value=object()), \
         patch('admin_routes.stripe.Customer.retrieve', return_value={'id': 'cus_new'}):
        response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(
                username='no-subscription',
                email='no-subscription@example.com',
                stripe_customer_id='cus_new',
            ),
        )

    assert response.status_code == 302
    with app.app_context():
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert subscription.plan.name == 'Free'
        assert subscription.status == 'active'
        assert subscription.stripe_customer_id == 'cus_new'


def test_subscription_link_syncs_verified_billing_state(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        user_id = user.id
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        subscription.api_calls_used = 6
        db.session.commit()

    client = app.test_client()
    log_in_admin(client)
    verified_subscription = stripe_sdk.Subscription.construct_from(
        stripe_subscription(status='trialing'),
        'sk_test',
    )
    verified_customer = stripe_sdk.Customer.construct_from(
        {'id': 'cus_verified', 'deleted': False},
        'sk_test',
    )
    with patch('admin_routes.get_stripe_config', return_value=object()), \
         patch('admin_routes.stripe.Subscription.retrieve', return_value=verified_subscription), \
         patch('admin_routes.stripe.Customer.retrieve', return_value=verified_customer):
        response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(stripe_subscription_id='sub_verified'),
        )

    assert response.status_code == 302
    with app.app_context():
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert subscription.plan.name == 'Premium'
        assert subscription.status == 'trialing'
        assert subscription.billing_cycle == 'monthly'
        assert subscription.stripe_subscription_id == 'sub_verified'
        assert subscription.stripe_customer_id == 'cus_verified'
        assert subscription.current_period_start is not None
        assert subscription.current_period_end is not None
        assert subscription.api_calls_used == 0


def test_same_plan_subscription_relink_preserves_api_usage(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        premium = SubscriptionPlan.query.filter_by(name='Premium').one()
        subscription = UserSubscription.query.filter_by(user_id=user.id).one()
        subscription.plan_id = premium.id
        subscription.stripe_customer_id = 'cus_old'
        subscription.stripe_subscription_id = 'sub_old'
        subscription.status = 'active'
        subscription.api_calls_used = 7
        db.session.commit()
        user_id = user.id

    client = app.test_client()
    log_in_admin(client)
    with patch('admin_routes.get_stripe_config', return_value=object()), \
         patch('admin_routes.stripe.Subscription.retrieve', return_value=stripe_subscription()), \
         patch('admin_routes.stripe.Customer.retrieve', return_value={'id': 'cus_verified'}):
        client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(stripe_subscription_id='sub_verified'),
        )

    with app.app_context():
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert subscription.plan.name == 'Premium'
        assert subscription.api_calls_used == 7


@pytest.mark.parametrize(
    ('customer_id', 'subscription_id', 'subscription_result', 'customer_result', 'expected_message'),
    [
        ('cus_wrong', 'sub_verified', stripe_subscription(), {'id': 'cus_verified'}, b'different customer'),
        ('', 'sub_unknown', stripe_subscription(subscription_id='sub_unknown', price_id='price_unknown'), {'id': 'cus_verified'}, b'not mapped'),
        ('cus_deleted', '', None, {'id': 'cus_deleted', 'deleted': True}, b'has been deleted'),
    ],
)
def test_invalid_stripe_links_are_rejected_atomically(
    app, customer_id, subscription_id, subscription_result, customer_result, expected_message
):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        user_id = user.id

    client = app.test_client()
    log_in_admin(client)
    with patch('admin_routes.get_stripe_config', return_value=object()), \
         patch('admin_routes.stripe.Subscription.retrieve', return_value=subscription_result), \
         patch('admin_routes.stripe.Customer.retrieve', return_value=customer_result):
        response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(
                username='should-roll-back',
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
            ),
            follow_redirects=True,
        )

    assert expected_message in response.data
    with app.app_context():
        user = db.session.get(User, user_id)
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert user.username == 'activity-user'
        assert subscription.stripe_customer_id is None
        assert subscription.stripe_subscription_id is None


def test_stripe_conflicts_and_api_failures_do_not_change_user(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        user_id = user.id
        other = User(username='stripe-owner', email='stripe-owner@example.com')
        other.set_password('password')
        db.session.add(other)
        db.session.flush()
        free = SubscriptionPlan.query.filter_by(name='Free').one()
        db.session.add(UserSubscription(
            user_id=other.id,
            plan_id=free.id,
            stripe_customer_id='cus_taken',
            stripe_subscription_id='sub_taken',
        ))
        db.session.commit()

    client = app.test_client()
    log_in_admin(client)
    with patch('admin_routes.get_stripe_config', return_value=object()), \
         patch('admin_routes.stripe.Customer.retrieve', return_value={'id': 'cus_taken'}):
        customer_conflict_response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(username='should-roll-back', stripe_customer_id='cus_taken'),
            follow_redirects=True,
        )
    subscription_conflict_response = client.post(
        f'/admin/users/{user_id}/edit',
        data=edit_payload(username='should-roll-back', stripe_subscription_id='sub_taken'),
        follow_redirects=True,
    )
    with patch('admin_routes.get_stripe_config', return_value=object()), \
         patch('admin_routes.stripe.Subscription.retrieve', side_effect=RuntimeError('Stripe unavailable')):
        failure_response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(username='should-also-roll-back', stripe_subscription_id='sub_failure'),
            follow_redirects=True,
        )

    assert b'customer is already linked to another user' in customer_conflict_response.data
    assert b'subscription is already linked to another user' in subscription_conflict_response.data
    assert b'could not verify that subscription ID' in failure_response.data
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.username == 'activity-user'


def test_stripe_format_and_configuration_errors_are_atomic(app):
    with app.app_context():
        user_id = User.query.filter_by(username='activity-user').one().id

    client = app.test_client()
    log_in_admin(client)
    format_response = client.post(
        f'/admin/users/{user_id}/edit',
        data=edit_payload(username='should-roll-back', stripe_customer_id='not-a-customer'),
        follow_redirects=True,
    )
    with patch('admin_routes.get_stripe_config', return_value=None):
        config_response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(username='should-also-roll-back', stripe_customer_id='cus_unverified'),
            follow_redirects=True,
        )

    assert b'must be a valid cus_' in format_response.data
    assert b'Stripe is not configured' in config_response.data
    with app.app_context():
        user = db.session.get(User, user_id)
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert user.username == 'activity-user'
        assert subscription.stripe_customer_id is None


def test_unchanged_ids_skip_stripe_and_blank_ids_unlink_locally(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        user_id = user.id
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        subscription.stripe_customer_id = 'cus_existing'
        subscription.stripe_subscription_id = 'sub_existing'
        subscription.status = 'active'
        subscription.api_calls_used = 5
        original_plan_id = subscription.plan_id
        db.session.commit()

    client = app.test_client()
    log_in_admin(client)
    with patch('admin_routes.get_stripe_config') as get_config:
        client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(
                email='updated@example.com',
                stripe_customer_id='cus_existing',
                stripe_subscription_id='sub_existing',
            ),
        )
        unlink_response = client.post(
            f'/admin/users/{user_id}/edit',
            data=edit_payload(email='updated@example.com'),
        )

    assert unlink_response.status_code == 302
    get_config.assert_not_called()
    with app.app_context():
        subscription = UserSubscription.query.filter_by(user_id=user_id).one()
        assert subscription.stripe_customer_id is None
        assert subscription.stripe_subscription_id is None
        assert subscription.plan_id == original_plan_id
        assert subscription.status == 'active'
        assert subscription.api_calls_used == 5


def test_user_edit_requires_admin_and_csrf(app):
    with app.app_context():
        user_id = User.query.filter_by(username='activity-user').one().id

    unauthenticated_response = app.test_client().post(
        f'/admin/users/{user_id}/edit',
        data=edit_payload(),
    )
    assert unauthenticated_response.status_code == 302
    assert unauthenticated_response.headers['Location'].endswith('/admin/login')

    app.config['WTF_CSRF_ENABLED'] = True
    client = app.test_client()
    log_in_admin(client)
    csrf_response = client.post(
        f'/admin/users/{user_id}/edit',
        data=edit_payload(),
    )
    assert csrf_response.status_code == 400


def test_user_management_shows_joined_and_latest_key_usage(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        user_id = user.id
        db.session.add_all([
            ApiKey(
                key='ffmpeg_activity_old',
                name='Old key',
                user_id=user.id,
                last_used=datetime(2026, 8, 18, 9, 15),
            ),
            ApiKey(
                key='ffmpeg_activity_new',
                name='New key',
                user_id=user.id,
                last_used=datetime(2026, 8, 19, 22, 30),
            ),
        ])

        never_user = User(
            username='never-used',
            email='never@example.com',
            created_at=datetime(2026, 8, 2, 13, 0),
            email_verified=True,
        )
        never_user.set_password('password')
        db.session.add(never_user)
        db.session.commit()

    client = app.test_client()
    log_in_admin(client)
    response = client.get('/admin/users')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<th>Joined</th>' in body
    assert '<th>Last Used</th>' in body
    assert '08/19/2026 22:30 UTC' in body
    assert '08/18/2026 09:15 UTC' not in body
    assert 'Never' in body
    assert f'href="/admin/users/{user_id}"' in body


def test_user_detail_requires_admin_authentication(app):
    with app.app_context():
        user_id = User.query.filter_by(username='activity-user').one().id

    response = app.test_client().get(f'/admin/users/{user_id}')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/admin/login')


def test_user_detail_shows_only_ten_newest_logs_for_exact_user(app):
    with app.app_context():
        user = User.query.filter_by(username='activity-user').one()
        api_key = ApiKey(
            key='ffmpeg_activity_history',
            name='History key',
            user_id=user.id,
            last_used=datetime(2026, 8, 20, 12, 30),
        )
        other_user = User(
            username='other-user',
            email='other@example.com',
            email_verified=True,
        )
        other_user.set_password('password')
        db.session.add_all([api_key, other_user])
        db.session.flush()

        base_time = datetime(2026, 8, 20, 10, 0)
        logs = []
        for index in range(12):
            status_code = 500 if index == 11 else (400 if index == 10 else 200)
            logs.append(ApiLog(
                user_id=user.id,
                username=user.username,
                api_key_id=api_key.id,
                endpoint=f'/api/activity/{index:02d}',
                method='POST',
                status_code=status_code,
                processing_time_ms=index * 10,
                created_at=base_time + timedelta(minutes=index),
            ))
        other_log = ApiLog(
            user_id=other_user.id,
            username=other_user.username,
            endpoint='/api/other-user-secret',
            method='GET',
            status_code=200,
            created_at=base_time + timedelta(days=1),
        )
        db.session.add_all([*logs, other_log])
        db.session.commit()
        user_id = user.id
        newest_log_id = logs[-1].id

    client = app.test_client()
    log_in_admin(client)
    response = client.get(f'/admin/users/{user_id}')
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.count('/api/activity/') == 10
    assert '/api/activity/00' not in body
    assert '/api/activity/01' not in body
    assert '/api/activity/02' in body
    assert body.index('/api/activity/11') < body.index('/api/activity/10')
    assert '/api/other-user-secret' not in body
    assert 'History key' in body
    assert '400' in body
    assert '500' in body
    assert f'/admin/api-logs/{newest_log_id}' in body
    assert '08/20/2026 12:30 UTC' in body


def test_user_detail_handles_missing_user_and_empty_history(app):
    client = app.test_client()
    log_in_admin(client)

    missing_response = client.get('/admin/users/999999')

    with app.app_context():
        user_id = User.query.filter_by(username='activity-user').one().id
    empty_response = client.get(f'/admin/users/{user_id}')

    assert missing_response.status_code == 404
    assert empty_response.status_code == 200
    assert b'No Recorded API Calls' in empty_response.data
