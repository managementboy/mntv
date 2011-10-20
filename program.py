#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008, 2009
# Copyright (C) Elkin Fricke (elkin@elkin.de) 2011
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
import series
import tvrage.api

import UnRAR2

# Note that plugins aren't actually plugins at the moment, and that flags
# parsing will be a problem for plugins when we get there (I think).
from plugins import bittorrent

# import MythTV bindings... we could test if you have them, but if you don't, why do you need this script?
from MythTV import OldRecorded, Recorded, RecordedProgram, Record, Channel, \
                   MythDB, Video, MythVideo, MythBE, MythError, MythLog

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
#    os.chmod(datadir,0o777)
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
      out.write('Searching for videofiles in %s\n' % filename)
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
    inetref = ''
    # get show and episode details from TV-Rage, if possible

    #try if we can get TVRage information back
    out.write("Try to get episode data from TVRage or TTVDB...")
    try:
      se = series.ExtractSeasonEpisode(self.persistant['subtitle'])
      tvrage = series.TVRageSeasonEpisode(self.persistant['title'], se[0], se[1])
      ttvdb = series.TTVDBSeasonEpisode(self.persistant['title'], se[0], se[1])
      if ttvdb:
        titledescription = ttvdb
      else:
        titledescription = tvrage
      self.persistant['subtitle'] = titledescription[0]
      self.persistant['description'] = titledescription[1]
      realseason = se[0]
      realepisode = se[1]
      inetref = titledescription[2]      
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
      start = start.replace (se[0], se[1], se[2])
      finish = finish.replace (se[0], se[1], se[2])
      inetref = titledescription[4]
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
    
    if self.persistant['description'] == None:
      self.persistant['description'] = ''
    if self.persistant['subtitle'] == None:
      self.persistant['subtitle'] = ''
      
    # add the recording to the database using the MythTV python bindings
    tmp_recorded={}
    tmp_recorded[u'chanid'] = chanid
    tmp_recorded[u'starttime'] = start
    tmp_recorded[u'endtime'] = finish
    tmp_recorded[u'title'] = self.persistant['title']
    tmp_recorded[u'subtitle'] = self.persistant['subtitle']
    tmp_recorded[u'season'] = realseason
    tmp_recorded[u'episode'] = realepisode
    tmp_recorded[u'description'] = self.persistant['description']
    tmp_recorded[u'progstart'] = start
    tmp_recorded[u'progend'] = finish
    tmp_recorded[u'basename'] = dest_file
    tmp_recorded[u'filesize'] = self.persistant['size']
    Recorded().create(tmp_recorded)
    #

    # The quotes are missing around the description, because they are added
    # by the FormatSqlValue() call
    #self.db.ExecuteSql('insert into recorded (chanid, starttime, endtime, title, '
    #                  'subtitle, description, season, episode, hostname, basename, '
    #                  'progstart, progend, filesize, inetref, autoexpire) values '
    #                  '(%s, %s, %s, %s, '
    #                  '%s, %s, %s, %s, "%s", "%s", %s, %s, %s, %s, 1)'
    #                  %(chanid,
    #                    self.db.FormatSqlValue('', start),
    #                    self.db.FormatSqlValue('', finish),
    #                    self.db.FormatSqlValue('', self.persistant['title']),
    #                    self.db.FormatSqlValue('',
    #                            self.persistant['subtitle']),
    #                    self.db.FormatSqlValue('',
    #                            self.persistant['description']),
    #                    self.db.FormatSqlValue('',
    #                            realseason),
    #                    self.db.FormatSqlValue('', 
    #                            realepisode),
    #                    socket.gethostname(),
    #                    dest_file,
    #                    self.db.FormatSqlValue('', start),
    #                    self.db.FormatSqlValue('', finish),
    #                    self.db.FormatSqlValue('', self.persistant['size']),
    #                    self.db.FormatSqlValue('', '')))

    # insert the most basic date into the recordedprogram table
    # this is necessary as audio properties etc are found here
    self.db.ExecuteSql('insert into recordedprogram (chanid, starttime, endtime, '
                      'title, subtitle, description,'
                      'audioprop, subtitletypes, videoprop) values '
                      '(%s, %s, %s, '
                      '%s, %s, %s, '
                      '%s, %s, %s)'
                      %(chanid,
                        self.db.FormatSqlValue('', start),
                        self.db.FormatSqlValue('', finish),
                        self.db.FormatSqlValue('', self.persistant['title']),
                        self.db.FormatSqlValue('',
                                self.persistant['subtitle']),
                        self.db.FormatSqlValue('',
                                self.persistant['description']),
                        self.db.FormatSqlValue('', audioprop),
                        self.db.FormatSqlValue('', subtitletypes),
                        self.db.FormatSqlValue('', videoprop)))

    # add aspect to markup table
    if vid.values['ID_VIDEO_ASPECT']:
      #aspecttype = 0
      out.write('Storing aspect ratio: %s\n' % vid.values['ID_VIDEO_ASPECT'])
      if float(vid.values['ID_VIDEO_ASPECT']) < 1.4:
        aspecttype = 11
      elif float(vid.values['ID_VIDEO_ASPECT']) < 1.8:
        aspecttype = 12
      elif float(vid.values['ID_VIDEO_ASPECT']) < 2.3:
        aspecttype = 13 
        
      self.db.ExecuteSql('insert into recordedmarkup (chanid, starttime, mark, type, data)'
                         'values (%s, %s, 1, %s, NULL)'
                         %(chanid, self.db.FormatSqlValue('', start), aspecttype))
      
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
    # if we got an inetref from the TTVDB use it
    if inetref:
      out.write('Setting the inetref to %s\n' % inetref)
      self.db.ExecuteSql('update recorded set inetref="%s" where '
                        'basename="%s";'
                        %(inetref, dest_file))
    # else use the one provided by the subscription
    elif row:
      out.write('Setting the inetref to %s\n' % row['inetref'])
      self.db.ExecuteSql('update recorded set inetref="%s" where '
                        'basename="%s";'
                        %(row['inetref'], dest_file))

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
    out.write('Show Name:    ' + show.name + '\n')
    out.write('Seasons:      ' + str(show.seasons) + '\n')
    out.write('Last episode: ' + str(show.latest_episode) + '\n')
    #showtitle = "The Daily Show with Jon Stewart"
    
    season = 0
    #loop for all recordings in the database that have the same show name
    for row in self.db.GetRows('SELECT title, subtitle, basename, season, episode FROM recorded WHERE title LIKE "%s" OR subtitle LIKE "%s";' % (showtitle, showtitle)):
      seasonepisode = row['subtitle']
      matchme = ["[Ss]eason (\d{1})", "[Ss]eason(\d{1})", "[Ss]eries (\d{1})", "[Ss]eries(\d{1})"]
      for search in matchme:
        try:
          season = int(re.search(search, seasonepisode).group(1)) - 1
          out.write("Found an aditional Season or Series within the subtitle: will add %s\n" % season)
        except:
          pass
      out.write("Getting show from TVRage... ")
      try:
        se = series.ExtractSeasonEpisode(seasonepisode)
        titledescription = series.TVRageSeasonEpisode(showtitle, se[0] + season, se[1])
        out.write('Found %s %s %s %s\n' % (showtitle, titledescription[0], se[0] + season, se[1]))
        self.db.ExecuteSql ('update recorded set description=%s, title="%s", subtitle="%s", season=%s, episode=%s WHERE basename = "%s";' % (titledescription[1], showtitle, titledescription[0], se[0] + season, se[1], row['basename']))
      except:
        pass
      try:
        se = series.ExtractDate(seasonepisode)
        titledescription = series.TVRageDate(showtitle, se[0], se[1], se[2])
        out.write('Found %s %s %s %s\n' % (showtitle, titledescription[0], titledescription[2], titledescription[3]))
        self.db.ExecuteSql ('update recorded set description=%s, title="%s", subtitle="%s", season=%s, episode=%s WHERE basename = "%s";' % (self.db.FormatSqlValue('', titledescription[1]), showtitle, titledescription[0], titledescription[2], titledescription[3], row['basename']))
      except:
        pass

  def TTVDB(self, showtitle, out=sys.stdout):
    """TTVDB -- Get episode information from The TV database"""
   
    season = 0
    #loop for all recordings in the database that have the same show name
    for row in self.db.GetRows('SELECT title, subtitle, basename, season, episode FROM recorded WHERE title LIKE "%s" OR subtitle LIKE "%s";' % (showtitle, showtitle)):
      seasonepisode = row['subtitle']
      matchme = ["[Ss]eason (\d{1})", "[Ss]eason(\d{1})", "[Ss]eries (\d{1})", "[Ss]eries(\d{1})"]
      for search in matchme:
        try:
          season = int(re.search(search, seasonepisode).group(1)) - 1
          out.write("Found an aditional Season or Series within the subtitle: will add %s\n" % season)
        except:
          pass
      try:
        if re.search("[Ss]eason One", seasonepisode):
          season = 0
          out.write("Found an aditional Season or Series within the subtitle: will add %s\n" % season)
      except:
        pass
      out.write("Getting show from The TV database... \n")
      try:
        se = series.ExtractSeasonEpisode(seasonepisode)        
        titledescription = series.TTVDBSeasonEpisode(showtitle, se[0] + season, se[1])
        out.write('Found %s %s %s %s inetref: %s\n' % (showtitle, titledescription[0], se[0] + season, se[1], titledescription[2]))
        # only update those values we got non Null
        if titledescription[0]:
          self.db.ExecuteSql ('update recorded set subtitle="%s" WHERE basename = "%s";' % (titledescription[0], row['basename']))
        if titledescription[1]:
          self.db.ExecuteSql ('update recorded set description="%s" WHERE basename = "%s";' % (titledescription[1], row['basename']))
        if titledescription[2]:
          self.db.ExecuteSql ('update recorded set inetref=%s WHERE basename = "%s";' % (titledescription[2], row['basename']))
        if se[0]:
          self.db.ExecuteSql ('update recorded set season=%s WHERE basename = "%s";' % (se[0] + season, row['basename']))
        if se[1]:
          self.db.ExecuteSql ('update recorded set episode=%s WHERE basename = "%s";' % (se[1], row['basename']))
      except:
        out.write('did not find...\n')
        pass
      try:
        se = series.ExtractDate(seasonepisode)
        #titledescription = series.TVRageDate(showtitle, se[0], se[1], se[2])
        #out.write('Found %s %s %s %s\n' % (showtitle, titledescription[0], titledescription[2], titledescription[3]))
        #self.db.ExecuteSql ('update recorded set description="%s", title="%s", subtitle="%s", season=%s, episode=%s WHERE basename = "%s";' % (self.db.FormatSqlValue('', titledescription[1]), showtitle, titledescription[0], titledescription[2], titledescription[3], row['basename']))
      except:
        pass

  def titlefix(self, oldtitle, newtitle, out=sys.stdout):
    """titlefix -- fix the current title with a new one """
    # this replaces the old title with the new one, removes any references to the new title form the subtitle
    self.db.ExecuteSql ('UPDATE recorded SET title = "%s", subtitle = replace(subtitle,"%s","") WHERE title LIKE "%s";' % (newtitle, newtitle, oldtitle))

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
