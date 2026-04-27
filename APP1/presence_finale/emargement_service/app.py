"""
emargement_service - Presences et notifications

C'est le coeur metier de l'application. Il gere la feuille d'appel
(session + presences), la cloture de session, et l'envoi asynchrone
des emails aux absents.

La problematique principale resolue ici : avec 20+ absents, un envoi SMTP
synchrone bloquait le thread HTTP 80-90 secondes. La solution finale utilise
ThreadPoolExecutor pour deporter l'envoi en arriere-plan, avec un retry
exponentiel (1s, 2s, 4s) et un journal dans NotificationLog.

Port : 5003
Base : emarg_db (PostgreSQL)
"""

import os
import time
import jwt
import requests
import smtplib
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://emarg_user:emarg_pass@localhost:5432/emarg_db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Le pool de connexions SQLAlchemy doit etre configure pour le multithread.
# Sans ca, les threads secondaires provoquent des erreurs aleatoires en production.
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'max_overflow': 20,
    'pool_pre_ping': True
}
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

PLANNING_URL = os.environ.get('PLANNING_SERVICE_URL', 'http://planning_service:5002')

# Config SMTP entierement pilotee par variables d'environnement.
# Aucune valeur en dur dans le code.
SMTP_HOST     = os.environ.get('MAIL_SERVER',   'smtp.gmail.com')
SMTP_PORT     = int(os.environ.get('MAIL_PORT', '587'))
SMTP_USER     = os.environ.get('MAIL_USERNAME', '')
SMTP_PASS     = os.environ.get('MAIL_PASSWORD', '')
SMTP_EXPEDITEUR = os.environ.get('MAIL_SENDER', 'noreply@ecole.fr')

# Pool de 5 workers pour l'envoi asynchrone.
# 5 connexions SMTP simultanees sont largement suffisantes pour 30 etudiants.
pool_smtp = ThreadPoolExecutor(max_workers=5)

db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# Modeles
# ---------------------------------------------------------------------------

class Session(db.Model):
    """
    Une seance de cours. Cree par un formateur ou un admin.
    Quand une session est creee, une ligne Presence est generee automatiquement
    pour chaque etudiant de la promotion (statut 'absent' par defaut).
    Une fois fermee, elle est verrouilee et les emails sont envoyes.
    """
    __tablename__ = 'sessions'

    id            = db.Column(db.Integer, primary_key=True)
    promotion_id  = db.Column(db.Integer, nullable=False)
    # On denormalise le nom de la promo pour eviter un appel HTTP supplementaire
    # a chaque affichage de liste.
    promotion_nom = db.Column(db.String(100))
    matiere       = db.Column(db.String(100), nullable=False)
    formateur_id  = db.Column(db.Integer, nullable=False)
    formateur_nom = db.Column(db.String(100))
    date          = db.Column(db.Date, nullable=False)
    heure_debut   = db.Column(db.String(10), nullable=False)
    heure_fin     = db.Column(db.String(10), nullable=False)
    # 'ouverte' -> le formateur peut encore modifier les presences
    # 'fermee'  -> verrouilee, emails envoyes, plus de modification possible
    statut        = db.Column(db.String(20), default='ouverte')
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    presences = db.relationship('Presence', backref='session', lazy=True, cascade='all, delete-orphan')

    def compteurs(self):
        """Calcul a la volee sans requete supplementaire (relations deja chargees)."""
        return {
            'presents': sum(1 for p in self.presences if p.statut == 'present'),
            'absents':  sum(1 for p in self.presences if p.statut == 'absent'),
            'retards':  sum(1 for p in self.presences if p.statut == 'retard'),
            'excuses':  sum(1 for p in self.presences if p.statut == 'excuse'),
            'total':    len(self.presences)
        }

    def to_dict(self, avec_presences=False):
        c = self.compteurs()
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
            'nb_presents':   c['presents'],
            'nb_absents':    c['absents'],
            'nb_retards':    c['retards'],
            'nb_excuses':    c['excuses'],
            'nb_total':      c['total']
        }
        if avec_presences:
            d['presences'] = [p.to_dict() for p in self.presences]
        return d


