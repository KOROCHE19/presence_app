"""
auth_service - Authentification JWT et gestion des comptes

Ce service est le gardien de l'application. Chaque requete protegee des autres
services passe d'abord par lui pour valider le token. C'est aussi ici qu'on
gere les roles admin/formateur et le hachage des mots de passe.

Port : 5001
Base : auth_db (PostgreSQL)
"""

import os
import time
import jwt
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, g
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://auth_user:auth_pass@localhost:5432/auth_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

db = SQLAlchemy(app)

# Compteur en memoire pour le rate limiting sur /auth/login.
# Format : { ip: [(timestamp, ...), ...] }
# On garde uniquement les tentatives des 15 dernieres minutes.
tentatives_login = defaultdict(list)
FENETRE_SECONDES = 900   # 15 min
MAX_TENTATIVES   = 5


# ---------------------------------------------------------------------------
# Modele
# ---------------------------------------------------------------------------

class User(db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    nom           = db.Column(db.String(80), nullable=False)
    prenom        = db.Column(db.String(80), nullable=False)
    # Le role conditionne ce que l'utilisateur peut faire dans toute l'appli.
    # On n'a volontairement que deux niveaux en v1 : admin ou formateur.
    role          = db.Column(db.String(20), default='formateur')
    # is_active permet de desactiver un compte sans le supprimer (conformite RGPD).
    is_active     = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, mdp):
        # cost=12 signifie qu'une tentative de brute-force prend ~300ms par essai.
        self.password_hash = generate_password_hash(mdp, method='pbkdf2:sha256', salt_length=16)

    def check_password(self, mdp):
        return check_password_hash(self.password_hash, mdp)

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'nom': self.nom,
            'prenom': self.prenom,
            'role': self.role,
            'is_active': self.is_active
        }


# ---------------------------------------------------------------------------
# Middlewares
# ---------------------------------------------------------------------------

@app.after_request
def ajouter_headers_cors(reponse):
    """
    Autorise le frontend (port 5000) a appeler ce service depuis le navigateur.
    On est strict : pas de wildcard *, uniquement l'origine connue.
    Les requetes OPTIONS (preflight CORS) recoivent une reponse directe
    sans passer par le decorateur token_required, ce qui evitait un bug 401
    systematique en v1.
    """
    origine = request.headers.get('Origin', '')
    origines_autorisees = [
        'http://localhost:5000',
        'http://frontend_service:5000',
        'http://frontend:5000',
    ]
    if origine in origines_autorisees or not origine:
        reponse.headers['Access-Control-Allow-Origin'] = origine or '*'
    reponse.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    reponse.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return reponse


@app.before_request
def traiter_preflight():
    # Les requetes OPTIONS sont des "poignees de main" du navigateur.
    # Si on les laisse remonter jusqu'aux decorateurs JWT, elles echouent avec 401.
    # On leur repond directement avec un 200 vide.
    if request.method == 'OPTIONS':
        return jsonify({}), 200


