from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    tier = db.Column(db.String(20), default='free')
    scans_used = db.Column(db.Integer, default=0)
    scans_reset_date = db.Column(db.DateTime, default=datetime.utcnow)
    stripe_customer_id = db.Column(db.String(150), nullable=True)
    stripe_subscription_id = db.Column(db.String(150), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def can_scan(self):
        if self.tier in ['basic', 'premium']:
            return True
        return self.scans_used < 5

    def use_scan(self):
        self.scans_used += 1
        db.session.commit()