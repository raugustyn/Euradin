# -*- coding: utf-8 -*-
#-------------------------------------------------------------------------------
# Name:        importRUIAN
# Purpose:     Imports VFR data downloaded directory
#
# Author:      Radek Augustýn
# Copyright:   (c) VUGTK, v.v.i. 2014
# License:     CC BY-SA 4.0
#-------------------------------------------------------------------------------
helpStr = """
Import VFR data to database.

Requires: Python 2.7.5 or later
          OS4Geo with WFS Support (http://geo1.fsv.cvut.cz/landa/vfr/OSGeo4W_vfr.zip)

Usage: importruian.py [-dbname <database name>] [-host <host name>] [-port <database port>] [-user <user name>]
                      [-password <database password>] [-layers layer1,layer2,...] [-os4GeoPath <path>]
                      [-buildServicesTables <{True} {False}>] [-buildAutocompleteTables <{True} {False}>] [-help]')

       -dbname
       -host
       -port
       -user
       -password
       -layers
       -os4GeoPath
       -buildServicesTables
       -buildAutocompleteTables
       -Help         Print help
"""

DEMO_MODE = False # If set to true, there will be just few rows in every state database import lines applied.

import os
import sys
from os.path import join
from subprocess import call

import shared; shared.setupPaths()

from sharedtools import pathWithLastSlash, RUIANImporterConfig, getDataDirFullPath, extractFileName, RUNS_ON_WINDOWS, RUNS_ON_LINUX, COMMAND_FILE_EXTENSION
import sharedtools.log as log
import buildhtmllog

RUIAN2PG_LIBRARY_ZIP_URL = [
    "http://www.vugtk.cz/euradin/VFRLibrary/OSGeo4W_vfr_1.9.73.zip",
    "https://github.com/ctu-geoforall-lab/gdal-vfr/archive/master.zip"
][RUNS_ON_LINUX]
LIST_FILE_TAIL = "_list.txt"



config = None


def renameFile(fileName, prefix):
    assert isinstance(fileName, basestring)
    assert isinstance(prefix, basestring)

    parts = fileName.split(os.sep)
    resultParts = parts[:len(parts) - 1]
    resultParts.append(prefix + parts[len(parts) - 1])

    newFileName = os.sep.join(resultParts)
    if os.path.exists(newFileName): os.remove(newFileName)

    os.rename(fileName, newFileName)
    return newFileName


def createCommandFile(fileNameBase, commands):
    """Creates either fileNameBase.bat file or fileNameBase.sh file, depending on the operating system.
    If runs on Linux, then chmod 777 fileName is applied.

    :param fileNameBase: Base of the command script file name.
    :param commands: Context of the command file.
    :return:
    """
    assert isinstance(fileNameBase, basestring)
    assert isinstance(commands, basestring)

    fileName = fileNameBase + COMMAND_FILE_EXTENSION
    file = open(fileName, "w")

    if RUNS_ON_LINUX:
        file.write("#!/usr/bin/env bash\n")

    file.write(commands)
    if RUNS_ON_LINUX:
        os.chmod(fileName, 0o777)

    file.close()

    return fileName


def deleteFilesInLists(path, fileLists, extension):
    assert isinstance(path, basestring)
    assert os.path.exists(path)
    assert isinstance(fileLists, list)
    assert isinstance(extension, basestring)

    path = pathWithLastSlash(path)
    for fileList in fileLists:
        listFile = open(fileList, "r")
        i = 0
        for line in listFile:
            i += 1
            fileName = path + line.rstrip() + extension
            if os.path.exists(fileName):
                os.remove(fileName)
            log.logger.debug(str(i), ":", fileName)
        listFile.close()
        os.remove(fileList)


def joinPaths(basePath, relativePath):
    assert isinstance(basePath, basestring)
    assert isinstance(relativePath, basestring)

    basePath = basePath.replace("/", os.sep)
    relativePath = relativePath.replace("/", os.sep)
    if (os.path.exists(relativePath)):
        return relativePath
    else:
        basePathItems = basePath.split(os.sep)
        relativePathItems = relativePath.split(os.sep)
        endBaseIndex = len(basePathItems)
        startRelative = 0
        for subPath in relativePathItems:
            if subPath == "..":
                endBaseIndex = endBaseIndex - 1
                startRelative = startRelative + 1
            elif subPath == ".":
                startRelative = startRelative + 1
            else:
                break

        fullPath = os.sep.join(basePathItems[:endBaseIndex]) + os.sep + os.sep.join(relativePathItems[startRelative:])
        return fullPath


