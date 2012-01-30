#!/usr/bin/python

# Copyright (C) Elkin Fricke (elkin@elkin.de) 2011
# Released under the terms of the GNU GPL v2

import re
import sys
import tvrage.api
import utility
#import tvdb_api
import MythTV.ttvdb.tvdb_ui as tvdb_ui
import MythTV.ttvdb.tvdb_api as tvdb_api
from datetime import date
from datetime import datetime

def ExtractSeasonEpisode(seasonepisode, out=sys.stdout):
  """ExtractSeasonEpisode -- extract the season and episode number from a string and return these as integers
     seasonepisode = string containing a potential season and episode number
  """
  
  found = False
  # this list contains the regular expression that would find both the season and episode
  matchme = ["s(\d{2})e(\d{2})", "S(\d{2})E(\d{2})", "(\d{2})x(\d{2})", "(\d{1})x(\d{2})", "(\d{1})x(\d{1})"]
  
  # iterate through each regular expression to find the actual integer value
  for search in matchme:
    match = re.search(search, seasonepisode)
    if match:
      return int(match.group(1)), int(match.group(2))
      found = True
  
  #similar problem with titles containing "xx of yy"
  matchme = ["(\d{2})\s*of\s*(\d{2})", "(\d{1})\s*of\s*(\d{2})", "(\d{1})\s*of\s*(\d{1})", "(\d{2})\s*/\s*(\d{2})", "(\d{1})\s*/\s*(\d{2})", "(\d{1})\s*/\s*(\d{1})"]
  
  for search in matchme:
    # we need to assume that any such show is always the first season
    match = re.search(search, seasonepisode)
    if match:
      return 1, int(match.group(1))
      found = True
  
  # if we could not find anything...
  return 0
  
def ExtractDate(date, out=sys.stdout):
  """ExtractDate -- extract the year, month, day from a string and return these as integers
     date = string containing a date with year, month and (not or) day
  """
  
  # this list contains the regular expressions that contain the day month year
  matchyearfirst = ["(\d{4}).(\d{2}).(\d{2})", "(\d{4}) (\d{2}) (\d{2})", "(\d{4})-(\d{2})-(\d{2})", "(\d{4}) (\d{2})  (\d{2})"]
  matchyearlast = ["(\d{2}).(\d{2}).(\d{4})", "(\d{2}) (\d{2}) (\d{4})", "(\d{2})-(\d{2})-(\d{4})"]
  
  found = False
  # iterate through each regular expression to find the actual integer value
  for search in matchyearfirst:
    match = re.search(search, date)
    if match:
      return match.group(1), match.group(2), match.group(3)
      found = True

  for search in matchyearlast:
    match = re.search(search, date)
    if match:
      return match.group(3), match.group(2), match.group(1)
      found = True
      
  # if we could not find anything...
  return 0
  
def TVRageSeasonEpisode(title, season, episode, out=sys.stdout):
  """ TVRageSeasonEpisode -- Get and format subtitle and description from TVRage based on a season and episode
      title   = Official name of TV-show ... as exact as possible, please
      season  = season number (int)
      episode = episode number (int)
      returns the correct title and full description
  """
  try:
    #get the TVrage show information
    tvshow = tvrage.api.Show(title)
    #then get the TVrage Episode information
    tvrageepisode = tvshow.season(season).episode(episode)
    if title == tvrageepisode.show:
    #return subtitle and description
      return tvrageepisode.title, utility.massageDescription(tvrageepisode.summary)
    else:
      return 0
  except:
    return 0
    
def TVRageDate(title, year, month, day, out=sys.stdout):
  """ TVRageDate -- Get and format subtitle and description from TVRage based on a date
      title   = Official name of TV-show ... as exact as possible, please
      year    = year number (int)
      month   = month number (int)
      day     = number (int)
      returns the correct subtitle and full description then the season and episode number
  """
  found = False
  try:
    #get the TVrage show information
    tvshow = tvrage.api.Show(title)
    #then get the TVrage Episode information
    seasoncount = int(tvshow.seasons)
    while (seasoncount > 0) and not found:
      season = tvshow.season(seasoncount)
      for episodes in season:
        if tvshow.season(seasoncount).episode(episodes).airdate == date(year, month, day):
          subtitle = date(year, month, day).strftime("%Y.%m.%d"), tvshow.season(seasoncount).episode(episodes).title
          #return subtitle and description
          if title == tvshow.season(seasoncount).episode(episodes).show:
            return subtitle, utility.massageDescription(tvshow.season(seasoncount).episode(episodes).summary), tvshow.season(seasoncount).episode(episodes).season, tvshow.season(seasoncount).episode(episodes).number
            found = True
      seasoncount = seasoncount - 1
  except:
    return 0
  if not found:
    return 0
    
def TTVDBSeasonEpisode(title, season, episode, out=sys.stdout):
  """ TTVDBSeasonEpisode -- Get and format subtitle and description from The TV Database based on a season and episode
      title   = Official name of TV-show ... as exact as possible, please
      season  = season number (int)
      episode = episode number (int)
      returns the correct title and full description, season, episode and TTVDBID
  """
  found = False
  try:
    #get the TVrage show information
    tvshow = tvdb_api.Tvdb()
    #then get the TVrage Episode information
    tvrageepisode = tvshow[title][season][episode]
    #return subtitle and description
    try:
      description = utility.massageDescription(tvrageepisode['overview'].encode('latin-1','ignore'))
    except:
      description = utility.massageDescription(tvrageepisode['overview'])
    return tvrageepisode['episodename'], description, season, episode, tvrageepisode['seriesid']
    found = True
  except:
    return 0

def TTVDBDate(title, year, month, day, out=sys.stdout):
  """ TTVDBDate -- Get and format subtitle and description from The TV Database based on a date
      title   = Official name of TV-show ... as exact as possible, please
      year    = year number (int)
      month   = month number (int)
      day     = number (int)
      returns the correct subtitle and full description then the season and episode number and lastly the TTVDBID
  """
  found = False
  try:
    #get the TTVDB show information
    ttvdb = tvdb_api.Tvdb()
    tvshow = ttvdb[title]
    #then get the TVrage Episode information

    for season in tvshow:
      for episode in tvshow[season]:
        try:
          airdate = datetime.strptime(tvshow[season][episode]['firstaired'], '%Y-%m-%d')
        except:
          airdate = datetime(1,1,1)
        if airdate == datetime(year, month, day):
          subtitle = datetime(year, month, day).strftime("%Y.%m.%d"), tvshow[season][episode]['episodename']
          #return subtitle and description
          return subtitle, utility.massageDescription(tvshow[season][episode]['overview']), season, episode, tvshow[season][episode]['seriesid']
          found = True
  except:
    return 0 

def TTVDBSubtitle(title, subtitle, out=sys.stdout):
  """ TTVDBDate -- Get and format subtitle and description from The TV Database based on a show subtitle
      title    = Official name of TV-show ... as exact as possible, please
      subtitle = correct official subtitle of the show
      returns the correct subtitle and full description then the season and episode number and lastly the TTVDBID
  """
  found = False
  try:
    #get the TTVDB show information
    ttvdb = tvdb_api.Tvdb()
    tvshow = ttvdb[title]
    for season in tvshow:
      for episode in tvshow[season]:
        if tvshow[season][episode]['episodename'] == subtitle:
          return subtitle, utility.massageDescription(tvshow[season][episode]['overview']), season, episode, tvshow[season][episode]['seriesid']
          found = True
  except:
    return 0
