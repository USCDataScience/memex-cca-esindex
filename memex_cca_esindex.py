#!/usr/bin/env python2.7
# encoding: utf-8
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 
# $Id$
#
# Author: mattmann
# Description: This program reads a Common Crawl Architecture dump 
# directory as generated by Apache Nutch, e.g,. see:
# https://wiki.apache.org/nutch/CommonCrawlDataDumper
# and then uses that CBOR-encoded JSON data as a basis for posting
# the data to Elasticsearch using this simple schema:
#
#
# {
#   url : <url of raw page>,
#   timestamp: <timestamp for data when scraped, in epoch milliseconds>,
#   team: <name of crawling team>,
#   crawler: <name of crawler; each type of crawler should have a distinct name or reference>,
#   raw_content: <full text of raw crawled page>,
#   content_type: <IANA mimetype representing the crawl_data content>,
#   crawl_data {
#     content: <optional; used to store cleaned/processed text, etc>,
#     images:[an array of URIs to the images present within the document],
#     videos:[an array of URIs to the videos present within the document]
# }
# To call this program, do something like the following
# 
#  ./memex_cca_esindex.py -t "JPL" -c "Nutch 1.11-SNAPSHOT" -d crawl_20150410_cca/ -u https://user:pass@localhost:9200/ -i memex-domains -o stuff
# 
# If you want verbose logging, turn it on with -v

from tika import parser
from elasticsearch import Elasticsearch
import json
import os
import cbor
import sys
import getopt

_verbose = False
_helpMessage = '''

Usage: memex_cca_esindex [-t <crawl team>] [-c <crawler id>] [-d <cca dir> [-u <url>] [-i <index>] [-o docType]

Operation:
-t --team
    The name of the crawler team, e.g. "JPL"
-c --crawlerId
    The identifier of the crawler, e.g., "Nutch 1.11-SNAPSHOT"
-d --dataDir
    The directory where CCA CBOR JSON files are located.
-u --url
    The URL to Elasticsearch. If you need auth, you can use RFC-1738 to specify the url, e.g., https://user:secret@localhost:443
-i --index
    The Elasticsearch index, e.g., memex-domains, to index to.
-o --docType
    The document type e.g., weapons, to index to.
'''

def list_files(dir):                                                                                                  
    r = []                                                                                                            
    subdirs = [x[0] for x in os.walk(dir)]                                                                            
    for subdir in subdirs:                                                                                            
        files = os.walk(subdir).next()[2]                                                                             
        if (len(files) > 0):                                                                                          
            for file in files:                                                                                        
                r.append(subdir + "/" + file)                                                                         
    return r    


def getContentType(ccaDoc):
    for header in ccaDoc["response"]["headers"]:
        if header[0] == "Content-Type":
            return header[1]
    return "application/octet-stream"

def indexDoc(url, doc, index, docType):
    print "Inexing "+doc["url"]+" to ES at: ["+url+"]"
    es = Elasticsearch([url])
    res = es.index(index=index, doc_type=docType,  body=doc)
    print(res['created'])

def esIndex(ccaDir, team, crawler, url, index, docType):
    ccaJsonList = list_files(ccaDir)
    print "Processing ["+str(len(ccaJsonList))+"] files."

    procList=[]
    failedList=[]
    failedReasons=[]

    for f in ccaJsonList:
        ccaDoc = None
        newDoc = {}
        with open(f, 'r') as fd:
            try:
                ccaDoc = json.loads(cbor.load(fd), encoding='utf8')
                newDoc["url"] = ccaDoc["url"]
                newDoc["timestamp"] = ccaDoc["imported"]
                newDoc["team"] = team
                newDoc["crawler"] = crawler
                newDoc["raw_content"] = ccaDoc["response"]["body"]
                newDoc["content_type"] = getContentType(ccaDoc)
                parsed = parser.from_buffer(newDoc["raw_content"])
                newDoc["crawl_data"] = {}
                newDoc["crawl_data"]["content"] = parsed["content"]
                verboseLog(json.dumps(newDoc))
                indexDoc(url, newDoc, index, docType)
                procList.append(f)
            except ValueError, err:
                failedList.append(f)
                failedReasons.append(str(err))

    print "Processed "+str(len(procList))+" CBOR files successfully."
    print "Failed files: "+str(len(failedList))

    if _verbose:
        for i in range(len(failedList)):
            verboseLog("File: "+failedList[i]+" failed because "+failedReasons[i])

def verboseLog(message):
    if _verbose:
        print >>sys.stderr, message

class _Usage(Exception):
    '''An error for problems with arguments on the command line.'''
    def __init__(self, msg):
        self.msg = msg

def main(argv=None):
   if argv is None:
     argv = sys.argv

   try:
       try:
          opts, args = getopt.getopt(argv[1:],'hvt:c:d:u:i:o:',['help', 'verbose', 'team=', 'crawlerId=', 'dataDir=', 'url=', 'index=', 'docType='])
       except getopt.error, msg:
         raise _Usage(msg)    
     
       if len(opts) == 0:
           raise _Usage(_helpMessage)
       team=None
       crawlerId=None
       dataDir=None
       url=None
       index=None
       docType=None
       
       for option, value in opts:           
          if option in ('-h', '--help'):
             raise _Usage(_helpMessage)
          elif option in ('-v', '--verbose'):
             global _verbose
             _verbose = True
          elif option in ('-t', '--team'):
              team = value
          elif option in ('-c', '--crawlerId'):
             crawlerId = value
          elif option in ('-d', '--dataDir'):
             dataDir = value
          elif option in ('-u', '--url'):
              url = value
          elif option in ('-i', '--index'):
              index = value
          elif option in ('-o', '--docType'):
              docType = value

       if team == None or crawlerId == None or dataDir == None or url == None or index == None or docType == None:
           raise _Usage(_helpMessage)

       esIndex(dataDir, team, crawlerId, url, index, docType)

   except _Usage, err:
       print >>sys.stderr, sys.argv[0].split('/')[-1] + ': ' + str(err.msg)
       return 2

if __name__ == "__main__":
   sys.exit(main())
