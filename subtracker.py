# Lifted heavily from Mustard Mine, and may have some unnecessary guff
import base64
import collections
import datetime
import functools
import json
import os
import sys
import threading
import time
import pytz
from pprint import pprint
# Hack: Get gevent to do its monkeypatching as early as possible.
# I have no idea what this is actually doing, but if you let the
# patching happen automatically, it happens too late, and we get
# RecursionErrors and such. There's a helpful warning on startup.
from gevent import monkey; monkey.patch_all(subprocess=True)
from flask import Flask, request, redirect, session, url_for, g, render_template, jsonify, Response, Markup
from authlib.integrations.requests_client import OAuth2Session
import requests

try:
	import config
except ImportError:
	# Construct a config object out of the environment
	import config_sample as config
	failed = []
	# Hack: Some systems like to give us a DATABASE_URL instead of a DATABASE_URI
	if "DATABASE_URL" in os.environ: os.environ["DATABASE_URI"] = os.environ["DATABASE_URL"]
	for var in dir(config):
		if var.startswith("__"): continue # Ignore dunders
		if var in os.environ: setattr(config, var, os.environ[var])
		else: failed.append(var)
	if failed:
		print("Required config variables %s not found - see config_sample.py" % ", ".join(failed), file=sys.stderr)
		sys.exit(1)
	sys.modules["config"] = config # Make the config vars available elsewhere

import database
app = Flask(__name__)
app.secret_key = config.SESSION_SECRET or base64.b64encode(os.urandom(12))

# Override Flask's forcing of Location headers to be absolute, since it
# gets stuff flat-out wrong. Also, the spec now says that relative
# headers are fine (and even when the spec said that the Location should
# to be absolute, everyone accepted relative URIs).
if os.environ.get("OVERRIDE_REDIRECT_HTTPS"):
	from werkzeug.middleware.proxy_fix import ProxyFix
	app.wsgi_app = ProxyFix(app.wsgi_app) # Grab info from Forwarded headers
	_redirect = redirect
	def redirect(*a, **kw):
		resp = _redirect(*a, **kw)
		resp.autocorrect_location_header = False
		return resp
	_url_for = url_for
	def url_for(*a, **kw): return _url_for(*a, **kw).replace("http://", "https://")

REQUIRED_SCOPES = "channel_subscriptions" # Ensure that these are sorted

class TwitchDataError(Exception):
	def __init__(self, error):
		self.__dict__.update(error)
		super().__init__(error["message"])

def query(endpoint, *, token, method="GET", params=None, data=None, auto_refresh=True):
	# If this is called outside of a Flask request context, be sure to provide
	# the auth token, and set auto_refresh to False.
	# TODO: Tidy up all this mess of auth patterns. It'll probably be easiest
	# to migrate everything to Helix first, and then probably everything will
	# use Bearer or App authentication.
	if token is None:
		auth = None
	elif token == "oauth":
		auth = "OAuth " + session["twitch_token"]
	elif token == "bearer":
		auth = "Bearer " + session["twitch_token"]
	elif token == "app":
		r = requests.post("https://id.twitch.tv/oauth2/token", data={
			"grant_type": "client_credentials",
			"client_id": config.CLIENT_ID, "client_secret": config.CLIENT_SECRET,
		})
		r.raise_for_status()
		data = r.json()
		auth = "Bearer " + data["access_token"]
		# TODO: Save the token so long as it's valid
		# expires = int(time.time()) + data["expires_in"] - 120
	else:
		auth = "OAuth " + token

	if not endpoint.startswith(("kraken/", "helix/")): raise ValueError("Need explicit selection of API (helix or kraken)")
	r = requests.request(method, "https://api.twitch.tv/" + endpoint,
		params=params, data=data, headers={
		"Accept": "application/vnd.twitchtv.v5+json",
		"Client-ID": config.CLIENT_ID,
		"Authorization": auth,
	})
	if auto_refresh and r.status_code == 401 and r.json()["message"] == "invalid oauth token":
		r = requests.post("https://id.twitch.tv/oauth2/token", data={
			"grant_type": "refresh_token",
			"refresh_token": session["twitch_refresh_token"],
			"client_id": config.CLIENT_ID, "client_secret": config.CLIENT_SECRET,
		})
		r.raise_for_status()
		resp = r.json()
		session["twitch_token"] = resp["access_token"]
		session["twitch_refresh_token"] = resp["refresh_token"]

		# Recurse for simplicity. Do NOT pass the original token, and be sure to
		# prevent infinite loops by disabling auto-refresh. Otherwise, pass-through.
		# (But DO pass the token-passing mode.)
		return query(endpoint, token="bearer" if token == "bearer" else "oauth",
			method=method, params=params, data=data, auto_refresh=False)
	if r.status_code == 403:
		# TODO: What if it *isn't* of this form??
		raise TwitchDataError(json.loads(r.json()["message"]))
	r.raise_for_status()
	if r.status_code == 204: return {}
	return r.json()

