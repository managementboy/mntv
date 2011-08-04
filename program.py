#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008, 2009
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

import database
import gflags
import mythnettvcore
import proxyhandler
import utility
import video

import tvrage.api

import UnRAR2

# Note that plugins aren't actually plugins at the moment, and that flags
# parsing will be a problem for plugins when we get there (I think).
from plugins import bittorrent

from stat import *


FLAGS = gflags.FLAGS
gflags.DEFINE_boolean('commflag', True,
                      'Run the mythcommflag command on new videos')
gflags.DEFINE_boolean('force', False,
                      'Force downloads to run, even if they failed recently')


# Exceptions returned by this module
class StorageException(utility.LoggingException):
  """ Errors with storage of programs """

class DownloadException(utility.LoggingException):
  """ Errors in the download process """

class DirectoryException(utility.LoggingException):
  """ Errors in importing a directory """


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
      dummy = 'blah'

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

    # TODO(mikal): Should I generate a more unique GUID?
    self.persistant['guid'] = self.persistant['url']
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

    filename = '%s/%s' %(datadir, self.persistant['filename'])
    out.write('Destination will be %s\n' % filename)
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

  def Download(self, datadir, force_proxy=None, force_budget=-1,
              out=sys.stdout):
    """Download -- download the show"""
    os.chmod(datadir,0o777)
    one_hour = datetime.timedelta(hours=1)
    one_hour_ago = datetime.datetime.now() - one_hour

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

    if self.persistant['url'].endswith('torrent') \
      or self.persistant.get('mime_type', '').endswith('torrent'):
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
      
    out.write('Done\n')
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
    chanid = self.db.GetSetting('chanid')
    filename = '%s/%s' %(datadir, self.persistant['filename'])
    out.write('Importing %s\n' % filename)
    utility.recursive_file_permissions(filename,-1,-1,0o777)

    if os.path.isdir(filename):
      #os.chmod(filename,0o777)
      # go through all subdirectories to find RAR files
      for root, dirnames, ents in os.walk(filename):
        for counter in fnmatch.filter(ents, '*'):
          if counter.endswith('.rar'):
             out.write('Extracting RARs, please wait... ')
             UnRAR2.RarFile(os.path.join(root, counter)).extract(path=filename)
             out.write('Extracted %s\n' % counter)
      
      handled = False

      # go throuhg all sundirectories again, to find video files
      out.write('Searching for videofiles in %s' % filename)
      for root, dirnames, ents in os.walk(filename):
        for counter in fnmatch.filter(ents, '*'):
          for extn in ['.avi', '.wmv', '.mp4', '.mkv']:
            if counter.endswith(extn):
              if not fnmatch.fnmatch(counter, '*ample*'):
                #filename = os.path.join(root, counter)
                filename = '%s/%s' %(root, counter)
                out.write('Picked %s from the directory\n' % filename)
                handled = True

      if not handled:
        raise DirectoryException(self.db,
                                'Don\'t know how to handle this directory')

    videodir = utility.GetVideoDir(self.db)
    vid = video.MythNetTvVideo(self.db, filename)

    # Try to use the publish time of the RSS entry as the start time...
    # The tuple will be in the format: 2003, 8, 6, 20, 43, 20
    try:
      tuple = eval(self.persistant['parsed_date'])
      start = datetime.datetime(tuple[0], tuple[1], tuple[2], tuple[3],
                                tuple[4], tuple[5])
    except:
      start = datetime.datetime.now()

    # Ensure uniqueness for the start time
    interval = datetime.timedelta(seconds = 1)
    while not self.db.GetOneRow('select basename from recorded where '
                                'starttime = %s and chanid = %s and ' 
                                'basename != "%s"' \
                                %(self.db.FormatSqlValue('', start),
                                  chanid, filename)) == None:
      start += interval
      
    # Determine the duration of the video
    duration = datetime.timedelta(seconds = 60)
  
    try:
      duration = datetime.timedelta(seconds = vid.Length())
    except video.LengthException, e:
      out.write('Could not determine the real length of the video.\n'
                'Instead we will just pretend its only one minute long.\n\n'
                '%s\n'
                % e)

    finish = start + duration
    realseason = 0
    realepisode = 0
    # get show and episode details from TV-Rage, if possible

    if self.persistant['title'] != 'Internet':
      try:
        show = tvrage.api.Show(self.persistant['title'])
      except:
        out.write('Show was not found on TVRage\n')
        pass

      # first try assuming a System of S##E##
      try:
        showseason = re.sub('[E]{1,2}.*$', '', self.persistant['subtitle'])
        showseason = re.sub('^.*[S]', '', showseason)
        showepisode = re.sub('^.*[E]', '', self.persistant['subtitle'])
        showepisode = re.sub('[ ].*$', '', showepisode)
        episode = show.season(int(showseason)).episode(int(showepisode))
        #self.persistant['title'] = show.title
        self.persistant['subtitle'] = episode.title
        self.persistant['description'] = utility.massageDescription(episode.summary)
        realseason = episode.season
        realepisode = episode.number
        out.write('Found the show on TVRage\n')
      except:
        #out.write('No TVRage' + `episode` + ' ' + `showseason` + ' ' + `showepisode`)
        pass

      # now try assuming a System of ##x##
      try:
        showseason = re.sub('[x]{1,2}.*$', '', self.persistant['subtitle'])
        showseason = re.sub('^.*[ ]', '', showseason)
        showepisode = re.sub('^.*[x]', '', self.persistant['subtitle'])
        showepisode = re.sub('[ ].*$', '', showepisode)
        episode = show.season(int(showseason)).episode(int(showepisode))
        #self.persistant['title'] = show.title
        self.persistant['subtitle'] = episode.title
        self.persistant['description'] = utility.massageDescription(episode.summary)
        realseason = episode.season 
        realepisode = episode.number 
        out.write('Found the show on TVRage\n')
      except:
        #out.write('No TVRage' + `episode` + ' ' + `showseason` + ' ' + `showepisode`)
        pass

      try:
        # what if we have a date like 2009.01.01?
        myairdate = re.search("(\d{4}).(\d{2}).(\d{2})", self.persistant['subtitle']) 
        #Go through all seasons, as TVRage does not provide a search by airdate 
        seasoncount = int(show.seasons)
        a = 0
        while (seasoncount > a):
          # the range starts with 0 so add 1 
          try:
            season = show.season(a+1)
            episodecount = int(len(season.keys()))
          except:
            break
          a = a+1
          b = 1
          while (episodecount >= b):
            # some episodes returned by tvrage have errors... try to catch them
            try:
              episode = show.season(a).episode(b)
              if episode.airdate.strftime("%Y.%m.%d") == myairdate.group(0):