class Presence(db.Model):
    """
    Une ligne par etudiant par session. Cree automatiquement a 'absent'
    a la creation de la session. Le formateur corrige les presents.
    """
    __tablename__ = 'presences'

    id              = db.Column(db.Integer, primary_key=True)
    session_id      = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    etudiant_id     = db.Column(db.Integer, nullable=False)
    # Noms denormalises pour l'affichage rapide sans appel HTTP
    etudiant_nom    = db.Column(db.String(100))
    etudiant_prenom = db.Column(db.String(100))
    etudiant_email  = db.Column(db.String(120))  # stocke pour l'envoi mail sans appel planning
    # 4 statuts possibles, conformement aux specs du CDC
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
            'saisi_a':         self.saisi_a.isoformat() if self.saisi_a else None
        }


class NotificationLog(db.Model):
    """
    Journal des emails envoyes. Permet de verifier apres coup si un email
    a bien ete delivre et combien de tentatives ont ete necessaires.
    """
    __tablename__ = 'notification_logs'

    id          = db.Column(db.Integer, primary_key=True)
    session_id  = db.Column(db.Integer, nullable=False)
    etudiant_id = db.Column(db.Integer, nullable=False)
    email_dest  = db.Column(db.String(120))
    # 'envoye', 'echec', 'simule' (quand SMTP pas configure)
    statut      = db.Column(db.String(20), nullable=False)
    tentatives  = db.Column(db.Integer, default=1)
    erreur      = db.Column(db.Text)
    envoye_a    = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id':          self.id,
            'session_id':  self.session_id,
            'etudiant_id': self.etudiant_id,
            'email_dest':  self.email_dest,
            'statut':      self.statut,
            'tentatives':  self.tentatives,
            'erreur':      self.erreur,
            'envoye_a':    self.envoye_a.isoformat() if self.envoye_a else None
        }


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth = request.headers.get('Authorization', '')
        parties = auth.split(' ')
        if len(parties) == 2:
            token = parties[1]
        if not token:
            return jsonify({'error': 'token manquant'}), 401
        try:
            payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        except jwt.InvalidTokenError:
            return jsonify({'error': 'token invalide'}), 401
        return f(payload, *args, **kwargs)
    return decorated


@app.after_request
def headers_cors(r):
    r.headers['Access-Control-Allow-Origin']  = '*'
    r.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    r.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE, OPTIONS'
    return r

@app.before_request
def preflight():
    if request.method == 'OPTIONS':
        return jsonify({}), 200


# ---------------------------------------------------------------------------
# Pipeline d'envoi SMTP asynchrone
# ---------------------------------------------------------------------------

def construire_email_absence(prenom, nom, matiere, date_str, horaire):
    """Genere le corps HTML du mail d'absence. Assemble les variables proprement."""
    return f"""
    <div style="font-family:Arial,sans-serif; max-width:520px; margin:auto;
                border:1px solid #e0e0e0; border-radius:8px; overflow:hidden;">
        <div style="background:#2c3e50; color:white; padding:20px;">
            <h2 style="margin:0; font-size:18px;">Gestion des Presences - CNAM</h2>
        </div>
        <div style="padding:24px; color:#333;">
            <p>Bonjour <strong>{prenom} {nom}</strong>,</p>
            <p>Votre absence a ete enregistree pour le cours suivant :</p>
            <table style="margin:16px 0; border-collapse:collapse; width:100%;">
                <tr><td style="padding:6px 12px; background:#f8f9fa; font-weight:bold; width:30%;">Matiere</td>
                    <td style="padding:6px 12px;">{matiere}</td></tr>
                <tr><td style="padding:6px 12px; font-weight:bold;">Date</td>
                    <td style="padding:6px 12px;">{date_str}</td></tr>
                <tr><td style="padding:6px 12px; background:#f8f9fa; font-weight:bold;">Horaire</td>
                    <td style="padding:6px 12px; background:#f8f9fa;">{horaire}</td></tr>
            </table>
            <p>Si cette absence est injustifiee ou si vous pensez qu il y a une erreur,
            contactez votre formateur ou l administration.</p>
            <p style="margin-top:24px;">Cordialement,<br>L equipe pedagogique du CNAM</p>
        </div>
    </div>
    """


