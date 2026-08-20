from datetime import datetime, timedelta
from pathlib import Path

import pytest
from flask import Flask
from flask_login import LoginManager

from admin_routes import admin_bp
from models import ApiKey, ApiLog, SubscriptionPlan, User, UserSubscription, db


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
        user = User(
            username='activity-user',
            email='activity@example.com',
            created_at=datetime(2026, 8, 1, 12, 0),
            email_verified=True,
        )
        user.set_password('password')
        db.session.add_all([plan, user])
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