def getOSGeoPath():
    if RUNS_ON_WINDOWS:
        path = config.WINDOWS_os4GeoPath
    else:
        path = config.LINUX_vfr2pgPath

    path = joinPaths(os.path.dirname(__file__), path)
    path = os.path.normpath(path)
    path = os.path.abspath(path)
    return path


def vfr2pgPath():
    if RUNS_ON_WINDOWS:
        return 'call "%s" vfr2pg' % getOSGeoPath()
    else:
        return "%svfr2pg  2>>%s 3>>%s" % getOSGeoPath()


def redirectLogsToFile(command, logFileName, errorsLogFileName):
    if config.CREATE_LOG_FILES:
        if RUNS_ON_WINDOWS:
            return "%s >%s 2>%s" % (command, logFileName, errorsLogFileName)
        else:
            return "%s 2>%s 3>%s" % (command, logFileName, errorsLogFileName)
    else:
        return command


def convertFileToDownloadLists(HTTPListName):
    assert isinstance(HTTPListName, basestring)

    result = []

    inFile = open(HTTPListName, "r")
    try:
        fileName = (HTTPListName[:HTTPListName.find(".txt")]) + LIST_FILE_TAIL
        outFile = open(fileName, "w")
        result.append(fileName)
        linesInFile = 0
        for line in inFile:
            linesInFile = linesInFile + 1
            if config.DEBUG_MAX_FILECOUNT and linesInFile > config.DEBUG_MAX_FILECOUNT:
                log.logger.warning("Stopping import at file #config.DEBUG_MAX_FILECOUNT.")
                break

            line = line[line.rfind("/") + 1:line.find("\n")]
            outFile.write(line + "\n")

        outFile.close()
    finally:
        inFile.close()
    return result


def getFullPath(configFileName, path):
    assert isinstance(configFileName, basestring)
    assert isinstance(path, basestring)

    if not os.path.exists(path):
        path = pathWithLastSlash(configFileName) + path
    return path


def paramsToCommandLine(params):
    result = ""
    for paramName, paramValue in  params.iteritems():
        if paramValue:
            result += " --" + paramName + " " + paramValue
    return result


def extractDatesAndType(patchListFileName):
    assert isinstance(patchListFileName, basestring)

    def getDate(line):
        result = line[line.rfind("/") + 1:]
        result = result[:result.find("_")]
        return result

    def getType(line):
        type = line[line.rfind("/") + 1:]
        type = type[type.find("_") + 1:type.find(".")]
        return type

    startDate = ""
    endDate = ""
    type = ""

    inFile = open(patchListFileName, "r")
    firstLine = True
    for line in inFile:
        if firstLine:
            endDate = getDate(line)
            type = getType(line)
            firstLine = False
        else:
            startDate = getDate(line)
    inFile.close()

    return (startDate, endDate, type)


def buildDownloadBatch(fileListFileName, fileNames):
    assert isinstance(fileListFileName, basestring)
    assert os.path.exists(fileListFileName)
    assert isinstance(fileNames, list)

    path = os.path.dirname(fileListFileName)

    (VFRlogFileName, VFRerrFileName) = buildhtmllog.getLogFileNames(fileListFileName)
    commands = "cd %s\n" % path
    overwriteCommand = "--o"
    for fileName in fileNames:
        params = {
                "file": extractFileName(fileName),
                "host": config.host,
                "dbname": config.dbname,
                "user": config.user,
                "passwd": config.password,
                "layer": config.layers
            }
        if RUNS_ON_LINUX:
            params["schema"] = config.schemaName

        importCmd = vfr2pgPath() + " " + paramsToCommandLine(params)

        importCmd += " " + overwriteCommand
        importCmd = redirectLogsToFile(importCmd, VFRlogFileName, VFRerrFileName)

        log.logger.debug(importCmd)
        commands += importCmd + "\n"
        overwriteCommand = "--append"

        commandFileName = createCommandFile(path + os.sep + "Import", commands)

    return (commandFileName, VFRlogFileName, VFRerrFileName)


