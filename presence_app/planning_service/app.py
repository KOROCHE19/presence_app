# service planning - gere les classes, promotions et la liste des etudiants
# l'admin ajoute les etudiants ici, les formateurs peuvent juste lire

import os
import io
import jwt
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import openpyxl

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


# import depuis un fichier CSV uploadé
# format attendu : nom,prenom,email,numero_etudiant (numero optionnel)
# la premiere ligne peut etre un header, elle est ignoree si elle contient "nom" ou "prenom"
@app.route('/planning/etudiants/import-csv', methods=['POST'])
@token_required
def importer_csv(user):
    if user.get('role') != 'admin':
        return jsonify({'error': 'admin seulement'}), 403

    promotion_id = request.form.get('promotion_id', type=int)
    if not promotion_id or not Promotion.query.get(promotion_id):
        return jsonify({'error': 'promotion_id invalide'}), 400

    if 'fichier' not in request.files:
        return jsonify({'error': 'pas de fichier envoyé'}), 400

    fichier = request.files['fichier']
    if fichier.filename == '':
        return jsonify({'error': 'fichier vide'}), 400

    nom_fichier = fichier.filename.lower()

    # --- fichier Excel (.xlsx ou .xls) ---
    if nom_fichier.endswith('.xlsx') or nom_fichier.endswith('.xls'):
        return _importer_depuis_excel(fichier, promotion_id)

    # --- fichier CSV (défaut) ---
    contenu = fichier.read().decode('utf-8', errors='ignore')
    lignes = contenu.strip().split('\n')
    return _importer_depuis_lignes_csv(lignes, promotion_id)


def _importer_depuis_excel(fichier, promotion_id):
    """Lit un fichier Excel et importe les étudiants.
    Colonnes attendues (dans l'ordre) : nom, prenom, email, numero_etudiant (optionnel).
    La première ligne est ignorée si elle contient des en-têtes."""
    nb_ajoutes = 0
    nb_ignores = 0
    erreurs = []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        ws = wb.active
        lignes = list(ws.iter_rows(values_only=True))
    except Exception as ex:
        return jsonify({'error': 'impossible de lire le fichier Excel : ' + str(ex)}), 400

    for i, row in enumerate(lignes):
        # convertir chaque cellule en chaîne propre
        cols = [str(c).strip() if c is not None else '' for c in row]

        # ignorer la ligne d'en-tête
        if i == 0 and any(mot in ' '.join(cols[:3]).lower() for mot in ['nom', 'prenom', 'email']):
            continue

        if len(cols) < 3:
            erreurs.append('ligne ' + str(i+1) + ' ignorée (pas assez de colonnes)')
            nb_ignores += 1
            continue

        nom, prenom, email = cols[0], cols[1], cols[2].lower()
        numero = cols[3] if len(cols) > 3 and cols[3] else None

        if not nom or not prenom or not email or '@' not in email:
            erreurs.append('ligne ' + str(i+1) + ' ignorée (données invalides)')
            nb_ignores += 1
            continue

        if Etudiant.query.filter_by(email=email).first():
            erreurs.append('ligne ' + str(i+1) + ' ignorée (email deja existant) : ' + email)
            nb_ignores += 1
            continue

        db.session.add(Etudiant(
            nom=nom, prenom=prenom, email=email,
            numero_etudiant=numero, promotion_id=promotion_id
        ))
        nb_ajoutes += 1

    db.session.commit()
    return jsonify({
        'message': str(nb_ajoutes) + ' etudiants importés, ' + str(nb_ignores) + ' ignorés',
        'nb_ajoutes': nb_ajoutes,
        'nb_ignores': nb_ignores,
        'erreurs': erreurs
    }), 201


def _importer_depuis_lignes_csv(lignes, promotion_id):
    """Traitement CSV (logique originale extraite pour la réutiliser)."""
    nb_ajoutes = 0
    nb_ignores = 0
    erreurs = []

    for i, ligne in enumerate(lignes):
        ligne = ligne.strip()
        if not ligne:
            continue

        # detecter et ignorer la ligne de header
        if i == 0 and ('nom' in ligne.lower() or 'prenom' in ligne.lower() or 'email' in ligne.lower()):
            continue

        # support virgule et point-virgule comme separateur
        if ';' in ligne:
            cols = ligne.split(';')
        else:
            cols = ligne.split(',')

        cols = [c.strip().strip('"') for c in cols]

        if len(cols) < 3:
            erreurs.append('ligne ' + str(i+1) + ' ignorée (pas assez de colonnes) : ' + ligne)
            nb_ignores += 1
            continue

        nom = cols[0]
        prenom = cols[1]
        email = cols[2].lower()
        numero = cols[3] if len(cols) > 3 and cols[3] else None

        if not nom or not prenom or not email or '@' not in email:
            erreurs.append('ligne ' + str(i+1) + ' ignorée (données invalides)')
            nb_ignores += 1
            continue

        if Etudiant.query.filter_by(email=email).first():
            erreurs.append('ligne ' + str(i+1) + ' ignorée (email deja existant) : ' + email)
            nb_ignores += 1
            continue

        e = Etudiant(
            nom=nom,
            prenom=prenom,
            email=email,
            numero_etudiant=numero,
            promotion_id=promotion_id
        )
        db.session.add(e)
        nb_ajoutes += 1

    db.session.commit()
    return jsonify({
        'message': str(nb_ajoutes) + ' etudiants importés, ' + str(nb_ignores) + ' ignorés',
        'nb_ajoutes': nb_ajoutes,
        'nb_ignores': nb_ignores,
        'erreurs': erreurs
    }), 201


@app.route('/planning/etudiants/<int:id>', methods=['GET'])
@token_required
def voir_etudiant(user, id):
    e = Etudiant.query.get_or_404(id)
    return jsonify(e.to_dict()), 200


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