#                out.write('Episode match YYYY.MM.DD: (' + `a` + 'x' + `b` + ') ' + `episode.title` + '\n')
                self.persistant['subtitle'] = myairdate.group(1) + '.' + myairdate.group(2) + '.' +  myairdate.group(3) + ' ' + episode.title
                self.persistant['description'] = utility.massageDescription(episode.summary)
                realseason = a
                realepisode = b
            except:
 #             out.write('Episode match YYYY.MM.DD: (' + `a` + 'x' + `b` + ') ' + `episode.title` + '\n')
              pass
            b = b+1
      except:
        pass

      try:
        # what if we have a date like 2009 01 01?
        myairdate = re.search("(\d{4}) (\d{2}) (\d{2})", self.persistant['subtitle']) 
        #Go through all seasons, as TVRage does not provide a search by airdate 
        seasoncount = int(show.seasons)
        a = 0
        while (seasoncount > a):
          # the range starts with 0 so add 1 
          try:
            season = show.season(a+1)
            episodecount = int(len(season.keys()))
          except:
            break
          a = a+1
          b = 0
          while (episodecount > b):
            # some episodes returned by tvrage have errors... try to catch them
            try:
              episode = show.season(a).episode(b)
              if episode.airdate.strftime("%Y %m %d") == myairdate.group(0):
                out.write('Episode match YYYY MM DD: (' + `a` + 'x' + `b` + ') ' + `episode.title` + '\n')
                self.persistant['subtitle'] = myairdate.group(1) + '.' + myairdate.group(2) + '.' +  myairdate.group(3) + ' ' + episode.title
                self.persistant['description'] = utility.massageDescription(episode.summary)
                realseason = a
                realepisode = b 
            except:
              pass
            b = b+1
      except:
        pass

      try:
        # what if we have a date like 20090101?
        myairdate = re.search("(\d{4})(\d{2})(\d{2})", self.persistant['subtitle']) 
        #Go through all seasons, as TVRage does not provide a search by airdate 
        seasoncount = int(show.seasons)
        a = 0
        while (seasoncount > a):
          # the range starts with 0 so add 1 
          try:
            season = show.season(a+1)
            episodecount = int(len(season.keys()))
          except:
            break
          a = a+1
          b = 0
          while (episodecount > b):
            # some episodes returned by tvrage have errors... try to catch them
            try:
              episode = show.season(a).episode(b)
              if episode.airdate.strftime("%Y%m%d") == myairdate.group(0):
                out.write('Episode match YYYYMMDD  : (' + `a` + 'x' + `b` + ') ' + `episode.title` + '\n')
                self.persistant['subtitle'] = myairdate.group(1) + '.' + myairdate.group(2) + '.' +  myairdate.group(3) + ' ' + episode.title
                self.persistant['description'] = utility.massageDescription(episode.summary)
                realseason = a
                realepisode = b
            except:
              pass
            b = b+1
      except:
        pass
        
      try:
        # what if we have a date like 2009-01-01?
        myairdate = re.search("(\d{4})-(\d{2})-(\d{2})", self.persistant['subtitle']) 
        #Go through all seasons, as TVRage does not provide a search by airdate 
        seasoncount = int(show.seasons)
        a = 0
        while (seasoncount > a):
          # the range starts with 0 so add 1 
          try:
            season = show.season(a+1)
            episodecount = int(len(season.keys()))
          except:
            break
          a = a+1
          b = 0
          while (episodecount > b):
            # some episodes returned by tvrage have errors... try to catch them
            try:
              episode = show.season(a).episode(b)
              if episode.airdate.strftime("%Y-%m-%d") == myairdate.group(0):
                out.write('Episode match YYYYMMDD  : (' + `a` + 'x' + `b` + ') ' + `episode.title` + '\n')
                self.persistant['subtitle'] = myairdate.group(1) + '.' + myairdate.group(2) + '.' +  myairdate.group(3) + ' ' + episode.title
                self.persistant['description'] = utility.massageDescription(episode.summary)
                realseason = a+1
                realepisode = b
            except:
              pass
            b = b+1
      except:
        pass

    # Determine the audioproperties of the video
    audioprop = vid.Audioprop()

    # Determine the subtitles of the video
    subtitletypes = vid.Subtitletypes()

    # Determine the Videoproperties
    videoprop = vid.Videoprop()

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

    # Transcode file to a better format if needed. transcoded is the filename
    # without the data directory portion
    if vid.NeedsTranscode(out=out):
      transcoded_filename = vid.Transcode(datadir, out=out)
      transcoded = '%s/%s' %(datadir, transcoded_filename)
      os.remove(filename)
    else:
      transcoded = filename
      transcoded_filename = filename.split('/')[-1]

    out.write('Importing video %s...\n' % self.persistant['guid'])
    epoch = time.mktime(datetime.datetime.now().timetuple())
    dest_file = '%d_%s' %(epoch, transcoded_filename.replace(' ', '_'))
    
    #changed from move to copy use "find * -mtime +3 -delete" or something
    #similar to delete old downloads
    shutil.copy('%s' % transcoded,
                '%s/%s' %(videodir, dest_file))

    # Ensure sensible permissions on the recording that MythTV stores
    os.chmod('%s/%s' %(videodir, dest_file),
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP |
            stat.S_IROTH | stat.S_IWOTH)

    filestats = os.stat('%s/%s' %(videodir, dest_file))
    self.persistant['size'] = filestats [stat.ST_SIZE]
    # The quotes are missing around the description, because they are added
    # by the FormatSqlValue() call
    self.db.ExecuteSql('insert into recorded (chanid, starttime, endtime, title, '
                      'subtitle, description, season, episode, hostname, basename, '
                      'progstart, progend, filesize, inetref, autoexpire) values '
                      '(%s, %s, %s, %s, '
                      '%s, %s, %s, %s, "%s", "%s", %s, %s, %s, %s, 1)'
                      %(chanid,
                        self.db.FormatSqlValue('', start),
                        self.db.FormatSqlValue('', finish),
                        self.db.FormatSqlValue('', self.persistant['title']),
                        self.db.FormatSqlValue('',
                                self.persistant['subtitle']),
                        self.db.FormatSqlValue('',
                                self.persistant['description']),
                        self.db.FormatSqlValue('',
                                realseason),
                        self.db.FormatSqlValue('', 
                                realepisode),
                        socket.gethostname(),
                        dest_file,
                        self.db.FormatSqlValue('', start),
                        self.db.FormatSqlValue('', finish),
                        self.db.FormatSqlValue('', self.persistant['size']),
                        self.db.FormatSqlValue('', '')))

    self.db.ExecuteSql('insert into recordedprogram (chanid, starttime, endtime, '
                      'title, subtitle, description, category, category_type, '
                      'airdate, stars, previouslyshown, title_pronounce, stereo, '
                      'subtitled, hdtv, closecaptioned, partnumber, parttotal, '
                      'seriesid, originalairdate, colorcode, syndicatedepisodenumber, programid, '
                      'manualid, generic, listingsource, first, last, '
                      'audioprop, subtitletypes, videoprop) values '
                      '(%s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s)'
                      %(chanid,
                        self.db.FormatSqlValue('', start),
                        self.db.FormatSqlValue('', finish),
                        self.db.FormatSqlValue('', self.persistant['title']),
                        self.db.FormatSqlValue('',
                                self.persistant['subtitle']),
                        self.db.FormatSqlValue('',
                                self.persistant['description']),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', audioprop),
                        self.db.FormatSqlValue('', subtitletypes),
                        self.db.FormatSqlValue('', videoprop)))

    # If there is a category set for this subscription, then set that as well
    row = self.db.GetOneRow('select * from mythnettv_category where '
                            'title="%s";'
                            % self.persistant['title'])
    if row:
      out.write('Setting category to %s\n' % row['category'])
      self.db.ExecuteSql('update recorded set category="%s" where '
                        'basename="%s";'
                        %(row['category'], dest_file))

    # Ditto the group
    row = self.db.GetOneRow('select * from mythnettv_group where '
                            'title="%s";'
                            % self.persistant['title'])
    if row:
      out.write('Setting recording group to %s\n' % row['recgroup'])
      self.db.ExecuteSql('update recorded set recgroup="%s" where '
                        'basename="%s";'
                        %(row['recgroup'], dest_file))
    
    # Ditto the inetref
    row = self.db.GetOneRow('select * from mythnettv_subscriptions where '
                            'title="%s";'
                            % self.persistant['title'])

    if row:
      out.write('Setting the inetref to %s\n' % row['inetref'])
      self.db.ExecuteSql('update recorded set inetref="%s" where '
                        'basename="%s";'
                        %(row['inetref'], dest_file))


