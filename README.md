Sub Tracker
===========

Source code for https://twitch-sub-tracker.herokuapp.com/ and also available for
individual deployment as desired.

TODO:

* Receive uploads of CSV files of historical subscriber data
* Periodically (automatically) check with the API for new subs
  - Daily would be best
  - Allow a manual recheck
* With previously-uploaded CSV data, there are names but no IDs.
  - Ideally, figure out the effective date of the file, and use that
  - Otherwise, try to find whatever we can. Use the CmdrRoot API.


Requires Python 3.6 or newer. MAY run on 3.5 but not guaranteed.

NOTE: On Python 3.8+, newer versions of gevent and werkzeug may be needed:
pip install -v git+git://github.com/gevent/gevent.git#egg=gevent
pip install -v git+git://github.com/pallets/werkzeug