def _envoyer_avec_retry(email_dest, prenom, nom, matiere, date_str, horaire, session_id, etudiant_id):
    """
    Tache executee dans un thread du pool. Tente l'envoi jusqu'a 3 fois
    avec un backoff exponentiel (1s, 2s, 4s) avant d'abandonner.
    Loge le resultat dans NotificationLog dans tous les cas.
    """
    sujet    = f"Absence enregistree - {matiere} du {date_str}"
    corps    = construire_email_absence(prenom, nom, matiere, date_str, horaire)
    nb_essai = 0
    derniere_erreur = None

    # Simulation si SMTP non configure (dev local)
    if not SMTP_USER or not SMTP_PASS:
        print(f"[SIMULATION MAIL] -> {email_dest} : {sujet}")
        _ecrire_log(session_id, etudiant_id, email_dest, 'simule', 1, None)
        return

    delais = [1, 2, 4]
    for delai in delais:
        nb_essai += 1
        try:
            msg = MIMEMultipart('alternative')
            msg['From']    = SMTP_EXPEDITEUR
            msg['To']      = email_dest
            msg['Subject'] = sujet
            msg.attach(MIMEText(corps, 'html', 'utf-8'))

            serveur = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
            serveur.starttls()
            serveur.login(SMTP_USER, SMTP_PASS)
            serveur.sendmail(SMTP_EXPEDITEUR, email_dest, msg.as_string())
            serveur.quit()

            print(f"[MAIL OK] -> {email_dest} (tentative {nb_essai})")
            _ecrire_log(session_id, etudiant_id, email_dest, 'envoye', nb_essai, None)
            return

        except Exception as err:
            derniere_erreur = str(err)
            print(f"[MAIL ERREUR tentative {nb_essai}] {email_dest} : {err}")
            if delai != delais[-1]:
                time.sleep(delai)

    # On a epuise les tentatives
    print(f"[MAIL ECHEC DEFINITIF] {email_dest} apres {nb_essai} tentatives")
    _ecrire_log(session_id, etudiant_id, email_dest, 'echec', nb_essai, derniere_erreur)


def _ecrire_log(session_id, etudiant_id, email_dest, statut, tentatives, erreur):
    """
    Ecrit dans NotificationLog depuis un thread secondaire.
    Le contexte applicatif Flask doit etre explicitement cree dans les threads,
    sinon SQLAlchemy leve une RuntimeError (pas de contexte applicatif).
    """
    with app.app_context():
        log = NotificationLog(
            session_id  = session_id,
            etudiant_id = etudiant_id,
            email_dest  = email_dest,
            statut      = statut,
            tentatives  = tentatives,
            erreur      = erreur
        )
        db.session.add(log)
        db.session.commit()


