"""
planning_service - Cours, promotions et import des etudiants

Ce service est la source de verite pour tout ce qui concerne l'organisation
pedagogique : quelles classes existent, quels groupes, quels etudiants.
L'emargement_service l'appelle pour savoir qui doit etre present a chaque session.

Port : 5002
Base : planning_db (PostgreSQL)
"""

import os
import io
import csv
import jwt
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import openpyxl

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://planning_user:planning_pass@localhost:5432/planning_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

# Limite anti-DoS pour les imports. Au-dela, on refuse le fichier.
IMPORT_MAX_LIGNES = 5000

db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# Modeles
# ---------------------------------------------------------------------------

class Classe(db.Model):
    """
    Une filiere complete : DevOps, DevWeb, Secretariat, Communication...
    Une classe regroupe plusieurs promotions (groupes annuels).
    """
    __tablename__ = 'classes'

    id          = db.Column(db.Integer, primary_key=True)
    nom         = db.Column(db.String(100), nullable=False)
    code        = db.Column(db.String(20), unique=True, nullable=False)
    description = db.Column(db.Text)

    promotions  = db.relationship('Promotion', backref='classe', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'nom': self.nom,
            'code': self.code,
            'description': self.description,
            'nb_promotions': len(self.promotions)
        }


class Promotion(db.Model):
    """
    Un groupe au sein d'une classe pour une annee donnee.
    Ex : DevOps 2025-2026 Groupe A.
    """
    __tablename__ = 'promotions'

    id        = db.Column(db.Integer, primary_key=True)
    nom       = db.Column(db.String(100), nullable=False)
    annee     = db.Column(db.String(20), nullable=False)
    classe_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)

    etudiants = db.relationship('Etudiant', backref='promotion', lazy=True)

    def to_dict(self, avec_etudiants=False):
        d = {
            'id': self.id,
            'nom': self.nom,
            'annee': self.annee,
            'classe_id': self.classe_id,
            'classe_nom': self.classe.nom if self.classe else None,
            'nb_etudiants': len([e for e in self.etudiants if e.is_active])
        }
        if avec_etudiants:
            d['etudiants'] = [e.to_dict() for e in self.etudiants if e.is_active]
        return d


class Etudiant(db.Model):
    """
    Un etudiant inscrit dans une promotion.
    is_active permet une desactivation douce conforme au RGPD :
    on ne supprime pas, on masque.
    """
    __tablename__ = 'etudiants'

    id               = db.Column(db.Integer, primary_key=True)
    nom              = db.Column(db.String(80), nullable=False)
    prenom           = db.Column(db.String(80), nullable=False)
    email            = db.Column(db.String(120), unique=True, nullable=False)
    numero_etudiant  = db.Column(db.String(20), unique=True, nullable=True)
    promotion_id     = db.Column(db.Integer, db.ForeignKey('promotions.id'), nullable=False)
    is_active        = db.Column(db.Boolean, default=True)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

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


# ---------------------------------------------------------------------------
# Decorateurs d'authentification
# ---------------------------------------------------------------------------

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth = request.headers.get('Authorization', '')
        parties = auth.split(' ')
        if len(parties) == 2 and parties[0] == 'Bearer':
            token = parties[1]

        if not token:
            return jsonify({'error': 'token manquant'}), 401
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.InvalidTokenError:
            return jsonify({'error': 'token invalide'}), 401

        return f(payload, *args, **kwargs)
    return decorated


def admin_seulement(f):
    @wraps(f)
    @token_required
    def decorated(user, *args, **kwargs):
        if user.get('role') != 'admin':
            return jsonify({'error': 'droits administrateur requis'}), 403
        return f(user, *args, **kwargs)
    return decorated


@app.after_request
def headers_cors(r):
    r.headers['Access-Control-Allow-Origin']  = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return r

@app.before_request
def preflight():
    if request.method == 'OPTIONS':
        return jsonify({}), 200


# ---------------------------------------------------------------------------
# Routes - sante
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status': 'ok', 'service': 'planning_service'}), 200
    except Exception as e:
        return jsonify({'status': 'erreur', 'detail': str(e)}), 503


# ---------------------------------------------------------------------------
# Routes - classes
# ---------------------------------------------------------------------------

@app.route('/planning/classes', methods=['GET'])
@token_required
def get_classes(user):
    classes = Classe.query.order_by(Classe.nom).all()
    return jsonify({'classes': [c.to_dict() for c in classes]}), 200


