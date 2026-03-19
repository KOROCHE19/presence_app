# emargement_service/app.py  —  v2
# Améliorations : pagination sur /sessions + gunicorn (plus de debug=True)

import os
import logging
import jwt
import requests
import smtplib
from datetime import datetime
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] emargement_service — %(message)s'
)
logger = logging.getLogger(__name__)

# ── app ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'postgresql://emarg_user:emarg_pass@localhost:5432/emarg_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

PLANNING_URL  = os.environ.get('PLANNING_SERVICE_URL', 'http://planning_service:5002')
MAIL_SERVER   = os.environ.get('MAIL_SERVER',   'smtp.gmail.com')
MAIL_PORT     = int(os.environ.get('MAIL_PORT', '587'))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_SENDER   = os.environ.get('MAIL_SENDER',   'noreply@ecole.fr')

db = SQLAlchemy(app)


# ── mail ──────────────────────────────────────────────────────────────────────
def envoyer_mail_absence(email_etudiant, prenom, nom, matiere, date, heure):
    sujet = f"Absence enregistrée - {matiere} du {date}"

    corps_html = f"""
    <div style="font-family:Arial; max-width:500px; margin:auto; border:1px solid #eee; border-radius:8px; overflow:hidden;">
        <div style="background:#2c3e50; color:white; padding:20px;">
            <h2 style="margin:0;">Gestion des Présences</h2>
        </div>
        <div style="padding:20px;">
            <p>Bonjour <b>{prenom} {nom}</b>,</p>
            <p>Vous avez été marqué(e) <b style="color:#e74c3c;">absent(e)</b> au cours suivant :</p>
            <ul>
                <li><b>Matière :</b> {matiere}</li>
                <li><b>Date :</b> {date}</li>
                <li><b>Heure :</b> {heure}</li>
            </ul>
            <p>Si cette absence est injustifiée ou s'il y a une erreur,
            contactez votre formateur ou l'administration.</p>
            <p>Cordialement,<br>L'équipe pédagogique</p>
        </div>
    </div>
    """

    if not MAIL_USERNAME or not MAIL_PASSWORD:
        logger.info('[SIMULATION MAIL] vers %s : %s', email_etudiant, sujet)
        return True

    try:
        msg            = MIMEMultipart('alternative')
        msg['From']    = MAIL_SENDER
        msg['To']      = email_etudiant
        msg['Subject'] = sujet
        msg.attach(MIMEText(corps_html, 'html', 'utf-8'))

        serveur = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        serveur.starttls()
        serveur.login(MAIL_USERNAME, MAIL_PASSWORD)
        serveur.sendmail(MAIL_SENDER, email_etudiant, msg.as_string())
        serveur.quit()

        logger.info('Mail envoyé à %s', email_etudiant)
        return True
    except Exception as e:
        logger.error('Erreur envoi mail à %s : %s', email_etudiant, e)
        return False


# ── modèles ───────────────────────────────────────────────────────────────────
class Session(db.Model):
    __tablename__ = 'sessions'
    id            = db.Column(db.Integer, primary_key=True)
    promotion_id  = db.Column(db.Integer, nullable=False)
    promotion_nom = db.Column(db.String(100))
    matiere       = db.Column(db.String(100), nullable=False)
    formateur_id  = db.Column(db.Integer, nullable=False)
    formateur_nom = db.Column(db.String(100))
    date          = db.Column(db.Date, nullable=False)
    heure_debut   = db.Column(db.String(10), nullable=False)
    heure_fin     = db.Column(db.String(10), nullable=False)
    statut        = db.Column(db.String(20), default='ouverte')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    presences = db.relationship('Presence', backref='session', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, avec_presences=False):
        d = {
            'id':            self.id,
            'promotion_id':  self.promotion_id,
            'promotion_nom': self.promotion_nom,
            'matiere':       self.matiere,
            'formateur_id':  self.formateur_id,
            'formateur_nom': self.formateur_nom,
            'date':          str(self.date),
            'heure_debut':   self.heure_debut,
            'heure_fin':     self.heure_fin,
            'statut':        self.statut,
            'nb_presents':   len([p for p in self.presences if p.statut == 'present']),
            'nb_absents':    len([p for p in self.presences if p.statut == 'absent']),
            'nb_total':      len(self.presences),
        }
        if avec_presences:
            d['presences'] = [p.to_dict() for p in self.presences]
        return d


