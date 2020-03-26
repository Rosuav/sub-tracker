Sub Tracker
===========

Source code for https://sub-tracker.herokuapp.example.com/ and also available for
individual deployment as desired.

TODO:

* Receive uploads of CSV files of historical subscriber data
* Periodically (automatically) check with the API for new subs
  - Daily would be best
  - Allow a manual recheck


Requires Python 3.6 or newer. MAY run on 3.5 but not guaranteed.

NOTE: On Python 3.8+, newer versions of gevent and werkzeug may be needed:
pip install -v git+git://github.com/gevent/gevent.git#egg=gevent
pip install -v git+git://github.com/pallets/werkzeug
