from google.appengine.ext.webapp import template

register = template.create_template_register()

@register.filter
def contains(var, k):
    try:
        return k in var
    except TypeError:
        return False