#    out.write('Rebuilding seek table\n')
#    commands.getoutput('mythtranscode --mpeg2 --buildindex --allkeys --infile "%s/%s"'
#                       % (videodir, dest_file))

#    out.write('Creating Thumbnail\n')
#    commands.getoutput('ffmpegthumbnailer -i "%s/%s" -o "%s/%s.png" -s 0'
#                      % (videodir, dest_file, videodir, dest_file))

#    if FLAGS.commflag:
#      out.write('Rebuilding seek table\n')
#      commands.getoutput('mythcommflag --rebuild --file "%s/%s"'
#                         % (videodir, dest_file))
#      
#     print 'Adding commercial flag job to backend queue'
#      commands.getoutput('mythcommflag --queue --file "%s/%s"'
#                         %(videodir, dest_file))

    self.SetImported()
    out.write('Done\n\n')

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
                  'filename', 'inactive', 'attempts', 'failed']:
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
    
  def Updatemeta(self, filename):
    """UpdateMeta-- Update metadata gained from video files"""
    
    # Construct a video object
    vid = None
    vid = video.MythNetTvVideo(self.db, filename)
    
    # Determine the audioproperties of the video
    audioprop = vid.Audioprop()

    # Determine the subtitles of the video
    subtitletypes = vid.Subtitletypes()

    # Determine the Videoproperties
    videoprop = vid.Videoprop()
    
