# -*- coding: utf-8 -*-
# Based on contents from https://github.com/Diecke/service.subtitles.addicted
# Thanks Diecke!

import os
import sys
import xbmc
import urllib
import urllib2
import xbmcvfs
import xbmcaddon
import xbmcgui
import xbmcplugin
import shutil
import unicodedata
import re
import socket
import string
import threading

from BeautifulSoup import BeautifulSoup

__addon__ = xbmcaddon.Addon()
__scriptid__ = __addon__.getAddonInfo('id')
__scriptname__ = __addon__.getAddonInfo('name')
__version__ = __addon__.getAddonInfo('version')
__language__ = __addon__.getLocalizedString

__cwd__ = xbmc.translatePath(__addon__.getAddonInfo('path')).decode("utf-8")
__profile__ = xbmc.translatePath(__addon__.getAddonInfo('profile')).decode("utf-8")
__resource__ = xbmc.translatePath(os.path.join(__cwd__, 'resources', 'lib')).decode("utf-8")
__temp__ = xbmc.translatePath(os.path.join(__profile__, 'temp', '')).decode("utf-8")

sys.path.append(__resource__)

from Addic7edUtilities import log, get_language_info

self_host = "http://www.addic7ed.com"
self_release_pattern = re.compile("Version (.+), ([0-9]+).([0-9])+ MBs")

req_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 5.1; en-US) AppleWebKit/525.13 (KHTML, like Gecko) '
                  'Chrome/0.A.B.C Safari/525.13',
    'Referer': 'http://www.addic7ed.com'}


def get_url(url):
    request = urllib2.Request(url, headers=req_headers)
    opener = urllib2.build_opener()
    response = opener.open(request)

    return response.read(), response.geturl()


def append_subtitle(sub_link):
    list_item = xbmcgui.ListItem(
        label=sub_link['lang']['name'],
        label2=sub_link['filename'],
        iconImage=sub_link['rating'],
        thumbnailImage=sub_link['lang']['2let'])

    list_item.setProperty("sync", 'true' if sub_link["sync"] else 'false')
    list_item.setProperty("hearing_imp", 'true' if sub_link["hearing_imp"] else 'false')

    url = "plugin://%s/?action=download&link=%s&filename=%s" % (__scriptid__, sub_link['link'], sub_link['filename'])
    xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=url, listitem=list_item, isFolder=False)


def query_tvshow(name, season, episode, languages, file_original_path):
    if season.isdigit() is not True or episode.isdigit() is not True:
        return None
    name = addic7ize(name).lower().replace(" ", "_")
    search_url = "%s/serie/%s/%s/%s/addic7ed" % (self_host, name, season, episode)
    query(search_url, languages, file_original_path)


def query_film(name, year, languages, file_original_path):
    if type(year) is not int:
        return None
    name = urllib.quote(name.replace(" ", "_"))
    search_url = "%s/film/%s_(%s)-Download" % (self_host, name, str(year))
    query(search_url, languages, file_original_path)


def query(search_url, languages, file_original_path=None):
    sub_links = []
    socket.setdefaulttimeout(20)
    request = urllib2.Request(search_url, headers=req_headers)
    request.add_header('Pragma', 'no-cache')
    page = urllib2.build_opener().open(request)
    content = page.read()
    content = content.replace("The safer, easier way", "The safer, easier way \" />")
    soup = BeautifulSoup(content)

    if file_original_path is not None:
        file_original_path_clean = normalize_string(file_original_path.encode('utf-8'))
        file_name = str(os.path.basename(file_original_path_clean)).split("-")[-1].lower()
    else:
        file_name = None

    for language_html in soup("td", {"class": "language"}):
        box = language_html.findPrevious("td", {"class": "NewsTitle", "colspan": "3"})
        full_language = str(language_html).split('class="language">')[1].split('<a')[0].replace("\n", "")
        sub_teams = self_release_pattern.match(str(box.contents[1])).groups()[0]

        if file_name is not None and (str(sub_teams.replace("WEB-DL-", "").lower()).find(str(file_name))) > -1:
            hashed = True
        else:
            hashed = False

        sub_language = get_language_info(full_language)
        if sub_language is None:
            sub_language = {}

        status_td = language_html.findNext("td")
        status = status_td.find("b").string.strip()

        link_td = status_td.findNext("td")
        link = "%s%s" % (self_host, link_td.find("a")["href"])

        if box.findNext("td", {"class": "newsDate", "colspan": "2"}).findAll('img', {'title': 'Hearing Impaired'}):
            hearing_imp = True
        else:
            hearing_imp = False

        if status == "Completed" and (sub_language['3let'] in languages):
            title = soup.find('span', {'class': 'titulo'}).contents[0].strip(' \t\n\r')
            sub_links.append(
                {'rating': '0',
                 'filename': "%s - %s" % (title, sub_teams),
                 'sync': hashed,
                 'link': link,
                 'lang': sub_language,
                 'hearing_imp': hearing_imp})

    sub_links.sort(key=lambda x: [not x['sync']])
    log(__name__, "sub='%s'" % sub_links)

    for sub_link in sub_links:
        append_subtitle(sub_link)


def search_manual(search_string, languages):
    url = self_host + "/search.php?search=" + search_string + '&Submit=Search'
    content, response_url = get_url(url)

    if content is not None:
        if not response_url.startswith(self_host + "/search.php?"):
            # A single result has been found
            query(response_url, languages)
        else:
            # A table containing several results
            soup = BeautifulSoup(content)
            table = soup.find('table', attrs={'class': 'tabel'})
            if table is not None:
                links = table.findAll('a')
                threads = [threading.Thread(target=query, args=(self_host + "/" + link['href'], languages))
                           for link in links]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()


