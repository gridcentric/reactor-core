from . endpoints import endpoint

# Sessions.
def sessions(name):
    return "%s/sessions" % (endpoint(name))

def session(name, session):
    return "%s/%s" % (sessions(name), session)

def sessions_dropped(name):
    return "%s/dropped" % (endpoint(name))

def session_dropped(name, session):
    return "%s/%s" % (sessions_dropped(name), session)
