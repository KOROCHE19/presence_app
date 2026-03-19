# service planning - gere les classes, promotions et la liste des etudiants
# l'admin ajoute les etudiants ici, les formateurs peuvent juste lire

import os
import jwt
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://planning_user:planning_pass@localhost:5432/planning_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

db = SQLAlchemy(app)


# table classe (ex: BTS SIO, LP Dev Web...)
class Classe(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text)

    # une classe a plusieurs promotions
    promotions = db.relationship('Promotion', backref='classe', lazy=True)

    def to_dict(self):
        return {'id': self.id, 'nom': self.nom, 'code': self.code, 'description': self.description}


# table promotion (ex: BTS SIO 2025-2026, groupe A...)
class Promotion(db.Model):
    __tablename__ = 'promotions'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100), nullable=False)
    annee = db.Column(db.String(20), nullable=False)  # ex: 2025-2026
    classe_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)

    # une promotion a plusieurs etudiants
    etudiants = db.relationship('Etudiant', backref='promotion', lazy=True)

    def to_dict(self, avec_etudiants=False):
        d = {
            'id': self.id,
            'nom': self.nom,
            'annee': self.annee,
            'classe_id': self.classe_id,
            'classe_nom': self.classe.nom if self.classe else None,
            'nb_etudiants': len(self.etudiants)
        }
        if avec_etudiants:
            d['etudiants'] = [e.to_dict() for e in self.etudiants]
        return d


# table etudiant
class Etudiant(db.Model):
    __tablename__ = 'etudiants'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(80), nullable=False)
    prenom = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    numero_etudiant = db.Column(db.String(20), unique=True)
    promotion_id = db.Column(db.Integer, db.ForeignKey('promotions.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'nom': self.nom,
            'prenom': self.prenom,
            'email': self.email,
            'numero_etudiant': self.numero_etudiant,
            'promotion_id': self.promotion_id,
            'is_active': self.is_active
        }


# verif token
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


# --- classes ---

@app.route('/planning/classes', methods=['GET'])
@token_required
def get_classes(user):
    classes = Classe.query.all()
    return jsonify({'classes': [c.to_dict() for c in classes]}), 200


@app.route('/planning/classes', methods=['POST'])
@token_required
def creer_classe(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403

    data = request.get_json()
    if not data.get('nom') or not data.get('code'):
        return jsonify({'error': 'nom et code obligatoires'}), 400

    if Classe.query.filter_by(code=data['code']).first():
        return jsonify({'error': 'code deja utilisé'}), 400

    c = Classe(nom=data['nom'], code=data['code'], description=data.get('description'))
    db.session.add(c)
    db.session.commit()

    return jsonify({'message': 'classe créée', 'classe': c.to_dict()}), 201


# --- promotions ---

@app.route('/planning/promotions', methods=['GET'])
@token_required
def get_promotions(user):
    # filtre par classe si demandé
    q = Promotion.query
    if request.args.get('classe_id'):
        q = q.filter_by(classe_id=request.args.get('classe_id', type=int))
    promotions = q.all()
    return jsonify({'promotions': [p.to_dict() for p in promotions]}), 200


@app.route('/planning/promotions/<int:id>', methods=['GET'])
@token_required
def voir_promotion(user, id):
    p = Promotion.query.get_or_404(id)
    return jsonify(p.to_dict(avec_etudiants=True)), 200


@app.route('/planning/promotions', methods=['POST'])
@token_required
def creer_promotion(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403

    data = request.get_json()
    if not data.get('nom') or not data.get('annee') or not data.get('classe_id'):
        return jsonify({'error': 'nom, annee et classe_id obligatoires'}), 400

    # verif que la classe existe
    if not Classe.query.get(data['classe_id']):
        return jsonify({'error': 'classe introuvable'}), 404

    p = Promotion(nom=data['nom'], annee=data['annee'], classe_id=data['classe_id'])
    db.session.add(p)
    db.session.commit()

    return jsonify({'message': 'promotion créée', 'promotion': p.to_dict()}), 201


# --- etudiants ---

@app.route('/planning/etudiants', methods=['GET'])
@token_required
def get_etudiants(user):
    q = Etudiant.query.filter_by(is_active=True)
    if request.args.get('promotion_id'):
        q = q.filter_by(promotion_id=request.args.get('promotion_id', type=int))
    etudiants = q.all()
    return jsonify({'etudiants': [e.to_dict() for e in etudiants]}), 200


@app.route('/planning/etudiants', methods=['POST'])
@token_required
def ajouter_etudiant(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403

    data = request.get_json()
    for champ in ['nom', 'prenom', 'email', 'promotion_id']:
        if not data.get(champ):
            return jsonify({'error': 'champ manquant : ' + champ}), 400

    if Etudiant.query.filter_by(email=data['email'].lower()).first():
        return jsonify({'error': 'email deja utilisé'}), 400

    if not Promotion.query.get(data['promotion_id']):
        return jsonify({'error': 'promotion introuvable'}), 404

    e = Etudiant(
        nom=data['nom'],
        prenom=data['prenom'],
        email=data['email'].lower(),
        numero_etudiant=data.get('numero_etudiant'),
        promotion_id=data['promotion_id']
    )
    db.session.add(e)
    db.session.commit()

    return jsonify({'message': 'etudiant ajouté', 'etudiant': e.to_dict()}), 201


# ajout en masse depuis un csv/liste (admin)
@app.route('/planning/etudiants/import', methods=['POST'])
@token_required
def importer_etudiants(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403

    data = request.get_json()
    etudiants_data = data.get('etudiants', [])
    promotion_id = data.get('promotion_id')

    if not promotion_id or not Promotion.query.get(promotion_id):
        return jsonify({'error': 'promotion_id invalide'}), 400

    nb_ajoutes = 0
    nb_ignores = 0
    for ed in etudiants_data:
        if not ed.get('nom') or not ed.get('prenom') or not ed.get('email'):
            nb_ignores += 1
            continue
        if Etudiant.query.filter_by(email=ed['email'].lower()).first():
            nb_ignores += 1
            continue
        e = Etudiant(
            nom=ed['nom'],
            prenom=ed['prenom'],
            email=ed['email'].lower(),
            numero_etudiant=ed.get('numero_etudiant'),
            promotion_id=promotion_id
        )
        db.session.add(e)
        nb_ajoutes += 1

    db.session.commit()
    return jsonify({'message': str(nb_ajoutes) + ' etudiants ajoutés, ' + str(nb_ignores) + ' ignorés'}), 201


@app.route('/planning/etudiants/<int:id>', methods=['PUT'])
@token_required
def modifier_etudiant(user, id):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403

    e = Etudiant.query.get_or_404(id)
    data = request.get_json()

    if 'nom' in data: e.nom = data['nom']
    if 'prenom' in data: e.prenom = data['prenom']
    if 'promotion_id' in data: e.promotion_id = data['promotion_id']
    if 'is_active' in data: e.is_active = data['is_active']

    db.session.commit()
    return jsonify({'message': 'etudiant modifié', 'etudiant': e.to_dict()}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("tables planning créées")
    app.run(host='0.0.0.0', port=5002, debug=True)
