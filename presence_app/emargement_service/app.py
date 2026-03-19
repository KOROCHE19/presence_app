# service emargement - feuilles de presence
# le formateur ouvre une session, coche present/absent pour chaque etudiant

import os
import jwt
import requests
import smtplib
from datetime import datetime
from functools import wraps
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://emarg_user:emarg_pass@localhost:5432/emarg_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'secret123')

PLANNING_URL = os.environ.get('PLANNING_SERVICE_URL', 'http://planning_service:5002')

# config mail - a remplir dans le .env ou docker-compose
MAIL_SERVER   = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
MAIL_PORT     = int(os.environ.get('MAIL_PORT', '587'))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
MAIL_SENDER   = os.environ.get('MAIL_SENDER', 'noreply@ecole.fr')

db = SQLAlchemy(app)


# envoie un mail d'absence a l'etudiant
def envoyer_mail_absence(email_etudiant, prenom, nom, matiere, date, heure):
    sujet = "Absence enregistrée - " + matiere + " du " + date

    corps_html = """
    <div style="font-family:Arial; max-width:500px; margin:auto; border:1px solid #eee; border-radius:8px; overflow:hidden;">
        <div style="background:#2c3e50; color:white; padding:20px;">
            <h2 style="margin:0;">Gestion des Présences</h2>
        </div>
        <div style="padding:20px;">
            <p>Bonjour <b>""" + prenom + " " + nom + """</b>,</p>
            <p>Vous avez été marqué(e) <b style="color:#e74c3c;">absent(e)</b> au cours suivant :</p>
            <ul>
                <li><b>Matière :</b> """ + matiere + """</li>
                <li><b>Date :</b> """ + date + """</li>
                <li><b>Heure :</b> """ + heure + """</li>
            </ul>
            <p>Si cette absence est injustifiée ou si vous pensez qu'il y a une erreur,
            contactez votre formateur ou l'administration.</p>
            <p>Cordialement,<br>L'équipe pédagogique</p>
        </div>
    </div>
    """

    # si pas de config smtp on fait juste un print
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[SIMULATION MAIL] vers " + email_etudiant + " : " + sujet)
        return True

    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = MAIL_SENDER
        msg['To'] = email_etudiant
        msg['Subject'] = sujet
        msg.attach(MIMEText(corps_html, 'html', 'utf-8'))

        serveur = smtplib.SMTP(MAIL_SERVER, MAIL_PORT)
        serveur.starttls()
        serveur.login(MAIL_USERNAME, MAIL_PASSWORD)
        serveur.sendmail(MAIL_SENDER, email_etudiant, msg.as_string())
        serveur.quit()

        print("mail envoyé a " + email_etudiant)
        return True
    except Exception as e:
        print("erreur envoi mail : " + str(e))
        return False


# table session de cours
class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    promotion_id = db.Column(db.Integer, nullable=False)
    promotion_nom = db.Column(db.String(100))  # copié pour eviter appel http a chaque fois
    matiere = db.Column(db.String(100), nullable=False)
    formateur_id = db.Column(db.Integer, nullable=False)
    formateur_nom = db.Column(db.String(100))
    date = db.Column(db.Date, nullable=False)
    heure_debut = db.Column(db.String(10), nullable=False)  # ex: "08:00"
    heure_fin = db.Column(db.String(10), nullable=False)
    statut = db.Column(db.String(20), default='ouverte')  # ouverte ou fermée
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    presences = db.relationship('Presence', backref='session', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, avec_presences=False):
        d = {
            'id': self.id,
            'promotion_id': self.promotion_id,
            'promotion_nom': self.promotion_nom,
            'matiere': self.matiere,
            'formateur_id': self.formateur_id,
            'formateur_nom': self.formateur_nom,
            'date': str(self.date),
            'heure_debut': self.heure_debut,
            'heure_fin': self.heure_fin,
            'statut': self.statut,
            'nb_presents': len([p for p in self.presences if p.statut == 'present']),
            'nb_absents': len([p for p in self.presences if p.statut == 'absent']),
            'nb_total': len(self.presences)
        }
        if avec_presences:
            d['presences'] = [p.to_dict() for p in self.presences]
        return d