@app.route('/planning/classes', methods=['POST'])
@admin_seulement
def creer_classe(admin):
    data = request.get_json() or {}
    if not data.get('nom') or not data.get('code'):
        return jsonify({'error': 'nom et code obligatoires'}), 400

    code = data['code'].upper().strip()
    if Classe.query.filter_by(code=code).first():
        return jsonify({'error': 'ce code est deja utilise'}), 409

    c = Classe(nom=data['nom'].strip(), code=code, description=data.get('description'))
    db.session.add(c)
    db.session.commit()
    return jsonify({'message': 'classe creee', 'classe': c.to_dict()}), 201


# ---------------------------------------------------------------------------
# Routes - promotions
# ---------------------------------------------------------------------------

@app.route('/planning/promotions', methods=['GET'])
@token_required
def get_promotions(user):
    q = Promotion.query
    if request.args.get('classe_id'):
        q = q.filter_by(classe_id=request.args.get('classe_id', type=int))
    return jsonify({'promotions': [p.to_dict() for p in q.order_by(Promotion.annee.desc(), Promotion.nom).all()]}), 200


@app.route('/planning/promotions/<int:pid>', methods=['GET'])
@token_required
def voir_promotion(user, pid):
    p = Promotion.query.get_or_404(pid)
    return jsonify(p.to_dict(avec_etudiants=True)), 200


@app.route('/planning/promotions', methods=['POST'])
@admin_seulement
def creer_promotion(admin):
    data = request.get_json() or {}
    for champ in ['nom', 'annee', 'classe_id']:
        if not data.get(champ):
            return jsonify({'error': f'champ manquant : {champ}'}), 400

    if not Classe.query.get(data['classe_id']):
        return jsonify({'error': 'classe introuvable'}), 404

    p = Promotion(nom=data['nom'], annee=data['annee'], classe_id=data['classe_id'])
    db.session.add(p)
    db.session.commit()
    return jsonify({'message': 'promotion creee', 'promotion': p.to_dict()}), 201


@app.route('/planning/promotions/<int:pid>', methods=['PUT'])
@admin_seulement
def modifier_promotion(admin, pid):
    p = Promotion.query.get_or_404(pid)
    data = request.get_json() or {}
    if 'nom' in data:
        p.nom = data['nom']
    if 'annee' in data:
        p.annee = data['annee']
    db.session.commit()
    return jsonify({'message': 'promotion mise a jour', 'promotion': p.to_dict()}), 200


# ---------------------------------------------------------------------------
# Routes - etudiants
# ---------------------------------------------------------------------------

@app.route('/planning/etudiants', methods=['GET'])
@token_required
def get_etudiants(user):
    q = Etudiant.query.filter_by(is_active=True)
    if request.args.get('promotion_id'):
        q = q.filter_by(promotion_id=request.args.get('promotion_id', type=int))
    etudiants = q.order_by(Etudiant.nom, Etudiant.prenom).all()
    return jsonify({'etudiants': [e.to_dict() for e in etudiants]}), 200


@app.route('/planning/etudiants/<int:eid>', methods=['GET'])
@token_required
def voir_etudiant(user, eid):
    e = Etudiant.query.get_or_404(eid)
    return jsonify(e.to_dict()), 200


@app.route('/planning/etudiants', methods=['POST'])
@admin_seulement
def ajouter_etudiant(admin):
    data = request.get_json() or {}
    for champ in ['nom', 'prenom', 'email', 'promotion_id']:
        if not data.get(champ):
            return jsonify({'error': f'champ manquant : {champ}'}), 400

    email = data['email'].lower().strip()
    if Etudiant.query.filter_by(email=email).first():
        return jsonify({'error': 'cet email est deja utilise'}), 409

    if not Promotion.query.get(data['promotion_id']):
        return jsonify({'error': 'promotion introuvable'}), 404

    e = Etudiant(
        nom=data['nom'].strip(),
        prenom=data['prenom'].strip(),
        email=email,
        numero_etudiant=data.get('numero_etudiant') or None,
        promotion_id=data['promotion_id']
    )
    db.session.add(e)
    db.session.commit()
    return jsonify({'message': 'etudiant ajoute', 'etudiant': e.to_dict()}), 201


