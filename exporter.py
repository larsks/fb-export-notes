#!/usr/bin/python

import os
import sys
import time
import datetime

from xml.etree import ElementTree as ET

######################################################################
#
# BEGIN VIRTUALENV IMPORT
#
# This mess of code gets us packages installed into a virtualenv
# using easy_install.
#

HERE = os.path.dirname(__file__)
LIBDIR = 'runtime/lib/python2.5'
SITEDIR = os.path.join(HERE, LIBDIR, 'site-packages')

# This was mostly extracted by site.py.
for line in open(os.path.join(SITEDIR, 'easy-install.pth')):
    if line.startswith("import"):
        exec line
    elif line.startswith('#'):
        pass
    else:
        sys.path.append(os.path.join(SITEDIR, line.strip()))

#
# END VIRTUALENV IMPORT
#
######################################################################

import facebook
import cherrypy
import wsgiref.handlers

from google.appengine.ext.webapp import template
from google.appengine.api import memcache
from google.appengine.api import urlfetch
from google.appengine.ext import db
sys.modules['memcache'] = memcache

import csvformatter
import htmlformatter
import atomformatter

class User (db.Model):
    session_key = db.StringProperty(required=True)
    uid = db.IntegerProperty(required=True)
    name = db.StringProperty()
    when = db.DateTimeProperty(required=True)
    selected = db.StringListProperty()

def fb_require_login(f):
    '''Decorator for functions that require a valid Facebook session to
    operate.'''

    def _(self, *args, **kwargs):
        fb = cherrypy.request.facebook

        if False:
            pass
        elif 'fb_sig_session_key' in kwargs and 'fb_sig_user' in kwargs:
            fb.session_key = kwargs['fb_sig_session_key']
            fb.uid = kwargs['fb_sig_user']
        elif 'x_sig_session_key' in kwargs and 'x_sig_user' in kwargs:
            fb.session_key = kwargs['x_sig_session_key']
            fb.uid = kwargs['x_sig_user']
        elif 'auth_token' in kwargs:
            fb.auth.getSession()
        else:
            return fb.redirect(fb.get_login_url())

        return f(self, *args, **kwargs)

    return _

