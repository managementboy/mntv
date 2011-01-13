from hachoir_core.error import HachoirError
from hachoir_core.cmd_line import unicodeFilename
from hachoir_parser import createParser
from hachoir_core.tools import makePrintable
from hachoir_metadata import extractMetadata
from hachoir_core.i18n import getTerminalCharset
from sys import argv, stderr, exit

if len(argv) != 2:
    print >>stderr, "usage: %s filename" % argv[0]
    exit(1)
filename = argv[1]
filename, realname = unicodeFilename(filename), filename
parser = createParser(filename, realname)
if not parser:
    print >>stderr, "Unable to parse file"
    exit(1)
try:
    metadata = extractMetadata(parser)
except HachoirError, err:
    print "Metadata extraction error: %s" % unicode(err)
    metadata = None
if not metadata:
    print "Unable to extract metadata"
    exit(1)

width = metadata.get('width')
height = metadata.get('height')
if (width == 850) and (height == 480):
    print "is 480p"
elif height == 720:
    print "is 720p"
elif height == 1080:
    print "is 1080p"
else:
    print height, "x", width