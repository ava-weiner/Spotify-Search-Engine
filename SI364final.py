import os
import requests
import json
from flask import Flask, render_template, session, redirect, request, url_for, flash
from flask_script import Manager, Shell
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, FileField, PasswordField, BooleanField, SelectMultipleField, ValidationError
from wtforms.validators import Required, Length, Email, Regexp, EqualTo
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate, MigrateCommand
from werkzeug.security import generate_password_hash, check_password_hash
from flask import jsonify
from sqlalchemy import desc

from flask_login import LoginManager, login_required, logout_user, login_user, UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.debug = True
app.use_reloader = True
app.config['SECRET_KEY'] = 'hardtoguessstring'
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL') or "postgresql://avaweiner@localhost/avawFinaldb"
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

manager = Manager(app)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
manager.add_command('db', MigrateCommand)

login_manager = LoginManager()
login_manager.session_protection = 'strong'
login_manager.login_view = 'login'
login_manager.init_app(app)

client_id = ""
client_secret = ""
redirect_uri = ''
oauth_token = ""

########################
######## Models ########
########################
user_playlist = db.Table('User_Playlist', db.Column('track_id', db.String, db.ForeignKey('tracks.id')), db.Column('playlist_id', db.Integer, db.ForeignKey('personalplaylists.id')))

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(255), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    playlists = db.relationship('PersonalPlaylist', backref='User')

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class Track(db.Model):
    __tablename__ = "tracks"
    id = db.Column(db.String, primary_key=True)
    title = db.Column(db.String(128))
    uri = db.Column(db.String(256))
    popularity = db.Column(db.Integer)
    artist_id = db.Column(db.String, db.ForeignKey('artist.id'))

    def __repr__(self):
        return "{}".format(self.title)

class Artist(db.Model):
    __tablename__ = "artist"
    id = db.Column(db.String, primary_key=True)
    name = db.Column(db.String(128))
    image_url = db.Column(db.String)
    rating = db.Column(db.String)

    def __repr__(self):
        return "{}".format(self.name)

class PersonalPlaylist(db.Model):
    __tablename__ = "personalplaylists"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    tracks = db.relationship('Track',secondary=user_playlist,backref=db.backref('personalplaylists',lazy='dynamic'),lazy='dynamic')


########################
######## Forms #########
########################

class RegistrationForm(FlaskForm):
    username = StringField('Username:',validators=[Required(),Length(1,64),Regexp('^[A-Za-z][A-Za-z0-9_.]*$',0,'Usernames must have only letters, numbers, dots or underscores')])
    password = PasswordField('Password:',validators=[Required(),EqualTo('password2',message="Passwords must match")])
    password2 = PasswordField("Confirm Password:",validators=[Required()])
    submit = SubmitField('Register User')

    def validate_username(self,field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('Username already taken')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[Required(), Length(1,64)])
    password = PasswordField('Password', validators=[Required()])
    remember_me = BooleanField('Keep me logged in')
    submit = SubmitField('Log In')

class TrackForm(FlaskForm):
    search = StringField('What song are you looking for?', validators=[Required()])
    submit = SubmitField('Search')

    def validate_search(self, field):
        if '"'in self.search.data:
            raise ValidationError('Do not include quotation marks in your search.')

class DeleteButtonForm(FlaskForm):
    submit = SubmitField('Delete')

class UpdateButtonForm(FlaskForm):
    submit = SubmitField('Update')

class ArtistForm(FlaskForm):
    artist = StringField('What artist would you like to find?', validators=[Required()])
    rating = StringField('What rating would you give this artist?', validators=[Required()])
    submit = SubmitField('Search')

class UpdateArtistRating(FlaskForm):
    rating = StringField('What new rating would you give this artist?', validators=[Required()])
    submit = SubmitField('Update')