# table presence - une ligne par etudiant par session
class Presence(db.Model):
    __tablename__ = 'presences'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=False)
    etudiant_id = db.Column(db.Integer, nullable=False)
    etudiant_nom = db.Column(db.String(100))  # copié pour affichage rapide
    etudiant_prenom = db.Column(db.String(100))
    statut = db.Column(db.String(20), default='absent')  # present, absent, retard, excusé
    commentaire = db.Column(db.Text)
    saisi_a = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'session_id': self.session_id,
            'etudiant_id': self.etudiant_id,
            'etudiant_nom': self.etudiant_nom,
            'etudiant_prenom': self.etudiant_prenom,
            'statut': self.statut,
            'commentaire': self.commentaire,
            'saisi_a': self.saisi_a.isoformat() if self.saisi_a else None
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


# --- sessions ---

# lister les sessions
@app.route('/emargement/sessions', methods=['GET'])
@token_required
def get_sessions(user):
    q = Session.query

    if request.args.get('promotion_id'):
        q = q.filter_by(promotion_id=request.args.get('promotion_id', type=int))
    if request.args.get('formateur_id'):
        q = q.filter_by(formateur_id=request.args.get('formateur_id', type=int))
    if request.args.get('date'):
        q = q.filter_by(date=request.args.get('date'))

    sessions = q.order_by(Session.date.desc()).all()
    return jsonify({'sessions': [s.to_dict() for s in sessions], 'total': len(sessions)}), 200


# créer une session de cours
@app.route('/emargement/sessions', methods=['POST'])
@token_required
def creer_session(user):
    data = request.get_json()
    for champ in ['promotion_id', 'matiere', 'date', 'heure_debut', 'heure_fin']:
        if not data.get(champ):
            return jsonify({'error': 'champ manquant : ' + champ}), 400

    # on recupere le nom de la promo depuis le service planning
    promo_nom = None
    try:
        token = request.headers['Authorization'].split(' ')[1]
        rep = requests.get(
            PLANNING_URL + '/planning/promotions/' + str(data['promotion_id']),
            headers={'Authorization': 'Bearer ' + token},
            timeout=3
        )
        if rep.status_code == 200:
            promo_nom = rep.json().get('nom')
    except:
        pass  # si le service planning est pas dispo on met None

    s = Session(
        promotion_id=data['promotion_id'],
        promotion_nom=promo_nom,
        matiere=data['matiere'],
        formateur_id=user['user_id'],
        formateur_nom=user.get('nom', '') + ' ' + user.get('prenom', ''),
        date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
        heure_debut=data['heure_debut'],
        heure_fin=data['heure_fin'],
        statut='ouverte'
    )
    db.session.add(s)
    db.session.commit()

    # on cree automatiquement une ligne presence pour chaque etudiant de la promo
    # par defaut tout le monde est absent, le formateur cochera les presents
    try:
        token = request.headers['Authorization'].split(' ')[1]
        rep = requests.get(
            PLANNING_URL + '/planning/etudiants?promotion_id=' + str(data['promotion_id']),
            headers={'Authorization': 'Bearer ' + token},
            timeout=3
        )
        if rep.status_code == 200:
            etudiants = rep.json().get('etudiants', [])
            for e in etudiants:
                p = Presence(
                    session_id=s.id,
                    etudiant_id=e['id'],
                    etudiant_nom=e['nom'],
                    etudiant_prenom=e['prenom'],
                    statut='absent'  # absent par defaut
                )
                db.session.add(p)
            db.session.commit()
            print(str(len(etudiants)) + ' presences créées pour la session ' + str(s.id))
    except Exception as e:
        print("erreur recuperation etudiants : " + str(e))

    return jsonify({'message': 'session créée', 'session': s.to_dict(avec_presences=True)}), 201