class Exporter (object):
    _cp_config = {
            'tools.facebook.on'             : True,
            'tools.sessions.on'             : True,
            'tools.sessions.storage_type'   : 'memcached',
            'tools.sessions.servers	'       : [ 'memcached://' ],
            'tools.sessions.name'           : '_fb_exporter_id',
            'tools.sessions.clean_thread'   : True,
            'tools.sessions.timeout'        : 60,
            }

    def __init__ (self):
        self.formats = {}
        
        for format in [
                csvformatter.CSVFormatter(),
                htmlformatter.HTMLFormatter(),
                atomformatter.AtomFormatter(),
                ]:
            self.formats[format.id] = format

    def render (self, page, context):
        '''Render a template.'''

        base = os.path.join(os.path.dirname(__file__), 'templates', page)
        path = None

        # Allow templates to be specified with or without extension.
        for p in [base, '%s.html' % base]:
            if os.path.exists(p):
                path = p
                break

        if not path:
            raise cherrypy.HTTPError('500',
                    'Unable to find requested template (%s).' % page)

        return template.render(path, context)

    @cherrypy.expose
    @fb_require_login
    def index(self, **kwargs):
        '''Render the main canvas page.'''

        return self.render('index', {
            'formats': self.formats.values(),
            'fb': cherrypy.request.facebook,
            'config': cherrypy.request.app.config['facebook'],
            'message': kwargs.get('message'),
            })

    def error(self, message):
        '''Return the user to the canvas url and display the
        given error message.'''

        canvas_url = cherrypy.request.app.config['facebook']['canvas_url']
        return cherrypy.request.facebook.redirect('%s?message=%s' % (canvas_url, message))

    @cherrypy.expose
    @fb_require_login
    def prepare(self, **kwargs):
        fb = cherrypy.request.facebook

        if not 'export' in kwargs:
            return self.error('You have not selected anything to export.')

        # Make sure export is a list.
        if not hasattr(kwargs['export'], 'append'):
            kwargs['export'] = [ kwargs['export'] ]

        user = fb.users.getInfo(fb.uid, 'name, first_name, last_name, profile_url')[0]
        u = User(
                key_name = fb.session_key,
                uid = int(fb.uid),
                name = user['name'],
                session_key = fb.session_key,
                when = datetime.datetime.now(),
                selected = kwargs['export'],
                )

        u.put()

        return self.render('prepare', {
            'formats': self.formats.values(),
            'fb': cherrypy.request.facebook,
            'config': cherrypy.request.app.config['facebook'],
            })

    @cherrypy.expose
    def export(self, uid, session_key, format, output_file):
        '''Generate the exported data.'''

        fb = cherrypy.request.facebook
        fb.uid = uid
        fb.session_key = session_key

        user = User.get_by_key_name(session_key)
        if user is None:
            return self.error('You have not selected anything to export.')

        try:
            feed = []

            # Extend feed with each object type selected by the user.
            for x in user.selected:
                f = getattr(self, 'get_%s' % x)
                feed.extend(f())
            
            format = self.formats[format]
            user = fb.users.getInfo(fb.uid, 'name, first_name, last_name, profile_url')[0]
            cherrypy.response.headers['Content-Type'] = format.content_type

            # Format the items in the feed, sorted by date created.
            return format.format(user,
                sorted(feed, key=lambda x: x['created']))
        except urlfetch.DownloadError:
            return self.render('error', { 'message':
                'DownloadError: An operation time out; try reloading the page.'})
        
    def get_notes(self):
        fb = cherrypy.request.facebook
        notes = fb.fql.query(
                '''SELECT note_id, created_time,
                    updated_time, title, content
                    FROM note WHERE uid=%s''' % fb.uid)

        feed = []
        for note in notes:
            feed.append({
                'type'      : 'note',
                'id'        : note['note_id'],
                'title'     : note['title'],
                'created'   :
                datetime.datetime.fromtimestamp(int(note['created_time'])),
                'updated'   :
                datetime.datetime.fromtimestamp(int(note['updated_time'])),
                'content'   : note['content'],
                })

        return feed

    def get_status(self):
        fb = cherrypy.request.facebook
        statuses = fb.fql.query(
                '''SELECT status_id, time, message
                    FROM status WHERE uid=%s''' % fb.uid)

        feed = []
        for status in statuses:
            feed.append({
                'type'      : 'status',
                'id'        : status['status_id'],
                'title'     : status['message'],
                'created'   :
                datetime.datetime.fromtimestamp(int(status['time'])),
                'content'   : status['message'],
                })

        return feed

    def get_links(self):
        fb = cherrypy.request.facebook
        links = fb.fql.query(
                '''SELECT link_id, created_time, title, summary,
                owner_comment, url
                    FROM link WHERE owner=%s''' % fb.uid)

        feed = []
        for link in links:
            feed.append({
                'type'      : 'link',
                'id'        : link['link_id'],
                'title'     : link['title'],
                'created'   :
                datetime.datetime.fromtimestamp(int(link['created_time'])),
                'summary'   : link['summary'],
                'content'   : link['owner_comment'],
                'url'       : link['url'],
                })

        return feed

class FacebookTool (object):
    '''This sets up a cherrypy.request.facebook for each incoming
    request.'''

    def __call__(self):
        cherrypy.request.facebook = facebook.Facebook(
                cherrypy.request.app.config['facebook']['api_key'],
                cherrypy.request.app.config['facebook']['secret_key'])

        cherrypy.request.facebook.redirect = self.redirect

    def redirect(self, url):
        if cherrypy.request.params.get('fb_sig_in_canvas'):
            return '<fb:redirect url="%s" />' % url
        else:
            raise cherrypy.HTTPRedirect(url)

def main():
    cherrypy.tools.facebook = cherrypy.Tool(
            'before_handler',
            FacebookTool())

    root = Exporter()
    app = cherrypy.tree.mount(root, "/", config='app.ini')
    wsgiref.handlers.CGIHandler().run(app)

if __name__ == '__main__':
    main()

