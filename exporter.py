#!/usr/bin/python

import os
import sys
import time
import datetime

from xml.etree import ElementTree as ET

HERE = os.path.dirname(__file__)
LIBDIR = 'runtime/lib/python2.5'
SITEDIR = os.path.join(HERE, LIBDIR, 'site-packages')

for line in open(os.path.join(SITEDIR, 'easy-install.pth')):
    if line.startswith("import"):
        exec line
    elif line.startswith('#'):
        pass
    else:
        sys.path.append(os.path.join(SITEDIR, line.strip()))

import facebook
import cherrypy
import wsgiref.handlers

from google.appengine.ext.webapp import template
from google.appengine.api import memcache
sys.modules['memcache'] = memcache

import csvformatter
import htmlformatter
import atomformatter

def fb_require_login(f):
    '''Decorator for functions that require a valid Facebook session to
    operate.'''

    def _(self, *args, **kwargs):
        fb = cherrypy.request.facebook

        if 'session_key' in cherrypy.session and 'uid' in cherrypy.session:
            fb.session_key = cherrypy.session['session_key']
            fb.uid = cherrypy.session['uid']
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

        cherrypy.session['session_key'] = fb.session_key
        cherrypy.session['uid'] = fb.uid
        return f(self, *args, **kwargs)

    return _

class Exporter:
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
        base = os.path.join(os.path.dirname(__file__), 'templates', page)
        path = None

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
        return self.render('index', {
            'formats': self.formats.values(),
            'fb': cherrypy.request.facebook,
            'baseurl': cherrypy.request.app.config['facebook']['base url'],
            })

    @cherrypy.expose
    @fb_require_login
    def export(self, **kwargs):
        if not 'export' in kwargs:
            return self.render('error', {
                'message': 'You have not selected anything to export.'})

        # Make sure export is a list.
        if not hasattr(kwargs['export'], 'append'):
            kwargs['export'] = [ kwargs['export'] ]

        for x in kwargs['export']:
            if not hasattr(self, 'get_%s' % x):
                return self.render('error', {
                    'message': '''Don't know how to export %s.''' % x})

        if not 'format' in kwargs:
            return self.render('error', {
                'message': 'You have not selected an export format.'})

        if not kwargs['format'] in self.formats:
            return self.render('error', {
                'message': 'You have selected an invalid export format.'})

        feed = []
        for x in kwargs['export']:
            f = getattr(self, 'get_%s' % x)
            feed.extend(f())
        
        format = self.formats[kwargs['format']]
        fb = cherrypy.request.facebook
        user = fb.users.getInfo(fb.uid, 'name, first_name, last_name, profile_url')[0]
        cherrypy.response.headers['Content-Type'] = format.content_type
        return '\n'.join(format.format(user,
            sorted(feed, key=lambda x: x['created'])))
        
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
                'title'     : note['title'].encode('utf8'),
                'created'   :
                datetime.datetime.fromtimestamp(int(note['created_time'])),
                'updated'   :
                datetime.datetime.fromtimestamp(int(note['updated_time'])),
                'content'   : note['content'].encode('utf8'),
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
                'title'     : status['message'].encode('utf8'),
                'created'   :
                datetime.datetime.fromtimestamp(int(status['time'])),
                'content'   : status['message'].encode('utf8'),
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
                'title'     : link['title'].encode('utf8'),
                'created'   :
                datetime.datetime.fromtimestamp(int(link['created_time'])),
                'summary'   : link['summary'].encode('utf8'),
                'content'   : link['owner_comment'] and link['owner_comment'].encode('utf8'),
                'url'       : link['url'].encode('utf8'),
                })

        return feed

class FacebookTool:
    '''This sets up a cherrypy.request.facebook for each incoming
    request.'''

    def __call__(self):
        cherrypy.request.facebook = facebook.Facebook(
                cherrypy.request.app.config['facebook']['api key'],
                cherrypy.request.app.config['facebook']['secret key'])

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

