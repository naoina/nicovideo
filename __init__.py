"""Nicovideo(http://www.nicovideo.jp/) handling library for Python3.x."""

__author__ = "Naoya Inada <naoina@naniyueni.org>"

import os.path
import re
import time
import json

from collections import OrderedDict
from datetime import datetime
from xml.etree import ElementTree
from xml.sax.saxutils import unescape

from urllib.parse import (quote, parse_qs)
from urllib.parse import urlencode as orig_urlencode
from urllib.request import (build_opener, urlopen, HTTPCookieProcessor)
from http.cookiejar import CookieJar
from nicovideo.decorator import decorator # for pydoc

__all__ = [
    # Classes
    "Tag", "TagSort", "Nicovideo", "Mylist", "NicoLogin",

    # Exceptions
    "DeletedError", "LoginError", "NotLoginError", "ExistsError", "MaxError"
    ]

LOGIN_BASE = "https://secure.nicovideo.jp/secure/"
LOGIN_URL  = LOGIN_BASE + "login?site=niconico"
LOGOUT_URL = LOGIN_BASE + "logout"
THUMB_URL  = "http://ext.nicovideo.jp/api/getthumbinfo/"
I_NICOVIDEO_URL = "http://i.nicovideo.jp/v3/video.array?v="
MAIN_URL   = "http://www.nicovideo.jp/"
TAGSEARCH_URL  = MAIN_URL + "tag/{word}?page={page}&sort={sort}&order={order}&rss=atom"
NEWARRIVAL_URL = MAIN_URL + "newarrival?page={page}&rss=atom"
WATCH_URL = MAIN_URL + "watch/{video_id}"
GETVIDEO_URL   = MAIN_URL + "api/getflv?v={video_id}&as3=1"
FEED_NS = "http://www.w3.org/2005/Atom"

RETRY_WAIT  = 5 # sec
RETRY_COUNT = 5

def urlencode(*args, **kwargs):
    return orig_urlencode(*args, **kwargs).encode('utf-8')

def retry(fn, count, interval=3):
    while True:
        try:
            return fn()
        except:
            if count:
                time.sleep(interval)
            else:
                raise

            count -= 1


class IVideo(object):
    """Video information from i.nicovideo.jp API"""

    def __init__(self, video_id):
        f = retry(lambda: urlopen(I_NICOVIDEO_URL + video_id), RETRY_COUNT)
        try:
            self.parse(f)
        except DeletedError as e:
            raise DeletedError(" ".join((video_id, str(e))))

    def parse(self, src):
        info = ElementTree.parse(src).getroot()
        count = info.find("count").text
        if count.isdigit and int(count) == 0:
            raise DeletedError("failed to get video info")
        video_info = info.find("video_info")
        for name in ("video", "thread"):
            setattr(self, name, lambda: None)
            for child in video_info.find(name).findall("*"):
                value = child.text
                if value and value.isdigit():
                    value = int(value)
                setattr(getattr(self, name), child.tag, value)
        self.video.title = unescape(self.video.title, {'&quot;': '"'})
        self.video.first_retrieve = datetime.strptime(
            self.video.first_retrieve, "%Y-%m-%dT%H:%M:%S+09:00")
        tags = Tags()
        for tag in video_info.findall("tags/tag_info/tag"):
            tags.append(Tag(tag.text, False))
        self.tags = tags