class Presence(db.Model):
    __tablename__ = 'presences'
    id              = db.Column(db.Integer, primary_key=True)
    session_id      = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    etudiant_id     = db.Column(db.Integer, nullable=False)
    etudiant_nom    = db.Column(db.String(100))
    etudiant_prenom = db.Column(db.String(100))
    statut          = db.Column(db.String(20), default='absent')
    commentaire     = db.Column(db.Text)
    saisi_a         = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id':              self.id,
            'session_id':      self.session_id,
            'etudiant_id':     self.etudiant_id,
            'etudiant_nom':    self.etudiant_nom,
            'etudiant_prenom': self.etudiant_prenom,
            'statut':          self.statut,
            'commentaire':     self.commentaire,
            'saisi_a':         self.saisi_a.isoformat() if self.saisi_a else None,
        }


# ── décorateur JWT ────────────────────────────────────────────────────────────
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth  = request.headers.get('Authorization', '')
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
    return jsonify({'status': 'ok', 'service': 'emargement'}), 200


@app.route('/emargement/sessions', methods=['GET'])
@token_required
def get_sessions(user):
    """
    AMÉLIORATION 3 — Pagination des sessions
    Paramètres :
      - promotion_id, formateur_id, date : filtres optionnels
      - page     : numéro de page (défaut 1)
      - per_page : taille de page (défaut 20, max 100)
    """
    q = Session.query

    if request.args.get('promotion_id'):
        q = q.filter_by(promotion_id=request.args.get('promotion_id', type=int))
    if request.args.get('formateur_id'):
        q = q.filter_by(formateur_id=request.args.get('formateur_id', type=int))
    if request.args.get('date'):
        q = q.filter_by(date=request.args.get('date'))

    q = q.order_by(Session.date.desc())

    page     = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)

    pagination = q.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'sessions': [s.to_dict() for s in pagination.items],
        'total':    pagination.total,
        'pages':    pagination.pages,
        'page':     page,
        'per_page': per_page,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev,
    }), 200


@app.route('/emargement/sessions', methods=['POST'])
@token_required
def creer_session(user):
    data = request.get_json()
    for champ in ['promotion_id', 'matiere', 'date', 'heure_debut', 'heure_fin']:
        if not data.get(champ):
            return jsonify({'error': f'champ manquant : {champ}'}), 400

    promo_nom = None
    try:
        token = request.headers['Authorization'].split(' ')[1]
        rep   = requests.get(
            f"{PLANNING_URL}/planning/promotions/{data['promotion_id']}",
            headers={'Authorization': f'Bearer {token}'},
            timeout=3,
        )
        if rep.status_code == 200:
            promo_nom = rep.json().get('nom')
    except Exception as e:
        logger.warning('Impossible de récupérer le nom de la promo : %s', e)

    s = Session(
        promotion_id  = data['promotion_id'],
        promotion_nom = promo_nom,
        matiere       = data['matiere'],
        formateur_id  = user['user_id'],
        formateur_nom = user.get('nom', '') + ' ' + user.get('prenom', ''),
        date          = datetime.strptime(data['date'], '%Y-%m-%d').date(),
        heure_debut   = data['heure_debut'],
        heure_fin     = data['heure_fin'],
        statut        = 'ouverte',
    )
    db.session.add(s)
    db.session.commit()

    # Récupère tous les étudiants (sans pagination — appel interne)
    try:
        token = request.headers['Authorization'].split(' ')[1]
        rep   = requests.get(
            f"{PLANNING_URL}/planning/etudiants",
            params={'promotion_id': data['promotion_id'], 'all': 'true'},
            headers={'Authorization': f'Bearer {token}'},
            timeout=5,
        )
        if rep.status_code == 200:
            etudiants = rep.json().get('etudiants', [])
            for e in etudiants:
                db.session.add(Presence(
                    session_id      = s.id,
                    etudiant_id     = e['id'],
                    etudiant_nom    = e['nom'],
                    etudiant_prenom = e['prenom'],
                    statut          = 'absent',
                ))
            db.session.commit()
            logger.info('%d présences créées pour la session %d', len(etudiants), s.id)
    except Exception as e:
        logger.error('Erreur récupération étudiants : %s', e)

    return jsonify({'message': 'session créée', 'session': s.to_dict(avec_presences=True)}), 201


