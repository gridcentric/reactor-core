from . import ROOT

# The path to the authorization hash used by the API to validate requests.
AUTH_HASH = "%s/auth" % (ROOT)
def auth_hash():
    return AUTH_HASH