def envoyer_mails_absents(session_id, absents, matiere, date_str, horaire):
    """
    Lance les taches d'envoi dans le pool. Retourne immediatement,
    les mails partent en arriere-plan.
    """
    for presence in absents:
        pool_smtp.submit(
            _envoyer_avec_retry,
            presence.etudiant_email or '',
            presence.etudiant_prenom or '',
            presence.etudiant_nom or '',
            matiere,
            date_str,
            horaire,
            session_id,
            presence.etudiant_id
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status': 'ok', 'service': 'emargement_service'}), 200
    except Exception as e:
        return jsonify({'status': 'erreur', 'detail': str(e)}), 503


# Sessions -------------------------------------------------------------------

@app.route('/emargement/sessions', methods=['GET'])
@token_required
def get_sessions(user):
    q = Session.query

    # Le filtrage par formateur est realise cote serveur.
    # Le frontend affiche ce que le backend retourne, sans logique propre.
    if request.args.get('formateur_id'):
        q = q.filter_by(formateur_id=request.args.get('formateur_id', type=int))
    if request.args.get('promotion_id'):
        q = q.filter_by(promotion_id=request.args.get('promotion_id', type=int))

    sessions = q.order_by(Session.date.desc(), Session.heure_debut.desc()).all()
    return jsonify({'sessions': [s.to_dict() for s in sessions], 'total': len(sessions)}), 200


@app.route('/emargement/sessions/<int:sid>', methods=['GET'])
@token_required
def voir_session(user, sid):
    s = Session.query.get_or_404(sid)
    return jsonify(s.to_dict(avec_presences=True)), 200


@app.route('/emargement/sessions', methods=['POST'])
@token_required
def creer_session(user):
    """
    Cree la session et initialise immediatement la feuille d'appel.
    Chaque etudiant de la promotion recoit une ligne Presence avec statut 'absent'.
    Le formateur n'a plus qu'a cocher les presents.
    """
    data = request.get_json() or {}
    for champ in ['promotion_id', 'matiere', 'date', 'heure_debut', 'heure_fin']:
        if not data.get(champ):
            return jsonify({'error': f'champ manquant : {champ}'}), 400

    # On recupere le nom de la promotion pour la denormaliser dans la session.
    # Si le service planning est indisponible, on continue quand meme.
    promo_nom = None
    token = request.headers.get('Authorization', '').split(' ')[-1]
    try:
        rep = requests.get(
            f"{PLANNING_URL}/planning/promotions/{data['promotion_id']}",
            headers={'Authorization': f'Bearer {token}'},
            timeout=3
        )
        if rep.status_code == 200:
            promo_nom = rep.json().get('nom')
    except Exception:
        pass

    nom_formateur = f"{user.get('nom', '')} {user.get('prenom', '')}".strip()
    s = Session(
        promotion_id  = data['promotion_id'],
        promotion_nom = promo_nom,
        matiere       = data['matiere'],
        formateur_id  = user['user_id'],
        formateur_nom = nom_formateur,
        date          = datetime.strptime(data['date'], '%Y-%m-%d').date(),
        heure_debut   = data['heure_debut'],
        heure_fin     = data['heure_fin'],
        statut        = 'ouverte'
    )
    db.session.add(s)
    db.session.commit()

    # Initialisation automatique des presences (absent par defaut)
    nb_etudiants = 0
    try:
        rep = requests.get(
            f"{PLANNING_URL}/planning/etudiants?promotion_id={data['promotion_id']}",
            headers={'Authorization': f'Bearer {token}'},
            timeout=5
        )
        if rep.status_code == 200:
            for e in rep.json().get('etudiants', []):
                db.session.add(Presence(
                    session_id      = s.id,
                    etudiant_id     = e['id'],
                    etudiant_nom    = e['nom'],
                    etudiant_prenom = e['prenom'],
                    etudiant_email  = e.get('email', ''),
                    statut          = 'absent'
                ))
                nb_etudiants += 1
            db.session.commit()
            print(f"{nb_etudiants} presences initialisees pour la session {s.id}")
    except Exception as ex:
        print(f"erreur init presences : {ex}")

    return jsonify({'message': 'session creee', 'session': s.to_dict(avec_presences=True)}), 201


# Presences individuelles ----------------------------------------------------

@app.route('/emargement/presences/<int:pid>', methods=['PATCH', 'PUT'])
@token_required
def modifier_presence(user, pid):
    """Mise a jour d'un statut via AJAX. Repond en moins de 200ms."""
    p = Presence.query.get_or_404(pid)
    s = Session.query.get(p.session_id)

    if s.statut == 'fermee':
        return jsonify({'error': 'session fermee, modification impossible'}), 400

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'acces refuse'}), 403

    data = request.get_json() or {}

    if 'statut' in data:
        statuts_valides = ['present', 'absent', 'retard', 'excuse']
        if data['statut'] not in statuts_valides:
            return jsonify({'error': f'statut invalide, valeurs acceptees : {statuts_valides}'}), 400
        p.statut = data['statut']

    if 'commentaire' in data:
        p.commentaire = data['commentaire']

    p.saisi_a = datetime.utcnow()
    db.session.commit()
    return jsonify({'message': 'presence mise a jour', 'presence': p.to_dict()}), 200


# Action groupee (BulkAction) ------------------------------------------------

