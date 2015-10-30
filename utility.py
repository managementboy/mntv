#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2008
# Released under the terms of the GNU GPL v2

# Simple utility methods


import decimal
import os
import socket
import types


def DisplayFriendlySize(bytes):
  """DisplayFriendlySize -- turn a number of bytes into a nice string"""

  t = type(bytes)
  if t != types.LongType and t != types.IntType and t != decimal.Decimal:
    return 'NotANumber(%s=%s)' %(t, bytes)

  for x in ['bytes','KB','MB','GB']:
    if bytes < 1024.0 and bytes > -1024.0:
      return "%3.1f%s" % (bytes, x)
    bytes /= 1024.0
  return "%3.1f%s" % (bytes, 'TB')


def DisplayFriendlyTime(seconds):
  """DisplayFriendlyTime -- turn a number of seconds into a nice string"""

  if seconds < 60:
    return '%d seconds' % seconds

  if seconds < 60 * 60:
    minutes = seconds / 60
    return '%d minutes, %d seconds' %(minutes, seconds - (minutes * 60))

  hours = seconds / (60 * 60)
  minutes = (seconds - (hours * 60 * 60)) / 60
  seconds = seconds - (hours * 60 * 60) - (minutes * 60)
  return '%d hours, %d minutes, %d seconds' %(hours, minutes, seconds)


class FilenameException(Exception):
  """ Errors with filenames """


# The following is a way of simplifying the lookup code for video directoies.
# The tuple format is (tablename, where, column)
_VIDEODIRPATH = [('storagegroup', 'groupname="MythNetTV"', 'dirname'),
                 ('storagegroup', 'groupname="Default"', 'dirname'),
                 ('settings', 'value="RecordFilePrefix"', 'data')]

def GetVideoDir():
  """GetVideoDir -- return the directory to store video in"""
  # Video directory lookup changes for the introduction of storage groups
  # in MythTV 0.21
  # TODO(mikal): I wonder if this works with 0.21 properly? I should test.
  videodir = getBiggestSG()

  # Check we ended up with a video directory
  if videodir == None:
    raise FilenameException('Could not determine the video '
                            'directory for this machine. Please report '
                            'this to mythnettv@stillhq.com')
  
  # Check that it exists as well
  if not os.path.exists(videodir):
    raise FilenameException('MythTV is misconfigured. The video '
                            'directory "%s" does not exist. Please create '
                            'it, and then rerun MythNetTV.'
                            % videodir)

  return videodir

def findFullFile(filename):
  SG = MythTV.MythBE().getSGList(socket.gethostname(), 'Default', '')
  for dir in SG:
    fulldir = dir + '/' + filename
    if os.path.isfile(fulldir):
      return fulldir

def ExplainVideoDir():
  """ExplainVideoDir -- return the directory to store video in"""

  videodir = getBiggestSG()

  if videodir:
    print 'Will use: %s\n\n' % videodir
    print '** All entries below here are informational only **\n\n'

  # Check we ended up with a video directory
  if videodir == None:
    print 'Found no video directory'
    return
  
  # Check that it exists as well
  if not os.path.exists(videodir):
    print 'Video directory does not exist on disk!'

  print 'End of checks'


class LoggingException(Exception):
  """ Log exceptions to the database as well as returning them as exceptions
  """

  def __init__(self, db, error):
    if db:
      try:
        db.Log(error)
      except:
        pass

    Exception.__init__(self, error)
    
    
# everything here was just copied from R.D.Vaughan's Mirobridge script
# License:Creative Commons GNU GPL v2
# (http://creativecommons.org/licenses/GPL/2.0/)

import re
from pyparsing import *
import pyparsing