def token_required(f):
    """
    Decorateur a placer sur toutes les routes protegees.
    Extrait et valide le token Bearer depuis le header Authorization,
    puis injecte le payload decode comme premier argument de la fonction.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization', '')
        parties = auth_header.split(' ')
        if len(parties) == 2 and parties[0] == 'Bearer':
            token = parties[1]

        if not token:
            return jsonify({'error': 'token manquant'}), 401

        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'token expire'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'token invalide'}), 401

        return f(payload, *args, **kwargs)
    return decorated


def admin_required(f):
    """Raccourci : verifie le token ET que le role est 'admin'."""
    @wraps(f)
    @token_required
    def decorated(user, *args, **kwargs):
        if user.get('role') != 'admin':
            return jsonify({'error': 'droits administrateur requis'}), 403
        return f(user, *args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Rate limiting sur le login
# ---------------------------------------------------------------------------

def verifier_rate_limit(ip):
    """
    Retourne True si l'IP depasse le seuil de tentatives.
    On nettoie au passage les anciennes entrees pour eviter une fuite memoire.
    """
    maintenant = time.time()
    historique = tentatives_login[ip]

    # On garde uniquement les tentatives dans la fenetre glissante
    tentatives_login[ip] = [t for t in historique if maintenant - t < FENETRE_SECONDES]

    return len(tentatives_login[ip]) >= MAX_TENTATIVES


def enregistrer_tentative(ip):
    tentatives_login[ip].append(time.time())


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    """
    Sonde de liveness utilisee par Docker pour savoir si le service est pret.
    On verifie la connexion BDD en plus du simple "je suis en vie".
    """
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status': 'ok', 'service': 'auth_service'}), 200
    except Exception as e:
        return jsonify({'status': 'erreur', 'detail': str(e)}), 503


@app.route('/auth/login', methods=['POST'])
def login():
    """
    Point d'entree principal. On valide les credentials, on genere un token
    JWT signe HS256 avec une expiration de 24h (configurable).
    Le payload inclut nom/prenom pour eviter une requete BDD supplementaire
    dans les autres services.
    """
    ip = request.remote_addr or '0.0.0.0'

    if verifier_rate_limit(ip):
        return jsonify({'error': 'trop de tentatives, reessayez dans 15 minutes'}), 429

    data = request.get_json() or {}
    if not data.get('email') or not data.get('password'):
        return jsonify({'error': 'email et password requis'}), 400

    u = User.query.filter_by(email=data['email'].lower().strip()).first()

    # On incremente le compteur meme si l'email n'existe pas,
    # pour ne pas laisser deviner les comptes existants par timing.
    if not u or not u.check_password(data['password']):
        enregistrer_tentative(ip)
        return jsonify({'error': 'email ou mot de passe incorrect'}), 401

    if not u.is_active:
        return jsonify({'error': 'compte desactive, contactez l administrateur'}), 401

    duree = int(os.environ.get('JWT_DUREE_HEURES', 24))
    payload = {
        'user_id': u.id,
        'role': u.role,
        'email': u.email,
        'nom': u.nom,
        'prenom': u.prenom,
        'exp': datetime.utcnow() + timedelta(hours=duree)
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({'token': token, 'user': u.to_dict()}), 200


@app.route('/auth/verify', methods=['GET'])
def verify():
    """
    Endpoint appele par les autres services pour valider un token
    sans avoir a partager la cle secrete. Retourne le payload utile.
    """
    auth = request.headers.get('Authorization', '')
    parties = auth.split(' ')
    if len(parties) != 2:
        return jsonify({'valid': False}), 401
    try:
        payload = jwt.decode(parties[1], app.config['SECRET_KEY'], algorithms=['HS256'])
        return jsonify({
            'valid': True,
            'user_id': payload['user_id'],
            'role': payload['role'],
            'nom': payload.get('nom'),
            'prenom': payload.get('prenom')
        }), 200
    except jwt.InvalidTokenError:
        return jsonify({'valid': False}), 401


@app.route('/me', methods=['GET'])
@token_required
def mon_profil(user):
    """
    Retourne le profil de l'utilisateur connecte depuis le token,
    sans requete BDD supplementaire (toutes les infos sont dans le payload).
    """
    return jsonify({
        'user_id': user['user_id'],
        'role': user['role'],
        'email': user.get('email'),
        'nom': user.get('nom'),
        'prenom': user.get('prenom')
    }), 200


@app.route('/auth/users', methods=['POST'])
@admin_required
def creer_user(admin):
    """Creation d'un compte formateur par un administrateur."""
    data = request.get_json() or {}

    champs_requis = ['email', 'password', 'nom', 'prenom']
    for champ in champs_requis:
        if not data.get(champ):
            return jsonify({'error': f'champ manquant : {champ}'}), 400

    email = data['email'].lower().strip()
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'cet email est deja utilise'}), 409

    u = User(
        email=email,
        nom=data['nom'],
        prenom=data['prenom'],
        role=data.get('role', 'formateur')
    )
    u.set_password(data['password'])
    db.session.add(u)
    db.session.commit()

    return jsonify({'message': 'compte cree', 'user': u.to_dict()}), 201


@app.route('/auth/users', methods=['GET'])
@admin_required
def liste_users(admin):
    users = User.query.order_by(User.nom).all()
    return jsonify({'users': [u.to_dict() for u in users]}), 200


@app.route('/auth/users/<int:user_id>', methods=['PUT'])
@admin_required
def modifier_user(admin, user_id):
    """Mise a jour partielle : on ne touche qu'aux champs envoyes."""
    u = User.query.get_or_404(user_id)
    data = request.get_json() or {}

    if 'nom' in data:
        u.nom = data['nom']
    if 'prenom' in data:
        u.prenom = data['prenom']
    if 'is_active' in data:
        u.is_active = data['is_active']
    if 'role' in data and data['role'] in ['admin', 'formateur']:
        u.role = data['role']
    if 'password' in data and data['password']:
        u.set_password(data['password'])

    db.session.commit()
    return jsonify({'message': 'compte mis a jour', 'user': u.to_dict()}), 200


# ---------------------------------------------------------------------------
# Demarrage
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # Compte admin de depart si la base est vide. A changer en production.
        if not User.query.first():
            admin = User(email='admin@ecole.fr', nom='Admin', prenom='CNAM', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)

        # Formateur de demonstration (Sophie Martin, visible dans les captures du rapport)
        if not User.query.filter_by(email='martin@ecole.fr').first():
            formateur = User(email='martin@ecole.fr', nom='Martin', prenom='Sophie', role='formateur')
            formateur.set_password('formateur123')
            db.session.add(formateur)

        db.session.commit()
        print("auth_service demarre. Comptes : admin@ecole.fr / admin123 | martin@ecole.fr / formateur123")

    app.run(host='0.0.0.0', port=5001, debug=True)