@app.route('/emargement/sessions/<int:sid>/bulk', methods=['POST'])
@token_required
def action_groupee(user, sid):
    """
    Passe tous les etudiants d'une session au meme statut en un seul appel.
    Utile pour "Tout present" ou "Tout absent" en debut de session.
    """
    s = Session.query.get_or_404(sid)

    if s.statut == 'fermee':
        return jsonify({'error': 'session deja fermee'}), 400

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'acces refuse'}), 403

    data = request.get_json() or {}
    nouveau_statut = data.get('statut', 'present')

    if nouveau_statut not in ['present', 'absent', 'retard', 'excuse']:
        return jsonify({'error': 'statut invalide'}), 400

    maintenant = datetime.utcnow()
    for p in s.presences:
        p.statut  = nouveau_statut
        p.saisi_a = maintenant

    db.session.commit()
    return jsonify({
        'message': f'{len(s.presences)} presences passees a "{nouveau_statut}"',
        'session': s.to_dict(avec_presences=True)
    }), 200


# Cloture de session ---------------------------------------------------------

@app.route('/emargement/sessions/<int:sid>/fermer', methods=['POST'])
@token_required
def fermer_session(user, sid):
    """
    Verrouille la session et declenche le pipeline d'envoi asynchrone.
    La reponse HTTP est immediate (< 200ms).
    Les emails partent en arriere-plan via ThreadPoolExecutor.
    """
    s = Session.query.get_or_404(sid)

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'vous n etes pas le formateur de cette session'}), 403

    if s.statut == 'fermee':
        return jsonify({'error': 'session deja fermee'}), 400

    s.statut = 'fermee'
    db.session.commit()

    # On cible absents ET retardataires : tous ceux qui n'etaient pas presents.
    # Les excuses ne recoivent pas d'email (absence justifiee).
    a_notifier = [p for p in s.presences if p.statut in ('absent', 'retard')]
    horaire = f"{s.heure_debut} - {s.heure_fin}"

    envoyer_mails_absents(s.id, a_notifier, s.matiere, str(s.date), horaire)

    return jsonify({
        'message': f'session fermee, {len(a_notifier)} email(s) en cours d envoi',
        'session': s.to_dict(),
        'emails_planifies': len(a_notifier)
    }), 200


# Logs de notifications ------------------------------------------------------

@app.route('/emargement/sessions/<int:sid>/notifications', methods=['GET'])
@token_required
def logs_notifications(user, sid):
    """Retourne l'historique des emails envoyes pour une session."""
    logs = NotificationLog.query.filter_by(session_id=sid).order_by(NotificationLog.envoye_a).all()
    return jsonify({'logs': [l.to_dict() for l in logs], 'total': len(logs)}), 200


# Statistiques ---------------------------------------------------------------

@app.route('/emargement/stats', methods=['GET'])
@token_required
def stats_globales(user):
    """
    KPIs pour le tableau de bord administrateur.
    Taux de presence global, nombre de sessions, emails envoyes.
    """
    total_presences = Presence.query.count()
    total_presents  = Presence.query.filter_by(statut='present').count()
    total_sessions  = Session.query.count()
    sessions_ouvertes = Session.query.filter_by(statut='ouverte').count()
    emails_envoyes  = NotificationLog.query.filter_by(statut='envoye').count()

    taux = round(total_presents / total_presences * 100, 1) if total_presences else 0

    return jsonify({
        'taux_presence':    taux,
        'total_sessions':   total_sessions,
        'sessions_ouvertes': sessions_ouvertes,
        'emails_envoyes':   emails_envoyes,
        'total_presences':  total_presences
    }), 200


@app.route('/emargement/stats/promotion/<int:promo_id>', methods=['GET'])
@token_required
def stats_promotion(user, promo_id):
    """Statistiques de presence pour une promotion donnee."""
    sessions = Session.query.filter_by(promotion_id=promo_id).all()
    if not sessions:
        return jsonify({'taux_presence': 0, 'nb_sessions': 0}), 200

    sid_liste = [s.id for s in sessions]
    total  = Presence.query.filter(Presence.session_id.in_(sid_liste)).count()
    presents = Presence.query.filter(
        Presence.session_id.in_(sid_liste),
        Presence.statut == 'present'
    ).count()
    taux = round(presents / total * 100, 1) if total else 0

    return jsonify({
        'promotion_id': promo_id,
        'nb_sessions':  len(sessions),
        'taux_presence': taux,
        'total_presences': total,
        'nb_presents': presents
    }), 200


# ---------------------------------------------------------------------------
# Demarrage
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print('emargement_service demarre. Tables creees.')
    app.run(host='0.0.0.0', port=5003, debug=True)