class PlaylistCreateForm(FlaskForm):
    name = StringField('Playlist Name',validators=[Required()])
    track_picks = SelectMultipleField('Songs to include', validators=[Required()])
    submit = SubmitField("Create Playlist")

    def validate_track_picks(self, field):
        print("hi")
        if len(field.data) < 2:
            raise ValidationError('A playlist must include at least 2 songs.')

########################
### Helper functions ###
########################

def search_tracks(search):
    baseurl = "https://api.spotify.com/v1/search"
    headers ={"Content-Type": "application/json", "Authorization": "Bearer " + oauth_token}
    params_d = {'q' : search , 'type' : 'track', 'limit': 5}
    response = requests.get(baseurl, headers=headers, params=params_d)
    js = json.loads(response.text)
    tracks = []
    for t in js['tracks']['items']:
        tracks.append(t)
    return tracks

def search_artist_by_id(id):
    url = "https://api.spotify.com/v1/artists/{0}".format(id)
    headers ={"Content-Type": "application/json", "Authorization": "Bearer " + oauth_token}
    response = requests.get(url, headers=headers)
    js = json.loads(response.text)
    return js

def search_artist_by_name(name):
    baseurl = "https://api.spotify.com/v1/search"
    headers ={"Content-Type": "application/json", "Authorization": "Bearer " + oauth_token}
    params_d = {'q' : name , 'type' : 'artist', 'limit': 1}
    response = requests.get(baseurl, headers=headers, params=params_d)
    js = json.loads(response.text)
    return js['artists']['items'][0]

def get_or_create_track(db_session, id, title, uri, popularity, artist_id):
    track = db_session.query(Track).filter_by(title=title).first()
    if track:
        return track
    else:
        track = Track(id=id, title=title, uri=uri, popularity=popularity, artist_id=artist_id)
        db_session.add(track)
        db_session.commit()
        return track

def get_or_create_artist(db_session, id, rating="0"):
    artist = db_session.query(Artist).filter_by(id=id).first()
    if artist:
        return artist
    else:
        s = search_artist_by_id(id)
        artist = Artist(id = s['id'], name = s['name'], image_url = s['images'][2]['url'], rating=rating)
        db_session.add(artist)
        db_session.commit()
        return artist

def get_track_by_id(id):
    t = Track.query.filter_by(id=id).first()
    return t

def get_or_create_playlist(db_session, name, current_user, track_list=[]):
    playlist = PersonalPlaylist.query.filter_by(name=name, user_id = current_user.id).first()
    if playlist:
        return playlist
    else:
        playlist = PersonalPlaylist(name=name, user_id=current_user.id, tracks=[])
        for t in track_list:
            playlist.tracks.append(t)
        db_session.add(playlist)
        db_session.commit()
        return playlist

########################
#### View functions ####
########################

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route('/')
def home_page():
    num_songs = len(Track.query.all())
    num_artists = len(Artist.query.all())
    return render_template('home.html', songs=num_songs, artists=num_artists)