def search_filename(filename):
    title, year = xbmc.getCleanMovieTitle(filename)
    log(__name__, "clean title: \"%s\" (%s)" % (title, year))
    try:
        year_val = int(year)
    except ValueError:
        year_val = 0
    if title and year_val > 1900:
        query_film(title, year, item['3let_language'], filename)
    else:
        match = re.search(r'\WS(?P<season>\d\d)E(?P<episode>\d\d)', title, flags=re.IGNORECASE)
        if match is not None:
            tvshow = string.strip(title[:match.start('season') - 1])
            season = string.lstrip(match.group('season'), '0')
            episode = string.lstrip(match.group('episode'), '0')
            query_tvshow(tvshow, season, episode, item['3let_language'], filename)
        else:
            search_manual(filename, item['3let_language'])


def search(data):
    filename = os.path.splitext(os.path.basename(data['file_original_path']))[0]
    log(__name__, "Search_addic7ed='%s', filename='%s', addon_version=%s" % (data, filename, __version__))

    if data['mansearch']:
        search_manual(data['mansearchstr'], data['3let_language'])
    elif data['tvshow']:
        query_tvshow(data['tvshow'], data['season'], data['episode'], data['3let_language'], filename)
    elif data['title'] and data['year']:
        query_film(data['title'], data['year'], data['3let_language'], filename)
    else:
        search_filename(filename)


def download(link):
    subtitle_list = []

    if xbmcvfs.exists(__temp__):
        shutil.rmtree(__temp__)
    xbmcvfs.mkdirs(__temp__)

    sub_file = os.path.join(__temp__, "addic7ed.srt")

    f, _ = get_url(link)

    local_file_handle = open(sub_file, "wb")
    local_file_handle.write(f)
    local_file_handle.close()

    subtitle_list.append(sub_file)

    if len(subtitle_list) == 0:
        xbmc.executebuiltin((u'Notification(%s,%s)' % (__scriptname__, __language__(32003))).encode('utf-8'))

    return subtitle_list


def normalize_string(string_to_normalize):
    return unicodedata.normalize('NFKD', unicode(unicode(string_to_normalize, 'utf-8'))).encode('ascii', 'ignore')


# Sometimes search fail because Addic7ed uses URLs that does not match the TheTVDB format.
# This will probably grow to be a hardcoded collection over time.
def addic7ize(name):
    addic7ize_dict = eval(open(__cwd__ + '/addic7ed_dict.txt').read())
    return addic7ize_dict.get(name, name)


def get_params():
    param = {}
    param_string = sys.argv[2]
    if len(param_string) >= 2:
        cleaned_params = param_string.replace('?', '')
        if cleaned_params[-1] == '/':
            cleaned_params = cleaned_params[0:len(cleaned_params) - 2]
        pairs_of_params = cleaned_params.split('&')
        param = {}
        for i in range(len(pairs_of_params)):
            splitparams = pairs_of_params[i].split('=')
            if (len(splitparams)) == 2:
                param[splitparams[0]] = splitparams[1]

    return param


params = get_params()

if params['action'] == 'search' or params['action'] == 'manualsearch':
    item = {'temp': False, 'rar': False, 'mansearch': False, 'year': xbmc.getInfoLabel("VideoPlayer.Year"),
            'season': str(xbmc.getInfoLabel("VideoPlayer.Season")),
            'episode': str(xbmc.getInfoLabel("VideoPlayer.Episode")),
            'tvshow': normalize_string(xbmc.getInfoLabel("VideoPlayer.TVshowtitle")),
            'title': normalize_string(xbmc.getInfoLabel("VideoPlayer.OriginalTitle")),
            'file_original_path': urllib.unquote(xbmc.Player().getPlayingFile().decode('utf-8')), '3let_language': []}

    if 'searchstring' in params:
        item['mansearch'] = True
        item['mansearchstr'] = params['searchstring']

    for lang in urllib.unquote(params['languages']).decode('utf-8').split(","):
        item['3let_language'].append(xbmc.convertLanguage(lang, xbmc.ISO_639_2))

    if item['title'] == "":
        item['title'] = normalize_string(xbmc.getInfoLabel("VideoPlayer.Title"))  # no original title, get just Title

    if item['episode'].lower().find("s") > -1:  # Check if season is "Special"
        item['season'] = "0"  #
        item['episode'] = item['episode'][-1:]

    if item['file_original_path'].find("http") > -1:
        item['temp'] = True

    elif item['file_original_path'].find("rar://") > -1:
        item['rar'] = True
        item['file_original_path'] = os.path.dirname(item['file_original_path'][6:])

    elif item['file_original_path'].find("stack://") > -1:
        stackPath = item['file_original_path'].split(" , ")
        item['file_original_path'] = stackPath[0][8:]

    search(item)

elif params['action'] == 'download':
    subs = download(params["link"])
    for sub in subs:
        listItem = xbmcgui.ListItem(label=sub)
        xbmcplugin.addDirectoryItem(handle=int(sys.argv[1]), url=sub, listitem=listItem, isFolder=False)

xbmcplugin.endOfDirectory(int(sys.argv[1]))  # send end of directory to XBMC
