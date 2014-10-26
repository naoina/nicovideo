A library for Nicovideo
============================================================

http://www.nicovideo.jp/

Features
--------

- Get a video information
- Mylist manipulation
- Get the video informations from new arrival
- Get the video informations by tag search
- Video download

Requirements
------------

- Python 3.x and later

Installation
------------

from pypi::

   % pip install nicovideo

from source::

   % python setup.py install

Usage
-----

::

   from nicovideo import Nicovideo

   nico = Nicovideo()
   nico.append('sm9')
   nico.append('sm3504435')
   for v in nico:
      print(v.video_id)
      print(v.title)
      print(v.description)
      print(v.watch_url)

See source for more details.

LICENSE
-------

MIT
