#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008, 2009
# Copyright (C) Elkin Fricke (elkin@elkin.de) 2011, 2012
# Released under the terms of the GNU GPL v2

import commands
import datetime
import MySQLdb
import re
import os
import shutil
import stat
import socket
import sys
import tempfile
import time
import unicodedata
import fnmatch
import urlparse

import database
import gflags
import mythnettvcore
import proxyhandler
import utility
import series
import tvrage.api

import UnRAR2

# Note that plugins aren't actually plugins at the moment, and that flags
# parsing will be a problem for plugins when we get there (I think).
from plugins import bittorrent
from plugins import streamingsites

# import MythTV bindings... we could test if you have them, but if you don't, why do you need this script?
from MythTV import OldRecorded, Recorded, RecordedProgram, Record, Channel, System, \
                   MythDB, Video, MythVideo, MythBE, MythError, MythLog, MythXML

from stat import *

# import a modified version from ffmpeg wrapper
from plugins import video_inspector

FLAGS = gflags.FLAGS
gflags.DEFINE_boolean('force', False,
                      'Force downloads to run, even if they failed recently')


# Exceptions returned by this module
class StorageException(utility.LoggingException):
  """ Errors with storage of programs """

class DownloadException(utility.LoggingException):
  """ Errors in the download process """

class DirectoryException(utility.LoggingException):
  """ Errors in importing a directory """

