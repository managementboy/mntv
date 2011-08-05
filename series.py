#!/usr/bin/python

# Copyright (C) Elkin Fricke (elkin@elkin.de) 2011
# Released under the terms of the GNU GPL v2

import re
import sys
import tvrage.api
import utility
from datetime import date

def ExtractSeasonEpisode(seasonepisode, out=sys.stdout):
  """ExtractSeasonEpisode -- extract the season and episode number from a string and return these as integers"""
  
  # this list contains the regular expression that would find both the season and episode
  matchme = ["s(\d{2})e(\d{2})", "S(\d{2})E(\d{2})", "(\d{2})x(\d{2})", "(\d{1})x(\d{2})", "(\d{1})x(\d{1})"]
  
  # iterate through each regular expression to find the actual integer value
  for search in matchme:
    try:
      season = int(re.search(search, seasonepisode).group(1))
      episode = int(re.search(search, seasonepisode).group(2))
      return season, episode
    except:
      pass
  # if we could not find anything...
  return 0
  
def ExtractDate(date, out=sys.stdout):
  """ExtractDate -- extract the year, month, day from a string and return these as integers"""
  
  # this list contains the regular expression that would find both the season and episode
  matchyearfirst = ["(\d{4}).(\d{2}).(\d{2})", "(\d{4}) (\d{2}) (\d{2})", "(\d{4})-(\d{2})-(\d{2})"]
  matchyearlast = ["(\d{2}).(\d{2}).(\d{4})", "(\d{2}) (\d{2}) (\d{4})", "(\d{2})-(\d{2})-(\d{4})"]
  
  # iterate through each regular expression to find the actual integer value
  for search in matchyearfirst:
    try:
      year = int(re.search(search, date).group(1))
      month = int(re.search(search, date).group(2))
      day = int(re.search(search, date).group(3))
      return year, month, day
    except:
      pass
  for search in matchyearlast:
    try:
      year = int(re.search(search, date).group(3))
      month = int(re.search(search, date).group(2))
      day = int(re.search(search, date).group(1))
      return year, month, day
    except:
      pass
  # if we could not find anything...
  return 0
  
def TVRageSeasonEpisode(title, season, episode, out=sys.stdout):
  """ TVRageSeasonEpisode -- Get and format subtitle and description from TVRage based on a season and episode"""
  try:
    #get the TVrage show information
    tvrageshow = tvrage.api.Show(title)
    #then get the TVrage Episode information
    tvrageepisode = tvrageshow.season(season).episode(episode)
    #return subtitle and description
    return tvrageepisode.title, utility.massageDescription(tvrageepisode.summary)
  except:
    return 0
    
def TVRageDate(title, year, month, day, out=sys.stdout):
  """ TVRageDate -- Get and format subtitle and description from TVRage based on a date"""
  try:
    #get the TVrage show information
    tvrageshow = tvrage.api.Show(title)
    #then get the TVrage Episode information
    seasoncount = int(tvrageshow.seasons)
    while (seasoncount > 0):
      season = tvrageshow.season(seasoncount)
      for episodes in season:
        if tvrageshow.season(seasoncount).episode(episodes).airdate == date(year, month, day):
          subtitle = date(year, month, day).strftime("%Y.%m.%d") + ' ' + tvrageshow.season(seasoncount).episode(episodes).title
          #return subtitle and description
          return subtitle, utility.massageDescription(tvrageshow.season(seasoncount).episode(episodes).summary), tvrageshow.season(seasoncount).episode(episodes).season, tvrageshow.season(seasoncount).episode(episodes).number
      seasoncount = seasoncount - 1
  except:
    return 0
