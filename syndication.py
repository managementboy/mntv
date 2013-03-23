#!/usr/bin/python

# Copyright (C) Michael Still (mikal@stillhq.com) 2006, 2007, 2008
# Released under the terms of the GNU GPL v2

# Subscription functionality

import datetime
import time
import feedparser
import re
import sys

import database
import gflags
import mythnettvcore
import program
import utility


# Define command line flags
FLAGS = gflags.FLAGS


complained_about_swf = False


re_attributeparser = re.compile(ur'([^=]*)="([^"]*)" *(.*)', re.UNICODE)
def ParseAttributes(inputline):
  """ParseAttributes -- used to unmangle XML entity attributes"""
  line = inputline
  result = {}

  m = re_attributeparser.match(line)
  while m:
    result[m.group(1)] = m.group(2)
    line = m.group(3)
    m = re_attributeparser.match(line)

  return result


def Download(db, url, guid, mime,
             title, subtitle, description, date, date_parsed, out=sys.stdout):
  """Download -- add a program to the list of waiting downloads"""
  prog = program.MythNetTvProgram(db)
  if prog.FromUrl(url, guid):
    out.write('  Creating program for %s: %s from %s\n\n'
              %(database.Normalize(title), database.Normalize(subtitle), guid))
  elif FLAGS.verbose:
    out.write('  Already have %s: %s from %s\n'
              %(database.Normalize(title), database.Normalize(subtitle), guid))

    # TODO(mikal): Consider using accessor methods here
    for info in ['download_started', 'download_finished', 'imported',
                 'inactive', 'attempts']:
      out.write('    %s: %s\n' %(info, prog.persistant.get(info, None)))
    out.write('    Bytes transferred: %s\n'
              % utility.DisplayFriendlySize(prog.persistant.get('transferred', 0)))

  for row in db.GetRows('select guid from mythnettv_programs '
                        'where date is null;'):
    bad_program = program.MythNetTvProgram(db)
    bad_program.Load(row['guid'])
    bad_program.SetDate(datetime.datetime.now())
    bad_program.Store()
    out.write('Program with guid = %s has invalid date, using now\n'
              % row['guid'])

  # Update program details
  prog.SetMime(mime)
  prog.SetShowInfo(title, subtitle, description, date, date_parsed)


def GuessMimeType(url):
  """GuessMimeType -- guess a mime type based on a URL"""
  if url.endswith('m4v'):
    return 'video/x-m4v'
  return 'video/x-unguessable'


