#!C:\Python27\python.exe -u
# -*- coding: utf-8 -*-
import cgitb; cgitb.enable()

# *****************************************************************************
# Tento CGI skript vrací hodnoty pro Autocomplete
# *****************************************************************************

import jqueryautocompletePostGIS

import webserverbase

def getQueryValue(queryParams, id, defValue):
    # Vrací hodnotu URL Query parametruy id, pokud neexistuje, vrací hodnotu defValue
    if queryParams.has_key(id):
        return queryParams[id]
    else:
        return defValue

def processRequest(page, servicePathInfo, pathInfos, queryParams, response):
    if queryParams:
        max_matches = int(getQueryValue(queryParams, 'max_matches', 40))
        if page == "fill":
            response.htmlData = jqueryautocompletePostGIS.getFillResults(queryParams, max_matches)
        else:
            token = getQueryValue(queryParams, 'term', "")
            ruian_type = getQueryValue(queryParams, 'RUIANType', "zip")
            resultFormat = getQueryValue(queryParams, 'ResultFormat', "")
            resultArray = jqueryautocompletePostGIS.getAutocompleteResults(queryParams, ruian_type, token, resultFormat, max_matches)
            response.htmlData = "[\n" + ",\n\t".join(resultArray) + "\n]"
    else:
        response.htmlData = "[  ]"

    response.mimeFormat = "text/javascript"
    response.handled = True
    return response

if __name__ == '__main__':
    # Nastavení kódování češtiny na UTF-8
    import sys
    reload(sys)
    sys.setdefaultencoding('utf-8')

    # Spuštění serveru
    webserverbase.mainProcess(processRequest)