def addChannel(icon, channel_id, channel_num, callsign, channelname):
  """ add a new dummy channel to the mythtvbackend  """
  try:
    if Channel(channel_id):
      return False
  except:
    pass
  data={}
  data['chanid'] = channel_id
  data['channum'] = str(channel_num)
  data['freqid'] = str(channel_num)
  data['atsc_major_chan'] = int(channel_num)
  data['icon'] = u''
  if icon != u'':
    data['icon'] = icon
  data['callsign'] = callsign
  data['name'] = channelname
  data['last_record'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
  try:
    Channel().create(data)
  except MythError, e:
    return False

  return True

def getAspectRatio(videoheigth, videowidth):
    """getAspectRatio -- return MythTV compatible aspect ratio
    """
    videoaspect = float(videowidth) / float(videoheight)
    if videoheight >= 1080:
      return '1080'
    elif videoheight >= 720:
      return '720'
    elif videowidth >= 1280:
      return 'HDTV'
    elif videoaspect >= 1.4:
      return 'WIDESCREEN'
    else:
      return ''

def storeAspect(videoaspect)
    """storeAspect -- writes aspect ratio to MythTV database
    as the python bindings don't seem to have a solution to this
    and MythWeb needs it
    """
    if FLAGS.verbose:
      out.write('Storing aspect ratio: %s\n' % videoaspect)
    if videoaspect < 1.41:
      aspecttype = 11
    elif videoaspect < 1.81:
      aspecttype = 12
    elif videoaspect < 2.31:
      aspecttype = 13 
    try:
      self.db.ExecuteSql('insert into recordedmarkup (chanid, starttime, mark, type, data)'
                         'values (%s, %s, 1, %s, NULL)'
                           %(chanid, self.db.FormatSqlValue('', start), aspecttype))
    except:
      out.write('Error storing aspect ratio: %s\n' % videoaspect)
      pass

def SafeForFilename(s):
  """SafeForFilename -- convert s into something which can be used for a 
    filename.
  """

  for c in [' ', '(', ')', '{', '}', '[', ']', ':', '\'', '"']:
    s = s.replace(c, '_')
  return s


def Prompt(prompt):
  """Prompt -- prompt for input from the user"""

  sys.stdout.write('%s >> ' % prompt)
  return sys.stdin.readline().rstrip('\n')


class MythNetTvProgram:
  """MythNetTvProgram -- a downloadable program.

  This class embodies everything we can do with a program. The existance
  of this class does not mean that the show has been fully downloaded and
  made available in MythTV yet. Instances of this class persist to the MySQL
  database.
  """

  def __init__(self, db):
    self.persistant = {}
    self.db = db

  def FromUrl(self, url, guid):
    """FromUrl -- start a program based on its URL"""

    new_video = True

    # Some URLs have the ampersand escaped
    url = url.replace('&amp;', '&')

    # Persist what we know now
    self.persistant['url'] = url
    self.persistant['filename'] = SafeForFilename(self.GetFilename(url))
    self.persistant['guid'] = guid

    try:
      if self.db.GetOneRow('select * from mythnettv_programs '
                          'where guid="%s";' % guid).keys() != []:
        new_video = False
    except:
      pass

    self.Store()
    self.db.Log('Updated show from %s with guid %s' %(url, guid))
    return new_video

  def FromInteractive(self, url, title, subtitle, description):
    """FromInteractive -- create a program by prompting the user for input
    for all the bits we need. We check if we have the data first, so that
    we're not too annoying.
    """

    if url:
      self.persistant['url'] = url
    if title:
      self.persistant['title'] = title
    if subtitle:
      self.persistant['subtitle'] = subtitle
    if description:
      self.persistant['description'] = description

    for key in ['url', 'title', 'subtitle', 'description']:
      if not self.persistant.has_key(key):
        self.persistant[key] = Prompt(key)

    # The GUID is now generated as the hex value of a hash of title and Subtitle
    # we make sure we therefore only have one download per title and subtitle
    self.persistant['guid'] = utility.hashtitlesubtitle(title, subtitle)
    self.persistant['filename'] = SafeForFilename(self.GetFilename(
                                    self.persistant['url']))

    self.Store()

  def GetFilename(self, url, out=sys.stdout):
    """GetFilename -- return the filename portion of a URL"""

    # Some URLs have the ampersand escaped
    re_filename = re.compile('.*/([^/\?]*).*')
    m = re_filename.match(url)
    if m:
      return m.group(1)
    if not '/' in url:
      return url

    raise(self.db, 'Could not determine local filename for %s\n' % url)

  def GetTitle(self):
    """GetTitle -- return the title of the program"""
    return self.persistant['title']

  def GetSubtitle(self):
    """GetSubtitle -- return the subtitle of the program"""
    return self.persistant['subtitle']

  def GetDate(self):
    """GetDate -- return the date of the program"""
    return self.persistant['unparsed_date']

  def SetDate(self, date):
    """SetDate -- set the date of the program"""
    self.persistant['date'] = date.strftime('%a, %d %b %Y %H:%M:%S')
    self.persistant['unparsed_date'] = date.strftime('%a, %d %b %Y %H:%M:%S')
    self.persistant['parsed_date'] = date

  def GetMime(self):
    """GetMime -- return the program's mime type"""
    return self.persistant['mime_type']

  def SetMime(self, mime):
    """SetMime -- set the program's mime type"""
    self.persistant['mime_type'] = mime

  def Load(self, guid):
    """Load -- load information based on a GUID from the DB"""
    self.persistant = self.db.GetOneRow('select * from mythnettv_programs '
                                        'where guid="%s";' % guid)

  def Store(self):
    """Store -- persist to MySQL"""

    # We store the date of the entry a lot of different ways
    if not self.persistant.has_key('date'):
      self.SetDate(datetime.datetime.now())

    try:
      self.db.WriteOneRow('mythnettv_programs', 'guid', self.persistant)
    except MySQLdb.Error, (errno, errstr):
      if errno != 1064:
        raise StorageException(self.db, 'Could not store program %s: %s "%s"'
                              %(self.persistant['guid'], errno, errstr))
    except database.FormatException, e:
      raise e
    except Exception, e:
      raise StorageException(self.db,
                            'Could not store program: %s: "%s" (%s)\n\n%s'
                            %(self.persistant['guid'], e, type(e),
                              repr(self.persistant)))

  def SetUrl(self, url):
    """SetUrl -- set just the URL for the program"""

    self.persistant['url'] = url

  def SetShowInfo(self, title, subtitle, description, date, date_parsed):
    """SetShowInfo -- set show meta data"""

    self.persistant['title'] = title
    self.persistant['subtitle'] = subtitle
    self.persistant['description'] = utility.massageDescription(description)
    self.persistant['date'] = date
    self.persistant['unparsed_date'] = date
    self.persistant['parsed_date'] = repr(date_parsed)
    self.Store()
    self.db.Log('Set show info for guid %s' % self.persistant['guid'])

  def TemporaryFilename(self, datadir, out=sys.stdout):
    """TemporaryFilename -- calculate the filename to use in the temporary
    directory
    """
    # put filename from url in database
    try:
      self.persistant['filename'] = SafeForFilename(self.GetFilename(self.persistant['url']))
    except:
      pass
    filename = '%s/%s' %(datadir, self.persistant['filename'])
    # Store in database
    #self.persistant['tmp_name'] = filename
    out.write('Destination directory will be %s\n' % datadir)
    self.db.Log('Downloading %s to %s' %(self.persistant['guid'], filename))
    return filename

  def DownloadMPlayer(self, filename):
    """DownloadRTSP -- download a show using mplayer"""
    datadir = self.db.GetSettingWithDefault('datadir', FLAGS.datadir)
    (status, out) = commands.getstatusoutput('cd %s; '
                                            'mplayer -dumpstream "%s"'
                                            %(datadir,
                                              self.persistant['url']))
    if status != 0:
      raise DownloadException('MPlayer download failed')

    shutil.move(datadir + '/stream.dump', filename)
    return os.stat(filename)[ST_SIZE]

  def DownloadHTTP(self, filename, force_proxy=None, force_budget=-1,
                  out=sys.stdout):
    """DownloadHTTP -- download a show, using HTTP"""

    out.write('Download URL is "%s"\n' % self.persistant['url'])
    done = self.persistant.get('download_finished', '0')
    if done != '1':
      proxy = proxyhandler.HttpHandler(self.db)
      try:
        remote = proxy.Open(self.persistant['url'], force_proxy=force_proxy,
                            force_budget=force_budget, out=out)
        out.write('Downloading %s\n' % self.persistant['url'])
      except Exception, e:
        raise DownloadException(self.db, 'HTTP download failed: %s' % e)

      local = open(filename, 'w')
      total = int(self.persistant.get('transfered', 0))

      this_attempt_total = proxyhandler.HTTPCopy(self.db, proxy, remote, local,
                                                out=out)
      total += this_attempt_total

      self.persistant['transfered'] = repr(total)
      self.persistant['size'] = repr(total)
      self.persistant['last_attempt'] = datetime.datetime.now()
      self.Store()

      remote.close()
      local.close()

      return total

  def Info(self, s):
    """Info -- A callback for download status information"""
    sys.stdout.write('%s: %s --> %s\n' %(self.persistant['title'],
                                        self.persistant['subtitle'],
                                        s))
    self.persistant['last_attempt'] = datetime.datetime.now()
    self.Store()

  def Download(self, datadir, force_proxy=None, force_budget=-1, out=sys.stdout):
    """Download -- download the show"""

    one_hour = datetime.timedelta(hours=1)
    if self.persistant['url'].endswith('torrent') \
      or self.persistant.get('mime_type', '').endswith('torrent'):
      # give torrents more time to download, set to 6 hours
      one_hour = datetime.timedelta(hours=6)
    one_hour_ago = datetime.datetime.now() - one_hour

    if FLAGS.verbose:
      out.write('Considering %s: %s\n' %(self.persistant['title'],
                                      self.persistant['subtitle']))
    
    if 'last_attempt' in self.persistant and \
      self.persistant['last_attempt'] > one_hour_ago:
      out.write('Last attempt was too recent. It was at %s\n'
                % self.persistant['last_attempt'])

      if not FLAGS.force:
        return False
      else:
        out.write('Download forced\n')

    self.persistant['last_attempt'] = datetime.datetime.now()

    filename = self.TemporaryFilename(datadir, out=out)

    self.persistant['download_started'] = '1'
    self.Store()

    out.write('Downloading %s: %s\n\n'
              %(self.persistant['title'],
                self.persistant['subtitle']))
                                    

    if 'attempts' in self.persistant and self.persistant['attempts']:
      max_attempts = int(self.db.GetSettingWithDefault('attempts', 3))
      print ('This is a repeat attempt (%d attempts so far, max is %d)'
            %(self.persistant['attempts'], max_attempts))
      if self.persistant['attempts'] > max_attempts:
        out.write('Too many failed attempts, giving up on this program\n')
        self.persistant['download_finished'] = 0
        self.persistant['imported'] = 0
        self.persistant['failed'] = 1
        self.Store()
        return False

    self.persistant.setdefault('attempts', 0)
    self.persistant['attempts'] += 1
    self.Store()

    total = 0
    
    #deal with torrent downloads but not magnet links
    if self.persistant['url'].endswith('torrent') \
      or (self.persistant.get('mime_type', '').endswith('torrent')
      and not self.persistant['url'].startswith('magnet')):
      total = self.DownloadHTTP(filename, force_proxy=force_proxy, out=out)
      if total == 0:
        self.Store()
        return False

      # DownloadHTTP thinks everything is complete because the HTTP download
      # finished OK. That's wrong.
      self.persistant['download_finished'] = None
      self.persistant['imported'] = None
      self.Store()

      if self.persistant.get('tmp_name', '') == '':
        (tmpfd, tmpname) = tempfile.mkstemp(dir=datadir)
        os.close(tmpfd)
        os.unlink(tmpname)
        self.persistant['tmp_name'] = tmpname
        self.Store()
      else:
        tmpname = self.persistant['tmp_name']

      # Upload rate can either be the shipped default, a new default from
      # the settings tables, or a temporary override
      
      # TODO(mikal): this needs to be some sort of more generic settings
      # passing thing
      if FLAGS.uploadrate:
        upload_rate = FLAGS.uploadrate
      else:
        upload_rate = self.db.GetSettingWithDefault('uploadrate', 100)

      total = bittorrent.Download(filename, tmpname, self.Info,
                                  upload_rate=upload_rate,
                                  verbose=FLAGS.verbose, out=out)

      if total > 0:
        self.persistant['filename'] = tmpname.split('/')[-1]
        total += int(self.persistant.get('transfered', 0))

        
    # Now deal with magnet links
    elif self.persistant['url'].startswith('magnet'):
      #TODO do we realy need this for magnet links?
      if self.persistant.get('tmp_name', '') == '':
        (tmpfd, tmpname) = tempfile.mkstemp(dir=datadir)
        os.close(tmpfd)
        os.unlink(tmpname)
        self.persistant['tmp_name'] = tmpname
        self.Store()
      else:
        tmpname = self.persistant['tmp_name']

      # Upload rate can either be the shipped default, a new default from
      # the settings tables, or a temporary override

      if FLAGS.uploadrate:
        upload_rate = FLAGS.uploadrate
      else:
        upload_rate = self.db.GetSettingWithDefault('uploadrate', 100)

      total = bittorrent.Download(self.persistant['url'], tmpname, self.Info,
                                  upload_rate=upload_rate,
                                  verbose=FLAGS.verbose, out=out)
        
    # deal with Vimeo downloads
    elif self.persistant['url'].startswith('http://vimeo'):
      vimeoid = re.search('clip_id=(\d+)', self.persistant['url'])
      out.write('VimeoID:     %s\n' % vimeoid.group(1))
      total = streamingsites.Download('Vimeo', vimeoid.group(1), datadir)
      self.persistant['filename'] = total

    #deal with YouTube downloads
    #TODO does it realy work?
    elif self.persistant['url'].startswith('http://www.youtube'):
      url_data = urlparse.urlparse(self.persistant['url'])
      query = urlparse.parse_qs(url_data.query)
      youtubeid = query["v"][0]
      out.write('YouTubeID:   %s\n' % youtubeid)
      total = streamingsites.Download('YouTube', youtubeid, datadir)
      out.write('%s/n' % total)
      self.persistant['filename'] = total

    elif self.persistant['url'].startswith('http://'):
      total = self.DownloadHTTP(filename, force_proxy=force_proxy,
                                force_budget=force_budget)
    else:
      total = self.DownloadMPlayer(filename)

    if total == 0:
      return False

    self.persistant['last_attempt'] = datetime.datetime.now()
    self.persistant['download_finished'] = '1'
    self.persistant['transfered'] = repr(total)
    self.persistant['size'] = repr(total)
    self.Store()
      
    out.write('Download complete...\n')
    self.db.Log('Download of %s done' % self.persistant['guid'])
    return True

  def CopyLocalFile(self, datadir, out=sys.stdout):
    """CopyLocalFile -- copy a local file to the temporary directory, and
    treat it as if it was a download"""

    filename = self.TemporaryFilename(datadir, out=out)
    self.persistant['download_started'] = '1'
    self.Store()

    if self.persistant['url'] != filename:
      shutil.copyfile(self.persistant['url'], filename)

    self.persistant['download_finished'] = '1'
    size = os.stat(filename)[ST_SIZE]
    self.persistant['transfered'] = repr(size)
    self.persistant['size'] = repr(size)
    self.Store()

    self.db.Log('Download of %s done' % self.persistant['guid'])

  def Import(self, out=sys.stdout):
    """Import -- import a downloaded show into the MythTV user interface"""
    
    # Determine meta data
    self.db.Log('Importing %s' % self.persistant['guid'])
    datadir = self.db.GetSettingWithDefault('datadir', FLAGS.datadir)
    chanid = self.db.GetOneRow('select chanid from mythnettv_subscriptions where '
                            'title="%s";' % self.persistant['title'])
    if not chanid:
      chanid = self.db.GetSetting('chanid')
    else:
      chanid = chanid['chanid']
    filename = '%s/%s' %(datadir, self.persistant['filename'])
    if FLAGS.verbose:
      out.write('Importing %s\n' % filename)
    try:
      if os.path.isdir(self.persistant['tmp_name']):
        utility.recursive_file_permissions(filename,-1,-1,0o777)
      # go through all subdirectories to find RAR files
        for root, dirnames, ents in os.walk(self.persistant['tmp_name']):
          for counter in fnmatch.filter(ents, '*'):
	    # only pick those files that are single rars or the first part of a rar
            if (counter.endswith('.rar') or counter.endswith('zip')) and not (re.search('part[1-9][0-9]', counter) or re.search('part0[2-9]', counter)):
              if FLAGS.verbose:
		out.write('Extracting RARs, please wait... ')
              UnRAR2.RarFile(os.path.join(root, counter)).extract(path=self.persistant['tmp_name'])
              if FLAGS.verbose:
		out.write('Extracted %s\n' % counter)
        handled = False

        # go through all sundirectories again, to find video files
        if FLAGS.verbose:
	  out.write('Searching for videofiles in %s\n' % self.persistant['tmp_name'])
        for root, dirnames, ents in os.walk(self.persistant['tmp_name']):
          for counter in fnmatch.filter(ents, '*'):
            for extn in ['.avi', '.wmv', '.mp4', '.mkv']:
              if counter.endswith(extn) and not fnmatch.fnmatch(counter, '*ample*'):
                filename = '%s/%s' %(root, counter)
                if FLAGS.verbose:
		  out.write(' Picked %s from the directory\n' % counter)
                #self.persistant['filename'] = filename
                handled = True
   
        if not handled:
          raise DirectoryException(self.db,
                                  'Don\'t know how to handle this directory')
    except:
      pass

    videodir = utility.GetVideoDir()
    vid = video_inspector.VideoInspector(filename)    

    # Try to use the publish time of the RSS entry as the start time...
    try:
      start = datetime.datetime.strptime(str(self.persistant['date']), '%Y-%m-%d %H:%M:%S')
      #start = datetime.datetime.strptime(self.persistant['unparsed_date'], '%a, %d %b %Y %H:%M:%S')
      if FLAGS.verbose:
	out.write('  Using database time as timestamp for recording\n')
    except:
      start = datetime.datetime.now()
      if FLAGS.verbose:
	out.write('  Using now as timestamp for recording - %s\n' % start)
      
   
    # Ensure uniqueness for the start time
    interval = datetime.timedelta(seconds = 1)
    while self.db.GetOneRow('select basename from recorded where starttime = %s and chanid = %s and basename != "%s"' \
                                %(self.db.FormatSqlValue('', start),
                                  chanid, filename)):
      start += interval
      
    # Determine the duration of the video
    duration = datetime.timedelta(seconds = 60)
  
    try:
      duration = datetime.timedelta(seconds = vid.duration())
    except:
      #Could not determine the real length of the video.
      #Instead we will just pretend its only one minute long.
      pass

    finish = start + duration
    realseason = 0
    realepisode = 0
    inetref = ''
    # get show and episode details from TV-Rage, if possible

    
    #try if we can get TVRage or TTVDB information back
    try:
      se = series.ExtractSeasonEpisode(self.persistant['subtitle'])
      tvrage = series.TVRageSeasonEpisode(self.persistant['title'], se[0], se[1])
      ttvdb = series.TTVDBSeasonEpisode(self.persistant['title'], se[0], se[1])
      # if ttvdb did not return correct date take tvrage (mythtv likes ttvdb)
      if ttvdb:
        titledescription = ttvdb
      else:
        titledescription = tvrage
      self.persistant['subtitle'] = titledescription[0]
      self.persistant['description'] = titledescription[1]
      realseason = se[0]
      realepisode = se[1]
      inetref = titledescription[4]
      if FLAGS.verbose:
	out.write("Found on TVRage or TTVDB: S%sE%s inetref:%s\n" % (realseason, realepisode, inetref))
    except:
      pass
    # do the same to check if we can find the date in the subtitle
    try:
      se = series.ExtractDate(self.persistant['subtitle'])
      tvrage = series.TVRageDate(self.persistant['title'], se[0], se[1], se[2])
      ttvdb = series.TTVDBDate(self.persistant['title'], se[0], se[1], se[2])
      if ttvdb:
        titledescription = ttvdb
      else:
        titledescription = tvrage
      self.persistant['subtitle'] = titledescription[0]
      self.persistant['description'] = titledescription[1]
      realseason = titledescription[2]
      realepisode = titledescription[3]
      # update start and finish if we have the correct date from TVRage
      start = start.replace (year=se[0], month=se[1], day=se[2])
      finish = finish.replace (year=se[0], month=se[1], day=se[2])
      inetref = titledescription[4]
      if FLAGS.verbose:
	out.write("Found on TVRage or TTVDB: S%sE%s inetref:%s\n" % (realseason, realepisode, inetref))
    except:
      pass

    # Determine the audioproperties of the video
    audioprop = vid.audio_channels_string().upper()
    if audioprop == '5.1':
      audioprop = 'SURROUND'

    # Determine the subtitles of the video
    subtitletypes = ''
    if vid.subtitle_stream():
      subtitletypes = 'NORMAL'
    
    videoprop = ''
    videoprop = getAspectRatio(vid.height(), vid.width())

    # Archive the original version of the video
    archiverow = self.db.GetOneRow('select * from mythnettv_archive '
                                  'where title="%s"'
                                  % self.persistant['title'])
    if archiverow:
      archive_location = ('%s/%s_%s'
                          %(archiverow['path'],
                            SafeForFilename(self.persistant['title']),
                            SafeForFilename(self.persistant['subtitle'])))
      out.write('Possible archive location: %s\n' % archive_location)

      if self.persistant['url'].startswith(archiverow['path']):
        out.write('File was imported from the archive location, '
                  'not archiving\n')
      elif not os.path.exists(archive_location):
        out.write('Archiving the original\n')
        shutil.copyfile(filename, archive_location)
      else:
        out.write('Archive destination already exists\n')

    transcoded_filename = filename.split('/')[-1]

    out.write('Importing video %s...\n' % self.persistant['guid'])
    epoch = time.mktime(datetime.datetime.now().timetuple())
    dest_file = '%d_%s' %(epoch, transcoded_filename.replace(' ', '_'))
    
    # moving is better than copying as it uses less space and 
    # once the file is gone, it can not be imported again
    try:
      shutil.move('%s' % filename,
                  '%s/%s' %(videodir, dest_file))
    except:
      out.write('Problem: moving %s did not work, please check file permissions.\n Will copy instead.' % filename)
      shutil.copy('%s' % filename,
                  '%s/%s' %(videodir, dest_file))
    # clean up after us...
    try:
      if self.persistant['mime_type'] == 'application/x-bittorrent':
        if FLAGS.verbose:
	  out.write('deleting temporary directory %s...\n' % self.persistant['tmp_name'])
        try:
          shutil.rmtree(self.persistant['tmp_name'])
        except:
          out.write('Error: deleting temporary directory %s. Delete manually.\n' % self.persistant['tmp_name'])
    except:
      pass

    # Ensure sensible permissions on the recording that MythTV stores
    os.chmod('%s/%s' %(videodir, dest_file),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP |
            stat.S_IROTH | stat.S_IWOTH)

    filestats = os.stat('%s/%s' %(videodir, dest_file))
    self.persistant['size'] = filestats [stat.ST_SIZE]
    
    if not self.persistant['description']:
      self.persistant['description'] = ''
      if FLAGS.verbose:
	out.write('Empty description field\n')
    if not self.persistant['subtitle']:
      if FLAGS.verbose:
	out.write('Empty subtitle field\n')
      self.persistant['subtitle'] = ''
      
    # add the recording to the database using the MythTV python bindings
    tmp_recorded={} # we need a place to store
    tmp_recorded[u'chanid'] = chanid
    tmp_recorded[u'starttime'] = start
    tmp_recorded[u'endtime'] = finish
    tmp_recorded[u'title'] = self.persistant['title']
    tmp_recorded[u'subtitle'] = self.persistant['subtitle']
    tmp_recorded[u'season'] = realseason
    tmp_recorded[u'episode'] = realepisode
    if self.persistant['description'] == ' ':
      tmp_recorded[u'description'] = ''
    else:
      tmp_recorded[u'description'] = self.persistant['description']
    tmp_recorded[u'progstart'] = start
    tmp_recorded[u'progend'] = finish
    tmp_recorded[u'basename'] = dest_file
    tmp_recorded[u'filesize'] = self.persistant['size']
    tmp_recorded[u'lastmodified'] = datetime.datetime.now()
    tmp_recorded[u'hostname'] = socket.gethostname()

    storeAspect(videoaspect)

    # if the height and/or width of the recording is known, store it in the markuptable
    if videoheight:
      if FLAGS.verbose:
	out.write('Storing height: %s\n' % videoheight)
      self.db.ExecuteSql('insert into recordedmarkup (chanid, starttime, mark, type, data)'
                         'values (%s, %s, 12, 31, %s)'
                         %(chanid, self.db.FormatSqlValue('', start), videoheight))
    if videowidth:
      if FLAGS.verbose:
	out.write('Storing width: %s\n' % videowidth)
      self.db.ExecuteSql('insert into recordedmarkup (chanid, starttime, mark, type, data)'
                         'values (%s, %s, 12, 30, %s)'
                         %(chanid, self.db.FormatSqlValue('', start), videowidth))

    # If there is a category set for this subscription, then set that as well
    row = self.db.GetOneRow('select * from mythnettv_category where '
                            'title="%s";'
                            % self.persistant['title'])
    if row:
      if FLAGS.verbose:
	out.write('Setting category to %s\n' % row['category'])
      tmp_recorded[u'category'] = row['category']

    # Ditto the group
    row = self.db.GetOneRow('select * from mythnettv_group where '
                            'title="%s";'
                            % self.persistant['title'])
    if row:
      if FLAGS.verbose:
	out.write('Setting recording group to %s\n' % row['recgroup'])
      tmp_recorded[u'recgroup'] = row['recgroup']
    
    # Ditto the inetref
    row = self.db.GetOneRow('select * from mythnettv_subscriptions where '
                            'title="%s";'
                            % self.persistant['title']) 
                            
    # if we got an inetref from the TTVDB use it
    if inetref:
      if FLAGS.verbose:
	out.write('Setting the inetref to %s\n' % inetref)
      tmp_recorded[u'inetref'] = inetref

    # else use the one provided by the subscription
    elif row:
      if FLAGS.verbose:
	out.write('Setting the inetref to %s\n' % row['inetref'])
      tmp_recorded[u'inetref'] = row['inetref']
    
    # stet the playgroup if available
    if row:
      if FLAGS.verbose:
	out.write('Setting the playgroup to %s\n' % row['playgroup'])
      tmp_recorded[u'playgroup'] = row['playgroup']
      
    tmp_recorded[u'audioprop'] = audioprop
    tmp_recorded[u'subtitletypes'] = subtitletypes
    tmp_recorded[u'videoprop'] = videoprop
    #FIXME: we could get this from TTVDB
    tmp_recorded[u'originalairdate'] = '0000-00-00'

    Recorded().create(tmp_recorded)
    # add recordedprogram information using the MythTV python bindings 
    RecordedProgram().create(tmp_recorded)

    # use python bindings to generate a preview PNG
    try:
      out.write('Generate preview, just so it does not need to be done later\n')
      task = System(path='mythpreviewgen')
      task.command('--chanid "%s"' % chanid, '--starttime "%s"' % start)
    except:
      out.write('Could not generate preview image. Will be done by the frontend later.\n')
      pass
    
    self.SetImported()
    out.write('Finished\n\n')

    # And now mark the video as imported
    return

  def SetImported(self):
    """SetImported -- flag this program as having been imported"""

    self.persistant['download_finished'] = 1
    self.persistant['imported'] = 1
    self.Store()

  def SetNew(self):
    """SetNew -- make a program look like its new"""

    for field in ['download_started', 'download_finished', 'imported',
                  'imported', 'transfered', 'size', 'filename', 
                  'inactive', 'attempts', 'failed']:
      self.persistant[field] = None
    self.Store()

  def SetAttempts(self, count):
    """SetAttempts -- set the attempt count"""

    self.persistant['attempts'] = count
    self.Store()

  def Unfail(self):
    """Unfail -- unmark a program as failed"""

    self.persistant['download_finished'] = None
    self.persistant['failed'] = None
    self.persistant['attempts'] = 0
    self.persistant['last_attempt'] = None
    self.Store()
    
  def TVRage(self, showtitle, out=sys.stdout):
    """TVRage -- Get episode information from TVRage"""
    
    try:
      show = tvrage.api.Show(showtitle)
    except:
      return
    #out.write('Show Name:    ' + show.name + '\n')
    #out.write('Seasons:      ' + str(show.seasons) + '\n')
    #out.write('Last episode: ' + str(show.latest_episode) + '\n')
    #showtitle = "The Daily Show with Jon Stewart"
    
    season = 0
    #loop for all recordings in the database that have the same show name
    for row in self.db.GetRows('SELECT title, subtitle, basename, season, episode FROM recorded WHERE title LIKE "%s" OR subtitle LIKE "%s";' % (showtitle, showtitle)):
      seasonepisode = row['subtitle']
      matchme = ["[Ss]eason (\d{1})", "[Ss]eason(\d{1})", "[Ss]eries (\d{1})", "[Ss]eries(\d{1})"]
      for search in matchme:
        try:
          season = int(re.search(search, seasonepisode).group(1)) - 1
          out.write(" Found an aditional Season or Series within the subtitle: will add %s\n" % season)
        except:
          pass
      out.write(" Searching for show at TVRage... \n")
      try:
        se = series.ExtractSeasonEpisode(seasonepisode)
        titledescription = series.TVRageSeasonEpisode(showtitle, se[0] + season, se[1])
        out.write(' Found %s %s %s %s\n' % (showtitle, titledescription[0], se[0] + season, se[1]))
        self.db.ExecuteSql ('update recorded set description="%s", title="%s", subtitle="%s", season=%s, episode=%s WHERE basename = "%s";' % (titledescription[1], showtitle, titledescription[0], se[0] + season, se[1], row['basename']))
      except:
	if FLAGS.verbose:
	  out.write('  did not find by season/episode number...\n')
        pass
      try:
        se = series.ExtractDate(seasonepisode)
        titledescription = series.TVRageDate(showtitle, se[0], se[1], se[2])
        out.write(' Found %s %s %s %s\n' % (showtitle, titledescription[0], titledescription[2], titledescription[3]))
        self.db.ExecuteSql ('update recorded set description="%s", title="%s", subtitle="%s", season=%s, episode=%s WHERE basename = "%s";' % (self.db.FormatSqlValue('', titledescription[1]), showtitle, titledescription[0], titledescription[2], titledescription[3], row['basename']))
      except:
        if FLAGS.verbose:
	  out.write('  did not find by date...\n')
        pass

  def TTVDB(self, showtitle, out=sys.stdout):
    """TTVDB -- Get episode information from The TV database"""
   
    season = 0
    #loop for all recordings in the database that have the same show name
    for row in self.db.GetRows('SELECT title, subtitle, basename, season, episode, starttime, endtime FROM recorded WHERE title LIKE "%s" OR subtitle LIKE "%s";' % (showtitle, showtitle)):
      seasonepisode = row['subtitle']
      matchme = ["[Ss]eason (\d{1})", "[Ss]eason(\d{1})", "[Ss]eries (\d{1})", "[Ss]eries(\d{1})"]
      for search in matchme:
        try:
          season = int(re.search(search, seasonepisode).group(1)) - 1
          out.write("  Found an aditional Season or Series within the subtitle: will add %s\n" % season)
        except:
          pass
      try:
        if re.search("[Ss]eason One", seasonepisode) or re.search("[Ss]eries One", seasonepisode):
          season = 0
          out.write("  Found an aditional Season or Series within the subtitle: will add %s\n" % season)
      except:
        pass
      out.write(" Searching for show in the TV database... \n")
      found = False
      try:
        se = series.ExtractSeasonEpisode(seasonepisode)        
        titledescription = series.TTVDBSeasonEpisode(showtitle, se[0] + season, se[1])
        out.write(' Found: %s\t subtitle: %s\t Season:%s\t Episode:%s\t inetref: %s\n' % (showtitle, titledescription[0], se[0] + season, se[1], titledescription[2]))
        found = True
      except:
        if FLAGS.verbose:
	  out.write('  did not find by season/episode number...\n')
        pass
      if found == False:
        try:
          titledescription = series.TTVDBSubtitle(showtitle, seasonepisode)
          out.write(' Found: %s\t subtitle: %s\t Season:%s\t Episode:%s\t inetref: %s\n' 
                    % (showtitle, titledescription[0], titledescription[2], titledescription[3], titledescription[4]))
        except:
	  if FLAGS.verbose:
	    out.write('  did not find by subtitle...\n')
          pass

      if found == False:
	try:
          se = series.ExtractDate(seasonepisode)
          titledescription = series.TTVDBDate(showtitle, se[0], se[1], se[2])
          print (titledescription[4])
          # update start and finish if we have the correct date from TVRage
          out.write(' Found: %s\t subtitle: %s\t Season:%s\t Episode:%s\t inetref: %s\n' 
                    % (showtitle, titledescription[0], titledescription[2], titledescription[3], titledescription[4]))
          found = True
        except:
	  if FLAGS.verbose:
	    out.write('  did not find by date...\n')
          pass

	
      # only update those values we got non Null
      try:
        if titledescription[0]:
          self.db.ExecuteSql ('update recorded set subtitle="%s" WHERE basename = "%s";' 
                             % (titledescription[0], row['basename']))
        if titledescription[1]:
          self.db.ExecuteSql ('update recorded set description=%s WHERE basename = "%s";' 
                             % (self.db.FormatSqlValue('', titledescription[1]), row['basename']))
        else:
	  self.db.ExecuteSql ('update recorded set description=%s WHERE basename = "%s";' 
                             % (self.db.FormatSqlValue('', ''), row['basename']))
        if titledescription[4]:
          self.db.ExecuteSql ('update recorded set inetref=%s WHERE basename = "%s";' 
                             % (titledescription[4], row['basename']))
        if titledescription[2]:
          self.db.ExecuteSql ('update recorded set season=%s WHERE basename = "%s";' 
                             % (titledescription[2], row['basename']))
        if titledescription[3]:
          self.db.ExecuteSql ('update recorded set episode=%s WHERE basename = "%s";' 
                             % (titledescription[3], row['basename']))                   
        if se[0]:
          # if date available in subtitle update start and end time accordingly
          start = datetime.datetime.strptime(str(row['starttime']), '%Y-%m-%d %H:%M:%S')
          start = start.replace(year=int(se[0]),month=int(se[1]),day=int(se[2])) 

          end = datetime.datetime.strptime(str(row['endtime']), '%Y-%m-%d %H:%M:%S')
          end = end.replace(int(se[0]),int(se[1]),int(se[2]))
          self.db.ExecuteSql ('update recorded set starttime="%s", endtime="%s", progstart="%s", progend="%s" WHERE basename = "%s";'
                             % (start, end, start, end, row['basename']))
      except:
	out.write('No updates made...\n')
        pass

  def titlefix(self, oldtitle, newtitle, out=sys.stdout):
    """titlefix -- fix the current title with a new one """
    # this replaces the old title with the new one, removes any references to the new title form the subtitle
    self.db.ExecuteSql('UPDATE recorded SET title = "%s", subtitle = replace(subtitle,"%s","") WHERE title LIKE "%s";' 
                      % (newtitle, newtitle, oldtitle))

  def sefix(self, title, out=sys.stdout):
    """sepfix -- fix the season and episode data by trying to guess it from subtitle """
    #loop for all recordings in the database that have the same show name
    for row in self.db.GetRows('SELECT title, subtitle, basename FROM recorded WHERE title LIKE "%s";' % (title)):
      try:
        se = series.ExtractSeasonEpisode(row['subtitle'])
        self.db.ExecuteSql ('update recorded set season=%s, episode=%s WHERE basename = "%s";' % (se[0], se[1], row['basename']))
      except:
        out.write('Season and episode information could not be found in %s \n' % row['subtitle'])
        pass

  def overwrite(self, title, out=sys.stdout):
    for row in self.db.GetRows('SELECT title, subtitle, basename FROM recorded WHERE title LIKE "%s";' % (title)):
      row2 = self.db.GetRow('SELECT title, subtitle FROM mythnettv_programs WHERE basename LIKE "%s";' % (row['basename']))
      out.write('Subtitle: %s' % row2['subtitle'])