@app.route('/planning/etudiants/<int:eid>', methods=['PUT'])
@admin_seulement
def modifier_etudiant(admin, eid):
    e = Etudiant.query.get_or_404(eid)
    data = request.get_json() or {}

    if 'nom' in data:
        e.nom = data['nom']
    if 'prenom' in data:
        e.prenom = data['prenom']
    if 'promotion_id' in data:
        if not Promotion.query.get(data['promotion_id']):
            return jsonify({'error': 'promotion introuvable'}), 404
        e.promotion_id = data['promotion_id']
    if 'is_active' in data:
        e.is_active = data['is_active']

    db.session.commit()
    return jsonify({'message': 'etudiant modifie', 'etudiant': e.to_dict()}), 200


# ---------------------------------------------------------------------------
# Import CSV / Excel
# ---------------------------------------------------------------------------

# Noms de colonnes acceptes par le moteur d'import, peu importe la casse
# ou les variantes d'intitule selon l'origine du fichier.
ALIAS_COLONNES = {
    'nom':              ['nom', 'lastname', 'name', 'family_name'],
    'prenom':           ['prenom', 'firstname', 'first_name', 'given_name'],
    'email':            ['email', 'mail', 'courriel', 'e-mail'],
    'numero_etudiant':  ['numero_etudiant', 'numero', 'id_etudiant', 'student_id', 'num'],
}


def detecter_mapping_colonnes(entete):
    """
    A partir d'une liste de noms de colonnes extraite du fichier,
    retourne un dictionnaire { nom_interne: index_colonne }.
    Permet d'accepter 'Email', 'MAIL', 'courriel' sans modifier le fichier source.
    """
    mapping = {}
    for nom_interne, alias_liste in ALIAS_COLONNES.items():
        for idx, col in enumerate(entete):
            if col.strip().lower() in alias_liste:
                mapping[nom_interne] = idx
                break
    return mapping


def traiter_rangee(rang, mapping, num_ligne):
    """
    Extrait et valide les champs d'une rangee selon le mapping detecte.
    Retourne (dict_etudiant, message_erreur).
    """
    def cellule(cle, defaut=''):
        idx = mapping.get(cle)
        if idx is None or idx >= len(rang):
            return defaut
        val = rang[idx]
        return str(val).strip() if val is not None else defaut

    nom   = cellule('nom')
    prenom = cellule('prenom')
    email  = cellule('email').lower()
    numero = cellule('numero_etudiant') or None

    if not nom or not prenom:
        return None, f'ligne {num_ligne} : nom ou prenom vide'
    if not email or '@' not in email:
        return None, f'ligne {num_ligne} : email invalide ({email!r})'

    return {'nom': nom, 'prenom': prenom, 'email': email, 'numero_etudiant': numero}, None


@app.route('/planning/etudiants/import-csv', methods=['POST'])
@admin_seulement
def importer_etudiants(admin):
    """
    Import en masse depuis un CSV ou un Excel.
    Retourne un rapport JSON detaille meme en cas d'erreurs partielles
    (mode best-effort : on insere ce qu'on peut).

    Rapport retourne :
      inseres, ignores, doublons_fichier, doublons_base, erreurs (liste)
    """
    promotion_id = request.form.get('promotion_id', type=int)
    if not promotion_id or not Promotion.query.get(promotion_id):
        return jsonify({'error': 'promotion_id invalide ou introuvable'}), 400

    if 'fichier' not in request.files:
        return jsonify({'error': 'aucun fichier envoye'}), 400

    fichier = request.files['fichier']
    if not fichier.filename:
        return jsonify({'error': 'fichier vide'}), 400

    nom_lower = fichier.filename.lower()
    if nom_lower.endswith('.xlsx') or nom_lower.endswith('.xls'):
        return _import_excel(fichier, promotion_id)
    else:
        return _import_csv(fichier, promotion_id)