class Video:
    """Video information class."""

    def __init__(self, video_id):
        try:
            f = retry(lambda: urlopen(THUMB_URL + video_id), RETRY_COUNT)
            self._parse(f)
        except DeletedError as e:
            raise DeletedError(" ".join([video_id, str(e)]))

    def _parse(self, source):
        if isinstance(source, str):
            thumbinfo = ElementTree.fromstring(source)
        elif isinstance(source, bytes):
            thumbinfo = ElementTree.fromstring(source.decode("utf-8", "ignore"))
        elif hasattr(source, "read"):
            thumbinfo = ElementTree.parse(source).getroot()
        else:
            raise TypeError("source is string, bytes and file object only.")

        if thumbinfo.get("status") != "ok":
            err = thumbinfo.find("error/description").text
            raise DeletedError(err)

        thumb = thumbinfo.find("thumb")

        element_text = [
                "video_id", "title", "description", "thumbnail_url", "first_retrieve",
                "length", "movie_type", "last_res_body", "watch_url", "thumb_type",
                "embeddable", "no_live_play", "user_id"
                ]

        element_int = [
                "size_high", "size_low", "view_counter", "comment_num", "mylist_counter"
                ]

        for e in element_text:
            elem = thumb.find(e)
            value = elem.text if hasattr(elem, "text") else ""

            exec(r'self.{} = value'.format(e))

        for e in element_int:
            exec(r'self.{0} = int(thumb.find("{0}").text)'.format(e))

        self.title = unescape(self.title, {'&quot;': '"'})
        self.first_retrieve = datetime.strptime(self.first_retrieve, "%Y-%m-%dT%H:%M:%S+09:00")
        self.embeddable = self.embeddable == "1"

        l = self.length.split(":")
        self.length = int(l[0]) * 60 + int(l[1]) # convert to seconds.

        self._parsetag(thumb)

    def _parsetag(self, thumb):
        self.tags = Tags()

        for tags in [t for t in thumb.findall("tags") if t.get("domain") == "jp"]:
            for tag in [t for t in tags if hasattr(t, "text")]:
                self.tags.append(Tag(tag.text, tag.get("lock")))

class Tags(list):
    def __iter__(self):
        for tag in super().__iter__():
            yield tag.tag

    def __contains__(self, item):
        return item in [t.tag for t in super().__iter__()]

class Tag:
    def __init__(self, tag, islock):
        self.tag = tag
        self.islock = bool(islock)

class ErrorBase(Exception):
    def __str__(self):
        return str(self._msg)

class DeletedError(ErrorBase):
    def __init__(self, msg):
        self._msg = msg

class LoginError(ErrorBase):    _msg = "login incorrect"
class NotLoginError(ErrorBase): _msg = "not logged in"
class OverAccessError(ErrorBase): _msg = "access overload"

# The sort order of tag search.
class TagSort:
    POST = "f"
    PLAY = "v"
    COMMENTTIME = ""
    COMMENTNUM = "r"
    MYLIST = "m"
    TIME   = "l"

class NicoLogin:
    """Common login session class."""

    islogin = False

    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        orig_open = self.opener.open

        def retry_open(*args, **kwds):
            return retry(lambda: orig_open(*args, **kwds), RETRY_COUNT, RETRY_WAIT)

        self.opener.open = retry_open

    def login(self, mail, password):
        """Login for http://www.nicovideo.jp/
        Raises LoginError if the can't login.
        """
        f = self.opener.open(LOGIN_URL, urlencode({"mail": mail, "password": password}))

        if f.read().decode("utf-8", "ignore").find("エラーメッセージ") != -1:
            raise LoginError

        self.islogin = True

    def logout(self):
        """Logout for http://www.nicovideo.jp/"""
        self.opener.open(LOGOUT_URL)
        self.islogin = False

    @classmethod
    def require(cls, f):
        def _(fn, cls, *args, **kwds):
            if not cls.islogin:
                raise NotLoginError

            return f(cls, *args, **kwds)
        return decorator(_, f)