@app.route('/emargement/sessions/<int:id>', methods=['GET'])
@token_required
def voir_session(user, id):
    s = Session.query.get_or_404(id)
    return jsonify(s.to_dict(avec_presences=True)), 200


@app.route('/emargement/sessions/<int:id>/fermer', methods=['POST'])
@token_required
def fermer_session(user, id):
    s = Session.query.get_or_404(id)

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'vous n\'êtes pas le formateur de cette session'}), 403

    if s.statut == 'fermée':
        return jsonify({'error': 'session déjà fermée'}), 400

    s.statut = 'fermée'
    db.session.commit()

    absents  = [p for p in s.presences if p.statut == 'absent']
    nb_mails = 0
    token    = request.headers.get('Authorization', '').split(' ')[-1]

    for p in absents:
        email_etudiant = None
        try:
            rep = requests.get(
                f"{PLANNING_URL}/planning/etudiants/{p.etudiant_id}",
                headers={'Authorization': f'Bearer {token}'},
                timeout=3,
            )
            if rep.status_code == 200:
                email_etudiant = rep.json().get('email')
        except Exception as e:
            logger.warning('Impossible de récupérer email étudiant %d : %s', p.etudiant_id, e)

        if not email_etudiant:
            logger.warning('Pas d\'email pour étudiant %d, mail non envoyé', p.etudiant_id)
            continue

        ok = envoyer_mail_absence(
            email_etudiant,
            p.etudiant_prenom or '',
            p.etudiant_nom    or '',
            s.matiere,
            str(s.date),
            f"{s.heure_debut} - {s.heure_fin}",
        )
        if ok:
            nb_mails += 1

    logger.info('Session %d fermée — %d mails envoyés', s.id, nb_mails)
    return jsonify({
        'message':       f'session fermée, {nb_mails} mails envoyés',
        'session':       s.to_dict(),
        'mails_envoyes': nb_mails,
    }), 200


@app.route('/emargement/presences/<int:id>', methods=['PUT'])
@token_required
def modifier_presence(user, id):
    p = Presence.query.get_or_404(id)
    s = Session.query.get(p.session_id)

    if s.statut == 'fermée':
        return jsonify({'error': 'session fermée, impossible de modifier'}), 400

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'accès refusé'}), 403

    data = request.get_json()
    if 'statut' in data:
        if data['statut'] not in ['present', 'absent', 'retard', 'excusé']:
            return jsonify({'error': 'statut invalide'}), 400
        p.statut = data['statut']

    if 'commentaire' in data:
        p.commentaire = data['commentaire']

    p.saisi_a = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'présence modifiée', 'presence': p.to_dict()}), 200


@app.route('/emargement/sessions/<int:id>/presences', methods=['PUT'])
@token_required
def saisir_toutes_presences(user, id):
    s = Session.query.get_or_404(id)

    if s.statut == 'fermée':
        return jsonify({'error': 'session fermée'}), 400

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'accès refusé'}), 403

    data          = request.get_json()
    presences_data = data.get('presences', [])
    nb = 0

    for pd in presences_data:
        p = Presence.query.filter_by(session_id=id, etudiant_id=pd.get('etudiant_id')).first()
        if p:
            p.statut      = pd.get('statut', 'absent')
            p.commentaire = pd.get('commentaire')
            p.saisi_a     = datetime.utcnow()
            nb += 1

    db.session.commit()
    return jsonify({'message': f'{nb} présences mises à jour', 'session': s.to_dict(avec_presences=True)}), 200


# ── init DB ───────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    logger.info('Tables emargement créées / vérifiées')

# AMÉLIORATION 5 : démarrage via gunicorn — voir Dockerfile