def massageDescription(description, extras=False):
    '''Massage the Miro description removing all HTML.
    return the massaged description
    '''

    def unescape(text):
       """Removes HTML or XML character references
          and entities from a text string.
       @param text The HTML (or XML) source text.
       @return The plain text, as a Unicode string, if necessary.
       from Fredrik Lundh
       2008-01-03: input only unicode characters string.
       http://effbot.org/zone/re-sub.htm#unescape-html
       """
       def fixup(m):
          text = m.group(0)
          if text[:2] == u"&#":
             # character reference
             try:
                if text[:3] == u"&#x":
                   return unichr(int(text[3:-1], 16))
                else:
                   return unichr(int(text[2:-1]))
             except ValueError:
                logger.warn(u"Remove HTML or XML character references: Value Error")
                pass
          else:
             # named entity
             # reescape the reserved characters.
             try:
                if text[1:-1] == u"amp":
                   text = u"&amp;amp;"
                elif text[1:-1] == u"gt":
                   text = u"&amp;gt;"
                elif text[1:-1] == u"lt":
                   text = u"&amp;lt;"
                else:
                   logger.info(u"%s" % text[1:-1])
                   text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
             except KeyError:
                logger.warn(u"Remove HTML or XML character references: keyerror")
                pass
          return text # leave as is
       return re.sub(u"&#?\w+;", fixup, text)

    details = {}
    if not description: # Is there anything to massage
        if extras:
            details[u'plot'] = description
            return details
        else:
            return description

    director_text = u'Director: '
    director_re = re.compile(director_text, re.UNICODE)
    ratings_text = u'Rating: '
    ratings_re = re.compile(ratings_text, re.UNICODE)

    removeText = replaceWith("")
    scriptOpen,scriptClose = makeHTMLTags(u"script")
    scriptBody = scriptOpen + SkipTo(scriptClose) + scriptClose
    scriptBody.setParseAction(removeText)

    anyTag,anyClose = makeHTMLTags(Word(alphas,alphanums+u":_"))
    anyTag.setParseAction(removeText)
    anyClose.setParseAction(removeText)
    htmlComment.setParseAction(removeText)

    commonHTMLEntity.setParseAction(replaceHTMLEntity)

    # first pass, strip out tags and translate entities
    firstPass = (htmlComment | scriptBody | commonHTMLEntity |
                 anyTag | anyClose ).transformString(description)

    # first pass leaves many blank lines, collapse these down
    repeatedNewlines = LineEnd() + OneOrMore(LineEnd())
    repeatedNewlines.setParseAction(replaceWith(u"\n\n"))
    secondPass = repeatedNewlines.transformString(firstPass)
    text = secondPass.replace(u"Link to Catalog\n ",u'')
    text = unescape(text)

    if extras:
        text_lines = text.split(u'\n')
        for index in range(len(text_lines)):
            text_lines[index] = text_lines[index].rstrip()
            index+=1
    else:
        text_lines = [text.replace(u'\n', u' ')]

    if extras:
        description = u''
        for text in text_lines:
            if len(director_re.findall(text)):
                details[u'director'] = text.replace(director_text, u'')
                continue
            # probe the nature [...]Rating: 3.0/5 (1 vote cast)
            if len(ratings_re.findall(text)):
                data = text[text.index(ratings_text):].replace(ratings_text, u'')
                try:
                    number = data[:data.index(u'/')]
                    # HD trailers ratings are our of 5 not 10 like MythTV so must be multiplied by two
                    try:
                        details[u'userrating'] = float(number) * 2
                    except ValueError:
                        details[u'userrating'] = 0.0
                except:
                    details[u'userrating'] = 0.0
                text = text[:text.index(ratings_text)]
            if text.rstrip():
                description+=text+u' '
    else:
        description = text_lines[0].replace(u"[...]Rating:", u"[...] Rating:")

    if extras:
        details[u'plot'] = description.rstrip()
        return details
    else:
        return description
    # end massageDescription()
    
    
    
import glob
def recursive_file_permissions(path,mode,uid=-1,gid=-1):
  '''
  Recursively updates file permissions on a given path.
  UID and GID default to -1, and mode is required
  '''
  for item in glob.glob(path+'/*'):
    if os.path.isdir(item):
      recursive_file_permissions(os.path.join(path,item),mode,uid,gid)
    else:
      try:
        os.chown(os.path.join(path,item),uid,gid)
        os.chmod(os.path.join(path,item),mode)
      except:
        print('File permissions on {0} not updated due to error.'.format(os.path.join(path,item)))
        
import hashlib
def hashtitlesubtitle(title,subtitle):
  '''
  Makes a hash of a title and a subtitle and returns it as hex
  '''
  m = hashlib.md5()
  m.update(title)
  if subtitle:
    m.update(subtitle.encode('utf8'))
  return m.hexdigest()

import MythTV
def getBiggestSG():
  '''
  Returns the path of the recording Storage Group with most space available
  '''
  #get all free space data from backend for each SG
  free = MythTV.MythBE().getFreeSpace()
  #get list of SG for recordings
  SG = MythTV.MythBE().getSGList(socket.gethostname(), 'Default', '')
  mylist = {}
  #itterate through all FreeSpace items
  for i in free:
    #if path equals recordings SG
    if i.path in SG:
      #store free space data and path
      mylist[i.path]=i.freespace
  #return only a string of the largest SG
  return str(max(mylist.iterkeys(), key=lambda k: mylist[k]))


def removeAfter(string, suffix):
    try: 
      return string[:string.index(suffix) + len(suffix)]
    except:
      return string
