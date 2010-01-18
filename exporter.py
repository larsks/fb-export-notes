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

try:
    from google.appengine.api import memcache
    sys.modules['memcache'] = memcache
except ImportError:
    pass

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
    @cherrypy.expose
    @fb_require_login
    def index(self, **kwargs):
        text = ['<h1>Params</h1>']
        
        text.append('<table>')
        for k,v in kwargs.items():
            text.append('<tr><td>%s</td><td>%s</td></tr>' % (k,v))
        text.append('</table>')

        fb = cherrypy.request.facebook

        text.append('<p>api = %s</p>' % fb.api_key)
        text.append('<p>secret = %s</p>' % fb.secret_key)
        text.append('<p>fb user = %s</p>' % fb.uid)
        text.append('<p>fb session_key = %s</p>' % fb.session_key)

        try:
            user = fb.users.getLoggedInUser()
            text.append('<p>user info: %s</p>' % user)
        except facebook.FacebookError, detail:
            text.append('<p>api call failed: %s</p>' % detail)

        info = fb.users.getInfo(fb.uid)

        text.append('<h1>User info</h1>')
        for d in info:
            text.append('<h2>%s</h2>' % d['name'])
            text.append('<table>')
            for k,v in d.items():
                text.append('<tr><td>%s</td><td>%s</td></tr>' % (k,v))
            text.append('</table>')

        text.append('<p>session id: %s</p>' % cherrypy.session.id)

        text.append('''<a href="%s/notes_xml?fb_sig_user=%s&fb_sig_session_key=%s"
            >Notes (Atom feed)</a>''' % (
                cherrypy.request.app.config['facebook']['base url'],
                fb.uid,
                fb.session_key))
            
        text.append('''<a href="%s/status_xml?fb_sig_user=%s&fb_sig_session_key=%s"
            >Status (Atom feed)</a>''' % (
                cherrypy.request.app.config['facebook']['base url'],
                fb.uid,
                fb.session_key))
            
        return '\n'.join(text)

    @cherrypy.expose
    def session_info(self, **kwargs):
        text = ['<h1>Session</h1>']

        text.append('<p>session id: %s</p>' % cherrypy.session.id)
        text.append('<table>')
        for k,v in cherrypy.session.items():
            text.append('<tr><td>%s</td><td>%s</td></tr>' % (k,v))
        text.append('</table>')

        return '\n'.join(text)

    @cherrypy.expose
    @fb_require_login
    def notes(self, **kwargs):
        fb = cherrypy.request.facebook
        notes = fb.fql.query(
                '''SELECT note_id, created_time,
                    updated_time, title, content
                    FROM note WHERE uid=%s''' % fb.uid)

        text = [ '<h1>Notes</h1>' ]
        text.append('<table>')
        for note in notes:
            text.append('<tr><td>%(note_id)s</td><td>%(title)s</td></tr>' % note)
        text.append('</table>')

        return '\n'.join(text)

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

