import psycopg2.extras
import config
import contextlib
import collections
import json
import os
import base64
import pytz
from datetime import datetime, timedelta

# NOTE: We use one single connection per process, but every function in this module
# creates its own dedicated cursor. This means that these functions should be thread
# safe; psycopg2 has thread-safe connections but not thread-safe cursors.
assert psycopg2.threadsafety >= 2
postgres = psycopg2.connect(config.DATABASE_URI)

# Assumes that dict preserves insertion order (CPython 3.6+, other Python 3.7+, possible 3.5)
# Otherwise, tables might be created in the wrong order, breaking foreign key refs.
TABLES = {
	"users": [
		"twitchid integer primary key",
		"subs_updated timestamptz not null default '1970-1-1Z'",
	],
	"subs": [
		"twitchid integer not null references subtracker.users",
		"tenure smallint not null",
		"primary key (twitchid, tenure)",
		"created timestamptz not null",
		"tier smallint not null",
		"streak smallint not null",
	],
}

# https://postgrespro.com/list/thread-id/1544890
# Allow <<DEFAULT>> to be used as a value in an insert statement
class Default(object):
	def __conform__(self, proto):
		if proto is psycopg2.extensions.ISQLQuote: return self
	def getquoted(self): return "DEFAULT"
DEFAULT = Default()
del Default

def create_tables():
	with postgres, postgres.cursor() as cur:
		cur.execute("create schema if not exists subtracker")
		cur.execute("""select table_name, column_name
				from information_schema.columns
				where table_schema = 'subtracker'
				order by ordinal_position""")
		tables = collections.defaultdict(list)
		for table, column in cur:
			tables[table].append(column)
		for table, columns in TABLES.items():
			if table not in tables:
				# Table doesn't exist - create it. Yes, I'm using percent
				# interpolation, not parameterization. It's an unusual case.
				cur.execute("create table subtracker.%s (%s)" % (
					table, ",".join(columns)))
			else:
				# Table exists. Check if all its columns do.
				# Note that we don't reorder columns. Removing works,
				# but inserting doesn't - new columns will be added at
				# the end of the table.
				want = {c.split()[0]: c for c in columns if not c.startswith("primary key")}
				have = tables[table]
				need = [c for c in want if c not in have] # Set operations but preserving order to
				xtra = [c for c in have if c not in want] # the greatest extent possible.
				if not need and not xtra: continue # All's well!
				actions = ["add " + want[c] for c in need] + ["drop column " + c for c in xtra]
				cur.execute("alter table subtracker." + table + " " + ", ".join(actions))
create_tables()

def ensure_user(twitchid):
	try:
		with postgres, postgres.cursor() as cur:
			cur.execute("insert into subtracker.users values (%s)", [twitchid])
	except psycopg2.IntegrityError:
		pass

def bulk_load_subs(twitchid, data):
	...

def update_subs_from_api(twitchid, data):
	...
