#!/usr/bin/python

import os
import sys
import time

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

NS_ATOM         = 'http://www.w3.org/2005/Atom'

def atomElement(e):
    return '{%s}%s' % (NS_ATOM, e)

def fmtTime(t):
    return time.strftime('%Y-%m-%dT%H:%M:%S.000-05:00', time.localtime(t))

def addSubElement(parent, name, attrs=None, text=None):
    ele = ET.SubElement(parent, name)
    if attrs:
        for k, v in attrs.items():
            ele.set(k,v)
    if text:
        ele.text = text

    return ele

def fb_require_login(f):
    def _(self, *args, **kwargs):
        fb = cherrypy.request.facebook

        if 'session_key' in cherrypy.session and 'uid' in cherrypy.session:
            fb.session_key = cherrypy.session['session_key']
            fb.uid = cherrypy.session['uid']
        elif 'fb_sig_session_key' in kwargs and 'fb_sig_user' in kwargs:
            fb.session_key = kwargs['fb_sig_session_key']
            fb.uid = kwargs['fb_sig_user']
        elif 'auth_token' in kwargs:
            fb.auth.getSession()
        else:
            return fb.redirect(fb.get_login_url())

        cherrypy.session['session_key'] = fb.session_key
        cherrypy.session['uid'] = fb.uid
        return f(self, *args, **kwargs)

    return _

class Exporter:
    def __init__ (self):
        self.formats = {}
        
        for format in [
                csvformatter.CSVFormatter(),
                htmlformatter.HTMLFormatter(),
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
    def index(self, **kwargs):
        return self.render('index', {'formats': self.formats.values()})

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
        cherrypy.response.headers['Content-Type'] = format.content_type
        return '\n'.join(format.format(feed))
        
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
                'created'   : note['created_time'],
                'updated'   : note['updated_time'],
                'content'   : note['content'],
                })

        return feed

    @cherrypy.expose
    @fb_require_login
    def status_xml(self, **kwargs):
        cherrypy.response.headers['Content-Type'] = "application/atom+xml"
        fb = cherrypy.request.facebook

        statuses = fb.fql.query(
                '''SELECT status_id, time, source, message 
                FROM status
                WHERE uid=%s
                ORDER BY time''' % fb.uid)

        user = fb.users.getInfo(fb.uid, 'first_name, profile_url')[0]
        name = user['first_name']
        profile_url = user['profile_url']

        feed = ET.Element(atomElement('feed'))
        addSubElement(feed, atomElement('title'),
                attrs={'type': 'text'}, 
                text='Notes for %s' % name)
        addSubElement(addSubElement(feed, atomElement('author')),
                atomElement('name'),
                text=name)

        for status in statuses:
            entry = addSubElement(feed, atomElement('entry'))
            addSubElement(entry, atomElement('id'),
                    text='%s?v=feed&story_fbid=%s' % (profile_url,
                        status['status_id']))
            addSubElement(entry, atomElement('title'),
                    attrs={'type': 'text'},
                    text=status['message'])
            addSubElement(entry, atomElement('published'),
                    text=fmtTime(status['time']))
            addSubElement(entry, atomElement('author'),
                    text=name)
            addSubElement(entry, atomElement('content'),
                    attrs={'type': 'html'},
                    text=status['message'])
        
        return ET.tostring(feed)

    @cherrypy.expose
    @fb_require_login
    def notes_xml(self, **kwargs):
        cherrypy.response.headers['Content-Type'] = "application/atom+xml"
        fb = cherrypy.request.facebook
        notes = fb.fql.query(
                '''SELECT note_id, created_time,
                    updated_time, title, content
                    FROM note
                    WHERE uid=%s
                    ORDER BY created_time''' % fb.uid)

        name = fb.users.getInfo(fb.uid, 'first_name')[0]['first_name']

        feed = ET.Element(atomElement('feed'))
        addSubElement(feed, atomElement('title'),
                attrs={'type': 'text'}, 
                text='Notes for %s' % name)
        addSubElement(addSubElement(feed, atomElement('author')),
                atomElement('name'),
                text=name)

        for note in notes:
            entry = addSubElement(feed, atomElement('entry'))
            addSubElement(entry, atomElement('id'),
                    text='http://www.facebook.com/notes.php?id=%s' % note['note_id'])
            addSubElement(entry, atomElement('title'),
                    attrs={'type': 'text'},
                    text=note['title'])
            addSubElement(entry, atomElement('published'),
                    text=fmtTime(note['created_time']))
            addSubElement(entry, atomElement('updated'),
                    text=fmtTime(note['updated_time']))
            addSubElement(entry, atomElement('author'),
                    text=name)
            addSubElement(entry, atomElement('content'),
                    attrs={'type': 'html'},
                    text=note['content'].replace('\n', '<br/>'))
        
        return ET.tostring(feed)

class FacebookTool:
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