################################################################################
### Nicovideo SECTION
################################################################################
class Nicovideo(NicoLogin):
    """Handling the Nicovideo."""

    def __init__(self, use_i_nicovideo_api=False):
        super().__init__()
        self._video = OrderedDict()
        self._mylist = {}
        self._use_i_nicovideo_api = use_i_nicovideo_api

    def __contains__(self, video_id):
        return video_id in self._video

    def __iter__(self):
        for v in self._video.values():
            yield v

    def __reversed__(self):
        return reversed(self._video)

    def __getitem__(self, video_id):
        return self._video[video_id]

    def __len__(self):
        return len(self._video)

    def __add__(self, inst):
        tmp = OrderedDict(self._video)
        tmp.update(inst)

        return tmp

    def __del__(self):
        self.logout()

    def append(self, video: str):
        """Append video information."""
        if isinstance(video, Video):
            video_id = video.video_id
            v = video
        elif isinstance(video, IVideo):
            video_id = video.video.id
            v = video
        else:
            video_id = video
            if self._use_i_nicovideo_api:
                v = IVideo(video_id)
            else:
                v = Video(video_id)
        self._video[video_id] = v

    def extend(self, nicovideo):
        """Extend video information by sequence of video_id."""
        for v in nicovideo:
            self.append(v)

    def pop(self, last=True) -> Video:
        """return and remove a Video instance.
        Video instance are returned in LIFO order if last is true or FIFO order
        if false.
        """
        return self._video.popitem(last)[1]

    def remove(self, video_id):
        """Remove video information of video_id."""
        self._video.pop(video_id)

    def clear(self):
        """Remove all items."""
        self._video.clear()

    @NicoLogin.require
    def getvideo(self, video_id, filename=""):
        """Download video.
        Raises NotLoginError if not logged in.
        """
        self.opener.open(WATCH_URL.format(video_id=video_id)) # Set referer

        s = self.opener.open(GETVIDEO_URL.format(video_id=video_id)).read().decode()
        f = self.opener.open(parse_qs(s)["url"][0])

        type = f.headers["Content-Type"]
        ext = "swf" if type == "application/x-shockwave-flash" else type.rsplit("/", 1)[1]

        filename = (video_id if filename == "" else filename) + "." + ext

        if not os.path.exists(filename):
            with open(filename, "wb") as out:
                out.write(f.read())

        return filename

    @NicoLogin.require
    def mylist(self, group_id):
        """Return Mylist instance by group_id.
        group_id is last number of http://www.nicovideo.jp/mylist/0000000
        Raises NotLoginError if not logged in.
        """
        try:
            return self._mylist[group_id]
        except KeyError:
            self._mylist[group_id] = Mylist(group_id, self)
            return self._mylist[group_id]

    def newarrival(self, page=1):
        """Get list of video_id from Atom feed of new arrial.
        page is feed page number.
        """
        return self._parserss(NEWARRIVAL_URL.format(page=page))

    def tagsearch(self, andkey="", orkey="", page=1, sort=TagSort.POST, reverse=False):
        """Get list of video_id by tag search.

        andkey is keyword of AND searching.
        orkey is keyword of OR searching.
        page is page number of search result.
        sort is sort order for search.
        reverse is reverse order of search result.
        """
        if not (andkey or orkey):
            return

        gen = lambda s, sep: quote(s) if isinstance(s, str) else sep.join(map(quote, s))
        keyword = []

        if andkey: keyword.append(gen(andkey, " "))
        if orkey: keyword.append(gen(orkey, "+or+"))

        fmt = {
            "word": " ".join(keyword),
            "page": page,
            "sort": sort,
            "order": "a" if reverse else ""
            }

        return self._parserss(TAGSEARCH_URL.format(**fmt))

    def _qn(self, e):
        return ElementTree.QName(FEED_NS, e).text

    def _parserss(self, url):
        f = retry(lambda: urlopen(url), RETRY_COUNT)
        feed = ElementTree.parse(f)

        result = []
        for entry in feed.findall(self._qn("entry")):
            link = entry.find(self._qn("link")).get("href")
            id = re.search("/([^/]+?)$", link)

            if bool(id):
                result.append(id.group(1))

        return result

################################################################################
### Mylist SECTION
################################################################################
MYLIST_URL = {
    "mylist": MAIN_URL + "my/mylist",
    "mylist_add": MAIN_URL + "mylist_add/video/{video_id}",
    "add":  MAIN_URL + "api/mylist/add",
    "remove": MAIN_URL + "api/mylist/delete",
    "list": MAIN_URL + "api/mylist/list",
}

class ExistsError(ErrorBase): _msg = "already registered"
class MaxError(ErrorBase): _msg = "registration upper limit"