#    self.db.ExecuteSql('update recordedprogram set audioprop="%s", subtitleprop="%s", videoprop="%s" where '
#                         'basename="%s";'
#                         audioprop, subtitletypes, videoprop, filename))
    # If there is a category set for this subscription, then set that as well
    row = self.db.GetOneRow('select * from recorded where '
                            'basename="%s";'
                            % filename)
    row2 = self.db.GetOneRow('select * from recordedprogram where chanid="%s" AND starttime="%s" AND endtime="%s";' % ( row['chanid'], row['progstart'],row['progend']))
#    print ('chanid="%s"' % row['chanid'])
#    self.db.ExecuteSql(
    if row2 is not None:
      self.db.ExecuteSql('update recordedprogram set audioprop="%s", subtitletypes="%s", videoprop="%s", filesize="%s" where chanid="%s" AND starttime="%s" AND endtime="%s";' % (audioprop, subtitletypes, videoprop, row['chanid'], row['progstart'], row['progend']))
    else:
      self.db.ExecuteSql('insert into recordedprogram (chanid, starttime, endtime, '
                      'title, subtitle, description, category, category_type, '
                      'airdate, stars, previouslyshown, title_pronounce, stereo, '
                      'subtitled, hdtv, closecaptioned, partnumber, parttotal, '
                      'seriesid, originalairdate, colorcode, syndicatedepisodenumber, programid, '
                      'manualid, generic, listingsource, first, last, '
                      'audioprop, subtitletypes, videoprop) values '
                      '(%s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s, %s, %s, '
                      '%s, %s, %s)'
                      %(row['chanid'],
                        self.db.FormatSqlValue('', row['progstart']),
                        self.db.FormatSqlValue('', row['progend']),
                        self.db.FormatSqlValue('', row['title']),
                        self.db.FormatSqlValue('', row['subtitle']),
                        self.db.FormatSqlValue('', row['description']),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', ''),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', 0),
                        self.db.FormatSqlValue('', audioprop),
                        self.db.FormatSqlValue('', subtitletypes),
                        self.db.FormatSqlValue('', videoprop)))

  def TVRage(self, showtitle, out=sys.stdout):
    """TVRage -- Get episode information from TVRage"""

    show = tvrage.api.Show(showtitle)
    out.write('Show Name:   ' + show.name + '\n')
    out.write('Seasons:     ' + str(show.seasons) + '\n')
    out.write('Last episode:' + str(show.latest_episode) + '\n')
    #showtitle = "The Daily Show with Jon Stewart"
    
    #loop for all recordings in the database that have the same show name
    for row in self.db.GetRows('SELECT title, subtitle, basename FROM recorded WHERE title LIKE "%s" OR subtitle LIKE "%s";' % (showtitle, showtitle)):
      seasonepisode = row['subtitle']
      episodetosubtitle = ''
      episodeseason = 0
      episodenumber = 0
      # sometimes the subtitle contains a Season but the season number is 1, fix this
      try:
        match = re.compile(r'[Ss]eason(\d+)')
        # I can later add this to the season by reducing by one
        series = int(match.search(seasonepisode).group(1)) - 1
      except:
        series = 0
        pass
      
      try:
        match = re.compile(r'[Ss]eason (\d+)')
        # I can later add this to the season by reducing by one
        series = int(match.search(seasonepisode).group(1)) - 1
      except:
        series = 0
      pass
      #same for title
      try:
        match = re.compile(r'[Ss]eason (\d+)')
        series = int(match.search(row['title']).group(1)) - 1
      except:
        series = 0
        pass

      # only write to database if set to true      
      writesql = 0
      
      try:  
        # try assuming a system of S##E##
        se = re.search("S(\d{2})E(\d{2})", seasonepisode)
        showseason = int(se.group(1))
        showepisode = int(se.group(2))
        showseason = int(showseason) + int(series)
        episode = show.season(int(showseason)).episode(int(showepisode))
        episodetosubtitle = `episode.title`
        episodeseason = `episode.season`
        episodenumber = `episode.number`
        out.write('Current S##E## subtitle: ' + `row['subtitle']` + '\n')
