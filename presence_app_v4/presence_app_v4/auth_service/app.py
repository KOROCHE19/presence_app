# auth_service/app.py  —  v2
# Améliorations : flask-limiter sur /auth/login + gunicorn (plus de debug=True)

import os
import logging
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] auth_service — %(message)s'
)
logger = logging.getLogger(__name__)

# ── app ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'postgresql://auth_user:auth_pass@localhost:5432/auth_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

db = SQLAlchemy(app)

# ── AMÉLIORATION 1 : Rate Limiting ───────────────────────────────────────────
# Protège contre les attaques brute-force sur la route de connexion.
# Stockage en mémoire (suffisant pour un seul process gunicorn).
# En production multi-instance, utiliser storage_uri="redis://redis:6379".
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=[],          # pas de limite globale
    storage_uri="memory://",
)


# ── modèle ────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    nom           = db.Column(db.String(80),  nullable=False)
    prenom        = db.Column(db.String(80),  nullable=False)
    role          = db.Column(db.String(20),  default='formateur')  # admin | formateur
    is_active     = db.Column(db.Boolean,     default=True)
    created_at    = db.Column(db.DateTime,    default=datetime.utcnow)

    def set_password(self, mdp):
        self.password_hash = generate_password_hash(mdp)

    def check_password(self, mdp):
        return check_password_hash(self.password_hash, mdp)

    def to_dict(self):
        return {
            'id':        self.id,
            'email':     self.email,
            'nom':       self.nom,
            'prenom':    self.prenom,
            'role':      self.role,
            'is_active': self.is_active,
        }


# ── décorateur JWT ────────────────────────────────────────────────────────────
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth = request.headers.get('Authorization', '')
        parts = auth.split(' ')
        if len(parts) == 2 and parts[0] == 'Bearer':
            token = parts[1]
        if not token:
            return jsonify({'error': 'token manquant'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'token expiré'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'token invalide'}), 401
        return f(data, *args, **kwargs)
    return decorated


# ── routes ────────────────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'auth'}), 200


@app.route('/auth/login', methods=['POST'])
@limiter.limit('5 per minute')          # ← AMÉLIORATION 1 : max 5 tentatives/min/IP
@limiter.limit('20 per hour')           # et max 20 tentatives/heure/IP
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'email et password requis'}), 400

    u = User.query.filter_by(email=data['email'].lower()).first()

    # Même message d'erreur qu'email inconnu ou mdp faux → pas d'énumération
    if not u or not u.check_password(data['password']):
        logger.warning('Tentative de connexion échouée pour : %s', data.get('email'))
        return jsonify({'error': 'email ou mot de passe incorrect'}), 401

    if not u.is_active:
        return jsonify({'error': 'compte désactivé'}), 401

    payload = {
        'user_id': u.id,
        'role':    u.role,
        'email':   u.email,
        'nom':     u.nom,
        'prenom':  u.prenom,
        'exp':     datetime.utcnow() + timedelta(hours=24),
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

    logger.info('Connexion réussie : %s (%s)', u.email, u.role)
    return jsonify({'token': token, 'user': u.to_dict()}), 200


# Gestionnaire d'erreur 429 renvoyé par flask-limiter
@app.errorhandler(429)
def trop_de_requetes(e):
    logger.warning('Rate limit dépassé depuis IP : %s', request.remote_addr)
    return jsonify({
        'error': 'Trop de tentatives de connexion. Réessayez dans 1 minute.',
        'retry_after': '60 secondes',
    }), 429


@app.route('/auth/verify', methods=['GET'])
def verify():
    auth  = request.headers.get('Authorization', '')
    parts = auth.split(' ')
    if len(parts) != 2:
        return jsonify({'valid': False}), 401
    try:
        payload = jwt.decode(parts[1], app.config['SECRET_KEY'], algorithms=['HS256'])
        return jsonify({'valid': True, 'user_id': payload['user_id'], 'role': payload['role']}), 200
    except jwt.InvalidTokenError:
        return jsonify({'valid': False}), 401


@app.route('/auth/users', methods=['POST'])
@token_required
def creer_user(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403

    data = request.get_json()
    for champ in ['email', 'password', 'nom', 'prenom']:
        if not data.get(champ):
            return jsonify({'error': f'champ manquant : {champ}'}), 400

    if User.query.filter_by(email=data['email'].lower()).first():
        return jsonify({'error': 'email déjà utilisé'}), 400

    u = User(
        email=data['email'].lower(),
        nom=data['nom'],
        prenom=data['prenom'],
        role=data.get('role', 'formateur'),
    )
    u.set_password(data['password'])
    db.session.add(u)
    db.session.commit()

    logger.info('Compte créé : %s (%s)', u.email, u.role)
    return jsonify({'message': 'compte créé', 'user': u.to_dict()}), 201


@app.route('/auth/users', methods=['GET'])
@token_required
def liste_users(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403
    users = User.query.all()
    return jsonify({'users': [u.to_dict() for u in users]}), 200


# ── init DB ───────────────────────────────────────────────────────────────────
def init_db():
    db.create_all()
    if not User.query.first():
        admin = User(email='admin@ecole.fr', nom='Admin', prenom='Super', role='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        logger.info('Compte admin par défaut créé : admin@ecole.fr / admin123')


with app.app_context():
    init_db()

# ── AMÉLIORATION 5 : plus de app.run(debug=True) ─────────────────────────────
# Le serveur de développement Flask n'est plus utilisé.
# Démarrage via gunicorn dans le Dockerfile :
#   CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "app:app"]