class Mylist(NicoLogin):
    """Handling the mylist of Nicovideo"""

    def __init__(self, group_id, nicologin=None):
        """Initailize Mylist instance.
        group_id is last number of http://www.nicovideo.jp/mylist/0000000
        Using existing login session if nicologin is NicoLogin instance.
        """
        super().__init__()
        if isinstance(nicologin, NicoLogin):
            self.opener = nicologin.opener
            self.islogin = nicologin.islogin

        self._group_id = group_id
        self._oldurl  = ""
        self._oldhtml = ""
        self._cachedlist = None

    @NicoLogin.require
    def add(self, video_id):
        """Add a video_id to a mylist.
        Raises NotLoginError if not logged in.
        """
        self.video_id = video_id
        qs = {"group_id": self._group_id,
              "item_type": 0,
              "item_id": self._getitem_id(video_id),
              "description": "",
              "token": self._gettoken(MYLIST_URL["mylist_add"].format(video_id=video_id)),
              }
        res = self.opener.open(MYLIST_URL["add"], urlencode(qs))
        self._raise_if_error(res)
        self._cachedlist = None

    @NicoLogin.require
    def remove(self, video_id):
        """Remove a video_id from mylist.
        If the video_id not in mylist, raise a KeyError.
        Raises NotLoginError if not logged in.
        """
        self.video_id = video_id
        target = self._get_json_obj(video_id)

        if not target:
            raise KeyError(video_id)
        self._remove([target])

    @NicoLogin.require
    def discard(self, video_id):
        """Remove a video_id from mylist.
        If the video_id not in mylist, do nothing.
        Raises NotLoginError if not logged in.
        """
        try:
            self.remove(video_id)
        except KeyError:
            return

    @NicoLogin.require
    def clear(self):
        """Remove all items in mylist.
        Raises NotLoginError if not logged in.
        """
        self._remove(self._list_json())

    @NicoLogin.require
    def __iter__(self):
        for item in self._list_json():
            yield item["item_data"]["video_id"]

    @NicoLogin.require
    def __len__(self):
        return len(self._list_json())

    @NicoLogin.require
    def __contains__(self, video_id):
        return self._get_json_obj(video_id) is not None

    @NicoLogin.require
    def __reversed__(self):
        for item in reversed(self._list_json()):
            yield item["item_data"]["video_id"]

    def _get_json_obj(self, video_id):
        for item in self._list_json():
            if item["item_data"]["video_id"] == video_id:
                return item
        return None

    def _remove(self, targets):
        if not targets:
            return

        id_list = ["id_list[{}][]={}".format(t["item_type"],
            quote(str(t["item_id"]))) for t in targets]
        param = "&".join(["group_id=" + self._group_id,
                          "token=" + self._gettoken(MYLIST_URL["mylist"])] +
                          id_list)
        res = self.opener.open(MYLIST_URL["remove"], param.encode('utf-8'))
        self._raise_if_error(res)
        self._cachedlist = None

    def _list_json(self):
        if self._cachedlist:
            return self._cachedlist

        res = self.opener.open(MYLIST_URL["list"], urlencode({"group_id": self._group_id}))
        self._cachedlist = json.loads(res.read().decode("utf-8",
            "ignore"))["mylistitem"]

        return self._cachedlist

    def _raise_if_error(self, jsonobj):
        result = json.loads(jsonobj.read().decode("utf-8", "ignore"))
        if result["status"] != "ok":
            if result["status"] == "fail":
                if result["error"]["code"] == "EXIST":
                    raise ExistsError(self.video_id)
                elif result["error"]["code"] == "MAXERROR":
                    raise MaxError(self.video_id)
                else:
                    raise Exception(result)
            else:
                raise Exception(result)

    def _getitem_id(self, video_id):
        url = MYLIST_URL["mylist_add"].format(video_id=video_id)
        pat = r'<input type="hidden" name="item_id" value="(\d+)">'

        return self._scrape_mylist(url, pat)

    def _gettoken(self, url):
        return self._scrape_mylist(url, r'NicoAPI\.token = "(.*)"')

    def _scrape_mylist(self, url, pat):
        html = self._gethtml(url)
        m = re.search(pat, html)

        return m.group(1) if m else None

    def _gethtml(self, url):
        if self._oldurl == url and self._oldhtml:
            return self._oldhtml

        html = self.opener.open(url).read().decode("utf-8", "ignore")

        self._oldurl = url
        self._oldhtml = html

        return html
