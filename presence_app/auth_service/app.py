# service auth - gestion des comptes et connexion
# les utilisateurs : admin ou formateur

import os
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://auth_user:auth_pass@localhost:5432/auth_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

db = SQLAlchemy(app)


# table utilisateur
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    nom = db.Column(db.String(80), nullable=False)
    prenom = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), default='formateur')  # le role d'admin ou de formateur
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, mdp):
        self.password_hash = generate_password_hash(mdp)

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


# decorateur verif token
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split(' ')
            if len(parts) == 2:
                token = parts[1]
        if not token:
            return jsonify({'error': 'token manquant'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except:
            return jsonify({'error': 'token invalide'}), 401
        return f(data, *args, **kwargs)
    return decorated


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'}), 200


# connexion
@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'email et password requis'}), 400

    u = User.query.filter_by(email=data['email'].lower()).first()
    if not u or not u.check_password(data['password']):
        return jsonify({'error': 'email ou mot de passe incorrect'}), 401

    if not u.is_active:
        return jsonify({'error': 'compte désactivé'}), 401

    payload = {
        'user_id': u.id,
        'role': u.role,
        'email': u.email,
        'nom': u.nom,
        'prenom': u.prenom,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({'token': token, 'user': u.to_dict()}), 200


# verif token (utilisé par les autres services)
@app.route('/auth/verify', methods=['GET'])
def verify():
    auth = request.headers.get('Authorization', '')
    parts = auth.split(' ')
    if len(parts) != 2:
        return jsonify({'valid': False}), 401
    try:
        payload = jwt.decode(parts[1], app.config['SECRET_KEY'], algorithms=['HS256'])
        return jsonify({'valid': True, 'user_id': payload['user_id'], 'role': payload['role']}), 200
    except:
        return jsonify({'valid': False}), 401


# créer un compte (admin seulement)
@app.route('/auth/users', methods=['POST'])
@token_required
def creer_user(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403

    data = request.get_json()
    for champ in ['email', 'password', 'nom', 'prenom']:
        if not data.get(champ):
            return jsonify({'error': 'champ manquant : ' + champ}), 400

    if User.query.filter_by(email=data['email'].lower()).first():
        return jsonify({'error': 'email deja utilisé'}), 400

    u = User(
        email=data['email'].lower(),
        nom=data['nom'],
        prenom=data['prenom'],
        role=data.get('role', 'formateur')
    )
    u.set_password(data['password'])
    db.session.add(u)
    db.session.commit()

    return jsonify({'message': 'compte créé', 'user': u.to_dict()}), 201


# liste des users
@app.route('/auth/users', methods=['GET'])
@token_required
def liste_users(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403
    users = User.query.all()
    return jsonify({'users': [u.to_dict() for u in users]}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # creation d'un admin par defaut si la table est vide
        if not User.query.first():
            admin = User(email='admin@ecole.fr', nom='Admin', prenom='CNAM', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("admin créé : admin@ecole.fr / admin123")
    app.run(host='0.0.0.0', port=5001, debug=True)