@app.route('/login',methods=["GET","POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is not None and user.verify_password(form.password.data):
            login_user(user, form.remember_me.data)
            return redirect(request.args.get('next') or url_for('home_page'))
        flash('Invalid username or password.')
    return render_template('login.html',form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out')
    return redirect(url_for('home_page'))

@app.route('/register',methods=["GET","POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data,password=form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('You can now log in!')
        return redirect(url_for('login'))
    return render_template('register.html',form=form)

@app.route('/secret')
@login_required
def secret():
    return "Only authenticated users can do this! Try to log in or contact the site admin."

@app.route('/track_search', methods=['GET', 'POST'])
def track_search():
    form = TrackForm()
    results = None
    if request.method == "POST" and form.validate_on_submit():
        search = search_tracks(search = form.search.data)
        results = []
        for t in search:
            artist = get_or_create_artist(db.session, id = t['artists'][0]['id'])
            track = get_or_create_track(db.session, id = t['id'], title = t['name'], uri = t['uri'], popularity = t['popularity'], artist_id = artist.id)
            results.append((track.title, 'https://open.spotify.com/embed?uri={0}'.format(track.uri)))
    errors = [v for v in form.errors.values()]
    if len(errors) > 0:
        flash("ERRORS IN FORM SUBMISSION: " + str(errors))
    return render_template('track_search.html', form=form, results=results)

@app.route('/artist_search')
def artist_search():
    form = ArtistForm()
    return render_template('artist_form.html', form=form)

@app.route('/artist_results', methods=['GET', 'POST'])
def artist_results():
    form = ArtistForm(request.args)
    if request.method == "GET" and form.validate():
        search = search_artist_by_name(name = form.artist.data)
        artist = get_or_create_artist(db.session, id = search['id'], rating = form.rating.data)
        artist_info = (artist.name, artist.image_url)
        return render_template('artist_results.html', artist_info=artist_info)
    errors = [v for v in form.errors.values()]
    if len(errors) > 0:
        flash("ERRORS IN FORM SUBMISSION: " + str(errors))
    return redirect(url_for('artist_search'))

@app.route('/all_tracks')
def all_tracks():
    form_del = DeleteButtonForm()
    tracks = Track.query.all()
    info = []
    for t in tracks:
        artist = Artist.query.filter_by(id=t.artist_id).first()
        info.append((t.title, artist.name, 'https://open.spotify.com/embed?uri={0}'.format(t.uri)))
    return render_template('all_tracks.html', tracks = info, formdel=form_del)

@app.route('/delete/<track>', methods=["GET","POST"])
def deleteSong(track):
    s = Track.query.filter_by(title = track).first()
    db.session.delete(s)
    db.session.commit()
    flash("Successfully deleted {}".format(track))
    return redirect(url_for('all_tracks'))

@app.route('/all_artists')
def all_artists():
    form = UpdateButtonForm()
    artists = Artist.query.all()
    return render_template('all_artists.html', artists=artists, form=form)

@app.route('/update/<artist>', methods = ['GET','POST'])
def updateArtist(artist):
    form = UpdateArtistRating()
    a = Artist.query.filter_by(name = artist).first()
    if form.validate_on_submit():
        new_rating = form.rating.data
        a.rating = new_rating
        db.session.commit()
        flash("Updated rating of " + artist)
        return redirect(url_for('all_artists'))
    return render_template('update_rating.html',artist = artist, form = form)

@app.route('/create_playlist',methods=["GET","POST"])
@login_required
def create_playlist():
    form = PlaylistCreateForm()
    tracks = Track.query.all()
    choices = [(t.id, t.title) for t in tracks]
    form.track_picks.choices = choices
    if request.method == "POST" and form.validate_on_submit():
        tracks_selected = form.track_picks.data
        print (tracks_selected)
        track_objects = [get_track_by_id(id) for id in tracks_selected]
        get_or_create_playlist(db.session, name = form.name.data, current_user = current_user, track_list = track_objects)
        print ("Playlist made")
        return redirect(url_for('playlists'))
    errors = [v for v in form.errors.values()]
    if len(errors) > 0:
        flash("ERRORS IN FORM SUBMISSION: " + str(errors))
    return render_template("create_playlist.html", form=form)

@app.route('/playlists',methods=["GET","POST"])
@login_required
def playlists():
    playlists = PersonalPlaylist.query.filter_by(user_id= current_user.id).all()
    return render_template('playlists.html', playlists=playlists)

@app.route('/playlist/<id_num>')
def single_playlist(id_num):
    id_num = int(id_num)
    playlist = PersonalPlaylist.query.filter_by(id=id_num).first()
    tracks = playlist.tracks.all()
    return render_template('playlist.html',playlist=playlist, tracks=tracks)

@app.route('/ajax')
def most_popular():
    pop = Track.query.order_by(desc(Track.popularity)).first()
    a = Artist.query.filter_by(id=pop.artist_id).first()
    song_info = jsonify([pop.title, a.name])
    return song_info

if __name__ == '__main__':
    db.create_all()
    manager.run()