# voir une session avec toutes les presences
@app.route('/emargement/sessions/<int:id>', methods=['GET'])
@token_required
def voir_session(user, id):
    s = Session.query.get_or_404(id)
    return jsonify(s.to_dict(avec_presences=True)), 200


# fermer une session - envoie un mail a chaque absent
@app.route('/emargement/sessions/<int:id>/fermer', methods=['POST'])
@token_required
def fermer_session(user, id):
    s = Session.query.get_or_404(id)

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'vous etes pas le formateur de cette session'}), 403

    if s.statut == 'fermée':
        return jsonify({'error': 'session deja fermée'}), 400

    s.statut = 'fermée'
    db.session.commit()

    # on recupere les emails des absents depuis le service planning
    # et on envoie un mail pour chaque absent (excusé = pas de mail)
    absents = [p for p in s.presences if p.statut == 'absent']
    nb_mails = 0

    token = request.headers.get('Authorization', '').split(' ')[-1]

    for p in absents:
        # on recupere l'email de l'etudiant via le service planning
        email_etudiant = None
        try:
            rep = requests.get(
                PLANNING_URL + '/planning/etudiants/' + str(p.etudiant_id),
                headers={'Authorization': 'Bearer ' + token},
                timeout=3
            )
            if rep.status_code == 200:
                email_etudiant = rep.json().get('email')
        except:
            pass

        # si on a pas l'email on peut pas envoyer
        if not email_etudiant:
            print("pas d'email pour etudiant " + str(p.etudiant_id) + ", mail non envoyé")
            continue

        ok = envoyer_mail_absence(
            email_etudiant,
            p.etudiant_prenom or '',
            p.etudiant_nom or '',
            s.matiere,
            str(s.date),
            s.heure_debut + ' - ' + s.heure_fin
        )
        if ok:
            nb_mails += 1

    return jsonify({
        'message': 'session fermée, ' + str(nb_mails) + ' mails envoyés',
        'session': s.to_dict(),
        'mails_envoyes': nb_mails
    }), 200


# --- presences ---

# modifier la presence d'un etudiant
@app.route('/emargement/presences/<int:id>', methods=['PUT'])
@token_required
def modifier_presence(user, id):
    p = Presence.query.get_or_404(id)
    s = Session.query.get(p.session_id)

    if s.statut == 'fermée':
        return jsonify({'error': 'session fermée impossible de modifier'}), 400

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'acces refusé'}), 403

    data = request.get_json()
    if 'statut' in data:
        if data['statut'] not in ['present', 'absent', 'retard', 'excusé']:
            return jsonify({'error': 'statut invalide'}), 400
        p.statut = data['statut']

    if 'commentaire' in data:
        p.commentaire = data['commentaire']

    p.saisi_a = datetime.utcnow()
    db.session.commit()

    return jsonify({'message': 'presence modifiée', 'presence': p.to_dict()}), 200


# saisir toutes les presences d'une session en une fois
@app.route('/emargement/sessions/<int:id>/presences', methods=['PUT'])
@token_required
def saisir_toutes_presences(user, id):
    s = Session.query.get_or_404(id)

    if s.statut == 'fermée':
        return jsonify({'error': 'session fermée'}), 400

    if s.formateur_id != user['user_id'] and user.get('role') != 'admin':
        return jsonify({'error': 'acces refusé'}), 403

    data = request.get_json()
    presences_data = data.get('presences', [])

    nb = 0
    for pd in presences_data:
        p = Presence.query.filter_by(session_id=id, etudiant_id=pd.get('etudiant_id')).first()
        if p:
            p.statut = pd.get('statut', 'absent')
            p.commentaire = pd.get('commentaire')
            p.saisi_a = datetime.utcnow()
            nb += 1

    db.session.commit()
    return jsonify({'message': str(nb) + ' presences mises a jour', 'session': s.to_dict(avec_presences=True)}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("tables emargement créées")
    app.run(host='0.0.0.0', port=5003, debug=True)