def createStateDatabase(path, fileListFileName):
    assert isinstance(path, basestring)
    assert isinstance(fileListFileName, basestring)

    log.logger.info("Načítám stavovou databázi ze seznamu " + fileListFileName)
    GDALFileListNames = convertFileToDownloadLists(fileListFileName)
    downloadBatchFileName, VFRlogFileName, VFRerrFileName = buildDownloadBatch(fileListFileName, GDALFileListNames)

    log.logger.info("Spouštím %s, průběh viz. %s a %s." % (downloadBatchFileName, VFRlogFileName, VFRerrFileName))
    call(downloadBatchFileName)
    deleteFilesInLists(path, GDALFileListNames, ".xml.gz")
    #os.remove(downloadBatchFileName) # @TODO
    renameFile(fileListFileName, "__")


def updateDatabase(updateFileName):
    assert isinstance(updateFileName, basestring)

    def removeDataFiles():
        dataPath = pathWithLastSlash(os.path.split(updateFileName)[0])
        inFile = open(updateFileName, "r")
        try:
            for line in inFile:
                fileName = os.path.basename(line)
                if os.path.exists(dataPath + fileName):
                    os.remove(dataPath + fileName)
        finally:
            inFile.close()
        pass

    log.logger.info("Importing update data from " + updateFileName)

    (startDate, endDate, type) = extractDatesAndType(updateFileName)
    log.logger.info("\tPočáteční datum:" + startDate)
    log.logger.info("\tKonečné datum:" + endDate)
    log.logger.info("\tTyp dat:" + type)


    (VFRlogFileName, VFRerrFileName) = buildhtmllog.getLogFileNames(updateFileName)
    importCmd = vfr2pgPath() + " " + paramsToCommandLine({
                                        "host": config.host,
                                        "dbname": config.dbname,
                                        "user": config.user,
                                        "passwd": config.password,
                                        "schema": config.schemaName,
                                        "date": startDate + ":" + endDate,
                                        "type": type,
                                        "layer": config.layers
                                    })
    importCmd = redirectLogsToFile(importCmd, VFRlogFileName, VFRerrFileName)

    commands = "cd " + os.path.dirname(os.path.abspath(updateFileName)) + "\n"
    commands += importCmd + "\n"
    batchFileName = createCommandFile(os.path.dirname(os.path.abspath(updateFileName)) + os.sep + "Import", commands)

    call(batchFileName)
    #os.remove(batchFileName) # @TODO
    #removeDataFiles()

    renameFile(updateFileName, "__")
    log.logger.info("Import update data done.")


def processDownloadedDirectory(path):
    assert isinstance(path, basestring)

    log.logger.info("Načítám stažené soubory do databáze...")
    log.logger.info("--------------------------------------")
    log.logger.info("Zdrojová data : " + path)

    path = pathWithLastSlash(path)
    stateFileList = ""
    updatesFileList = []
    for file in os.listdir(path):
        if file.endswith(".txt"):
            if file.startswith("Download_") and not file.endswith(LIST_FILE_TAIL):
                stateFileList = join(path, file)
            elif file.startswith("Patch_"):
                updatesFileList.append(join(path, file))

    result = False
    if stateFileList != "":
        createStateDatabase(path, stateFileList)
        result = True
    else:
        log.logger.info("Stavová data nejsou obsahem zdrojových dat.")

    if len(updatesFileList) == 0:
        log.logger.info("Denní aktualizace nejsou obsahem zdrojových dat.")
    else:
        result = True
        for updateFileName in updatesFileList:
            updateDatabase(updateFileName)

    log.logger.info(u"Generuji sestavu importů.")
    buildhtmllog.buildHTMLLog()

    log.logger.info("Načítání stažených souborů do databáze - hotovo.")
    return result



def doImport(argv):
    global config
    
    from sharedtools import setupUTF
    setupUTF()

    config = RUIANImporterConfig()
    config.loadFromCommandLine(argv, helpStr)
    log.createLogger(getDataDirFullPath() + "Download.log")
    log.logger.info("Importing VFR data to database.")

    osGeoPath = getOSGeoPath()
    if not os.path.exists(osGeoPath):
        print "Error: VFR import library %s not found" % osGeoPath
        print "Download file %s, expand it into RUIANToolbox base directory and run script again." % RUIAN2PG_LIBRARY_ZIP_URL

        sys.exit()

    rebuildAuxiliaryTables = processDownloadedDirectory(getDataDirFullPath())

    if config.buildServicesTables and rebuildAuxiliaryTables:
        from RUIANServices.services.auxiliarytables import buildAll, buildServicesTables
        if config.buildAutocompleteTables:
            buildAll()
        else:
            buildServicesTables()

    from RUIANServices.services.RUIANConnection import saveRUIANVersionDateToday
    saveRUIANVersionDateToday()


if __name__ == "__main__":
    doImport(sys.argv)