#        self.db.ExecuteSql ('update recorded set description=%s, title=%s, subtitle=%s, season=%s, episode=%s, originalairdate=%s WHERE basename = "%s";' % (self.db.FormatSqlValue('', episode.summary), self.db.FormatSqlValue('', show.name), self.db.FormatSqlValue('', episodetosubtitle), self.db.FormatSqlValue('', episode.season), self.db.FormatSqlValue('', episode.number), self.db.FormatSqlValue('', episode.airdate), row['basename']))
        out.write('Found the folowing show on TVRage: ' + `episode`  + '\n')
        writesql = 1
      except:
        pass

      try:  
        # try assuming a system of S##E##
        se = re.search("s(\d{2})e(\d{2})", seasonepisode)
        showseason = int(se.group(1))
        showepisode = int(se.group(2))
        showseason = int(showseason) + int(series)
        episode = show.season(int(showseason)).episode(int(showepisode))
        episodetosubtitle = `episode.title`
        episodeseason = `episode.season`
        episodenumber = `episode.number`
        out.write('Current S##E## subtitle: ' + `row['subtitle']` + '\n')
#        self.db.ExecuteSql ('update recorded set description=%s, title=%s, subtitle=%s, season=%s, episode=%s, originalairdate=%s WHERE basename = "%s";' % (self.db.FormatSqlValue('', episode.summary), self.db.FormatSqlValue('', show.name), self.db.FormatSqlValue('', episodetosubtitle), self.db.FormatSqlValue('', episode.season), self.db.FormatSqlValue('', episode.number), self.db.FormatSqlValue('', episode.airdate), row['basename']))
        out.write('Found the folowing show on TVRage: ' + `episode`  + '\n')
        writesql = 1
      except:
        pass


      try:
        # now try assuming a system of ##x##
        showseason = re.sub('[x]{1,2}.*$', '', row['subtitle'])
        showseason = re.sub('^.*[ ]', '', showseason)
        showepisode = re.sub('^.*[x]', '', row['subtitle'])
        showepisode = re.sub('[ ].*$', '', showepisode)
