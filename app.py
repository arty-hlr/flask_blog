import datetime
import functools
import os
import re
import urllib
import hashlib

from flask import (Flask, flash, Markup, redirect, render_template, request,
                   Response, session, url_for)
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.extra import ExtraExtension
from micawber import bootstrap_basic, parse_html
from micawber.cache import Cache as OEmbedCache
from peewee import *
from playhouse.flask_utils import FlaskDB, get_object_or_404, object_list
from playhouse.postgres_ext import *
from playhouse.db_url import connect

import credentials

ADMIN_USERNAME = credentials.username
ADMIN_HASH = credentials.admin_hash
APP_DIR = os.path.dirname(os.path.realpath(__file__))
DATABASE = connect(os.environ.get('DATABASE_URL'))
DEBUG = False
SECRET_KEY = credentials.session_key
SITE_WIDTH = 800


app = Flask(__name__)
app.config.from_object(__name__)

flask_db = FlaskDB(app)
database = flask_db.database
oembed_providers = bootstrap_basic(OEmbedCache())


class Category(flask_db.Model):
    name = CharField(unique=True)
    number = IntegerField()

class Entry(flask_db.Model):
    title = CharField()
    slug = CharField(unique=True)
    content = TextField()
    category = CharField()
    published = BooleanField(index=True)
    timestamp = DateTimeField(default=datetime.datetime.now, index=True)

    @property
    def html_content(self):
        """
        Generate HTML representation of the markdown-formatted blog entry,
        and also convert any media URLs into rich media objects such as video
        players or images.
        """
        hilite = CodeHiliteExtension(linenums=False, css_class='highlight')
        extras = ExtraExtension()
        markdown_content = markdown(self.content, extensions=[hilite, extras])
        oembed_content = parse_html(
            markdown_content,
            oembed_providers,
            urlize_all=True,
            maxwidth=app.config['SITE_WIDTH'])
        return Markup(oembed_content)

    def save(self, *args, **kwargs):
        # Generate a URL-friendly representation of the entry's title.
        if not self.slug:
            self.slug = re.sub('[^\w]+', '-', self.title.lower()).strip('-')
        ret = super(Entry, self).save(*args, **kwargs)

        self.update_category()
        return ret

    def update_category(self):
        if self.published:
            Category.update({Category.number: Category.number+1}).where(Category.name == self.category).execute()

    @classmethod
    def only_category(cls,cat):
        return Entry.select().where(Entry.category == cat,Entry.published == True)

    @classmethod
    def public(cls):
        return Entry.select().where(Entry.published == True)

    @classmethod
    def drafts(cls):
        return Entry.select().where(Entry.published == False)

    @classmethod
    def search(cls, query):
        words = [word.strip() for word in query.split() if word.strip()]
        if not words:
            # Return an empty query.
            return Entry.noop()
        else:
            search = ' '.join(words)

        return (Entry.select()
                .where(
                    Match(Entry.content,search) &
                    (Entry.published == True)))

def login_required(fn):
    @functools.wraps(fn)
    def inner(*args, **kwargs):
        if session.get('logged_in'):
            return fn(*args, **kwargs)
        return redirect(url_for('login', next=request.path))
    return inner

@app.route('/login/', methods=['GET', 'POST'])
def login():
    next_url = request.args.get('next') or request.form.get('next')
    if request.method == 'POST' and request.form.get('username') and request.form.get('password'):
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = hashlib.sha512(password.encode()).hexdigest()
        if username == app.config['ADMIN_USERNAME'] and hashed_password == app.config['ADMIN_HASH']:
            session['logged_in'] = True
            session.permanent = True  # Use cookie to store session.
            flash('You are now logged in.', 'success')
            return redirect(next_url or url_for('index'))
        else:
            flash('Incorrect credentials.', 'danger')
    return render_template('login.html', next_url=next_url)

@app.route('/logout/', methods=['GET', 'POST'])
def logout():
    if request.method == 'POST':
        session.clear()
        return redirect(url_for('login'))
    return render_template('logout.html')

@app.route('/categories/')
def categories():
    query = Category.select().where(Category.number != 0).order_by(Category.name)
    return object_list(
        'categories.html',
        query,
        check_bounds=False)

@app.route('/category/<cat>/')
def category(cat):
    category = get_object_or_404(Category, Category.name == cat)
    query = Entry.only_category(cat).order_by(Entry.timestamp.desc())
    # raise(Exception)
    return object_list(
        'category.html',
        query,
        cat=cat)

@app.route('/')
def index():
    search_query = request.args.get('q')
    if search_query:
        query = Entry.search(search_query)
    else:
        query = Entry.public().order_by(Entry.timestamp.desc())

    # raise(Exception)
    return object_list(
        'index.html',
        query,
        search=search_query,
        check_bounds=False)

def _create_or_edit(entry, template):
    if request.method == 'POST':
        entry.title = request.form.get('title') or ''
        entry.content = request.form.get('content') or ''
        entry.category = request.form.get('category') or ''
        entry.published = request.form.get('published') or False
        preview = request.form.get('preview') or False
        if not (entry.title and entry.content and entry.category):
            flash('Title, Content, and Category are required.', 'danger')
        else:
            try:
                category = Category.get(Category.name == request.form.get('category'))
            except:
                with database.atomic():
                    category = Category.create(name=request.form.get('category'),number=0)
            try:
                with database.atomic():
                    entry.save()
            except IntegrityError:
                flash('Error: this title is already in use.', 'danger')
            else:
                flash('Entry saved successfully.', 'success')
                if entry.published or preview:
                    return redirect(url_for('detail', slug=entry.slug))
                else:
                    return redirect(url_for('edit', slug=entry.slug))

    return render_template(template, entry=entry)

@app.route('/create/', methods=['GET', 'POST'])
@login_required
def create():
    return _create_or_edit(Entry(title='', content=''), 'create.html')

@app.route('/drafts/')
@login_required
def drafts():
    query = Entry.drafts().order_by(Entry.timestamp.desc())
    return object_list('index.html', query, check_bounds=False)

@app.route('/<slug>/')
def detail(slug):
    if session.get('logged_in'):
        query = Entry.select()
    else:
        query = Entry.public()
    entry = get_object_or_404(query, Entry.slug == slug)
    return render_template('detail.html', entry=entry)

@app.route('/<slug>/edit/', methods=['GET', 'POST'])
@login_required
def edit(slug):
    entry = get_object_or_404(Entry, Entry.slug == slug)
    return _create_or_edit(entry, 'edit.html')

@app.route('/<slug>/delete/')
@login_required
def delete(slug):
    entry = Entry.get(Entry.slug == slug)
    deleted_entry = entry.title
    Category.update({Category.number: Category.number-1}).where(Category.name == entry.category).execute()
    entry.delete_instance()
    return render_template('deleted.html',deleted_entry=deleted_entry)

@app.route('/about/')
def about():
    return render_template('about.html')

@app.template_filter('clean_querystring')
def clean_querystring(request_args, *keys_to_remove, **new_values):
    querystring = dict((key, value) for key, value in request_args.items())
    for key in keys_to_remove:
        querystring.pop(key, None)
    querystring.update(new_values)
    return urllib.urlencode(querystring)

@app.errorhandler(404)
def not_found(exc):
    return Response('<h3>Not found</h3>'), 404

def main():
    app.run()

database.create_tables([Entry,Category], safe=True)

if __name__ == '__main__':
    main()