@app.route("/")
def mainpage():
	# NOTE: If we've *reduced* the required scopes, this will still force a re-login.
	# However, it'll be an easy login, as Twitch will recognize the existing auth.
	if "twitch_token" not in session or "twitch_user" not in session or session.get("twitch_auth_scopes") != REQUIRED_SCOPES:
		return render_template("login.html")
	user = session["twitch_user"]
	channelid = user["_id"]
	database.ensure_user(channelid)
	return render_template("index.html", username=user["display_name"])

@app.route("/login")
def login():
	twitch = OAuth2Session(config.CLIENT_ID, config.CLIENT_SECRET,
		scope=REQUIRED_SCOPES)
	uri, state = twitch.create_authorization_url("https://id.twitch.tv/oauth2/authorize",
		redirect_uri=os.environ.get("OVERRIDE_REDIRECT_URI") or url_for("authorized", _external=True))
	session["login_state"] = state
	return redirect(uri)

@app.route("/login/authorized")
def authorized():
	if "error" in request.args:
		# User cancelled the auth flow - discard auth (most likely there won't be any)
		session.pop("twitch_token", None)
		return redirect(url_for("mainpage"))
	twitch = OAuth2Session(config.CLIENT_ID, config.CLIENT_SECRET,
		state=session["login_state"])
	resp = twitch.fetch_access_token("https://id.twitch.tv/oauth2/token",
		code=request.args["code"],
		# For some bizarre reason, we need to pass this information along.
		client_id=config.CLIENT_ID, client_secret=config.CLIENT_SECRET,
		redirect_uri=url_for("authorized", _external=True))
	if "access_token" not in resp:
		# Something went wrong with the retrieval. No idea what or why,
		# so I'm doing a cop-out and just dumping to console.
		print("Unable to log in")
		pprint(resp)
		print("Returning generic failure.")
		raise Exception
	session["twitch_token"] = resp["access_token"]
	session["twitch_refresh_token"] = resp["refresh_token"]
	session["twitch_auth_scopes"] = " ".join(sorted(resp["scope"]))
	# kraken_user = query("kraken/user", token="oauth")
	# The Kraken response includes fields not in Helix, including created_at,
	# and email (though Helix gives us the latter if we add an OAuth scope).
	user = query("helix/users", token="bearer")["data"][0]
	user["_id"] = user["id"] # For now, everything looks for _id. Existing logins don't have user["id"].
	database.ensure_user(user["_id"])
	session["twitch_user"] = user
	return redirect(url_for("mainpage"))

# TODO: JSON API endpoints for uploading a CSV, and forcing a recheck

if __name__ == "__main__":
	import logging
	logging.basicConfig(level=logging.INFO)
	# Load us up using gunicorn, configured via the Procfile
	with open("Procfile") as f: cmd = f.read().strip().replace("web: ", "")
	if "PORT" not in os.environ: os.environ["PORT"] = "5000" # hack - pick a different default port
	sys.argv = cmd.split(" ")[1:] # TODO: Split more smartly
	from gunicorn.app.wsgiapp import run; run()
else:
	# Worker startup. This is the place to put any actual initialization work
	# as it won't be done on master startup.
	pass