#        showseason = int(showseason) + int(series)
        episode = show.season(int(showseason)).episode(int(showepisode))
        episodetosubtitle = `episode.title`
        episodeseason = `episode.season`
        episodenumber = `episode.number`
        out.write('Current ##x## subtitle: ' + `row['subtitle']` + '\n')
#        out.write(`episode.summary` + '\n')
#        out.write(`episode.season` + 'x' + `episode.number` + '\n')
#        out.write(`episode.link` + '\n')
#        self.db.ExecuteSql ('update recorded set description=%s, title=%s, subtitle=%s, season=%s, episode=%s, originalairdate=%s WHERE basename = "%s";' % (self.db.FormatSqlValue('', episode.summary), self.db.FormatSqlValue('', show.name), self.db.FormatSqlValue('', episodetosubtitle), self.db.FormatSqlValue('', episode.season), self.db.FormatSqlValue('', episode.number), self.db.FormatSqlValue('', episode.airdate), row['basename']))
        out.write('Found the folowing show on TVRage: ' + `episode`  + '\n')
        writesql = 1
      except:
        #out.write('##x## not found')
        pass

      try:
        # now try assuming a system of 1 of X
        showepisode = re.sub('[ of ]{1,2}.*$', '', row['subtitle'])
        showepisode = re.sub('^.*[ ]', '', showepisode)
        showseason = 1
        showseason = int(showseason) + int(series)
        episode = show.season(int(showseason)).episode(int(showepisode))
        episodetosubtitle = `episode.title`
        out.write('Current 1 of X subtitle: ' + `row['subtitle']` + '\n')
        out.write('Found the folowing show on TVRage: ' + `episode`  + '\n')