def Sync(db, xmlfile, title, out=sys.stdout):
  """Sync -- sync up with an RSS feed"""
  global complained_about_swf

  # Grab the XML
  xmllines = xmlfile.readlines()

  # Modify the XML to work around namespace handling bugs in FeedParser
  lines = []
  re_mediacontent = re.compile('(.*)<media:content([^>]*)/ *>(.*)')

  for line in xmllines:
    m = re_mediacontent.match(line)
    count = 1
    while m:
      line = '%s<media:wannabe%d>%s</media:wannabe%d>%s' %(m.group(1), count,
                                                         m.group(2),
                                                         count, m.group(3))
      m = re_mediacontent.match(line)
      count = count + 1

    lines.append(line)

  # Parse the modified XML
  xml = ''.join(lines)
  parser = feedparser.parse(xml)



  # Find the media:content entries
  for entry in parser.entries:
    # detect feedparser version
    try:                                       # feedparser >= 5.1.1 
      date = entry.published                  # publication date of entry 
      date_parsed = entry.published_parsed     # date parsed 
    except AttributeError:                      # older feedparser
      try:
        date = entry.date                       # feedparser < 5.1.1
        date_parsed = entry.date_parsed
      except: # needed because some feeds do not provide a viable date
        date = datetime.datetime.now()
        date_parsed = date
        time.sleep(1) # make sure every entry has a unique date

    videos = {}
    try:
      description = utility.massageDescription(entry.description)
    except:
      description = ''

    subtitle = entry.title

    if entry.has_key('media_description'):
      description = utility.massageDescription(entry['media_description'])
     
    # Enclosures
    if entry.has_key('enclosures'):
      for enclosure in entry.enclosures:
        try:
          videos[enclosure.type] = enclosure
        except:
          videos[GuessMimeType(enclosure.href)] = enclosure

    # Media:RSS
    for key in entry.keys():
      if key.startswith('media_wannabe'):
        attrs = ParseAttributes(entry[key])
        if attrs.has_key('type'):
          videos[attrs['type']] = attrs
        if attrs.has_key('title'):
          subtitle = attrs['title']

    done = False
    if FLAGS.verbose:
      out.write('  Considering: %s: %s\n' %(title, subtitle))

    # very crude, basic subtitle detection
    if not done and db.GetOneRow('select * from mythnettv_programs '
                                   'where title=%s and subtitle=%s;' %(db.FormatSqlValue('', title), db.FormatSqlValue('', subtitle))):
      done = True
      if FLAGS.verbose:
        out.write('   Dupicate detected %s: %s\n' %(title, subtitle))
    
    if not done and db.GetOneRow('select * from mythnettv_programs '
                                 'where guid="%s";' % utility.hashtitlesubtitle(title, subtitle)):
      done = True
      if FLAGS.verbose:
        out.write('   Dupicate detected in GUID: %s\n' % utility.hashtitlesubtitle(title, subtitle))
      
    # add this if you want actual bittorrent files instead of magnets 'application/x-bittorrent',
    for preferred in ['video/x-msvideo', 'video/mp4', 'video/x-xvid',
                      'video/wmv', 'video/x-ms-wmv', 'video/quicktime',
                      'video/x-m4v', 'video/x-flv', 'video/m4v',
                      'video/msvideo',
                      'video/vnd.objectvideo', 'video/ms-wmv', 'video/mpeg']:

      if not done and videos.has_key(preferred):
        Download(db,
                 videos[preferred]['url'],
                 utility.hashtitlesubtitle(title, subtitle),
                 preferred,
                 title,
                 subtitle,
                 description,
                 date,
                 date_parsed,
                 out=out)
        done = True

        
    if not done and entry.has_key('link'):
      if FLAGS.verbose:
        out.write('Link found: %s' %(entry['link']))
      if entry['link'].startswith('magnet'):
	if FLAGS.verbose:
	  out.write('    Warning: treating the link as if it where a Magnet link\n')
	Download(db,
               entry['link'],
               utility.hashtitlesubtitle(title, subtitle),
               'application/x-bittorrent',
               title,
               subtitle,
               description,
               date,
               date_parsed,
               out=out)
        done = True

    if not done and entry.has_key('magnetURI'):
      if FLAGS.verbose:
        out.write('%s' %(entry['magnetURI']))
      if entry['magnetURI'].startswith('magnet'):
        if FLAGS.verbose:
          out.write('    Warning: treating the magnetURI as if it where a Magnet link\n')
        Download(db,
               entry['magnetURI'],
               utility.hashtitlesubtitle(title, subtitle),
               'application/x-bittorrent',
               title,
               subtitle,
               description,
               date,
               date_parsed,
               out=out)
        done = True

    
     # handle youtube rss feeds
    if not done and entry['link'].startswith('http://www.youtube'):
      if FLAGS.verbose:
        out.write(' Warning: looks like a YouTube video link\n')
      Download(db,
             entry['link'],
             utility.hashtitlesubtitle(title, subtitle),
             'application/x-shockwave-flash',
             title,
             subtitle,
             description,
             date,
             date_parsed,
             out=out)
      done = True
      
    # handle xvideos rss feeds
    if not done and (entry['link'].startswith('http://www.xvideos') or entry['link'].startswith('http://www.youporn') or entry['link'].startswith('http://video.xnxx')):
      if FLAGS.verbose:
        out.write(' Warning: looks like a P0rn video link\n')
      Download(db,
             entry['link'],
             utility.hashtitlesubtitle(title, subtitle),
             'application/x-shockwave-flash',
             title,
             subtitle,
             description,
             date,
             date_parsed,
             out=out)
      done = True  
      
    if not done and videos.has_key('text/html'):
      db.Log('Warning: Treating text/html as an video enclosure type for '
             '%s' % utility.hashtitlesubtitle(title, subtitle))
      out.write('    Warning: Treating text/html as an video enclosure from %s for'
                ' %s pointing to %s\n'
                %(repr(videos.keys()), subtitle, videos['text/html']['url']))

      Download(db,
               videos['text/html']['url'],
               utility.hashtitlesubtitle(title, subtitle),
               'text/html',
               title,
               subtitle,
               description,
               date,
               date_parsed,
               out=out)
      done = True

    if not done and videos.has_key('application/x-shockwave-flash'):
      # we now can download vimeo videos
      if videos['application/x-shockwave-flash']['url'].startswith('http://vimeo'):
        Download(db,
                videos['application/x-shockwave-flash']['url'],
                utility.hashtitlesubtitle(title, subtitle),
                'application/x-shockwave-flash',
                title,
                subtitle,
                description,
                date,
                date_parsed,
                out=out)
        done = True
      if not complained_about_swf:
        out.write('%s\n' % repr(videos))
        out.write('Error: SWF is currently unsupported due to ffmpeg and mencoder not supporting compressed SWF files as input. Let mythnettv@stillhq.com know if you are aware of an open source way of transcoding these files.\n\n')
        complained_about_swf = True
      done = True

    if not done and len(videos.keys()) == 1:
      # If there is only one attachment, make the rather remarkable
      # assumption that it is a video
      out.write('Assuming that %s is a video format\n'
                % videos.keys()[0])
      Download(db,
               videos[videos.keys()[0]]['url'],
               utility.hashtitlesubtitle(title, subtitle),
               videos.keys()[0],
               title,
               subtitle,
               description,
               date,
               date_parsed,
               out=out)
      done = True

    if not done and videos:
      out.write('Error: Unsure which to prefer from: %s for %s\n  [%s]\n\n'
                %(repr(videos.keys()),
                  subtitle.encode('utf-8'),
                  repr(videos)))

    if not done and FLAGS.verbose:
      out.write('  No downloadable content\n')