def _import_csv(fichier, promotion_id):
    contenu = fichier.read().decode('utf-8', errors='replace')
    lignes_brutes = contenu.splitlines()

    if len(lignes_brutes) > IMPORT_MAX_LIGNES + 1:
        return jsonify({'error': f'fichier trop grand (max {IMPORT_MAX_LIGNES} lignes)'}), 400

    # csv.Sniffer detecte automatiquement virgule ou point-virgule
    echantillon = '\n'.join(lignes_brutes[:20])
    try:
        dialect = csv.Sniffer().sniff(echantillon, delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel  # fallback virgule si la detection echoue

    lecteur = csv.reader(lignes_brutes, dialect)
    rangees = list(lecteur)

    if not rangees:
        return jsonify({'error': 'fichier CSV vide'}), 400

    # La premiere ligne est un header si elle contient "nom", "prenom" ou "email"
    premiere = [c.strip().lower() for c in rangees[0]]
    if any(mot in premiere for mot in ['nom', 'prenom', 'email', 'name', 'mail']):
        entete  = rangees[0]
        donnees = rangees[1:]
    else:
        # Pas de header : on suppose l'ordre nom, prenom, email, numero
        entete  = ['nom', 'prenom', 'email', 'numero_etudiant']
        donnees = rangees

    mapping = detecter_mapping_colonnes(entete)
    # Fallback si la detection par nom de colonne n'a rien trouve :
    # on suppose l'ordre positonnel standard
    if 'nom' not in mapping:
        mapping = {'nom': 0, 'prenom': 1, 'email': 2, 'numero_etudiant': 3}

    return _inserer_etudiants(donnees, mapping, promotion_id)


def _import_excel(fichier, promotion_id):
    try:
        wb = openpyxl.load_workbook(io.BytesIO(fichier.read()), read_only=True, data_only=True)
        ws = wb.active
        rangees = list(ws.iter_rows(values_only=True))
    except Exception as ex:
        return jsonify({'error': f'impossible de lire le fichier Excel : {ex}'}), 400

    if not rangees:
        return jsonify({'error': 'fichier Excel vide'}), 400

    if len(rangees) > IMPORT_MAX_LIGNES + 1:
        return jsonify({'error': f'fichier trop grand (max {IMPORT_MAX_LIGNES} lignes)'}), 400

    # Detection header : memes regles que CSV
    premiere = [str(c).strip().lower() if c else '' for c in rangees[0]]
    if any(mot in premiere for mot in ['nom', 'prenom', 'email', 'name', 'mail']):
        entete  = [str(c) if c else '' for c in rangees[0]]
        donnees = [list(r) for r in rangees[1:]]
    else:
        entete  = ['nom', 'prenom', 'email', 'numero_etudiant']
        donnees = [list(r) for r in rangees]

    mapping = detecter_mapping_colonnes(entete)
    if 'nom' not in mapping:
        mapping = {'nom': 0, 'prenom': 1, 'email': 2, 'numero_etudiant': 3}

    return _inserer_etudiants(donnees, mapping, promotion_id)


def _inserer_etudiants(donnees, mapping, promotion_id):
    """
    Boucle d'insertion commune a CSV et Excel.
    On distingue trois types de rejets pour le rapport :
      - erreur de format (donnees invalides)
      - doublon dans le fichier (meme email vu deux fois dans le batch)
      - doublon en base (email deja enregistre)
    """
    inseres          = 0
    erreurs          = []
    emails_du_batch  = set()   # pour detecter les doublons dans le meme fichier
    doublons_fichier = 0
    doublons_base    = 0

    for num, rang in enumerate(donnees, start=2):
        # Ignorer les lignes completement vides
        valeurs = [str(v).strip() for v in rang if v is not None and str(v).strip()]
        if not valeurs:
            continue

        etudiant, err = traiter_rangee(rang, mapping, num)
        if err:
            erreurs.append(err)
            continue

        email = etudiant['email']

        # Doublon dans le batch courant
        if email in emails_du_batch:
            erreurs.append(f'ligne {num} : email deja vu dans ce fichier ({email})')
            doublons_fichier += 1
            continue

        # Doublon en base de donnees
        if Etudiant.query.filter_by(email=email).first():
            erreurs.append(f'ligne {num} : email deja en base ({email})')
            doublons_base += 1
            continue

        emails_du_batch.add(email)
        db.session.add(Etudiant(
            nom=etudiant['nom'],
            prenom=etudiant['prenom'],
            email=email,
            numero_etudiant=etudiant['numero_etudiant'],
            promotion_id=promotion_id
        ))
        inseres += 1

    db.session.commit()

    return jsonify({
        'message': f'{inseres} etudiant(s) importe(s)',
        'inseres':          inseres,
        'doublons_fichier': doublons_fichier,
        'doublons_base':    doublons_base,
        'ignores':          doublons_fichier + doublons_base + (len(erreurs) - doublons_fichier - doublons_base),
        'erreurs':          erreurs
    }), 201


# ---------------------------------------------------------------------------
# Demarrage
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print('planning_service demarre. Tables creees.')
    app.run(host='0.0.0.0', port=5002, debug=True)