#        writesql = True
      except:
        #out.write('# of # not found')
        pass
      
      try:
        # what if we have a date lik 2009.01.01?
        myairdate = re.search("(\d{4}).(\d{2}).(\d{2})", row['subtitle']) 
        #Go through all seasons, as TVRage does not provide a search by airdate 
        seasoncount = int(show.seasons)
        a = 0
        while (seasoncount > a):
          # the range starts with 0 so add 1 
          try:
            season = show.season(a+1)
            episodecount = int(len(season.keys()))
          except:
            break
          a = a+1
          b = 1
          while (episodecount >= b):
            # some episodes returned by tvrage have errors... try to catch them
            try:
              episode = show.season(a).episode(b)
              if episode.airdate.strftime("%Y.%m.%d") == myairdate.group(0):
                out.write('Episode match YYYY.MM.DD: (' + `a` + 'x' + `b` + ') ' + `episode.title` + '\n')
                episodetosubtitle = myairdate.group(1) + '.' + myairdate.group(2) + '.' +  myairdate.group(3) + ' ' + episode.title
                episodeseason = a
                episodenumber = b
                writesql = 1
            except:
              pass
            b = b+1
      except:
        pass

      try:
        # what if we have a date lik 2009 01 01?
        myairdate = re.search("(\d{4}) (\d{2}) (\d{2})", row['subtitle']) 
        #Go through all seasons, as TVRage does not provide a search by airdate 
        seasoncount = int(show.seasons)
        a = 0
        while (seasoncount > a):
          # the range starts with 0 so add 1 
          try:
            season = show.season(a+1)
            episodecount = int(len(season.keys()))
          except:
            break
          a = a+1
          b = 0
          while (episodecount > b):
            # some episodes returned by tvrage have errors... try to catch them
            try:
              episode = show.season(a).episode(b)
              if episode.airdate.strftime("%Y %m %d") == myairdate.group(0):
                out.write('Episode match YYYY MM DD: (' + `a` + 'x' + `b` + ') ' + `episode.title` + '\n')
                episodetosubtitle = myairdate.group(1) + '.' + myairdate.group(2) + '.' +  myairdate.group(3) + ' ' + episode.title
                episodeseason = a
                episodenumber = b
                writesql = 1
            except:
              pass
            b = b+1
      except:
        pass
        
      try:
        # what if we have a date like 20090101?
        myairdate = re.search("(\d{4})(\d{2})(\d{2})", row['subtitle']) 
        #Go through all seasons, as TVRage does not provide a search by airdate 
        seasoncount = int(show.seasons)
        a = 0
        while (seasoncount > a):
          # the range starts with 0 so add 1 
          try:
            season = show.season(a+1)
            episodecount = int(len(season.keys()))
          except:
            break
          a = a+1
          b = 0
          while (episodecount > b):
            # some episodes returned by tvrage have errors... try to catch them
            try:
              episode = show.season(a).episode(b)
              if episode.airdate.strftime("%Y%m%d") == myairdate.group(0):
                out.write('Episode match YYYYMMDD  : (' + `a` + 'x' + `b` + ') ' + `episode.title` + '\n')
                episodetosubtitle = myairdate.group(1) + '.' + myairdate.group(2) + '.' +  myairdate.group(3) + ' ' + episode.title
                episodeseason = a
                episodenumber = b
                writesql = 1
            except:
              pass
            b = b+1
      except:
        pass

      if writesql == 1:
        self.db.ExecuteSql ('update recorded set description=%s, title="%s", subtitle=%s, season=%s, episode=%s, originalairdate=%s WHERE basename = "%s";' % (self.db.FormatSqlValue('', utility.massageDescription(episode.summary)), show.name, self.db.FormatSqlValue('', episodetosubtitle), self.db.FormatSqlValue('', episodeseason), self.db.FormatSqlValue('', episodenumber), self.db.FormatSqlValue('', episode.airdate), row['basename']))
      else:
        out.write('Database could not be updated... \n')
        out.write(row['basename'] + ' ')
        out.write(row['subtitle'] + '\n')

  def titlefix(self, oldtitle, newtitle, out=sys.stdout):
    """titlefix -- fix the current title with a new one """
    # this replaces the old title with the new one, removes any references to the new title form the subtitle
    if oldtitle != 'Internet':
      self.db.ExecuteSql ('UPDATE recorded SET title = "%s", subtitle = replace(subtitle,"%s","") WHERE title LIKE "%s";' % (newtitle, newtitle, oldtitle))
    else:
      self.db.ExecuteSql ('UPDATE recorded SET title = "%s", subtitle = replace(subtitle,"%s","") WHERE title LIKE "%s" AND subtitle LIKE "%%%s%%";' % (newtitle, newtitle, oldtitle, newtitle))

  def sepfix(self, title, out=sys.stdout):
    """sepfix -- fix the season and episode data by trying to guess it from subtitle """
    #loop for all recordings in the database that have the same show name
    writesql = 0
    for row in self.db.GetRows('SELECT title, subtitle, basename FROM recorded WHERE title LIKE "%s";' % (title)):
      seasonepisode = row['subtitle']
      episodeseason = 0
      episodenumber = 0
      try:
        # try assuming a system of S##E##
        se = re.search("S(\d{2})E(\d{2})", seasonepisode)
        episodeseason = int(se.group(1))
        episodenumber = int(se.group(2))
        writesql = 1
      except:
        pass
      try:
        # now try assuming a system of ##x##
        se = re.search("(\d{1,2})x(\d{2})", seasonepisode)
        episodeseason = int(se.group(1))
        episodenumber = int(se.group(2))
        writesql = 1
      except:
        pass
      if writesql == 1:
        self.db.ExecuteSql ('update recorded set season=%s, episode=%s WHERE basename = "%s";' % (self.db.FormatSqlValue('', episodeseason), self.db.FormatSqlValue('', episodenumber), row['basename']))
      else:
        out.write('Database could not be updated... \n')
